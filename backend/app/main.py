import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .api_resources import build_router
from .auth import Auth
from .db import Database, iso
from .definitions import TASK_DEFS, TASK_NAMES, WORKFLOWS, WORKFLOW_NAMES
from .engine import Engine
from .monitor import Collector
from .security import SecretBox
from .settings import Settings
from .store import Store

settings = Settings()
engine = Engine(settings.conductor_url)
db = Database(settings)
secrets = SecretBox.from_settings(settings)
store = Store(db, settings, secrets)
auth = Auth(settings, db, store)


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')


@asynccontextmanager
async def lifespan(app):
    db.initialize()
    store.seed_defaults()
    collector = None
    if settings.monitor_enabled:
        collector = Collector(store, settings)
        app.state.collector_task = asyncio.create_task(collector.run())
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
    if collector is not None:
        collector.stop()
        try:
            await asyncio.wait_for(app.state.collector_task, timeout=10)
        except asyncio.TimeoutError:
            app.state.collector_task.cancel()
    await engine.close()
    db.close()


app = FastAPI(title='Orchestra AI', version='2.0.0', lifespan=lifespan)
app.include_router(build_router(settings, store, auth, engine))
owner = Depends(auth.require)


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.get('/healthz')
async def healthz():
    return {'status': 'up'}


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    credential: str = Field(min_length=8, max_length=500)


@app.post('/api/session')
async def login(body: LoginRequest, request: Request):
    """Exchange the owner password or master API token for an opaque session token."""
    client = request.client.host if request.client else 'unknown'
    if not auth.limiter.allow(client):
        raise HTTPException(429, 'Too many sign-in attempts. Wait a minute and retry.')
    credential = body.credential
    method = None
    if auth.master_ok(credential):
        method = 'api-token'
    elif auth.password_ok(credential):
        method = 'password'
    if not method:
        raise HTTPException(401, 'Invalid password or API token')
    raw, expires = auth.issue_session(request.headers.get('user-agent', ''))
    return {'authenticated': True, 'method': method, 'session_token': raw,
            'expires_at': iso(expires)}


@app.get('/api/session', dependencies=[owner])
async def session():
    return {'authenticated': True}


@app.delete('/api/session')
async def logout(authorization: str = Header(default='')):
    if authorization.startswith('Bearer '):
        try:
            auth.revoke_session(authorization.removeprefix('Bearer '))
        except Exception:
            pass
    return {'authenticated': False}


@app.get('/api/workflows', dependencies=[owner])
async def workflows():
    definitions = await engine.request('GET', 'metadata/workflow')
    return [d for d in definitions if d['name'] in WORKFLOW_NAMES]


@app.get('/api/workflows/catalog', dependencies=[owner])
async def workflow_catalog():
    """Every definition the engine knows about, with version and task shape."""
    definitions = await engine.request('GET', 'metadata/workflow')
    catalog = []
    for definition in definitions or []:
        tasks = definition.get('tasks') or []
        catalog.append({
            'name': definition.get('name'),
            'version': definition.get('version'),
            'description': definition.get('description', ''),
            'schema_version': definition.get('schemaVersion'),
            'owner_email': definition.get('ownerEmail'),
            'timeout_seconds': definition.get('timeoutSeconds'),
            'managed': definition.get('name') in WORKFLOW_NAMES,
            'task_count': len(tasks),
            'task_types': sorted({t.get('type', 'SIMPLE') for t in tasks}),
            'tasks': tasks,
        })
    return sorted(catalog, key=lambda d: (d['name'] or '', d['version'] or 0))


@app.get('/api/schedules', dependencies=[owner])
async def schedules():
    """Read-only view of Conductor's scheduler (no schedule is created here)."""
    try:
        return await engine.request('GET', 'scheduler/schedules')
    except HTTPException as exc:
        raise HTTPException(503, 'Scheduler API is unavailable on this Conductor build') from exc


class StartRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: Literal['incident_analysis', 'diagnostic_pipeline']
    service: str = Field(min_length=1, max_length=100, pattern=r'^[\w .:/-]+$')
    severity: Literal['critical', 'high', 'medium', 'low'] = 'medium'
    logs: str = Field(min_length=10, max_length=20000)
    failure_mode: Literal['none', 'once', 'always'] = 'none'
    delay_seconds: int = Field(default=0, ge=0, le=30)


@app.post('/api/executions', status_code=201, dependencies=[owner])
async def start(body: StartRequest):
    if body.name == 'incident_analysis':
        if not settings.enable_gemini or not settings.gemini_api_key:
            raise HTTPException(409, 'Gemini is disabled or its API key is missing. Configure .env and restart API/workers.')
        if body.failure_mode != 'none' or body.delay_seconds:
            raise HTTPException(422, 'Failure injection is only available for diagnostics')
    wid = await engine.request('POST', 'workflow', json={
        'name': body.name, 'version': 1, 'input': body.model_dump(exclude={'name'})})
    store.audit('owner', 'workflow.start', 'workflow', wid, {'name': body.name})
    return {'workflowId': wid}


@app.get('/api/executions', dependencies=[owner])
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


@app.get('/api/executions/{wid}', dependencies=[owner])
async def execution(wid: UUID):
    return await owned_execution(wid)


@app.post('/api/executions/{wid}/retry', dependencies=[owner])
async def retry(wid: UUID):
    data = await owned_execution(wid)
    if data['status'] not in ('FAILED', 'TIMED_OUT'):
        raise HTTPException(409, 'Only failed or timed-out executions can be retried')
    await engine.request('POST', f'workflow/{wid}/retry')
    store.audit('owner', 'workflow.retry', 'workflow', wid)
    return {'workflowId': str(wid)}


@app.post('/api/executions/{wid}/terminate', dependencies=[owner])
async def terminate(wid: UUID):
    data = await owned_execution(wid)
    if data['status'] not in ('RUNNING', 'PAUSED'):
        raise HTTPException(409, 'Execution is already terminal')
    await engine.request('DELETE', f'workflow/{wid}', params={'reason': 'Terminated by control-plane operator'})
    store.audit('owner', 'workflow.terminate', 'workflow', wid)
    return {'workflowId': str(wid)}


@app.get('/api/infrastructure', dependencies=[owner])
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
    try:
        started = time.monotonic()
        db.one('SELECT 1 AS ok')
        storage = {'type': 'PostgreSQL', 'status': 'connected',
                   'latencyMs': round((time.monotonic() - started) * 1000)}
    except Exception:
        storage = {'type': 'PostgreSQL', 'status': 'unavailable', 'latencyMs': None}
    return {'observedAt': now, 'engine': {'status': 'connected' if connected else 'unavailable', 'latencyMs': latency},
            'api': {'status': 'up'}, 'workers': workers,
            'gemini': {'configured': bool(settings.gemini_api_key), 'enabled': settings.enable_gemini, 'model': settings.gemini_model,
                       'status': 'configured' if settings.enable_gemini and settings.gemini_api_key else 'disabled'},
            'storage': storage}
