"""Tests for the MCP façade. No engine, database or network is used."""
import asyncio
import json

import httpx
import pytest

from app.mcp_server import (
    TOOLS,
    UNTRUSTED_NOTICE,
    BearerMiddleware,
    ControlPlane,
    ControlPlaneError,
    build_http_app,
    build_server,
)

TOKEN = 'test-token-0123456789abcdef0123456789'
SEEN: list[httpx.Request] = []


def make(handler, *, token: str = TOKEN) -> ControlPlane:
    def recording(request: httpx.Request) -> httpx.Response:
        SEEN.append(request)
        return handler(request)

    return ControlPlane('http://api.test', token=token,
                        transport=httpx.MockTransport(recording))


def json_response(payload, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


@pytest.fixture(autouse=True)
def _reset() -> None:
    SEEN.clear()


def test_list_executions_returns_whitelisted_summary_only() -> None:
    control = make(lambda r: json_response({
        'totalHits': 1,
        'results': [{
            'workflowId': 'w-1', 'workflowType': 'diagnostic_pipeline',
            'status': 'COMPLETED', 'input': 'A' * 5000, 'credential': 'leak-me',
            'tasks': [{'taskType': 'cp_diagnose_incident'}],
        }],
    }))
    result = control.list_executions(size=5)

    assert result['totalHits'] == 1
    row = result['executions'][0]
    assert row['workflowId'] == 'w-1'
    assert 'credential' not in row
    assert 'input' not in row and 'tasks' not in row


def test_list_executions_bounds_size_and_rejects_unknown_status() -> None:
    control = make(lambda r: json_response({'results': [], 'totalHits': 0}))
    control.list_executions(size=500)
    assert SEEN[-1].url.params['size'] == '25'

    with pytest.raises(ValueError):
        control.list_executions(status='WHATEVER')


def test_bearer_token_is_sent_but_never_echoed() -> None:
    control = make(lambda r: json_response({'results': [], 'totalHits': 0}))
    result = control.list_executions()
    assert SEEN[-1].headers['authorization'] == f'Bearer {TOKEN}'
    assert TOKEN not in json.dumps(result)


def test_missing_token_is_reported_not_guessed() -> None:
    control = make(lambda r: json_response({}), token='')
    with pytest.raises(Exception, match='token'):
        control.list_projects()
    assert SEEN == []


def test_get_execution_marks_payload_untrusted_and_clips_text() -> None:
    long_logs = 'ERROR timeout\n' * 1000
    control = make(lambda r: json_response({
        'workflowId': 'w-1', 'workflowType': 'diagnostic_pipeline', 'status': 'FAILED',
        'tasks': [{'taskType': 'cp_diagnose_incident', 'status': 'FAILED', 'retryCount': 1,
                   'inputData': {'logs': long_logs}, 'outputData': {'note': 'x' * 9000}}],
    }))
    result = control.get_execution('7f1f3e6c-1111-4222-8333-444455556666')

    assert result['untrusted'] is True
    assert result['notice'] == UNTRUSTED_NOTICE
    task = result['tasks'][0]
    assert task['retryCount'] == 1
    assert len(task['inputData']['logs']) < len(long_logs)
    assert len(task['outputData']['note']) < 9000


@pytest.mark.parametrize('call', [
    lambda c: c.get_execution('not-a-uuid'),
    lambda c: c.get_incident('nope'),
    lambda c: c.get_project('nope'),
    lambda c: c.create_service('nope', 'svc'),
    lambda c: c.retry_execution('nope'),
    lambda c: c.terminate_execution('nope'),
])
def test_identifiers_are_validated(call) -> None:
    control = make(lambda r: json_response({}))
    with pytest.raises(ValueError):
        call(control)
    assert SEEN == []


def test_get_incident_wraps_evidence_and_counts_observations() -> None:
    control = make(lambda r: json_response({
        'id': '7f1f3e6c-1111-4222-8333-444455556666', 'status': 'open',
        'severity': 'high', 'title': 'Cache down',
        'events': [{'id': 'e1', 'kind': 'opened', 'message': 'm'}],
        'observations': [{'id': 1}, {'id': 2}],
        'notifications': [{'secret': 'x'}],
    }))
    result = control.get_incident('7f1f3e6c-1111-4222-8333-444455556666')

    assert result['untrusted'] is True
    assert result['incident']['title'] == 'Cache down'
    assert result['observations'] == 2
    assert 'notifications' not in result


def test_infrastructure_health_summarises_real_states() -> None:
    control = make(lambda r: json_response({
        'observedAt': '2026-10-31T00:00:00Z',
        'storage': {'status': 'connected'},
        'engine': {'status': 'connected', 'telemetry': {'available': True}},
        'api': {'status': 'up'},
        'workers': [{'name': f'w{i}', 'status': 'polling'} for i in range(4)],
        'gemini': {'status': 'disabled', 'apiKey': 'leak-me'},
    }))
    result = control.infrastructure_health()

    assert result['storage'] == 'connected'
    assert result['engineTelemetry'] is True
    assert result['workersPolling'] == 4
    assert result['gemini'] == 'disabled'
    assert 'apiKey' not in json.dumps(result)


def test_create_cluster_posts_whitelisted_body() -> None:
    control = make(lambda r: json_response(
        {'id': 'c-1', 'name': 'Payments', 'kind': 'logical', 'internal': 'x'}, 201))
    result = control.create_cluster('Payments', description='billing')

    body = json.loads(SEEN[-1].content)
    assert body == {'name': 'Payments', 'kind': 'logical', 'description': 'billing'}
    assert result == {'cluster': {'id': 'c-1', 'name': 'Payments', 'kind': 'logical'}}


def test_create_cluster_rejects_unknown_kind() -> None:
    control = make(lambda r: json_response({}, 201))
    with pytest.raises(ValueError):
        control.create_cluster('Payments', kind='cluster')
    assert SEEN == []


def test_create_service_requires_real_uuid_and_sends_health_url() -> None:
    control = make(lambda r: json_response({'id': 's-1', 'name': 'api', 'current_status': 'unknown'}, 201))
    control.create_service('7f1f3e6c-1111-4222-8333-444455556666', 'api',
                           health_url='https://example.com/health')

    body = json.loads(SEEN[-1].content)
    assert body['project_id'] == '7f1f3e6c-1111-4222-8333-444455556666'
    assert body['health_url'] == 'https://example.com/health'


def test_retry_and_terminate_hit_the_engine_routes() -> None:
    control = make(lambda r: json_response({}))
    wid = '7f1f3e6c-1111-4222-8333-444455556666'
    control.retry_execution(wid)
    assert SEEN[-1].url.path == f'/api/executions/{wid}/retry'
    control.terminate_execution(wid)
    assert SEEN[-1].url.path == f'/api/executions/{wid}/terminate'


def test_audit_listing_passes_a_bounded_limit() -> None:
    control = make(lambda r: json_response([{'id': 1, 'actor': 'token:claude',
                                             'action': 'cluster.create', 'detail': {}}]))
    result = control.list_audit(limit=500)
    assert SEEN[-1].url.params['limit'] == '50'
    assert result['entries'][0]['actor'] == 'token:claude'


def test_upstream_failure_is_bounded_and_hides_details() -> None:
    control = make(lambda r: json_response({'detail': 'engine unavailable'}, 503))
    with pytest.raises(ControlPlaneError) as excinfo:
        control.list_executions()
    message = str(excinfo.value)
    assert '503' in message and 'engine unavailable' in message


def test_unreachable_api_is_reported_not_invented() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused', request=request)

    control = make(boom)
    with pytest.raises(ControlPlaneError, match='unreachable'):
        control.infrastructure_health()


def test_server_registers_the_documented_tools() -> None:
    control = make(lambda r: json_response({}))
    names = {tool.name for tool in asyncio.run(build_server(control).list_tools())}
    assert names == set(TOOLS)
    assert {'create_cluster', 'create_project', 'start_diagnostic'} <= names


def test_http_middleware_rejects_missing_or_wrong_token() -> None:
    calls: list[str] = []

    async def inner(scope, receive, send):
        calls.append(scope['path'])
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'{}'})

    guard = BearerMiddleware(inner, expected='client-secret')

    def run(headers):
        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(guard({'type': 'http', 'path': '/mcp', 'headers': headers},
                          None, send))
        return sent[0]['status'], sent

    assert run([])[0] == 401
    assert run([(b'authorization', b'Bearer wrong')])[0] == 401
    assert run([(b'authorization', b'Bearer client-secret')])[0] == 200
    assert calls == ['/mcp']


def test_http_healthz_is_public() -> None:
    from starlette.testclient import TestClient

    control = make(lambda r: json_response({}))
    app = build_http_app(build_server(control), 'client-secret')

    response = TestClient(app).get('/healthz')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
