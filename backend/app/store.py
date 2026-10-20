"""Persistence operations for the resource inventory, monitoring and incidents."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from .db import Database, iso
from .security import SecretBox, hash_password

log = logging.getLogger('orchestra.store')

JSON_FIELDS = {
    'external_ref', 'detail', 'evidence', 'detection', 'data', 'config', 'value',
}
SERVICE_STATUSES = ('healthy', 'degraded', 'down', 'unknown', 'disabled')
SEVERITY_ORDER = {'critical': 3, 'major': 2, 'minor': 1}

DEFAULT_CLUSTERS = [
    ('Production Applications', 'logical'),
    ('AI Services', 'logical'),
    ('Experimental Projects', 'logical'),
    ('Local Development', 'local'),
]


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug[:60] or 'item'


def serialize(record: dict | None) -> dict | None:
    if record is None:
        return None
    out = {}
    for key, value in record.items():
        if isinstance(value, datetime):
            out[key] = iso(value)
        elif isinstance(value, uuid.UUID):
            out[key] = str(value)
        else:
            out[key] = value
    return out


class Store:
    def __init__(self, db: Database, settings, secrets: SecretBox):
        self.db = db
        self.settings = settings
        self.secrets = secrets

    # -- shared helpers ----------------------------------------------------
    def unique_slug(self, table: str, base: str, *, scope: dict | None = None) -> str:
        slug = slugify(base)
        candidate, suffix = slug, 1
        while True:
            params: list = [candidate]
            where = 'slug = %s'
            for column, value in (scope or {}).items():
                where += f' AND {column} = %s'
                params.append(value)
            if not self.db.one(f'SELECT 1 FROM {table} WHERE {where}', tuple(params)):
                return candidate
            suffix += 1
            candidate = f'{slug}-{suffix}'

    def audit(self, actor: str, action: str, resource_type: str, resource_id: str = '', detail: dict | None = None) -> None:
        self.db.execute(
            'INSERT INTO audit_log (actor, action, resource_type, resource_id, detail)'
            ' VALUES (%s, %s, %s, %s, %s)',
            (actor, action, resource_type, str(resource_id), Jsonb(detail or {})),
        )

    def seed_defaults(self) -> None:
        for name, kind in DEFAULT_CLUSTERS:
            existing = self.db.one('SELECT id FROM clusters WHERE name = %s', (name,))
            if not existing:
                self.db.execute(
                    'INSERT INTO clusters (id, name, kind, description) VALUES (%s, %s, %s, %s)',
                    (new_id(), name, kind, 'Seeded logical group'),
                )
        if self.settings.owner_password:
            stored = self.db.one("SELECT value FROM app_settings WHERE key = 'owner_password_hash'")
            encoded = hash_password(self.settings.owner_password)
            # Re-seed only when the configured password changed.
            if not stored:
                self.db.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('owner_password_hash', %s)"
                    ' ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()',
                    (Jsonb({'hash': encoded}),),
                )
            else:
                from .security import verify_password

                if not verify_password(self.settings.owner_password, stored['value']['hash']):
                    self.db.execute(
                        "UPDATE app_settings SET value = %s, updated_at = now()"
                        " WHERE key = 'owner_password_hash'",
                        (Jsonb({'hash': encoded}),),
                    )

    def owner_hash(self) -> str | None:
        row = self.db.one("SELECT value FROM app_settings WHERE key = 'owner_password_hash'")
        return row['value']['hash'] if row else None

    # -- clusters ----------------------------------------------------------
    def list_clusters(self) -> list[dict]:
        rows = self.db.query(
            'SELECT c.*,'
            ' (SELECT count(*) FROM projects p WHERE p.cluster_id = c.id) AS project_count,'
            ' (SELECT count(*) FROM services s JOIN projects p ON p.id = s.project_id'
            '    WHERE p.cluster_id = c.id) AS service_count,'
            ' (SELECT count(*) FROM services s JOIN projects p ON p.id = s.project_id'
            "    WHERE p.cluster_id = c.id AND s.current_status = 'down') AS down_count,"
            ' (SELECT count(*) FROM incidents i JOIN projects p ON p.id = i.project_id'
            '    WHERE p.cluster_id = c.id AND i.resolved_at IS NULL) AS open_incidents'
            ' FROM clusters c ORDER BY c.kind = \'logical\', c.name'
        )
        return [serialize(r) for r in rows]

    def create_cluster(self, name: str, kind: str, description: str, provider: str | None) -> dict:
        row = self.db.one(
            'INSERT INTO clusters (id, name, kind, description, provider)'
            ' VALUES (%s, %s, %s, %s, %s) RETURNING *',
            (new_id(), name.strip(), kind, description.strip(), provider),
        )
        self.audit('owner', 'cluster.create', 'cluster', row['id'], {'name': name})
        return serialize(row)

    def update_cluster(self, cluster_id: uuid.UUID, fields: dict) -> dict | None:
        allowed = {k: v for k, v in fields.items() if k in ('name', 'kind', 'description', 'provider')}
        if not allowed:
            return self.get_cluster(cluster_id)
        sets = ', '.join(f'{k} = %s' for k in allowed)
        row = self.db.one(
            f'UPDATE clusters SET {sets}, updated_at = now() WHERE id = %s RETURNING *',
            (*allowed.values(), cluster_id),
        )
        if row:
            self.audit('owner', 'cluster.update', 'cluster', cluster_id, allowed)
        return serialize(row)

    def get_cluster(self, cluster_id: uuid.UUID) -> dict | None:
        return serialize(self.db.one('SELECT * FROM clusters WHERE id = %s', (cluster_id,)))

    def delete_cluster(self, cluster_id: uuid.UUID) -> bool:
        deleted = self.db.execute('DELETE FROM clusters WHERE id = %s', (cluster_id,)) > 0
        if deleted:
            self.audit('owner', 'cluster.delete', 'cluster', cluster_id)
        return deleted

    # -- projects ----------------------------------------------------------
    PROJECT_LIST = """
        SELECT p.*, c.name AS cluster_name, c.kind AS cluster_kind,
          (SELECT count(*) FROM services s WHERE s.project_id = p.id) AS service_count,
          (SELECT count(*) FROM services s WHERE s.project_id = p.id AND s.current_status = 'healthy') AS healthy_count,
          (SELECT count(*) FROM services s WHERE s.project_id = p.id AND s.current_status = 'degraded') AS degraded_count,
          (SELECT count(*) FROM services s WHERE s.project_id = p.id AND s.current_status = 'down') AS down_count,
          (SELECT count(*) FROM services s WHERE s.project_id = p.id
             AND (s.current_status = 'unknown' OR (s.monitoring_enabled AND
                  (s.last_checked_at IS NULL OR s.last_checked_at < now() - make_interval(secs => s.check_interval_seconds * 3))))) AS unknown_count,
          (SELECT count(*) FROM services s WHERE s.project_id = p.id AND NOT s.monitoring_enabled) AS disabled_count,
          (SELECT count(*) FROM incidents i WHERE i.project_id = p.id AND i.resolved_at IS NULL) AS open_incidents,
          (SELECT max(d.deployed_at) FROM deployments d WHERE d.project_id = p.id) AS last_deployed_at,
          (SELECT count(*) FROM environments e WHERE e.project_id = p.id) AS environment_count
        FROM projects p LEFT JOIN clusters c ON c.id = p.cluster_id
    """

    def list_projects(self, *, cluster_id: str | None = None, environment: str | None = None,
                      status: str | None = None, search: str | None = None) -> list[dict]:
        clauses, params = [], []
        if cluster_id:
            clauses.append('p.cluster_id = %s')
            params.append(uuid.UUID(cluster_id))
        if environment:
            clauses.append('EXISTS (SELECT 1 FROM environments e WHERE e.project_id = p.id AND e.slug = %s)')
            params.append(environment)
        if status:
            clauses.append('p.status = %s')
            params.append(status)
        if search:
            clauses.append('(p.name ILIKE %s OR p.description ILIKE %s)')
            params.extend([f'%{search}%', f'%{search}%'])
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = self.db.query(self.PROJECT_LIST + where + ' ORDER BY p.name', tuple(params))
        return [serialize(r) for r in rows]

    def get_project(self, project_id: uuid.UUID) -> dict | None:
        row = self.db.one(self.PROJECT_LIST + ' WHERE p.id = %s', (project_id,))
        if not row:
            return None
        project = serialize(row)
        project['environments'] = self.list_environments(project_id)
        project['services'] = self.list_services(project_id=str(project_id))
        project['deployments'] = self.list_deployments(project_id=str(project_id), limit=20)
        project['incidents'] = self.list_incidents(project_id=str(project_id), limit=20)
        return project

    def create_project(self, payload: dict) -> dict:
        project_id = new_id()
        slug = self.unique_slug('projects', payload['name'])
        with self.db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                'INSERT INTO projects (id, name, slug, description, cluster_id, repo_url, repo_branch)'
                ' VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (project_id, payload['name'].strip(), slug, payload.get('description', '').strip(),
                 payload.get('cluster_id'), (payload.get('repo_url') or None),
                 (payload.get('repo_branch') or None)),
            )
            for env in payload.get('environments') or []:
                cur.execute(
                    'INSERT INTO environments (id, project_id, name, slug, kind)'
                    ' VALUES (%s, %s, %s, %s, %s) ON CONFLICT (project_id, slug) DO NOTHING',
                    (new_id(), project_id, env['name'].strip(), slugify(env['name']), env['kind']),
                )
            cur.execute('SELECT id, slug, kind FROM environments WHERE project_id = %s', (project_id,))
            envs = {row['slug']: row['id'] for row in cur.fetchall()}
            for service in payload.get('services') or []:
                env_id = envs.get(slugify(service['environment'])) if service.get('environment') else None
                cur.execute(
                    'INSERT INTO services (id, project_id, environment_id, name, slug, kind, provider,'
                    ' health_url, monitoring_enabled, check_interval_seconds, timeout_seconds,'
                    ' expected_status, failure_threshold, recovery_threshold, current_status)'
                    ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    (new_id(), project_id, env_id, service['name'].strip(),
                     slugify(service['name']), service['kind'], service.get('provider', 'http'),
                     service.get('health_url') or None, service.get('monitoring_enabled', True),
                     service.get('check_interval_seconds', 60), service.get('timeout_seconds', 10),
                     service.get('expected_status', 200), service.get('failure_threshold', 2),
                     service.get('recovery_threshold', 1),
                     'unknown' if service.get('monitoring_enabled', True) else 'disabled'),
                )
        self.recompute_project_status(project_id)
        self.audit('owner', 'project.create', 'project', project_id, {'name': payload['name']})
        return self.get_project(project_id)

    def update_project(self, project_id: uuid.UUID, fields: dict) -> dict | None:
        allowed = {k: v for k, v in fields.items() if k in
                   ('name', 'description', 'cluster_id', 'repo_url', 'repo_branch')}
        if allowed:
            sets = ', '.join(f'{k} = %s' for k in allowed)
            self.db.execute(
                f'UPDATE projects SET {sets}, updated_at = now() WHERE id = %s',
                (*allowed.values(), project_id),
            )
            self.audit('owner', 'project.update', 'project', project_id, allowed)
        return self.get_project(project_id)

    def delete_project(self, project_id: uuid.UUID) -> bool:
        deleted = self.db.execute('DELETE FROM projects WHERE id = %s', (project_id,)) > 0
        if deleted:
            self.audit('owner', 'project.delete', 'project', project_id)
        return deleted

    def recompute_project_status(self, project_id: uuid.UUID) -> None:
        self.db.execute(
            """
            UPDATE projects p SET status = CASE
                WHEN NOT EXISTS (SELECT 1 FROM services s WHERE s.project_id = p.id AND s.monitoring_enabled)
                    THEN 'disabled'
                WHEN EXISTS (SELECT 1 FROM services s WHERE s.project_id = p.id AND s.current_status = 'down')
                    THEN 'down'
                WHEN EXISTS (SELECT 1 FROM services s WHERE s.project_id = p.id AND s.current_status = 'degraded')
                    THEN 'degraded'
                WHEN EXISTS (SELECT 1 FROM services s WHERE s.project_id = p.id AND s.current_status = 'healthy')
                    THEN 'healthy'
                ELSE 'unknown' END,
                updated_at = now()
            WHERE p.id = %s
            """,
            (project_id,),
        )

    # -- environments ------------------------------------------------------
    def list_environments(self, project_id: uuid.UUID) -> list[dict]:
        rows = self.db.query(
            'SELECT e.*, (SELECT count(*) FROM services s WHERE s.environment_id = e.id) AS service_count'
            ' FROM environments e WHERE e.project_id = %s ORDER BY e.kind, e.name',
            (project_id,),
        )
        return [serialize(r) for r in rows]

    def create_environment(self, project_id: uuid.UUID, name: str, kind: str) -> dict:
        slug = slugify(name)
        row = self.db.one(
            'INSERT INTO environments (id, project_id, name, slug, kind) VALUES (%s, %s, %s, %s, %s)'
            ' ON CONFLICT (project_id, slug) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind'
            ' RETURNING *',
            (new_id(), project_id, name.strip(), slug, kind),
        )
        self.audit('owner', 'environment.create', 'environment', row['id'], {'project': str(project_id)})
        return serialize(row)

    def delete_environment(self, environment_id: uuid.UUID) -> bool:
        deleted = self.db.execute('DELETE FROM environments WHERE id = %s', (environment_id,)) > 0
        if deleted:
            self.audit('owner', 'environment.delete', 'environment', environment_id)
        return deleted

    # -- services ----------------------------------------------------------
    SERVICE_LIST = """
        SELECT s.*, p.name AS project_name, p.cluster_id, e.name AS environment_name,
          e.kind AS environment_kind,
          (SELECT count(*) FROM observations o WHERE o.service_id = s.id
             AND o.observed_at > now() - interval '24 hours') AS observations_24h
        FROM services s
        JOIN projects p ON p.id = s.project_id
        LEFT JOIN environments e ON e.id = s.environment_id
    """

    def list_services(self, *, project_id: str | None = None, environment_id: str | None = None,
                      status: str | None = None, search: str | None = None,
                      limit: int = 200) -> list[dict]:
        clauses, params = [], []
        if project_id:
            clauses.append('s.project_id = %s')
            params.append(uuid.UUID(project_id))
        if environment_id:
            clauses.append('s.environment_id = %s')
            params.append(uuid.UUID(environment_id))
        if status:
            clauses.append('s.current_status = %s')
            params.append(status)
        if search:
            clauses.append('(s.name ILIKE %s OR p.name ILIKE %s)')
            params.extend([f'%{search}%', f'%{search}%'])
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = self.db.query(self.SERVICE_LIST + where + ' ORDER BY p.name, s.name LIMIT %s',
                             (*params, limit))
        return [serialize(r) for r in rows]

    def get_service(self, service_id: uuid.UUID) -> dict | None:
        row = self.db.one(self.SERVICE_LIST + ' WHERE s.id = %s', (service_id,))
        return serialize(row)

    def create_service(self, payload: dict) -> dict:
        project_id = uuid.UUID(str(payload['project_id']))
        env_id = payload.get('environment_id') or None
        slug = self.unique_slug('services', payload['name'], scope={'project_id': project_id})
        row = self.db.one(
            'INSERT INTO services (id, project_id, environment_id, connector_id, name, slug, kind,'
            ' provider, health_url, monitoring_enabled, check_interval_seconds, timeout_seconds,'
            ' expected_status, failure_threshold, recovery_threshold, external_ref, current_status)'
            ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *',
            (new_id(), project_id,
             uuid.UUID(str(env_id)) if env_id else None,
             uuid.UUID(str(payload['connector_id'])) if payload.get('connector_id') else None,
             payload['name'].strip(), slug, payload.get('kind', 'web'),
             payload.get('provider', 'http'), payload.get('health_url') or None,
             payload.get('monitoring_enabled', True), payload.get('check_interval_seconds', 60),
             payload.get('timeout_seconds', 10), payload.get('expected_status', 200),
             payload.get('failure_threshold', 2), payload.get('recovery_threshold', 1),
             Jsonb(payload.get('external_ref') or {}),
             'unknown' if payload.get('monitoring_enabled', True) else 'disabled'),
        )
        self.recompute_project_status(project_id)
        self.audit('owner', 'service.create', 'service', row['id'], {'name': payload['name']})
        return self.get_service(row['id'])

    def update_service(self, service_id: uuid.UUID, fields: dict) -> dict | None:
        allowed_keys = ('name', 'kind', 'provider', 'health_url', 'monitoring_enabled',
                        'check_interval_seconds', 'timeout_seconds', 'expected_status',
                        'failure_threshold', 'recovery_threshold', 'environment_id', 'external_ref')
        allowed = {k: v for k, v in fields.items() if k in allowed_keys}
        if 'external_ref' in allowed:
            allowed['external_ref'] = Jsonb(allowed['external_ref'] or {})
        if allowed:
            if allowed.get('monitoring_enabled') is False:
                allowed['current_status'] = 'disabled'
            sets = ', '.join(f'{k} = %s' for k in allowed)
            row = self.db.one(
                f'UPDATE services SET {sets}, updated_at = now() WHERE id = %s RETURNING project_id',
                (*allowed.values(), service_id),
            )
            if row:
                self.recompute_project_status(row['project_id'])
                self.audit('owner', 'service.update', 'service', service_id,
                           {k: str(v) for k, v in allowed.items() if k != 'external_ref'})
        return self.get_service(service_id)

    def delete_service(self, service_id: uuid.UUID) -> bool:
        row = self.db.one('DELETE FROM services WHERE id = %s RETURNING project_id', (service_id,))
        if row:
            self.recompute_project_status(row['project_id'])
            self.audit('owner', 'service.delete', 'service', service_id)
        return bool(row)

    def due_services(self, limit: int = 20) -> list[dict]:
        rows = self.db.query(
            'SELECT * FROM services WHERE monitoring_enabled AND provider <> \'manual\''
            ' AND health_url IS NOT NULL'
            ' AND (last_checked_at IS NULL'
            '      OR last_checked_at + make_interval(secs => check_interval_seconds) <= now())'
            ' ORDER BY last_checked_at NULLS FIRST LIMIT %s',
            (limit,),
        )
        return [serialize(r) for r in rows]

    def record_observation(self, service_id: uuid.UUID, *, status: str, source: str,
                           latency_ms: int | None, http_status: int | None,
                           message: str, evidence: dict | None = None) -> dict:
        row = self.db.one(
            'INSERT INTO observations (service_id, status, source, latency_ms, http_status, message, evidence)'
            ' VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *',
            (service_id, status, source, latency_ms, http_status, message[:500], Jsonb(evidence or {})),
        )
        return serialize(row)

    def observations(self, service_id: uuid.UUID, limit: int = 100) -> list[dict]:
        rows = self.db.query(
            'SELECT * FROM observations WHERE service_id = %s ORDER BY observed_at DESC LIMIT %s',
            (service_id, limit),
        )
        return [serialize(r) for r in rows]

    def apply_observation(self, service: dict, observation: dict) -> dict:
        """Move a service's state only when the configured thresholds are met."""
        current_status = service['current_status']
        if observation['status'] == 'unknown':
            # Monitoring produced no evidence about the application: never call that an outage.
            row = self.db.one(
                'UPDATE services SET last_checked_at = %s, last_error = %s, updated_at = now()'
                ' WHERE id = %s RETURNING *',
                (observation['observed_at'], (observation['message'] or 'unknown outcome')[:500],
                 service['id']),
            )
            updated = serialize(row)
            updated['_previous_status'] = current_status
            return updated
        healthy = observation['status'] == 'healthy'
        failures = 0 if healthy else service['consecutive_failures'] + 1
        successes = service['consecutive_successes'] + 1 if healthy else 0
        current = service['current_status']
        target = current
        if healthy and successes >= service['recovery_threshold']:
            target = 'healthy'
        elif not healthy and failures >= service['failure_threshold']:
            target = 'degraded' if observation['status'] == 'degraded' else 'down'
        changed = target != current
        row = self.db.one(
            'UPDATE services SET current_status = %s,'
            ' status_changed_at = CASE WHEN %s THEN now() ELSE status_changed_at END,'
            ' last_checked_at = %s,'
            ' last_ok_at = CASE WHEN %s THEN now() ELSE last_ok_at END,'
            ' consecutive_failures = %s, consecutive_successes = %s,'
            ' last_error = CASE WHEN %s THEN NULL ELSE %s END, updated_at = now()'
            ' WHERE id = %s RETURNING *',
            (target, changed, observation['observed_at'], healthy, failures, successes,
             healthy, (observation['message'] or '')[:500] or None, service['id']),
        )
        updated = serialize(row)
        updated['_previous_status'] = current
        return updated

    # -- deployments -------------------------------------------------------
    def list_deployments(self, *, project_id: str | None = None, limit: int = 50) -> list[dict]:
        params: list = []
        where = ''
        if project_id:
            where = ' WHERE d.project_id = %s'
            params.append(uuid.UUID(project_id))
        rows = self.db.query(
            'SELECT d.*, p.name AS project_name, e.name AS environment_name, s.name AS service_name'
            ' FROM deployments d JOIN projects p ON p.id = d.project_id'
            ' LEFT JOIN environments e ON e.id = d.environment_id'
            ' LEFT JOIN services s ON s.id = d.service_id'
            + where +
            ' ORDER BY d.deployed_at DESC LIMIT %s',
            (*params, limit),
        )
        return [serialize(r) for r in rows]

    def create_deployment(self, payload: dict) -> dict:
        row = self.db.one(
            'INSERT INTO deployments (id, project_id, environment_id, service_id, provider,'
            ' external_id, version, commit_sha, status, url, detail, deployed_at)'
            ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'
            ' ON CONFLICT (provider, external_id) WHERE external_id IS NOT NULL DO NOTHING RETURNING *',
            (new_id(), payload['project_id'],
             payload.get('environment_id'), payload.get('service_id'),
             payload.get('provider', 'manual'), payload.get('external_id'),
             payload.get('version'), payload.get('commit_sha', ''), payload.get('status', 'unknown'),
             payload.get('url'), Jsonb(payload.get('detail') or {}),
             payload.get('deployed_at') or datetime.now(timezone.utc)),
        )
        if row:
            self.audit('owner', 'deployment.create', 'deployment', row['id'],
                       {'project': str(payload['project_id']), 'status': payload.get('status')})
        return serialize(row)

    # -- incidents ---------------------------------------------------------
    INCIDENT_SELECT = """
        SELECT i.*, p.name AS project_name, s.name AS service_name,
          s.health_url, s.current_status AS service_status,
          (SELECT count(*) FROM incident_events ev WHERE ev.incident_id = i.id) AS event_count
        FROM incidents i JOIN projects p ON p.id = i.project_id
        JOIN services s ON s.id = i.service_id
    """

    def list_incidents(self, *, status: str | None = None, project_id: str | None = None,
                       service_id: str | None = None, limit: int = 100) -> list[dict]:
        clauses, params = [], []
        if status == 'active':
            clauses.append('i.resolved_at IS NULL')
        elif status:
            clauses.append('i.status = %s')
            params.append(status)
        if project_id:
            clauses.append('i.project_id = %s')
            params.append(uuid.UUID(project_id))
        if service_id:
            clauses.append('i.service_id = %s')
            params.append(uuid.UUID(service_id))
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = self.db.query(self.INCIDENT_SELECT + where + ' ORDER BY i.opened_at DESC LIMIT %s',
                             (*params, limit))
        return [serialize(r) for r in rows]

    def get_incident(self, incident_id: uuid.UUID) -> dict | None:
        row = self.db.one(self.INCIDENT_SELECT + ' WHERE i.id = %s', (incident_id,))
        if not row:
            return None
        incident = serialize(row)
        incident['events'] = [
            serialize(e) for e in self.db.query(
                'SELECT * FROM incident_events WHERE incident_id = %s ORDER BY at', (incident_id,))
        ]
        incident['observations'] = self.observations(row['service_id'], limit=50)
        incident['notifications'] = [
            serialize(n) for n in self.db.query(
                'SELECT * FROM notifications WHERE incident_id = %s ORDER BY created_at DESC',
                (incident_id,))
        ]
        return incident

    def open_incident(self, service: dict, observation: dict) -> tuple[dict | None, bool]:
        """Create one active incident per service; returns (incident, created)."""
        existing = self.db.one(
            'SELECT id FROM incidents WHERE service_id = %s AND resolved_at IS NULL',
            (service['id'],),
        )
        if existing:
            return None, False
        severity = 'critical' if service['kind'] in ('api', 'database') else 'major'
        title = f"{service['name']} {'is down' if observation['status'] == 'down' else 'is degraded'}"
        try:
            row = self.db.one(
                'INSERT INTO incidents (id, project_id, service_id, title, severity, detection)'
                ' VALUES (%s, %s, %s, %s, %s, %s) RETURNING *',
                (new_id(), service['project_id'], service['id'], title, severity,
                 Jsonb({'observation': observation, 'previous_status': service['current_status'],
                        'threshold': service['failure_threshold']})),
            )
        except Exception:
            log.exception('failed to open incident for service %s', service['id'])
            return None, False
        self.db.execute(
            'INSERT INTO incident_events (incident_id, kind, actor, message, data)'
            ' VALUES (%s, %s, %s, %s, %s)',
            (row['id'], 'opened', 'monitor',
             f"Health check reported {observation['status']} "
             f"({observation['message'] or 'no detail'}); threshold {service['failure_threshold']} reached",
             Jsonb({'observation_id': observation['id'], 'source': observation['source']})),
        )
        self.audit('monitor', 'incident.open', 'incident', row['id'], {'service': str(service['id'])})
        return serialize(row), True

    def acknowledge_incident(self, incident_id: uuid.UUID, note: str) -> dict | None:
        row = self.db.one(
            "UPDATE incidents SET status = 'acknowledged', acknowledged_at = now(), updated_at = now()"
            " WHERE id = %s AND resolved_at IS NULL RETURNING *", (incident_id,))
        if row:
            self.db.execute(
                'INSERT INTO incident_events (incident_id, kind, actor, message) VALUES (%s, %s, %s, %s)',
                (incident_id, 'acknowledged', 'owner', note or 'Acknowledged'),
            )
            self.audit('owner', 'incident.acknowledge', 'incident', incident_id)
        return self.get_incident(incident_id) if row else None

    def resolve_incident(self, incident_id: uuid.UUID, note: str, *, actor: str = 'owner') -> dict | None:
        row = self.db.one(
            "UPDATE incidents SET status = 'resolved', resolved_at = now(), resolution_note = %s,"
            " updated_at = now() WHERE id = %s AND resolved_at IS NULL RETURNING *",
            (note[:1000], incident_id),
        )
        if row:
            self.db.execute(
                'INSERT INTO incident_events (incident_id, kind, actor, message) VALUES (%s, %s, %s, %s)',
                (incident_id, 'resolved', actor, note or 'Resolved'),
            )
            self.audit(actor, 'incident.resolve', 'incident', incident_id)
        return self.get_incident(incident_id) if row else None

    def add_incident_note(self, incident_id: uuid.UUID, note: str) -> dict | None:
        if not self.db.one('SELECT 1 FROM incidents WHERE id = %s', (incident_id,)):
            return None
        self.db.execute(
            'INSERT INTO incident_events (incident_id, kind, actor, message) VALUES (%s, %s, %s, %s)',
            (incident_id, 'note', 'owner', note[:2000]),
        )
        self.db.execute('UPDATE incidents SET updated_at = now() WHERE id = %s', (incident_id,))
        return self.get_incident(incident_id)

    def resolve_incidents_for_service(self, service_id: uuid.UUID, note: str) -> list[dict]:
        resolved = []
        for row in self.db.query(
                'SELECT id FROM incidents WHERE service_id = %s AND resolved_at IS NULL',
                (service_id,)):
            incident = self.resolve_incident(row['id'], note, actor='monitor')
            if incident:
                resolved.append(incident)
        return resolved

    # -- alerts ------------------------------------------------------------
    def list_alerts(self) -> list[dict]:
        rows = self.db.query(
            'SELECT a.id, a.name, a.channel, a.project_id, a.min_severity, a.cooldown_seconds,'
            ' a.enabled, a.last_notified_at, a.created_at, p.name AS project_name'
            ' FROM alerts a LEFT JOIN projects p ON p.id = a.project_id ORDER BY a.name')
        return [serialize(r) for r in rows]

    def create_alert(self, payload: dict) -> dict:
        row = self.db.one(
            'INSERT INTO alerts (id, name, channel, target, project_id, min_severity, cooldown_seconds, enabled)'
            ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'
            ' RETURNING id, name, channel, project_id, min_severity, cooldown_seconds, enabled, created_at',
            (new_id(), payload['name'].strip(), 'webhook',
             self.secrets.seal(payload['target']), payload.get('project_id'),
             payload.get('min_severity', 'major'), payload.get('cooldown_seconds', 900),
             payload.get('enabled', True)),
        )
        self.audit('owner', 'alert.create', 'alert', row['id'], {'name': payload['name']})
        return serialize(row)

    def delete_alert(self, alert_id: uuid.UUID) -> bool:
        deleted = self.db.execute('DELETE FROM alerts WHERE id = %s', (alert_id,)) > 0
        if deleted:
            self.audit('owner', 'alert.delete', 'alert', alert_id)
        return deleted

    def eligible_alerts(self, incident: dict) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM alerts WHERE enabled AND channel = 'webhook'"
            ' AND (project_id IS NULL OR project_id = %s)'
            ' AND (last_notified_at IS NULL OR last_notified_at + make_interval(secs => cooldown_seconds) <= now())'
            ' ORDER BY name',
            (incident['project_id'],),
        )
        return [r for r in rows if SEVERITY_ORDER.get(incident['severity'], 0) >= SEVERITY_ORDER.get(r['min_severity'], 0)]

    def record_notification(self, incident_id, alert_id, status: str, error: str | None = None) -> None:
        self.db.execute(
            'INSERT INTO notifications (incident_id, alert_id, channel, status, error)'
            " VALUES (%s, %s, 'webhook', %s, %s)",
            (incident_id, alert_id, status, (error or '')[:300] or None),
        )
        if status == 'sent':
            self.db.execute('UPDATE alerts SET last_notified_at = now() WHERE id = %s', (alert_id,))

    # -- dashboard ---------------------------------------------------------
    def dashboard(self) -> dict:
        totals = self.db.one(
            'SELECT'
            ' (SELECT count(*) FROM projects) AS projects,'
            ' (SELECT count(*) FROM services) AS services,'
            ' (SELECT count(*) FROM services WHERE current_status = \'healthy\') AS healthy,'
            ' (SELECT count(*) FROM services WHERE current_status = \'degraded\') AS degraded,'
            ' (SELECT count(*) FROM services WHERE current_status = \'down\') AS down,'
            ' (SELECT count(*) FROM services WHERE current_status = \'unknown\') AS unknown,'
            ' (SELECT count(*) FROM services WHERE current_status = \'disabled\') AS disabled,'
            ' (SELECT count(*) FROM incidents WHERE resolved_at IS NULL) AS active_incidents,'
            ' (SELECT count(*) FROM connectors WHERE status = \'connected\') AS connectors,'
            ' (SELECT count(*) FROM services WHERE monitoring_enabled AND'
            '   (last_checked_at IS NULL OR last_checked_at < now() - make_interval(secs => check_interval_seconds * 3))) AS stale'
        )
        clusters = self.db.query(
            'SELECT c.id, c.name, c.kind,'
            ' (SELECT count(*) FROM projects p WHERE p.cluster_id = c.id) AS projects,'
            ' (SELECT count(*) FROM services s JOIN projects p ON p.id = s.project_id'
            '   WHERE p.cluster_id = c.id AND s.current_status = \'down\') AS down'
            ' FROM clusters c ORDER BY c.name'
        )
        environments = self.db.query(
            'SELECT e.kind, count(*) AS services,'
            ' count(*) FILTER (WHERE s.current_status = \'down\') AS down'
            ' FROM environments e JOIN services s ON s.environment_id = e.id GROUP BY e.kind ORDER BY e.kind')
        attention = self.db.query(
            'SELECT s.id, s.name, s.current_status, s.last_checked_at, s.last_error,'
            ' p.id AS project_id, p.name AS project_name, e.name AS environment_name'
            ' FROM services s JOIN projects p ON p.id = s.project_id'
            ' LEFT JOIN environments e ON e.id = s.environment_id'
            " WHERE s.current_status IN ('down', 'degraded')"
            ' ORDER BY CASE s.current_status WHEN \'down\' THEN 0 ELSE 1 END, s.status_changed_at DESC'
            ' LIMIT 10')
        return {
            'totals': serialize(totals),
            'clusters': [serialize(r) for r in clusters],
            'environments': [serialize(r) for r in environments],
            'needs_attention': [serialize(r) for r in attention],
            'incidents': self.list_incidents(status='active', limit=10),
            'deployments': self.list_deployments(limit=10),
            'projects': self.list_projects()[:20],
            'stale': [serialize(r) for r in self.db.query(
                'SELECT s.id, s.name, s.last_checked_at, p.name AS project_name, s.check_interval_seconds'
                ' FROM services s JOIN projects p ON p.id = s.project_id'
                ' WHERE s.monitoring_enabled AND (s.last_checked_at IS NULL OR'
                ' s.last_checked_at < now() - make_interval(secs => s.check_interval_seconds * 3))'
                ' ORDER BY s.last_checked_at NULLS FIRST LIMIT 10')],
            'observed_at': iso(datetime.now(timezone.utc)),
        }

    def audit_entries(self, limit: int = 100) -> list[dict]:
        return [serialize(r) for r in self.db.query(
            'SELECT * FROM audit_log ORDER BY at DESC LIMIT %s', (limit,))]

    # -- retention ---------------------------------------------------------
    def prune(self) -> dict:
        days = self.settings.monitor_retention_days
        keep = self.settings.monitor_retention_observations
        by_age = self.db.execute(
            "DELETE FROM observations WHERE observed_at < now() - make_interval(days => %s)", (days,))
        by_count = self.db.execute(
            'DELETE FROM observations o USING ('
            '  SELECT id, row_number() OVER (PARTITION BY service_id ORDER BY observed_at DESC) AS rn'
            '  FROM observations) ranked'
            ' WHERE o.id = ranked.id AND ranked.rn > %s', (keep,))
        sessions = self.db.execute('DELETE FROM sessions WHERE expires_at < now()')
        return {'observationsByAge': by_age, 'observationsByCount': by_count, 'sessions': sessions}
