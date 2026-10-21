import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from conductor.client.http.api_client import ApiClient
from conductor.client.http.models.task_result import TaskResult

from app.main import app, db, engine, settings, store
from app.lifecycle import digest, lifecycle_definitions, redact, version_probe
from app.runner_state import Ledger
from app.engine import Engine
from conftest import DB_AVAILABLE, requires_db

client = TestClient(app)
OWNER = {'Authorization': f'Bearer {settings.control_plane_token}'}
SHA = 'a' * 40


@pytest.fixture(autouse=True)
def reset():
    if DB_AVAILABLE:
        db.initialize()
        db.execute('TRUNCATE project_releases, project_work, project_runners, incident_events, notifications,'
                   ' incidents, observations, alerts, deployments, services, environments, projects, connectors, audit_log, sessions CASCADE')
    yield


def seed():
    project = client.post('/api/projects', headers=OWNER, json={
        'name': 'Lifecycle fixture',
        'description': 'Deterministic lifecycle fixture project',
        'repo_url': 'https://github.com/example/lifecycle-fixture',
        'environments': [{'name': 'production', 'kind': 'production'}],
        'services': [
            {'name': 'Portal', 'kind': 'web', 'health_url': 'https://example.com'},
            {'name': 'Desk API', 'kind': 'api', 'health_url': 'https://example.com/health'},
        ],
    }).json()
    for service in project['services']:
        client.patch(f"/api/services/{service['id']}", headers=OWNER, json={'external_ref': {
            'version_url': 'https://example.com/version',
            'readiness_url': 'https://example.com/ready'}})
    project_id = project['id']
    db.execute("UPDATE projects SET management = %s::jsonb WHERE id = %s",
               (json.dumps({'dependencies': [{'name': name, 'status': 'unknown', 'observed_at': None}
                                             for name in ['database', 'model provider', 'scheduler']]}),
                project_id))
    project = project_id
    pair = client.post(f'/api/projects/{project}/runners', headers=OWNER, json={'name': 'test laptop'}).json()
    db.execute("UPDATE project_runners SET diagnostics=jsonb_build_object('ready',true,'publication_ready',true,'checked_at',now()::text) WHERE id=%s",(pair['id'],))
    request = client.post(f'/api/projects/{project}/work', headers=OWNER, json={
        'runner_id': pair['id'], 'title': 'Add evidence', 'request': 'Add a readiness endpoint',
        'acceptance': 'Database failures must return unavailable', 'model_approved': True}).json()
    return project, pair, request


def assign(request, pair):
    workflow, task = str(uuid4()), str(uuid4())
    db.execute("UPDATE project_work SET workflow_id = %s, task_id = %s, active = true, submission = 'submitted' WHERE id = %s",
               (workflow, task, request['id']))
    return workflow, task, {'X-Runner-Token': pair['token']}


def test_runner_journal_survives_restart_without_relaunch(tmp_path):
    path = tmp_path / 'ledger.db'
    first = Ledger(path)
    assert first.reserve('work')
    first.save('work', 'running', {'session_id': 'local-session'})
    recovered = Ledger(path)
    assert not recovered.reserve('work')
    assert recovered.get('work') == ('running', {'session_id': 'local-session'})
    recovered.save('work', 'finished', {'head_sha': SHA})
    assert not first.reserve('work')
    assert first.get('work')[0] == 'finished'


def test_redaction_and_no_automatic_model_retries():
    assert redact({'token': 'secret', 'text': 'Bearer ghp_topsecret password=abc'}) == {
        'token': '[redacted]', 'text': 'Bearer [redacted] password=[redacted]'}
    task, flow = lifecycle_definitions()
    assert task['retryCount'] == 0
    assert not flow['restartable']


def test_authentication_is_required():
    assert client.post('/api/projects', json={'name': 'unauthorised'}).status_code == 401
    assert client.get('/api/runner/work/' + str(uuid4())).status_code == 401
    assert client.get('/api/work/' + str(uuid4())).status_code == 401


def test_task_poll_is_never_retried():
    async def check():
        calls = []
        def transport(req):
            calls.append(req)
            raise httpx.ReadTimeout('ambiguous', request=req)
        e = Engine('http://engine/api')
        await e.client.aclose()
        e.client = httpx.AsyncClient(base_url='http://engine/api/', transport=httpx.MockTransport(transport))
        with pytest.raises(HTTPException):
            await e.request('GET', 'tasks/poll/cp_project_code')
        assert len(calls) == 1
        await e.close()
    asyncio.run(check())


