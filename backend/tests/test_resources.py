import http.server
import json
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import app, db, settings, store
from app.security import SecretBox, UnsafeTarget, hash_password, resolve_public, verify_password

from conftest import DB_AVAILABLE, requires_db

client = TestClient(app)
HEADERS = {'Authorization': f'Bearer {settings.control_plane_token}'}


class _HealthServer(http.server.BaseHTTPRequestHandler):
    state = {'code': 200, 'hits': 0, 'payloads': []}

    def do_GET(self):  # health endpoint
        type(self).state['hits'] += 1
        self.send_response(type(self).state['code'])
        self.send_header('content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'ok')

    def do_POST(self):  # webhook receiver
        length = int(self.headers.get('content-length', 0))
        type(self).state['payloads'].append(json.loads(self.rfile.read(length) or b'{}'))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def server():
    _HealthServer.state = {'code': 200, 'hits': 0, 'payloads': []}
    httpd = http.server.HTTPServer(('127.0.0.1', 0), _HealthServer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield _HealthServer.state, f'http://127.0.0.1:{httpd.server_port}'
    httpd.shutdown()


@pytest.fixture(autouse=True)
def clean_database():
    if not DB_AVAILABLE:
        yield
        return
    db.initialize()
    store.seed_defaults()
    db.execute(
        'TRUNCATE incident_events, notifications, incidents, observations, alerts,'
        ' deployments, services, environments, projects, connectors, audit_log, sessions'
        ' RESTART IDENTITY CASCADE')
    yield


@pytest.fixture()
def allow_private(monkeypatch):
    monkeypatch.setattr(settings, 'http_check_allow_private', True)


# -- security primitives (no database needed) ------------------------------
def test_ssrf_guard_blocks_private_and_plain_http():
    with pytest.raises(UnsafeTarget):
        resolve_public('http://10.0.0.5/health')
    with pytest.raises(UnsafeTarget):
        resolve_public('https://127.0.0.1/health')
    with pytest.raises(UnsafeTarget):
        resolve_public('https://169.254.169.254/latest/meta-data')
    with pytest.raises(UnsafeTarget):
        resolve_public('file:///etc/passwd')
    with pytest.raises(UnsafeTarget):
        resolve_public('https://user:pass@example.com/')
    assert resolve_public('https://10.0.0.5/', allow_private=True)


def test_secret_box_requires_the_same_key():
    first = SecretBox(b'a' * 32)
    second = SecretBox(b'b' * 32)
    sealed = first.seal('super-secret-token')
    assert b'super-secret-token' not in sealed
    assert first.open(sealed) == 'super-secret-token'
    with pytest.raises(Exception):
        second.open(sealed)


def test_password_hash_roundtrip():
    encoded = hash_password('correct horse battery staple')
    assert 'correct horse' not in encoded
    assert verify_password('correct horse battery staple', encoded)
    assert not verify_password('wrong password', encoded)


def test_resource_endpoints_require_authentication():
    for method, path in [('get', '/api/projects'), ('get', '/api/dashboard'),
                         ('get', '/api/incidents'), ('get', '/api/connectors'),
                         ('post', '/api/clusters'), ('post', '/api/services')]:
        response = getattr(client, method)(path)
        assert response.status_code == 401, path
    assert client.get('/healthz').status_code == 200


def test_session_endpoint_rejects_bad_credentials():
    response = client.post('/api/session', json={'credential': 'not-the-password'})
    assert response.status_code == 401


# -- persistence -----------------------------------------------------------
@requires_db
def test_default_clusters_are_seeded():
    clusters = client.get('/api/clusters', headers=HEADERS).json()
    names = {c['name'] for c in clusters}
    assert {'Production Applications', 'AI Services', 'Experimental Projects', 'Local Development'} <= names
    assert all(c['kind'] in ('logical', 'provider', 'local') for c in clusters)


@requires_db
def test_project_and_service_crud_persists():
    created = client.post('/api/projects', headers=HEADERS, json={
        'name': 'Billing Platform',
        'description': 'subscriptions and invoicing',
        'environments': [{'name': 'production', 'kind': 'production'},
                         {'name': 'staging', 'kind': 'staging'}],
        'services': [{'name': 'Billing API', 'kind': 'api',
                      'health_url': 'https://example.com/health'}],
    })
    assert created.status_code == 201, created.text
    project = created.json()
    assert len(project['environments']) == 2
    assert project['services'][0]['kind'] == 'api'

    fetched = client.get(f"/api/projects/{project['id']}", headers=HEADERS).json()
    assert fetched['name'] == 'Billing Platform'

    patched = client.patch(f"/api/projects/{project['id']}", headers=HEADERS,
                           json={'description': 'updated'}).json()
    assert patched['description'] == 'updated'

    # A second project with the same name gets a distinct slug instead of a 500.
    duplicate = client.post('/api/projects', headers=HEADERS, json={'name': 'Billing Platform'})
    assert duplicate.status_code == 201
    assert duplicate.json()['slug'] != project['slug']

    service = client.post('/api/services', headers=HEADERS, json={
        'project_id': project['id'], 'name': 'Billing Worker', 'kind': 'worker',
        'provider': 'manual', 'monitoring_enabled': False,
    })
    assert service.status_code == 201, service.text
    assert service.json()['current_status'] == 'disabled'

    assert client.delete(f"/api/services/{service.json()['id']}", headers=HEADERS).status_code == 204
    assert client.delete(f"/api/projects/{project['id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/projects/{project['id']}", headers=HEADERS).status_code == 404


@requires_db
def test_clusters_move_projects_and_filter_dashboard():
    cluster = client.post('/api/clusters', headers=HEADERS,
                          json={'name': 'Side Projects', 'kind': 'logical'}).json()
    project = client.post('/api/projects', headers=HEADERS,
                          json={'name': 'Notes App', 'cluster_id': cluster['id']}).json()
    assert project['cluster_id'] == cluster['id']
    filtered = client.get('/api/projects', headers=HEADERS, params={'cluster_id': cluster['id']}).json()
    assert [p['id'] for p in filtered] == [project['id']]
    dashboard = client.get('/api/dashboard', headers=HEADERS).json()
    match = next(c for c in dashboard['clusters'] if c['id'] == cluster['id'])
    assert match['projects'] == 1
    assert client.delete(f"/api/clusters/{cluster['id']}", headers=HEADERS).status_code == 204


# -- monitoring, incidents and alerts --------------------------------------
@requires_db
def test_health_to_failure_incident_recovery_cycle(server, allow_private):
    state, base_url = server
    project = client.post('/api/projects', headers=HEADERS, json={
        'name': 'Checkout',
        'services': [{'name': 'Checkout API', 'kind': 'api', 'health_url': f'{base_url}/health',
                      'failure_threshold': 1, 'recovery_threshold': 1, 'check_interval_seconds': 15}],
    }).json()
    service_id = project['services'][0]['id']

    healthy = client.post(f'/api/services/{service_id}/check', headers=HEADERS).json()
    assert healthy['observation']['status'] == 'healthy'
    assert healthy['service']['current_status'] == 'healthy'

    state['code'] = 500
    down = client.post(f'/api/services/{service_id}/check', headers=HEADERS).json()
    assert down['observation']['status'] == 'down'
    assert down['service']['current_status'] == 'down'

    incidents = client.get('/api/incidents', headers=HEADERS, params={'status': 'active'}).json()
    assert len(incidents) == 1
    incident = client.get(f"/api/incidents/{incidents[0]['id']}", headers=HEADERS).json()
    assert incident['service_id'] == service_id
    assert incident['status'] == 'open'
    assert incident['detection']['observation']['http_status'] == 500
    assert any(e['kind'] == 'opened' for e in incident['events'])

    # The same continuing failure must not create a second incident.
    client.post(f'/api/services/{service_id}/check', headers=HEADERS)
    assert len(client.get('/api/incidents', headers=HEADERS, params={'status': 'active'}).json()) == 1

    acknowledged = client.post(f"/api/incidents/{incident['id']}/acknowledge", headers=HEADERS,
                               json={'note': 'Looking into the 500s'}).json()
    assert acknowledged['status'] == 'acknowledged'
    noted = client.post(f"/api/incidents/{incident['id']}/notes", headers=HEADERS,
                        json={'note': 'Database connection pool exhausted'}).json()
    assert any(e['kind'] == 'note' for e in noted['events'])

    state['code'] = 200
    recovered = client.post(f'/api/services/{service_id}/check', headers=HEADERS).json()
    assert recovered['service']['current_status'] == 'healthy'

    resolved = client.get(f"/api/incidents/{incident['id']}", headers=HEADERS).json()
    assert resolved['status'] == 'resolved'
    assert resolved['resolution_note'].startswith('Automatically recovered')
    assert any(e['kind'] == 'resolved' and e['actor'] == 'monitor' for e in resolved['events'])

    dashboard = client.get('/api/dashboard', headers=HEADERS).json()
    assert dashboard['totals']['active_incidents'] == 0
    assert dashboard['totals']['services'] == 1


@requires_db
def test_observation_history_and_unknown_for_blocked_target(allow_private, monkeypatch):
    project = client.post('/api/projects', headers=HEADERS, json={
        'name': 'Internal Tool',
        'services': [{'name': 'Internal API', 'health_url': 'http://127.0.0.1:9/health',
                      'failure_threshold': 1}],
    }).json()
    service_id = project['services'][0]['id']
    monkeypatch.setattr(settings, 'http_check_allow_private', False)
    result = client.post(f'/api/services/{service_id}/check', headers=HEADERS).json()
    assert result['observation']['status'] == 'unknown'
    assert 'check not performed' in result['observation']['message']
    # A blocked target must not be reported as an application outage.
    assert result['service']['current_status'] == 'unknown'
    assert client.get('/api/incidents', headers=HEADERS).json() == []

    history = client.get(f'/api/services/{service_id}/observations', headers=HEADERS).json()
    assert history[0]['source'] == 'http'
    assert history[0]['observed_at']


@requires_db
def test_alert_delivery_dedup_and_cooldown(server, allow_private):
    state, base_url = server
    alert = client.post('/api/alerts', headers=HEADERS, json={
        'name': 'Ops webhook', 'target': f'{base_url}/hook',
        'min_severity': 'major', 'cooldown_seconds': 900,
    })
    assert alert.status_code == 201, alert.text
    # The webhook target is sealed at rest and never echoed back.
    assert 'target' not in alert.json()
    assert base_url not in str(client.get('/api/alerts', headers=HEADERS).json())

    project = client.post('/api/projects', headers=HEADERS, json={
        'name': 'Alerts', 'services': [{'name': 'Alerts API', 'kind': 'api',
                                        'health_url': f'{base_url}/health', 'failure_threshold': 1}],
    }).json()
    service_id = project['services'][0]['id']

    state['code'] = 503
    client.post(f'/api/services/{service_id}/check', headers=HEADERS)
    assert len(state['payloads']) == 1
    assert state['payloads'][0]['incident']['severity'] == 'critical'

    active = client.get('/api/incidents', headers=HEADERS, params={'status': 'active'}).json()
    resolved = client.post(f"/api/incidents/{active[0]['id']}/resolve", headers=HEADERS,
                           json={'note': 'manual resolve'})
    assert resolved.status_code == 200

    # A new incident inside the cooldown window must not page again.
    state['code'] = 200
    client.post(f'/api/services/{service_id}/check', headers=HEADERS)
    state['code'] = 503
    client.post(f'/api/services/{service_id}/check', headers=HEADERS)
    assert len(state['payloads']) == 1

    db.execute('UPDATE alerts SET cooldown_seconds = 0')
    active = client.get('/api/incidents', headers=HEADERS, params={'status': 'active'}).json()
    client.post(f"/api/incidents/{active[0]['id']}/resolve", headers=HEADERS, json={'note': 'reset'})
    state['code'] = 200
    client.post(f'/api/services/{service_id}/check', headers=HEADERS)
    state['code'] = 503
    client.post(f'/api/services/{service_id}/check', headers=HEADERS)
    assert len(state['payloads']) == 2


@requires_db
def test_connector_credentials_never_returned():
    created = client.post('/api/connectors', headers=HEADERS, json={
        'provider': 'github', 'name': 'GitHub', 'token': 'ghp_example_token_value',
    })
    assert created.status_code == 201, created.text
    listed = client.get('/api/connectors', headers=HEADERS)
    assert 'ghp_example_token_value' not in listed.text
    assert 'credentials' not in listed.text
    assert listed.json()[0]['status'] == 'connected'

    # Replacing the token rotates the sealed value without exposing either one.
    rotated = client.patch(f"/api/connectors/{created.json()['id']}", headers=HEADERS,
                           json={'token': 'ghp_rotated_token_value'})
    assert rotated.status_code == 200
    assert 'ghp_rotated_token_value' not in rotated.text
    stored = db.one('SELECT credentials FROM connectors WHERE id = %s', (created.json()['id'],))
    assert b'ghp_rotated_token_value' not in stored['credentials']
    assert store.secrets.open(stored['credentials']) == 'ghp_rotated_token_value'


@requires_db
def test_agent_ingest_requires_matching_token(allow_private):
    connector = client.post('/api/connectors', headers=HEADERS, json={
        'provider': 'docker', 'name': 'Local Docker', 'token': 'agent-token-1234567890',
    }).json()
    project = client.post('/api/projects', headers=HEADERS, json={
        'name': 'Local Stack',
        'services': [{'name': 'Local Worker', 'kind': 'worker', 'provider': 'docker',
                      'monitoring_enabled': True, 'health_url': None}],
    }).json()
    service_id = project['services'][0]['id']
    db.execute("UPDATE services SET connector_id = %s, external_ref = %s::jsonb WHERE id = %s",
               (connector['id'], json.dumps({'agentKey': 'local-worker'}), service_id))

    bad = client.post('/api/agent/observations', headers={'X-Agent-Token': 'wrong'},
                      json={'agent_key': 'local-worker', 'status': 'healthy'})
    assert bad.status_code == 401

    good = client.post('/api/agent/observations',
                       headers={'X-Agent-Token': 'agent-token-1234567890'},
                       json={'agent_key': 'local-worker', 'status': 'healthy', 'latency_ms': 4})
    assert good.status_code == 200
    assert good.json()['status'] == 'healthy'
    history = client.get(f'/api/services/{service_id}/observations', headers=HEADERS).json()
    assert history[0]['source'] == 'agent'


@requires_db
def test_migrations_are_idempotent():
    assert db.migrate() == []  # already applied; running again must be a no-op
    assert db.one('SELECT count(*) AS applied FROM schema_migrations')['applied'] >= 1


@requires_db
def test_connector_validation_failure_is_recorded(monkeypatch):
    from app.api_resources import RailwayConnector
    from app.connectors import ConnectorError

    created = client.post('/api/connectors', headers=HEADERS, json={
        'provider': 'railway', 'name': 'Railway broken', 'token': 'railway-token-value',
    }).json()

    async def reject(self):
        raise ConnectorError('Railway rejected the token (HTTP 401)')

    monkeypatch.setattr(RailwayConnector, 'validate', reject)
    response = client.post(f"/api/connectors/{created['id']}/validate", headers=HEADERS)
    assert response.status_code == 502
    assert 'rejected the token' in response.json()['detail']
    stored = db.one('SELECT status, last_error FROM connectors WHERE id = %s', (created['id'],))
    assert stored['status'] == 'error'
    assert 'rejected the token' in stored['last_error']


@requires_db
def test_login_attempts_are_rate_limited():
    from app.main import auth

    auth.limiter._hits.clear()
    statuses = [
        client.post('/api/session', json={'credential': 'definitely-wrong-password'}).status_code
        for _ in range(auth.limiter.limit + 2)
    ]
    assert statuses[0] == 401
    assert statuses[-1] == 429
    auth.limiter._hits.clear()


def test_execution_start_includes_task_domain_when_configured(monkeypatch):
    from unittest.mock import AsyncMock
    from app.main import engine, settings

    monkeypatch.setattr(settings, 'task_domain', 'production')
    mock = AsyncMock(return_value='00000000-0000-0000-0000-000000000000')
    monkeypatch.setattr(engine, 'request', mock)
    response = client.post('/api/executions', headers=HEADERS, json={
        'name': 'diagnostic_pipeline', 'service': 'checkout',
        'logs': 'ERROR timeout at database', 'severity': 'high',
    })
    assert response.status_code == 201
    body = mock.call_args.kwargs['json']
    assert body['taskToDomain'] == {'*': 'production, NO_DOMAIN'}

    monkeypatch.setattr(settings, 'task_domain', '')
    client.post('/api/executions', headers=HEADERS, json={
        'name': 'diagnostic_pipeline', 'service': 'checkout',
        'logs': 'ERROR timeout at database', 'severity': 'high',
    })
    assert 'taskToDomain' not in mock.call_args.kwargs['json']


def test_prometheus_summary_handles_missing_and_partial_series():
    from app.telemetry import parse_prometheus, summarise

    text = """
# HELP workflow_failure_total Failed workflows
workflow_failure_total{status="FAILED",workflowName="diagnostic_pipeline"} 2.0
workflow_failure_total{status="TERMINATED"} 1.0
workflow_start_success_total 9.0
task_execution_seconds_count{taskType="cp_publish_report"} 4.0
task_execution_seconds_sum{taskType="cp_publish_report"} 0.8
tasks_in_workflow 3.0
jvm_memory_used_bytes{area="heap",id="G1 Old Gen"} 1.048576E8
jvm_memory_max_bytes{area="heap",id="G1 Old Gen"} 5.24288E8
process_uptime_seconds 123.5
task_poll_total{taskType="cp_normalize_incident"} 7.0
task_poll_total{taskType="unrelated"} 99.0
"""
    summary = summarise(parse_prometheus(text), ['cp_normalize_incident', 'cp_publish_report'])
    assert summary['workflow_failures'] == {'FAILED': 2, 'TERMINATED': 1}
    assert summary['workflow_start_success'] == 9
    assert summary['tasks_in_flight'] == 3
    assert summary['task_execution_ms'] == 200.0
    assert summary['task_queue_wait_ms'] is None
    assert summary['heap_used_mb'] == 100.0
    assert summary['heap_max_mb'] == 500.0
    assert summary['task_poll_total'] == {'cp_normalize_incident': 7}
    assert summary['uptime_seconds'] == 123.5
