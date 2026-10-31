"""Tests for the read-only MCP façade. No engine, database or network is used."""
import asyncio
import json

import httpx
import pytest

from app.mcp_server import (
    UNTRUSTED_NOTICE,
    ControlPlane,
    ControlPlaneError,
    build_client,
    build_server,
)

TOKEN = 'test-token-0123456789abcdef0123456789'
SEEN: list[httpx.Request] = []


def make(handler, *, writes: bool = False) -> ControlPlane:
    def recording(request: httpx.Request) -> httpx.Response:
        SEEN.append(request)
        return handler(request)

    client = build_client(TOKEN, 'http://api.test', httpx.MockTransport(recording))
    return ControlPlane(client, writes_enabled=writes)


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


def test_get_execution_rejects_non_uuid() -> None:
    control = make(lambda r: json_response({}))
    with pytest.raises(ValueError):
        control.get_execution('not-a-uuid')


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


def test_write_tools_are_disabled_unless_enabled() -> None:
    control = make(lambda r: json_response({}))
    with pytest.raises(PermissionError):
        control.start_diagnostic('svc', 'x' * 20)
    with pytest.raises(PermissionError):
        control.acknowledge_incident('7f1f3e6c-1111-4222-8333-444455556666')
    assert SEEN == []


def test_start_diagnostic_is_bounded_and_never_paid() -> None:
    control = make(lambda r: json_response({'workflowId': 'w-2'}, 201), writes=True)
    result = control.start_diagnostic('cache-service', 'ERROR connection refused', 'high')

    body = json.loads(SEEN[-1].content)
    assert body['name'] == 'diagnostic_pipeline'
    assert body['record_kind'] == 'verification'
    assert body['failure_mode'] == 'none'
    assert 'incident_analysis' not in json.dumps(body)
    assert result == {'workflowId': 'w-2', 'started': 'diagnostic_pipeline'}


@pytest.mark.parametrize('service,logs,severity', [
    ('', 'x' * 20, 'high'),
    ('bad\nname', 'x' * 20, 'high'),
    ('svc', 'short', 'high'),
    ('svc', 'x' * 20, 'urgent'),
])
def test_start_diagnostic_validates_input(service: str, logs: str, severity: str) -> None:
    control = make(lambda r: json_response({}, 201), writes=True)
    with pytest.raises(ValueError):
        control.start_diagnostic(service, logs, severity)
    assert SEEN == []


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


def test_server_registers_read_tools_and_opt_in_writes() -> None:
    control = make(lambda r: json_response({}))
    names = {tool.name for tool in asyncio.run(build_server(control).list_tools())}

    assert {'list_executions', 'get_execution', 'list_incidents', 'get_incident',
            'infrastructure_health', 'list_workflow_definitions'} <= names
    assert {'start_diagnostic', 'acknowledge_incident'} <= names