@requires_db
def test_dependencies_unknown_and_ci_classification():
    pid, pair, request = seed()
    assert db.one('SELECT count(*) AS n FROM services WHERE project_id = %s', (pid,))['n'] == 2
    lifecycle = client.get(f'/api/projects/{pid}/lifecycle', headers=OWNER).json()
    assert all(d['status'] == 'unknown' and d['observed_at'] is None for d in lifecycle['management']['dependencies'])
    assert 'token' not in json.dumps(lifecycle['runners'])
    store.create_deployment({'project_id': pid, 'provider': 'github', 'external_id': 'github-run-1', 'evidence_kind': 'ci', 'status': 'success'})
    store.create_deployment({'project_id': pid, 'provider': 'github', 'external_id': 'github-run-1', 'evidence_kind': 'ci', 'status': 'completed'})
    assert store.list_deployments(project_id=pid) == []
    assert client.get(f'/api/projects/{pid}/lifecycle', headers=OWNER).json()['ci'][0]['status'] == 'completed'
    assert store.get_project(pid)['last_deployed_at'] is None


@requires_db
def test_runner_scope_and_revocation():
    pid, pair, request = seed()
    workflow, task, headers = assign(request, pair)
    other = client.post(f'/api/projects/{pid}/runners', headers=OWNER, json={'name': 'other laptop'}).json()
    assert client.post('/api/runner/artifacts', headers={'X-Runner-Token': other['token']}, json={'work_id': request['id'], 'data': {}}).status_code == 404
    assert client.get('/api/projects', headers={'Authorization': 'Bearer ' + pair['token']}).status_code == 401
    assert db.one('SELECT token_hash FROM project_runners WHERE id = %s', (pair['id'],))['token_hash'] == digest(pair['token'])
    client.delete(f"/api/projects/{pid}/runners/{pair['id']}", headers=OWNER)
    assert client.post('/api/runner/artifacts', headers=headers, json={'work_id': request['id'], 'data': {}}).status_code == 401


@requires_db
def test_ambiguous_start_reserved_once_and_reconciled(monkeypatch):
    pid, pair, request = seed()
    mock = AsyncMock(side_effect=HTTPException(503, 'ambiguous'))
    monkeypatch.setattr(engine, 'request', mock)
    path = f"/api/work/{request['id']}"
    assert client.post(path + '/start', headers=OWNER).status_code == 503
    assert client.post(path + '/start', headers=OWNER).json()['submission'] == 'uncertain'
    assert mock.call_count == 1
    another = client.post(f'/api/projects/{pid}/work', headers=OWNER, json={
        'runner_id': pair['id'], 'title': 'Another', 'request': 'another change request',
        'acceptance': 'must remain waiting', 'model_approved': True}).json()
    assert client.post(f"/api/work/{another['id']}/start", headers=OWNER).status_code == 409
    monkeypatch.setattr(engine, 'request', AsyncMock(return_value=[{'workflowId': str(uuid4())}]))
    assert client.post(path + '/reconcile', headers=OWNER).json()['workflow_id']


@requires_db
def test_model_usage_requires_approval(monkeypatch):
    _, _, request = seed()
    db.execute('UPDATE project_work SET model_approved = false WHERE id = %s', (request['id'],))
    mock = AsyncMock()
    monkeypatch.setattr(engine, 'request', mock)
    assert client.post(f"/api/work/{request['id']}/start", headers=OWNER).status_code == 409
    mock.assert_not_awaited()


@requires_db
def test_approval_binds_clean_passing_exact_commit_and_invalidates(monkeypatch):
    _, pair, request = seed()
    workflow, task, headers = assign(request, pair)
    monkeypatch.setattr(engine, 'request', AsyncMock(return_value={'status': 'COMPLETED'}))
    path = f"/api/work/{request['id']}/approve"
    body = {'sha': SHA, 'approve_publication': True}
    assert client.post(path, headers=OWNER, json=body).status_code == 409
    evidence = {'head_sha': SHA, 'tests_passed': True, 'dirty': False}
    assert client.post('/api/runner/artifacts', headers=headers, json={'work_id': request['id'], 'data': evidence}).status_code == 200
    assert client.post(path, headers=OWNER, json={**body, 'sha': 'b' * 40}).status_code == 409
    assert client.post(path, headers=OWNER, json=body).status_code == 200
    pub = {'work_id': request['id'], 'sha': SHA, 'state': 'publishing'}
    assert client.post(f"/api/work/{request['id']}/reject", headers=OWNER).status_code == 200
    assert client.post('/api/runner/publication', headers=headers, json=pub).status_code == 409
    assert client.post(path, headers=OWNER, json=body).status_code == 200
    assert client.post('/api/runner/publication', headers=headers, json=pub).status_code == 200
    assert client.post('/api/runner/publication', headers=headers, json={**pub, 'pr_url': 'https://github.com/other/repo/pull/1'}).status_code == 422
    client.post('/api/runner/artifacts', headers=headers, json={'work_id': request['id'], 'data': {**evidence, 'head_sha': 'b' * 40}})
    assert client.post('/api/runner/publication', headers=headers, json=pub).status_code == 409


