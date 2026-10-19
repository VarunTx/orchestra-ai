from unittest.mock import AsyncMock
from uuid import uuid4
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app, engine, settings
from app.engine import Engine

client = TestClient(app)
HEADERS = {'Authorization': f'Bearer {settings.control_plane_token}'}
PAYLOAD = {'name':'diagnostic_pipeline', 'service':'checkout', 'logs':'ERROR timeout at database', 'severity':'high'}


def test_auth_and_health():
    assert client.get('/healthz').status_code == 200
    assert client.get('/api/workflows').status_code == 401
    assert client.post('/api/executions', json=PAYLOAD).status_code == 401


def test_validation():
    for overrides in ({'name':'arbitrary'}, {'logs':'short'}, {'delay_seconds':31}, {'extra':'no'}, {'severity':'unknown'}):
        assert client.post('/api/executions', headers=HEADERS, json=PAYLOAD | overrides).status_code == 422


def test_start_delegates_to_engine(monkeypatch):
    mock = AsyncMock(return_value=str(uuid4()))
    monkeypatch.setattr(engine, 'request', mock)
    response = client.post('/api/executions', headers=HEADERS, json=PAYLOAD)
    assert response.status_code == 201
    assert mock.call_args.args == ('POST', 'workflow')
    assert mock.call_args.kwargs['json']['input']['service'] == 'checkout'


def test_gemini_disabled():
    assert client.post('/api/executions', headers=HEADERS, json=PAYLOAD | {'name':'incident_analysis'}).status_code == 409


def test_retry_terminal_guard(monkeypatch):
    mock = AsyncMock(return_value={'workflowName':'diagnostic_pipeline','status':'COMPLETED'})
    monkeypatch.setattr(engine,'request',mock)
    assert client.post(f'/api/executions/{uuid4()}/retry',headers=HEADERS).status_code == 409
    assert mock.call_count == 1


def test_workflow_ownership(monkeypatch):
    monkeypatch.setattr(engine,'request',AsyncMock(return_value={'workflowName':'other','status':'RUNNING'}))
    assert client.get(f'/api/executions/{uuid4()}',headers=HEADERS).status_code == 404


def test_infra_reports_unknown_not_healthy(monkeypatch):
    monkeypatch.setattr(engine,'request',AsyncMock(side_effect=HTTPException(503,'down')))
    result=client.get('/api/infrastructure',headers=HEADERS).json()
    assert result['engine']['status'] == 'unavailable'
    assert all(w['status']=='unavailable' for w in result['workers'])


def test_transport_retries_reads_only():
    import asyncio
    async def run():
        for method, expected in [('GET',3),('POST',1)]:
            e=Engine('http://engine/api'); count=0
            def fail(req):
                nonlocal count
                count+=1
                raise httpx.ConnectError('unreachable',request=req)
            await e.client.aclose()
            e.client=httpx.AsyncClient(base_url='http://engine/api/',transport=httpx.MockTransport(fail))
            with pytest.raises(HTTPException) as exc:
                await e.request(method,'workflow')
            assert exc.value.status_code==503
            assert count==expected
            await e.close()
    asyncio.run(run())
