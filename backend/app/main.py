import asyncio
import hmac
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from .definitions import TASK_DEFS, TASK_NAMES, WORKFLOWS, WORKFLOW_NAMES
from .engine import Engine
from .settings import Settings

settings = Settings()
engine = Engine(settings.conductor_url)


@asynccontextmanager
async def lifespan(app):
    # Startup must fail if definitions cannot be installed; Compose can restart safely.
    deadline = time.monotonic() + 180
    while True:
        try:
            # Metadata registration is idempotent; tolerate cloud dependency startup order.
            await engine.request('POST', 'metadata/taskdefs', json=TASK_DEFS)
            await engine.request('PUT', 'metadata/workflow', json=WORKFLOWS)
            break
        except HTTPException as exc:
            if exc.status_code not in (502, 503) or time.monotonic() >= deadline:
                raise
            await asyncio.sleep(3)
    yield
    await engine.close()


app = FastAPI(title='Orchestra AI', version='1.0.0', lifespan=lifespan)


def authorize(authorization: str = Header(default='')):
    token = authorization.removeprefix('Bearer ')
    if not authorization.startswith('Bearer ') or not hmac.compare_digest(token, settings.control_plane_token):
        raise HTTPException(401, 'A valid control-plane token is required', headers={'WWW-Authenticate': 'Bearer'})


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get('/healthz')
async def healthz():
    return {'status': 'up'}


@app.get('/api/session', dependencies=[Depends(authorize)])
async def session():
    return {'authenticated': True}


@app.get('/api/workflows', dependencies=[Depends(authorize)])
async def workflows():
    definitions = await engine.request('GET', 'metadata/workflow')
    return [d for d in definitions if d['name'] in WORKFLOW_NAMES]


class StartRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: Literal['incident_analysis', 'diagnostic_pipeline']
    service: str = Field(min_length=1, max_length=100, pattern=r'^[\w .:/-]+$')
    severity: Literal['critical', 'high', 'medium', 'low'] = 'medium'
    logs: str = Field(min_length=10, max_length=20000)
    failure_mode: Literal['none', 'once', 'always'] = 'none'
    delay_seconds: int = Field(default=0, ge=0, le=30)


@app.post('/api/executions', status_code=201, dependencies=[Depends(authorize)])
async def start(body: StartRequest):
    if body.name == 'incident_analysis':
        if not settings.enable_gemini or not settings.gemini_api_key:
            raise HTTPException(409, 'Gemini is disabled or its API key is missing. Configure .env and restart API/workers.')
        if body.failure_mode != 'none' or body.delay_seconds:
            raise HTTPException(422, 'Failure injection is only available for diagnostics')
    wid = await engine.request('POST', 'workflow', json={
        'name': body.name, 'version': 1, 'input': body.model_dump(exclude={'name'})})
    return {'workflowId': wid}


@app.get('/api/executions', dependencies=[Depends(authorize)])
async def executions(start: int = Query(0, ge=0), size: int = Query(20, ge=1, le=100),
                     status: Literal['ALL', 'RUNNING', 'COMPLETED', 'FAILED', 'TIMED_OUT', 'TERMINATED', 'PAUSED'] = 'ALL'):
    query = 'workflowType IN (incident_analysis,diagnostic_pipeline)'
    if status != 'ALL':
        query += ' AND status=' + status
    return await engine.request('GET', 'workflow/search', params={
        'start': start, 'size': size, 'sort': 'startTime:DESC', 'freeText': '*', 'query': query})


async def owned_execution(wid: UUID):
    data = await engine.request('GET', f'workflow/{wid}', params={'includeTasks': 'true'})
    if data.get('workflowName', data.get('workflowType')) not in WORKFLOW_NAMES:
        raise HTTPException(404, 'Execution not found')
    return data


@app.get('/api/executions/{wid}', dependencies=[Depends(authorize)])
async def execution(wid: UUID):
    return await owned_execution(wid)


@app.post('/api/executions/{wid}/retry', dependencies=[Depends(authorize)])
async def retry(wid: UUID):
    data = await owned_execution(wid)
    if data['status'] not in ('FAILED', 'TIMED_OUT'):
        raise HTTPException(409, 'Only failed or timed-out executions can be retried')
    await engine.request('POST', f'workflow/{wid}/retry')
    return {'workflowId': str(wid)}


@app.post('/api/executions/{wid}/terminate', dependencies=[Depends(authorize)])
async def terminate(wid: UUID):
    data = await owned_execution(wid)
    if data['status'] not in ('RUNNING', 'PAUSED'):
        raise HTTPException(409, 'Execution is already terminal')
    await engine.request('DELETE', f'workflow/{wid}', params={'reason': 'Terminated by control-plane operator'})
    return {'workflowId': str(wid)}


@app.get('/api/infrastructure', dependencies=[Depends(authorize)])
async def infrastructure():
    now = int(time.time() * 1000)
    started = time.monotonic()
    try:
        await engine.request('GET', 'metadata/taskdefs')
        latency = round((time.monotonic() - started) * 1000)
        connected = True
    except HTTPException:
        latency, connected = None, False
    try:
        polls = await engine.request('GET', 'tasks/queue/polldata/all') if connected else []
        workers = []
        for name in TASK_NAMES:
            matching = [p for p in polls if p.get('queueName') == name]
            last = max((p.get('lastPollTime', 0) for p in matching), default=0)
            workers.append({'name': name, 'status': 'polling' if last and now - last < 60000 else 'unavailable',
                            'lastPollTime': last or None, 'pollers': matching})
    except HTTPException:
        workers = [{'name': n, 'status': 'unknown', 'lastPollTime': None, 'pollers': []} for n in TASK_NAMES]
    return {'observedAt': now, 'engine': {'status': 'connected' if connected else 'unavailable', 'latencyMs': latency},
            'api': {'status': 'up'}, 'workers': workers,
            'gemini': {'configured': bool(settings.gemini_api_key), 'enabled': settings.enable_gemini, 'model': settings.gemini_model,
                       'status': 'configured' if settings.enable_gemini and settings.gemini_api_key else 'disabled'},
            'storage': {'type': 'PostgreSQL', 'status': 'not independently probed'}}