@requires_db
def test_sdk_update_scoped_and_cancel_reserves_until_stopped(monkeypatch):
    pid, pair, request = seed()
    workflow, task, headers = assign(request, pair)
    mock = AsyncMock(return_value={'status': 'RUNNING'})
    monkeypatch.setattr(engine, 'request', mock)
    sdk = ApiClient().sanitize_for_serialization(TaskResult(workflow_instance_id=workflow, task_id=task,
                                                           status='IN_PROGRESS', output_data={}, callback_after_seconds=0))
    assert client.post('/api/runner/conductor/tasks', headers=headers, json=sdk).status_code == 200
    assert client.post('/api/runner/conductor/tasks', headers=headers, json={**sdk, 'taskId': str(uuid4())}).status_code == 404
    assert client.post(f"/api/work/{request['id']}/cancel", headers=OWNER).status_code == 200
    monkeypatch.setattr(engine, 'request', AsyncMock(return_value={'status': 'TERMINATED'}))
    client.get(f'/api/projects/{pid}/lifecycle', headers=OWNER)
    assert db.one('SELECT active FROM project_work WHERE id = %s', (request['id'],))['active']
    assert client.post(f"/api/runner/stopped/{request['id']}", headers=headers).status_code == 200
    assert not db.one('SELECT active FROM project_work WHERE id = %s', (request['id'],))['active']


@requires_db
def test_release_verifies_all_services_and_does_not_confuse_ci(monkeypatch):
    pid, _, _ = seed()
    rid = client.post(f'/api/projects/{pid}/releases', headers=OWNER, json={'expected_sha': SHA}).json()['id']
    from app import lifecycle, connectors
    from app.connectors import ProbeResult
    monkeypatch.setattr(lifecycle, 'version_probe', AsyncMock(return_value={'status': 'matched', 'observed_sha': SHA}))
    monkeypatch.setattr(connectors, 'probe_http', AsyncMock(return_value=ProbeResult('healthy')))
    assert client.post(f'/api/releases/{rid}/verify', headers=OWNER).json()['status'] == 'verified'
    monkeypatch.setattr(lifecycle, 'version_probe', AsyncMock(return_value={'status': 'mismatch', 'observed_sha': 'b' * 40}))
    assert client.post(f'/api/releases/{rid}/verify', headers=OWNER).json()['status'] == 'unverified'
    monkeypatch.setattr(lifecycle, 'version_probe', AsyncMock(return_value={'status': 'matched', 'observed_sha': SHA}))
    monkeypatch.setattr(connectors, 'probe_http', AsyncMock(return_value=ProbeResult('down')))
    assert client.post(f'/api/releases/{rid}/verify', headers=OWNER).json()['status'] == 'unverified'


def test_version_probe_rejects_private_targets_and_oversized_payload(monkeypatch):
    assert asyncio.run(version_probe('https://127.0.0.1/version', SHA))['status'] == 'unknown'
    original = httpx.AsyncClient
    def transport(request):
        return httpx.Response(200, content=b'x' * 5000)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(transport)))
    assert asyncio.run(version_probe('http://localhost/version', SHA, True))['status'] == 'unknown'


@requires_db
def test_resource_mappings_validate_and_persist():
    pid, _, _ = seed()
    service = db.one('SELECT id FROM services WHERE project_id = %s LIMIT 1', (pid,))['id']
    path = f'/api/services/{service}'
    assert client.patch(path, headers=OWNER, json={'external_ref': {'version_url': 'https://user:secret@example.com/version'}}).status_code == 422
    assert client.patch(path, headers=OWNER, json={'external_ref': {'arbitrary_command': 'deploy'}}).status_code == 422
    mapped = client.patch(path, headers=OWNER, json={'external_ref': {'version_url': 'https://example.com/version', 'readiness_url': 'https://example.com/ready'}})
    assert mapped.status_code == 200
    assert mapped.json()['external_ref']['readiness_url'] == 'https://example.com/ready'
