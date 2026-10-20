"""Resource inventory, monitoring, incident and connector APIs."""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .connectors import ConnectorError, GitHubConnector, RailwayConnector
from .monitor import check_service
from .store import Store

SERVICE_KINDS = Literal['web', 'api', 'database', 'worker', 'queue', 'cache', 'external']
ENV_KINDS = Literal['development', 'staging', 'production', 'custom']


def _clean_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) > 2048:
        raise ValueError('URL is too long')
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('URL must be an absolute http or https URL')
    return value


class ClusterIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    kind: Literal['logical', 'provider', 'local'] = 'logical'
    description: str = Field(default='', max_length=500)
    provider: str | None = Field(default=None, max_length=40)


class ClusterPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal['logical', 'provider', 'local'] | None = None
    description: str | None = Field(default=None, max_length=500)
    provider: str | None = Field(default=None, max_length=40)


class EnvironmentIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=60)
    kind: ENV_KINDS = 'custom'


class ServiceIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    kind: SERVICE_KINDS = 'web'
    provider: Literal['http', 'railway', 'github', 'docker', 'manual'] = 'http'
    health_url: str | None = None
    environment: str | None = Field(default=None, max_length=60)
    monitoring_enabled: bool = True
    check_interval_seconds: int = Field(default=60, ge=15, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    expected_status: int = Field(default=200, ge=100, le=599)
    failure_threshold: int = Field(default=2, ge=1, le=20)
    recovery_threshold: int = Field(default=1, ge=1, le=20)

    _url = field_validator('health_url')(classmethod(lambda cls, v: _clean_url(v)))


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=1000)
    cluster_id: uuid.UUID | None = None
    repo_url: str | None = Field(default=None, max_length=300)
    repo_branch: str | None = Field(default=None, max_length=120)
    environments: list[EnvironmentIn] = Field(default_factory=list, max_length=8)
    services: list[ServiceIn] = Field(default_factory=list, max_length=40)

    @field_validator('repo_url')
    @classmethod
    def _repo(cls, value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if not (value.startswith(('https://github.com/', 'git@github.com:', 'http://github.com/'))):
            raise ValueError('Repository must be a github.com URL')
        return value


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    cluster_id: uuid.UUID | None = None
    repo_url: str | None = Field(default=None, max_length=300)
    repo_branch: str | None = Field(default=None, max_length=120)


class ServicePatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: SERVICE_KINDS | None = None
    provider: Literal['http', 'railway', 'github', 'docker', 'manual'] | None = None
    health_url: str | None = None
    environment_id: uuid.UUID | None = None
    monitoring_enabled: bool | None = None
    check_interval_seconds: int | None = Field(default=None, ge=15, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    failure_threshold: int | None = Field(default=None, ge=1, le=20)
    recovery_threshold: int | None = Field(default=None, ge=1, le=20)

    _url = field_validator('health_url')(classmethod(lambda cls, v: _clean_url(v)))


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    project_id: uuid.UUID
    environment_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    kind: SERVICE_KINDS = 'web'
    provider: Literal['http', 'railway', 'github', 'docker', 'manual'] = 'http'
    health_url: str | None = None
    monitoring_enabled: bool = True
    check_interval_seconds: int = Field(default=60, ge=15, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    expected_status: int = Field(default=200, ge=100, le=599)
    failure_threshold: int = Field(default=2, ge=1, le=20)
    recovery_threshold: int = Field(default=1, ge=1, le=20)

    _url = field_validator('health_url')(classmethod(lambda cls, v: _clean_url(v)))


class DeploymentIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    project_id: uuid.UUID
    environment_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    provider: str = Field(default='manual', max_length=40)
    external_id: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=200)
    commit_sha: str = Field(default='', max_length=80)
    status: str = Field(default='unknown', max_length=40)
    url: str | None = None
    deployed_at: datetime | None = None

    _url = field_validator('url')(classmethod(lambda cls, v: _clean_url(v)))


class NoteIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    note: str = Field(default='', max_length=2000)


class AlertIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=10, max_length=2048)
    project_id: uuid.UUID | None = None
    min_severity: Literal['critical', 'major', 'minor'] = 'major'
    cooldown_seconds: int = Field(default=900, ge=0, le=86400)
    enabled: bool = True

    @field_validator('target')
    @classmethod
    def _target(cls, value: str) -> str:
        return _clean_url(value) or value


class ConnectorIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    provider: Literal['railway', 'github', 'docker']
    name: str = Field(min_length=1, max_length=80)
    token: str = Field(min_length=8, max_length=500)
    config: dict = Field(default_factory=dict)


class ConnectorPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    token: str | None = Field(default=None, min_length=8, max_length=500)


SAFE_TASK_TYPES = {'SIMPLE'}
SAFE_DEFINITION_KEYS = {
    'name', 'version', 'schemaVersion', 'description', 'ownerEmail', 'timeoutPolicy',
    'timeoutSeconds', 'restartable', 'inputParameters', 'outputParameters', 'tasks',
}
NAME = __import__('re').compile(r'^[a-z][a-z0-9_]{2,60}$')
REFERENCE = __import__('re').compile(r'^[A-Za-z][A-Za-z0-9_]{0,40}$')


class DefinitionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    definition: dict


class AgentObservationIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    agent_key: str = Field(min_length=1, max_length=80)
    status: Literal['healthy', 'degraded', 'down']
    message: str = Field(default='', max_length=500)
    latency_ms: int | None = Field(default=None, ge=0, le=600000)


def json_public_connector(row: dict) -> dict:
    """Never expose sealed credentials or raw tokens."""
    return {
        'id': row['id'], 'provider': row['provider'], 'name': row['name'],
        'config': row.get('config') or {}, 'status': row['status'],
        'last_validated_at': row['last_validated_at'], 'last_sync_at': row['last_sync_at'],
        'last_error': row['last_error'], 'created_at': row['created_at'],
    }


def build_router(settings, store: Store, auth, engine) -> APIRouter:
    router = APIRouter(prefix='/api')
    owner = Depends(auth.require)

    def not_found(what: str):
        return HTTPException(404, f'{what} not found')

    # -- dashboard ---------------------------------------------------------
    @router.get('/dashboard', dependencies=[owner])
    async def dashboard():
        data = store.dashboard()
        try:
            result = await engine.request('GET', 'workflow/search', params={
                'start': 0, 'size': 5, 'sort': 'startTime:DESC', 'freeText': '*',
                'query': 'workflowType IN (incident_analysis,diagnostic_pipeline) AND status=FAILED',
            })
            data['workflows'] = {
                'status': 'available',
                'failed': (result or {}).get('results', []),
                'totalHits': (result or {}).get('totalHits', 0),
            }
        except Exception:
            # Conductor being unreachable must degrade the page, not fail it.
            data['workflows'] = {'status': 'unavailable', 'failed': [], 'total_hits': None}
        return data

    # -- clusters ----------------------------------------------------------
    @router.get('/clusters', dependencies=[owner])
    async def clusters():
        return store.list_clusters()

    @router.post('/clusters', status_code=201, dependencies=[owner])
    async def create_cluster(body: ClusterIn):
        try:
            return store.create_cluster(body.name, body.kind, body.description, body.provider)
        except Exception:
            raise HTTPException(409, 'A cluster with that name already exists')

    @router.patch('/clusters/{cluster_id}', dependencies=[owner])
    async def patch_cluster(cluster_id: uuid.UUID, body: ClusterPatch):
        updated = store.update_cluster(cluster_id, body.model_dump(exclude_unset=True))
        if not updated:
            raise not_found('Cluster')
        return updated

    @router.delete('/clusters/{cluster_id}', status_code=204, dependencies=[owner])
    async def delete_cluster(cluster_id: uuid.UUID):
        if not store.delete_cluster(cluster_id):
            raise not_found('Cluster')

    # -- projects ----------------------------------------------------------
    @router.get('/projects', dependencies=[owner])
    async def projects(cluster_id: str | None = None, environment: str | None = None,
                       status: str | None = None, q: str | None = None):
        return store.list_projects(cluster_id=cluster_id, environment=environment,
                                   status=status, search=q)

    @router.post('/projects', status_code=201, dependencies=[owner])
    async def create_project(body: ProjectIn):
        payload = body.model_dump()
        if not payload['environments']:
            payload['environments'] = [{'name': 'production', 'kind': 'production'}]
        try:
            return store.create_project(payload)
        except Exception as exc:
            if 'projects_slug_key' in str(exc) or 'duplicate key' in str(exc):
                raise HTTPException(409, 'A project with that name already exists')
            raise

    @router.get('/projects/{project_id}', dependencies=[owner])
    async def project(project_id: uuid.UUID):
        found = store.get_project(project_id)
        if not found:
            raise not_found('Project')
        return found

    @router.patch('/projects/{project_id}', dependencies=[owner])
    async def patch_project(project_id: uuid.UUID, body: ProjectPatch):
        if not store.get_project(project_id):
            raise not_found('Project')
        return store.update_project(project_id, body.model_dump(exclude_unset=True))

    @router.delete('/projects/{project_id}', status_code=204, dependencies=[owner])
    async def delete_project(project_id: uuid.UUID):
        if not store.delete_project(project_id):
            raise not_found('Project')

    @router.post('/projects/{project_id}/environments', status_code=201, dependencies=[owner])
    async def create_environment(project_id: uuid.UUID, body: EnvironmentIn):
        if not store.get_project(project_id):
            raise not_found('Project')
        return store.create_environment(project_id, body.name, body.kind)

    @router.delete('/environments/{environment_id}', status_code=204, dependencies=[owner])
    async def delete_environment(environment_id: uuid.UUID):
        if not store.delete_environment(environment_id):
            raise not_found('Environment')

    # -- services ----------------------------------------------------------
    @router.get('/services', dependencies=[owner])
    async def services(project_id: str | None = None, environment_id: str | None = None,
                       status: str | None = None, q: str | None = None):
        return store.list_services(project_id=project_id, environment_id=environment_id,
                                   status=status, search=q)

    @router.post('/services', status_code=201, dependencies=[owner])
    async def create_service(body: ServiceCreate):
        payload = body.model_dump()
        if not store.get_project(payload['project_id']):
            raise not_found('Project')
        return store.create_service(payload)

    @router.get('/services/{service_id}', dependencies=[owner])
    async def service(service_id: uuid.UUID):
        found = store.get_service(service_id)
        if not found:
            raise not_found('Service')
        return found

    @router.patch('/services/{service_id}', dependencies=[owner])
    async def patch_service(service_id: uuid.UUID, body: ServicePatch):
        if not store.get_service(service_id):
            raise not_found('Service')
        return store.update_service(service_id, body.model_dump(exclude_unset=True))

    @router.delete('/services/{service_id}', status_code=204, dependencies=[owner])
    async def delete_service(service_id: uuid.UUID):
        if not store.delete_service(service_id):
            raise not_found('Service')

    @router.get('/services/{service_id}/observations', dependencies=[owner])
    async def observations(service_id: uuid.UUID, limit: int = Query(100, ge=1, le=500)):
        if not store.get_service(service_id):
            raise not_found('Service')
        return store.observations(service_id, limit=limit)

    @router.post('/services/{service_id}/check', dependencies=[owner])
    async def check_now(service_id: uuid.UUID):
        found = store.get_service(service_id)
        if not found:
            raise not_found('Service')
        if not found['health_url']:
            raise HTTPException(409, 'This service has no health URL to check')
        result = await check_service(store, settings, found)
        store.audit('owner', 'service.check', 'service', service_id)
        return {'observation': result['observation'], 'service': result['service'],
                'previous_status': result['previousStatus']}

    # -- deployments -------------------------------------------------------
    @router.get('/deployments', dependencies=[owner])
    async def deployments(project_id: str | None = None, limit: int = Query(50, ge=1, le=200)):
        return store.list_deployments(project_id=project_id, limit=limit)

    @router.post('/deployments', status_code=201, dependencies=[owner])
    async def create_deployment(body: DeploymentIn):
        if not store.get_project(body.project_id):
            raise not_found('Project')
        created = store.create_deployment(body.model_dump())
        if not created:
            raise HTTPException(409, 'Deployment already recorded for that provider id')
        return created

    # -- incidents ---------------------------------------------------------
    @router.get('/incidents', dependencies=[owner])
    async def incidents(status: str | None = None, project_id: str | None = None,
                        service_id: str | None = None):
        return store.list_incidents(status=status, project_id=project_id, service_id=service_id)

    @router.get('/incidents/{incident_id}', dependencies=[owner])
    async def incident(incident_id: uuid.UUID):
        found = store.get_incident(incident_id)
        if not found:
            raise not_found('Incident')
        return found

    @router.post('/incidents/{incident_id}/acknowledge', dependencies=[owner])
    async def acknowledge(incident_id: uuid.UUID, body: NoteIn):
        updated = store.acknowledge_incident(incident_id, body.note)
        if not updated:
            raise HTTPException(409, 'Incident is not open')
        return updated

    @router.post('/incidents/{incident_id}/resolve', dependencies=[owner])
    async def resolve(incident_id: uuid.UUID, body: NoteIn):
        updated = store.resolve_incident(incident_id, body.note)
        if not updated:
            raise HTTPException(409, 'Incident is already resolved')
        return updated

    @router.post('/incidents/{incident_id}/notes', dependencies=[owner])
    async def note(incident_id: uuid.UUID, body: NoteIn):
        updated = store.add_incident_note(incident_id, body.note)
        if not updated:
            raise not_found('Incident')
        return updated

    # -- alerts ------------------------------------------------------------
    @router.get('/alerts', dependencies=[owner])
    async def alerts():
        return store.list_alerts()

    @router.post('/alerts', status_code=201, dependencies=[owner])
    async def create_alert(body: AlertIn):
        return store.create_alert(body.model_dump())

    @router.delete('/alerts/{alert_id}', status_code=204, dependencies=[owner])
    async def delete_alert(alert_id: uuid.UUID):
        if not store.delete_alert(alert_id):
            raise not_found('Alert')

    # -- connectors --------------------------------------------------------
    @router.get('/connectors', dependencies=[owner])
    async def connectors():
        return [json_public_connector(r) for r in store.db.query(
            'SELECT * FROM connectors ORDER BY provider, name')]

    @router.post('/connectors', status_code=201, dependencies=[owner])
    async def create_connector(body: ConnectorIn):
        sealed = store.secrets.seal(body.token)
        row = store.db.one(
            'INSERT INTO connectors (id, provider, name, config, credentials, status)'
            " VALUES (%s, %s, %s, %s, %s, 'connected') RETURNING *",
            (uuid.uuid4(), body.provider, body.name.strip(), Jsonb(body.config), sealed),
        )
        store.audit('owner', 'connector.create', 'connector', row['id'], {'provider': body.provider})
        return json_public_connector(row)

    @router.patch('/connectors/{connector_id}', dependencies=[owner])
    async def patch_connector(connector_id: uuid.UUID, body: ConnectorPatch):
        fields = body.model_dump(exclude_unset=True)
        updates, params = [], []
        if 'name' in fields:
            updates.append('name = %s')
            params.append(fields['name'])
        if 'token' in fields:
            updates.append('credentials = %s')
            params.append(store.secrets.seal(fields['token']))
            updates.append("status = 'connected'")
        if not updates:
            raise HTTPException(422, 'Nothing to update')
        row = store.db.one(
            f'UPDATE connectors SET {", ".join(updates)}, updated_at = now() WHERE id = %s RETURNING *',
            (*params, connector_id))
        if not row:
            raise not_found('Connector')
        store.audit('owner', 'connector.update', 'connector', connector_id)
        return json_public_connector(row)

    @router.delete('/connectors/{connector_id}', status_code=204, dependencies=[owner])
    async def delete_connector(connector_id: uuid.UUID):
        if store.db.execute('DELETE FROM connectors WHERE id = %s', (connector_id,)) == 0:
            raise not_found('Connector')
        store.audit('owner', 'connector.delete', 'connector', connector_id)

    def connector_client(row: dict):
        token = store.secrets.open(row['credentials'])
        if row['provider'] == 'railway':
            return RailwayConnector(token, row['config'].get('endpoint'))
        if row['provider'] == 'github':
            return GitHubConnector(token, row['config'].get('endpoint'))
        return None

    @router.post('/connectors/{connector_id}/validate', dependencies=[owner])
    async def validate_connector(connector_id: uuid.UUID):
        row = store.db.one('SELECT * FROM connectors WHERE id = %s', (connector_id,))
        if not row:
            raise not_found('Connector')
        client = connector_client(row)
        if client is None:
            raise HTTPException(409, 'This connector is agent-based and cannot be validated remotely')
        try:
            account = await client.validate()
        except ConnectorError as exc:
            store.db.execute(
                "UPDATE connectors SET status = 'error', last_error = %s, updated_at = now() WHERE id = %s",
                (str(exc)[:300], connector_id))
            raise HTTPException(502, str(exc))
        store.db.execute(
            "UPDATE connectors SET status = 'connected', last_validated_at = now(), last_error = NULL,"
            " config = config || %s, updated_at = now() WHERE id = %s",
            (Jsonb(account), connector_id))
        store.audit('owner', 'connector.validate', 'connector', connector_id, account)
        return {'status': 'connected', **account}

    @router.post('/connectors/{connector_id}/sync', dependencies=[owner])
    async def sync_connector(connector_id: uuid.UUID):
        row = store.db.one('SELECT * FROM connectors WHERE id = %s', (connector_id,))
        if not row:
            raise not_found('Connector')
        client = connector_client(row)
        if client is None:
            raise HTTPException(409, 'This connector is agent-based; agents push observations directly')
        created = 0
        try:
            if row['provider'] == 'railway':
                snapshot = await client.collect()
                store.db.execute(
                    'UPDATE connectors SET config = config || %s, last_sync_at = now(),'
                    " status = 'connected', last_error = NULL, updated_at = now() WHERE id = %s",
                    (Jsonb({'inventory': snapshot.services, 'notes': snapshot.notes}), connector_id))
            else:
                projects = [p for p in store.db.query(
                    'SELECT id, repo_url FROM projects WHERE repo_url IS NOT NULL')]
                notes = []
                for project in projects:
                    snapshot = await client.collect_repo(project['repo_url'])
                    notes.append(snapshot.notes)
                    for deployment in snapshot.deployments:
                        deployment.setdefault('status', 'unknown')
                        result = store.create_deployment({
                            'project_id': project['id'],
                            'environment_id': None,
                            'service_id': None,
                            'provider': 'github',
                            'external_id': deployment['externalId'],
                            'version': deployment.get('version'),
                            'commit_sha': deployment.get('commitSha', ''),
                            'status': deployment.get('status', 'unknown'),
                            'url': deployment.get('url'),
                            'detail': deployment.get('detail') or {},
                            'deployed_at': deployment.get('deployedAt'),
                        })
                        created += 1 if result else 0
                store.db.execute(
                    "UPDATE connectors SET status = 'connected', last_sync_at = now(),"
                    " last_error = NULL, config = config || %s, updated_at = now() WHERE id = %s",
                    (Jsonb({'notes': ' | '.join(notes)[:800]}), connector_id))
        except ConnectorError as exc:
            store.db.execute(
                "UPDATE connectors SET status = 'error', last_error = %s, updated_at = now() WHERE id = %s",
                (str(exc)[:300], connector_id))
            raise HTTPException(502, str(exc))
        store.audit('owner', 'connector.sync', 'connector', connector_id, {'deployments': created})
        return {'status': 'synced', 'deployments_recorded': created}

    # -- agent ingest (token-authenticated, separate from owner sessions) ---
    @router.post('/agent/observations')
    async def agent_observation(body: AgentObservationIn, x_agent_token: str = Header(default='')):
        connectors = store.db.query(
            "SELECT * FROM connectors WHERE provider = 'docker' AND status <> 'unconfigured'")
        matched = None
        for connector in connectors:
            try:
                if hmac.compare_digest(store.secrets.open(connector['credentials']), x_agent_token):
                    matched = connector
                    break
            except Exception:
                continue
        if not matched:
            raise HTTPException(401, 'A valid agent token is required')
        service = store.db.one(
            "SELECT * FROM services WHERE connector_id = %s AND external_ref->>'agentKey' = %s",
            (matched['id'], body.agent_key))
        if not service:
            raise HTTPException(404, 'No service is linked to that agent key')
        observation = store.record_observation(
            service['id'], status=body.status, source='agent',
            latency_ms=body.latency_ms, http_status=None, message=body.message,
            evidence={'agent': body.agent_key})
        updated = store.apply_observation(service, observation)
        store.recompute_project_status(service['project_id'])
        return {'service_id': service['id'], 'status': updated['current_status']}

    # -- controlled workflow registration ----------------------------------
    def validate_definition(definition: dict) -> dict:
        """Only safe, worker-backed SIMPLE workflows may be registered from the API.

        HTTP/EVENT/SUB_WORKFLOW tasks are rejected so registration can never become an
        SSRF or arbitrary-execution primitive.
        """
        from .definitions import TASK_NAMES

        if not isinstance(definition, dict):
            raise HTTPException(422, 'definition must be a JSON object')
        unknown = set(definition) - SAFE_DEFINITION_KEYS
        if unknown:
            raise HTTPException(422, f'unsupported definition keys: {sorted(unknown)}')
        name = definition.get('name')
        if not isinstance(name, str) or not NAME.match(name):
            raise HTTPException(422, 'name must be lowercase letters, digits or underscore')
        if not isinstance(definition.get('version'), int) or not 1 <= definition['version'] <= 100:
            raise HTTPException(422, 'version must be an integer between 1 and 100')
        if definition.get('schemaVersion') != 2:
            raise HTTPException(422, 'schemaVersion must be 2')
        tasks = definition.get('tasks')
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 25:
            raise HTTPException(422, 'tasks must contain between 1 and 25 entries')
        references = set()
        for task in tasks:
            if not isinstance(task, dict):
                raise HTTPException(422, 'each task must be an object')
            task_type = task.get('type', 'SIMPLE')
            if task_type not in SAFE_TASK_TYPES:
                raise HTTPException(422, f'task type {task_type!r} is not registrable here')
            if task.get('name') not in TASK_NAMES:
                raise HTTPException(
                    422, f"task {task.get('name')!r} has no worker; only "
                         f"{sorted(TASK_NAMES)} can run")
            reference = task.get('taskReferenceName')
            if not isinstance(reference, str) or not REFERENCE.match(reference) or reference in references:
                raise HTTPException(422, 'taskReferenceName must be unique and alphanumeric')
            references.add(reference)
        parameters = definition.get('inputParameters', [])
        if not isinstance(parameters, list) or len(parameters) > 20 or \
                not all(isinstance(item, str) and NAME.match(item) for item in parameters):
            raise HTTPException(422, 'inputParameters must be lowercase identifiers')
        if not isinstance(definition.get('outputParameters', {}), dict):
            raise HTTPException(422, 'outputParameters must be an object')
        definition.setdefault('ownerEmail', 'operator@conductor.local')
        definition.setdefault('restartable', True)
        definition.setdefault('timeoutPolicy', 'TIME_OUT_WF')
        definition.setdefault('timeoutSeconds', 600)
        return definition

    @router.post('/workflows/definitions', status_code=201, dependencies=[owner])
    async def register_definition(body: DefinitionIn):
        definition = validate_definition(body.definition)
        catalog = await engine.request('GET', 'metadata/workflow')
        for existing in catalog or []:
            if existing.get('name') == definition['name'] and \
                    existing.get('version') == definition['version']:
                raise HTTPException(409, 'That name and version already exists; register a new version')
        await engine.request('PUT', 'metadata/workflow', json=[definition])
        store.audit('owner', 'workflow.register', 'workflow',
                    f"{definition['name']}@{definition['version']}",
                    {'tasks': [t['name'] for t in definition['tasks']]})
        return {'registered': True, 'name': definition['name'], 'version': definition['version']}

    # -- audit and settings ------------------------------------------------
    @router.get('/audit', dependencies=[owner])
    async def audit(limit: int = Query(100, ge=1, le=500)):
        return store.audit_entries(limit)

    @router.get('/settings', dependencies=[owner])
    async def settings_view():
        return {
            'monitoring': {
                'enabled': settings.monitor_enabled,
                'tick_seconds': settings.monitor_tick_seconds,
                'concurrency': settings.monitor_concurrency,
                'retention_days': settings.monitor_retention_days,
                'allow_private_targets': settings.http_check_allow_private,
            },
            'auth': {
                'password_login': bool(settings.owner_password),
                'session_ttl_hours': settings.session_ttl_hours,
                'api_token_configured': True,
            },
            'providers': {
                'gemini_enabled': settings.enable_gemini,
                'gemini_model': settings.gemini_model if settings.enable_gemini else None,
            },
            'secrets': {'owner_password': 'configured' if settings.owner_password else 'not configured'},
            'version': '2.0.0',
        }

    return router
