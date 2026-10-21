"""Project work and release evidence; Conductor owns all execution state."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from .security import resolve_public, UnsafeTarget
from .store import serialize

CODE_TASK = 'cp_project_code'
CODE_WORKFLOW = 'project_change'
PUBLISH_TASK = 'cp_project_publish'
PUBLISH_WORKFLOW = 'project_publication'
SHA = r'^[a-f0-9]{40}$'
TERMINAL = {'COMPLETED', 'FAILED', 'TIMED_OUT', 'TERMINATED'}


def lifecycle_definitions():
    # One attempt: ambiguous model sessions must be reconciled, never automatically repeated.
    task = dict(name=CODE_TASK, retryCount=0, timeoutSeconds=86400,
                responseTimeoutSeconds=120, timeoutPolicy='TIME_OUT_WF', ownerEmail='operator@conductor.local')
    workflow = dict(name=CODE_WORKFLOW, version=1, schemaVersion=2, restartable=False,
                    timeoutPolicy='TIME_OUT_WF', timeoutSeconds=86400,
                    ownerEmail='operator@conductor.local', inputParameters=['work_id', 'project_id'],
                    tasks=[dict(name=CODE_TASK, taskReferenceName='code', type='SIMPLE',
                                inputParameters={'work_id': '${workflow.input.work_id}',
                                                 'project_id': '${workflow.input.project_id}'})],
                    outputParameters={'result': '${code.output}'})
    return task, workflow


def publication_definitions():
    task, flow = lifecycle_definitions()
    task = {**task, 'name': PUBLISH_TASK, 'timeoutSeconds': 600}
    flow = {**flow, 'name': PUBLISH_WORKFLOW, 'timeoutSeconds': 600,
            'inputParameters': ['work_id','project_id','sha'],
            'tasks': [{'name':PUBLISH_TASK,'taskReferenceName':'publish','type':'SIMPLE',
                       'inputParameters': {'work_id':'${workflow.input.work_id}','sha':'${workflow.input.sha}'}}],
            'outputParameters': {'result':'${publish.output}'}}
    return task, flow


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def redact(value):
    """Defense in depth; never upload raw session transcripts or environment values."""
    if isinstance(value, dict):
        return {k: ('[redacted]' if re.search(r'token|password|secret|api.?key|authorization', k, re.I)
                    else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)(bearer\s+)[^\s"\']+', r'\1[redacted]', value)
        value = re.sub(r'(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,"\']+',
                       r'\1[redacted]', value)
        return value[:20000]
    return value


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Pair(Input):
    name: str = Field(min_length=1, max_length=80)


class Work(Input):
    runner_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=120)
    request: str = Field(min_length=10, max_length=10000)
    acceptance: str = Field(min_length=10, max_length=5000)
    model_approved: bool = False
    model_budget_seconds: int = Field(default=600,ge=30,le=3600)


class WorkPatch(Input):
    runner_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    request: str | None = Field(default=None, min_length=10, max_length=10000)
    acceptance: str | None = Field(default=None, min_length=10, max_length=5000)
    model_approved: bool | None = None
    model_budget_seconds: int | None = Field(default=None,ge=30,le=3600)


class DiagnosticCheck(Input):
    name: str = Field(max_length=80)
    ok: bool
    detail: str = Field(max_length=300)


class Preflight(Input):
    checks: list[DiagnosticCheck] = Field(min_length=1,max_length=20)
    publication_ready: bool = False


class Approval(Input):
    sha: str = Field(pattern=SHA)
    approve_publication: bool = False


class Release(Input):
    expected_sha: str = Field(pattern=SHA)


class RunnerResult(Input):
    taskId: uuid.UUID
    workflowInstanceId: uuid.UUID
    status: str = Field(pattern=r'^(IN_PROGRESS|COMPLETED|FAILED)$')
    outputData: dict = Field(default_factory=dict)
    workerId: str | None = None
    extendLease: bool = False
    callbackAfterSeconds: int = Field(default=0, ge=0, le=60)
    reasonForIncompletion: str | None = Field(default=None, max_length=500)


class Artifacts(Input):
    work_id: uuid.UUID
    data: dict


class Publication(Input):
    work_id: uuid.UUID
    sha: str = Field(pattern=SHA)
    pr_url: str | None = Field(default=None, max_length=400)
    state: str = Field(pattern=r'^(publishing|published|unknown|failed)$')


async def version_probe(url: str, expected: str, allow_private=False):
    """Small read-only request, same SSRF policy as health checks. No redirects."""
    try:
        target = resolve_public(url, allow_private=allow_private)
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            async with client.stream('GET', target) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 4096:
                        return {'status': 'unknown', 'reason': 'version response too large'}
                if response.status_code != 200:
                    return {'status': 'unknown', 'reason': f'HTTP {response.status_code}'}
                sha = json.loads(body).get('sha')
                if not isinstance(sha, str) or not re.fullmatch(SHA, sha):
                    return {'status': 'unknown', 'reason': 'no valid build SHA'}
                return {'status': 'matched' if sha == expected else 'mismatch', 'observed_sha': sha}
    except (UnsafeTarget, httpx.HTTPError, ValueError, AttributeError):
        return {'status': 'unknown', 'reason': 'version evidence unavailable'}


def build_lifecycle_router(store, auth, engine):
    router = APIRouter(prefix='/api')
    owner = Depends(auth.require)
    db = store.db

    def project(pid):
        row = db.one('SELECT * FROM projects WHERE id = %s', (pid,))
        if not row:
            raise HTTPException(404, 'Project not found')
        return row

    def work(wid):
        row = db.one('SELECT * FROM project_work WHERE id = %s', (wid,))
        if not row:
            raise HTTPException(404, 'Work request not found')
        return row

    async def runner(x_runner_token: str = Header(default='')):
        row = db.one('SELECT * FROM project_runners WHERE token_hash = %s AND revoked_at IS NULL',
                     (digest(x_runner_token),))
        if not row:
            raise HTTPException(401, 'A paired runner token is required')
        db.execute('UPDATE project_runners SET last_seen_at = now() WHERE id = %s', (row['id'],))
        return row

    def scoped(wid, paired):
        row = work(wid)
        if row['runner_id'] != paired['id'] or row['project_id'] != paired['project_id']:
            raise HTTPException(404, 'Work request not found')
        return row

    def require_preflight(row, publication=False):
        paired = db.one('SELECT * FROM project_runners WHERE id=%s AND revoked_at IS NULL', (row['runner_id'],))
        diagnostic = paired['diagnostics'] if paired else {}
        now = datetime.now(timezone.utc)
        try:
            fresh = (now - datetime.fromisoformat(diagnostic['checked_at'])).total_seconds() < 120
        except (KeyError, ValueError, TypeError):
            fresh = False
        if not fresh or not diagnostic.get('ready') or (publication and not diagnostic.get('publication_ready')):
            raise HTTPException(409, 'Laptop setup needed: connect the paired companion and fix its preflight checks before starting')

    @router.get('/runner/profile')
    async def runner_profile(paired=Depends(runner)):
        p = project(paired['project_id'])
        return {'project_id':str(p['id']),'repo_url':p['repo_url'],'repo_branch':p['repo_branch'] or 'main'}

    @router.post('/runner/preflight')
    async def preflight(body: Preflight, paired=Depends(runner)):
        diagnostic = {'checks': [c.model_dump() for c in body.checks],
                      'ready': all(c.ok for c in body.checks), 'publication_ready': body.publication_ready,
                      'checked_at':datetime.now(timezone.utc).isoformat()}
        db.execute('UPDATE project_runners SET diagnostics=%s WHERE id=%s', (Jsonb(redact(diagnostic)),paired['id']))
        return diagnostic

    @router.get('/projects/{pid}/lifecycle', dependencies=[owner])
    async def lifecycle(pid: uuid.UUID):
        p = project(pid)
        requests = db.query('SELECT * FROM project_work WHERE project_id = %s ORDER BY created_at DESC LIMIT 50', (pid,))
        for row in requests:
            row['execution'] = {'status': 'UNAVAILABLE' if row['workflow_id'] else 'NOT_STARTED'}
            if row['workflow_id']:
                try:
                    execution = await engine.request('GET', f"workflow/{row['workflow_id']}", params={'includeTasks': 'false'})
                    row['execution'] = {'status': execution['status']}
                    if execution['status'] in TERMINAL and not row['task_id'] and row['publication_submission']=='draft':
                        db.execute('UPDATE project_work SET active = false WHERE id = %s', (row['id'],))
                        row['active'] = False
                except HTTPException:
                    pass
        for row in requests:
            row['publication_execution']={'status':'NOT_STARTED'}
            if row['publication_workflow_id']:
                try:
                    pub = await engine.request('GET',f"workflow/{row['publication_workflow_id']}",params={'includeTasks':'false'})
                    row['publication_execution']={'status':pub['status']}
                    if pub['status'] in TERMINAL and not row['publication_task_id']:
                        db.execute('UPDATE project_work SET active=false WHERE id=%s',(row['id'],))
                        row['active']=False
                except HTTPException:
                    row['publication_execution']={'status':'UNAVAILABLE'}
        runners = db.query('SELECT id,name,last_seen_at,revoked_at,diagnostics FROM project_runners WHERE project_id = %s ORDER BY created_at', (pid,))
        for row in runners:
            row['connection'] = ('revoked' if row['revoked_at'] else 'online' if row['last_seen_at'] and
                                 (datetime.now(timezone.utc) - row['last_seen_at']).total_seconds() < 45 else 'offline')
        services = store.list_services(project_id=str(pid))
        connections = db.query('SELECT c.id,c.provider,c.status,c.last_error,pc.evidence,pc.checked_at FROM project_connections pc JOIN connectors c ON c.id=pc.connector_id WHERE pc.project_id=%s',(pid,))
        github = [c for c in connections if c['provider']=='github']
        capabilities = {
          'monitoring': {'ready':any(s['monitoring_enabled'] and (s['health_url'] or s['connector_id']) for s in services),'detail':'Add services and public health URLs; observations may still be unknown','setup_url':f'/projects/{pid}#services'},
          'github': {'ready':any(c['status']=='connected' and c['checked_at'] for c in github),'detail':next((c['last_error'] for c in github if c['last_error']),None) or 'Connect this project under Integrations, then validate and sync','setup_url':'/integrations'},
          'coding': {'ready':any(r['connection']=='online' and r['diagnostics'].get('ready') for r in runners),'detail':'Pair the companion and resolve preflight checks; every request needs separate model approval','setup_url':f'/projects/{pid}?tab=Work'},
          'releases': {'ready':bool(services) and all((s['external_ref'] or {}).get('version_url') for s in services),'detail':'Configure each version endpoint, then compare expected commit and readiness','setup_url':f'/projects/{pid}?tab=Health'}}
        return {'capabilities':capabilities,'connections':[serialize(c) for c in connections], 'management': p['management'], 'services': [serialize(s) for s in db.query('SELECT id,name,external_ref FROM services WHERE project_id = %s', (pid,))], 'work': [serialize(r) for r in requests],
                'runners': [serialize(r) for r in runners],
                'ci': [serialize(r) for r in db.query("SELECT * FROM deployments WHERE project_id = %s AND evidence_kind = 'ci' ORDER BY deployed_at DESC LIMIT 30", (pid,))],
                'releases': [serialize(r) for r in db.query('SELECT * FROM project_releases WHERE project_id = %s ORDER BY created_at DESC LIMIT 30', (pid,))]}

    @router.post('/projects/{pid}/runners', dependencies=[owner])
    async def pair(pid: uuid.UUID, body: Pair):
        project(pid)
        token = secrets.token_urlsafe(40)
        rid = uuid.uuid4()
        db.execute('INSERT INTO project_runners(id,project_id,name,token_hash) VALUES (%s,%s,%s,%s)',
                   (rid, pid, body.name, digest(token)))
        store.audit('owner', 'runner.pair', 'project', pid, {'runner_id': str(rid)})
        return {'id': str(rid), 'token': token}

    @router.delete('/projects/{pid}/runners/{rid}', dependencies=[owner])
    async def revoke(pid: uuid.UUID, rid: uuid.UUID):
        db.execute('UPDATE project_runners SET revoked_at = now() WHERE id = %s AND project_id = %s', (rid, pid))
        store.audit('owner', 'runner.revoke', 'project', pid, {'runner_id': str(rid)})
        return {'revoked': True}

    @router.post('/projects/{pid}/work', dependencies=[owner], status_code=201)
    async def create_work(pid: uuid.UUID, body: Work):
        p = project(pid)
        if not p['repo_url']:
            raise HTTPException(409, 'Link a repository first')
        if body.runner_id and not db.one('SELECT id FROM project_runners WHERE id = %s AND project_id = %s AND revoked_at IS NULL', (body.runner_id, pid)):
            raise HTTPException(422, 'Choose a paired runner for this project')
        wid = uuid.uuid4()
        row = db.one('INSERT INTO project_work(id,project_id,runner_id,title,request,acceptance,model_approved,model_budget_seconds)'
                     ' VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                     (wid, pid, body.runner_id, body.title, body.request, body.acceptance, body.model_approved, body.model_budget_seconds))
        store.audit('owner', 'work.create', 'project', pid, {'work_id': str(wid), 'model_approved': body.model_approved})
        return serialize(row)

    @router.patch('/work/{wid}', dependencies=[owner])
    async def edit_work(wid: uuid.UUID, body: WorkPatch):
        row = work(wid)
        if row['submission'] != 'draft':
            raise HTTPException(409, 'Only a draft can be edited; create a follow-up request')
        values = body.model_dump(exclude_unset=True)
        if values.get('runner_id') and not db.one('SELECT id FROM project_runners WHERE id=%s AND project_id=%s AND revoked_at IS NULL', (values['runner_id'], row['project_id'])):
            raise HTTPException(422, 'Choose a paired runner for this project')
        if any(v is None and k != 'runner_id' for k,v in values.items()):
            raise HTTPException(422, 'Draft fields cannot be null')
        if values:
            changed=db.execute('UPDATE project_work SET ' + ','.join(k + '=%s' for k in values) + ",updated_at=now() WHERE id=%s AND submission='draft'", (*values.values(), wid))
            if not changed:
                raise HTTPException(409,'The request has started; create a follow-up draft')
        return serialize(work(wid))

    @router.get('/work/{wid}', dependencies=[owner])
    async def inspect_work(wid: uuid.UUID):
        row = work(wid)
        execution = await engine.request('GET', f"workflow/{row['workflow_id']}", params={'includeTasks': 'true'}) if row['workflow_id'] else None
        return {**serialize(row), 'execution': execution}

    @router.post('/work/{wid}/start', dependencies=[owner])
    async def start(wid: uuid.UUID):
        row = work(wid)
        if not row['model_approved']:
            raise HTTPException(409, 'Approve model usage when creating this request before starting')
        require_preflight(row)
        # Reserve before calling Conductor. An ambiguous start remains reserved for reconciliation.
        with db.transaction() as conn:
            conn.execute('SELECT id FROM projects WHERE id = %s FOR UPDATE', (row['project_id'],))
            row = conn.execute('SELECT * FROM project_work WHERE id = %s FOR UPDATE', (wid,)).fetchone()
            if row['submission'] != 'draft':
                return {'submission': row['submission'], 'workflow_id': row['workflow_id']}
            if not row['model_approved']:
                raise HTTPException(409,'Model approval was withdrawn; review this draft again')
            require_preflight(row)
            if conn.execute('SELECT id FROM project_work WHERE project_id = %s AND active', (row['project_id'],)).fetchone():
                raise HTTPException(409, 'Another run is active; reconcile it first')
            if not conn.execute('SELECT id FROM project_runners WHERE id = %s AND revoked_at IS NULL', (row['runner_id'],)).fetchone():
                raise HTTPException(409, 'Runner revoked')
            conn.execute("UPDATE project_work SET submission = 'uncertain', active = true WHERE id = %s", (wid,))
        workflow_id = await engine.request('POST', 'workflow', json={
            'name': CODE_WORKFLOW, 'version': 1, 'correlationId': str(wid),
            'taskToDomain': {CODE_TASK: str(row['runner_id'])},
            'input': {'work_id': str(wid), 'project_id': str(row['project_id'])}})
        db.execute("UPDATE project_work SET workflow_id = %s, submission = 'submitted' WHERE id = %s", (workflow_id, wid))
        store.audit('owner', 'work.start', 'project', row['project_id'], {'work_id': str(wid)})
        return {'workflow_id': workflow_id}

    @router.post('/work/{wid}/reconcile', dependencies=[owner])
    async def reconcile(wid: uuid.UUID):
        row = work(wid)
        if not row['workflow_id'] and row['submission'] == 'uncertain':
            executions = await engine.request('GET', f'workflow/{CODE_WORKFLOW}/correlated/{wid}', params={'includeClosed': 'true', 'includeTasks': 'false'})
            if len(executions or []) != 1:
                raise HTTPException(409, 'Start outcome remains unknown; no automatic resubmission is allowed')
            db.execute("UPDATE project_work SET workflow_id = %s, submission = 'submitted' WHERE id = %s",
                       (executions[0]['workflowId'], wid))
        return serialize(work(wid))

    @router.post('/work/{wid}/publish', dependencies=[owner], status_code=201)
    async def request_publication(wid: uuid.UUID):
        row = work(wid)
        require_preflight(row, publication=True)
        with db.transaction() as conn:
            conn.execute('SELECT id FROM projects WHERE id=%s FOR UPDATE', (row['project_id'],))
            row = conn.execute('SELECT * FROM project_work WHERE id=%s FOR UPDATE', (wid,)).fetchone()
            if not row['publish_approved'] or row['approved_sha'] != row['artifacts'].get('head_sha') or not row['approved_sha']:
                raise HTTPException(409, 'Approve the exact reviewed commit before publication')
            if row['publication_submission'] != 'draft' or row['publication'].get('state'):
                raise HTTPException(409, 'Publication already requested; reconcile its outcome before any new write')
            if conn.execute('SELECT id FROM project_work WHERE project_id=%s AND active', (row['project_id'],)).fetchone():
                raise HTTPException(409, 'Another project task is active')
            conn.execute("UPDATE project_work SET publication_submission='uncertain',active=true WHERE id=%s", (wid,))
        workflow_id = await engine.request('POST','workflow',json={
            'name':PUBLISH_WORKFLOW,'version':1,'correlationId':'publication:'+str(wid),
            'taskToDomain':{PUBLISH_TASK:str(row['runner_id'])},
            'input':{'work_id':str(wid),'project_id':str(row['project_id']),'sha':row['approved_sha']}})
        db.execute("UPDATE project_work SET publication_workflow_id=%s,publication_submission='submitted' WHERE id=%s", (workflow_id,wid))
        store.audit('owner','publication.request','project',row['project_id'],{'work_id':str(wid),'sha':row['approved_sha']})
        return {'workflow_id':workflow_id}

    @router.post('/work/{wid}/publication/reconcile', dependencies=[owner])
    async def reconcile_publication(wid: uuid.UUID):
        row = work(wid)
        if row['publication_submission'] == 'uncertain' and not row['publication_workflow_id']:
            runs = await engine.request('GET',f'workflow/{PUBLISH_WORKFLOW}/correlated/publication:{wid}',params={'includeClosed':'true','includeTasks':'false'})
            if len(runs or []) != 1:
                raise HTTPException(409, 'Publication scheduling remains uncertain; no automatic resubmission')
            db.execute("UPDATE project_work SET publication_workflow_id=%s,publication_submission='submitted' WHERE id=%s",(runs[0]['workflowId'],wid))
        return serialize(work(wid))

    @router.post('/work/{wid}/publication/cancel', dependencies=[owner])
    async def cancel_publication(wid: uuid.UUID):
        row=work(wid)
        if not row['publication_workflow_id']:
            raise HTTPException(409,'Reconcile publication scheduling before cancelling')
        execution=await engine.request('GET',f"workflow/{row['publication_workflow_id']}",params={'includeTasks':'false'})
        if execution['status'] not in TERMINAL:
            await engine.request('DELETE',f"workflow/{row['publication_workflow_id']}",params={'reason':'Owner cancelled publication; any uncertain GitHub write must be reconciled'})
        db.execute("UPDATE project_work SET publication_submission='cancelled',active=%s WHERE id=%s",(bool(row['publication_task_id']),wid))
        return {'cancelled':True,'detail':'A write already sent to GitHub may have succeeded; the companion must reconcile it'}

    @router.post('/work/{wid}/cancel', dependencies=[owner])
    async def cancel(wid: uuid.UUID):
        row = work(wid)
        if row['publication_submission'] != 'draft':
            raise HTTPException(409,'Use the publication cancellation control for this request')
        if not row['workflow_id']:
            if row['submission'] == 'uncertain':
                raise HTTPException(409, 'Reconcile the uncertain start before cancelling')
            db.execute("UPDATE project_work SET submission = 'cancelled', active = false WHERE id = %s", (wid,))
        else:
            execution = await engine.request('GET', f"workflow/{row['workflow_id']}", params={'includeTasks': 'false'})
            if execution['status'] not in TERMINAL:
                await engine.request('DELETE', f"workflow/{row['workflow_id']}", params={'reason': 'Owner cancelled project work'})
            # Keep reservation until runner acknowledges stopping, or no task was delivered.
            db.execute("UPDATE project_work SET submission = 'cancelled', active = %s, approved_sha = NULL, publish_approved = false WHERE id = %s",
                       (bool(row['task_id']), wid))
        store.audit('owner', 'work.cancel', 'project', row['project_id'], {'work_id': str(wid)})
        return {'cancelled': True}

    @router.post('/work/{wid}/approve', dependencies=[owner])
    async def approve(wid: uuid.UUID, body: Approval):
        snapshot = work(wid)
        execution = await engine.request('GET', f"workflow/{snapshot['workflow_id']}", params={'includeTasks':'false'}) if snapshot['workflow_id'] else {}
        if execution.get('status') != 'COMPLETED':
            raise HTTPException(409, 'Coding workflow must complete before approval')
        with db.transaction() as conn:
            row = conn.execute('SELECT * FROM project_work WHERE id = %s FOR UPDATE', (wid,)).fetchone()
            if not row: raise HTTPException(404, 'Work request not found')
            if row['publication_submission'] != 'draft':
                raise HTTPException(409,'Publication has started; this review is frozen')
            artifacts = row['artifacts']
            if artifacts.get('head_sha') != body.sha or not artifacts.get('tests_passed') or artifacts.get('dirty', True):
                raise HTTPException(409, 'Approval requires the exact clean commit and passing test evidence')
            conn.execute('UPDATE project_work SET approved_sha = %s, approved_at = now(), publish_approved = %s WHERE id = %s',
                       (body.sha, body.approve_publication, wid))
        store.audit('owner', 'work.approve', 'project', row['project_id'], {'sha': body.sha, 'publication': body.approve_publication})
        return {'approved_sha': body.sha, 'publication_approved': body.approve_publication}

    @router.post('/work/{wid}/reject', dependencies=[owner])
    async def reject(wid: uuid.UUID):
        row = work(wid)
        if row['publication_submission'] != 'draft':
            raise HTTPException(409,'Publication has already started; reconcile its outcome before further changes')
        changed=db.execute("UPDATE project_work SET approved_sha = NULL, approved_at = NULL, publish_approved = false, submission = 'changes_requested' WHERE id = %s AND publication_submission='draft'", (wid,))
        if not changed:
            raise HTTPException(409,'Publication has started; this review is frozen')
        store.audit('owner', 'work.reject', 'project', row['project_id'], {'work_id': str(wid)})
        return {'decision': 'changes_requested'}

    @router.post('/projects/{pid}/releases', dependencies=[owner], status_code=201)
    async def release(pid: uuid.UUID, body: Release):
        project(pid)
        return serialize(db.one('INSERT INTO project_releases(id,project_id,expected_sha) VALUES (%s,%s,%s) RETURNING *',
                                (uuid.uuid4(), pid, body.expected_sha)))

    @router.post('/releases/{rid}/verify', dependencies=[owner])
    async def verify(rid: uuid.UUID):
        release = db.one('SELECT * FROM project_releases WHERE id = %s', (rid,))
        if not release:
            raise HTTPException(404, 'Release not found')
        services = db.query('SELECT * FROM services WHERE project_id = %s', (release['project_id'],))
        from .connectors import probe_http
        evidence = []
        for service in services:
            ref = service['external_ref']
            version = await version_probe(ref['version_url'], release['expected_sha'], store.settings.http_check_allow_private) if ref.get('version_url') else {'status': 'unknown'}
            ready = await probe_http(ref.get('readiness_url') or service['health_url'], timeout=5,
                                     expected_status=200, allow_private=store.settings.http_check_allow_private) if (ref.get('readiness_url') or service['health_url']) else None
            evidence.append({'service_id': str(service['id']), 'service': service['name'],
                             'version': version, 'readiness': ready.status if ready else 'unknown'})
        verified = bool(evidence) and all(e['version']['status'] == 'matched' and e['readiness'] == 'healthy' for e in evidence)
        result = {'status': 'verified' if verified else 'unverified', 'services': evidence,
                  'checked_at': datetime.now(timezone.utc).isoformat()}
        db.execute('UPDATE project_releases SET evidence = %s, checked_at = now() WHERE id = %s', (Jsonb(result), rid))
        store.audit('owner', 'release.verify', 'project', release['project_id'], {'release_id': str(rid), 'status': result['status']})
        return result

    @router.get('/runner/work/{wid}')
    async def runner_work(wid: uuid.UUID, paired=Depends(runner)):
        row = scoped(wid, paired)
        p = project(row['project_id'])
        execution = await engine.request('GET', f"workflow/{row['workflow_id']}", params={'includeTasks': 'false'}) if row['workflow_id'] else {}
        publication_execution = await engine.request('GET',f"workflow/{row['publication_workflow_id']}",params={'includeTasks':'false'}) if row['publication_workflow_id'] else {}
        return {**serialize(row),'publication_execution_status':publication_execution.get('status','NOT_STARTED'), 'repo_url': p['repo_url'], 'repo_branch': p['repo_branch'] or 'main',
                'execution_status': execution.get('status', 'UNKNOWN')}

    @router.post('/runner/artifacts')
    async def artifacts(body: Artifacts, paired=Depends(runner)):
        row = scoped(body.work_id, paired)
        safe = redact(body.data)
        if len(json.dumps(safe)) > 100000:
            raise HTTPException(413, 'Evidence too large')
        # Identical at-least-once delivery preserves review; changed evidence invalidates it.
        if json.dumps(row['artifacts'],sort_keys=True) == json.dumps(safe,sort_keys=True):
            return {'recorded': True}
        if row['publication_submission'] != 'draft':
            raise HTTPException(409, 'Publication has started; review evidence is frozen')
        changed = db.execute("UPDATE project_work SET artifacts=%s,approved_sha=NULL,approved_at=NULL,publish_approved=false,updated_at=now() WHERE id=%s AND artifacts IS DISTINCT FROM %s AND publication_submission='draft'", (Jsonb(safe),row['id'],Jsonb(safe)))
        if not changed and work(row['id'])['artifacts'] != safe:
            raise HTTPException(409,'Evidence changed concurrently or publication has started')
        return {'recorded': True}

    @router.post('/runner/stopped/{wid}')
    async def stopped(wid: uuid.UUID, paired=Depends(runner)):
        row = scoped(wid, paired)
        execution = await engine.request('GET', f"workflow/{row['workflow_id']}", params={'includeTasks': 'false'})
        if execution['status'] not in TERMINAL:
            raise HTTPException(409, 'Execution is not terminal')
        db.execute("UPDATE project_work SET active = false WHERE id = %s AND publication_submission='draft'", (wid,))
        return {'stopped': True}

    @router.post('/runner/publication/stopped/{wid}')
    async def publication_stopped(wid: uuid.UUID, paired=Depends(runner)):
        row=scoped(wid,paired)
        if not row['publication_workflow_id']:
            raise HTTPException(409,'No publication execution')
        run=await engine.request('GET',f"workflow/{row['publication_workflow_id']}",params={'includeTasks':'false'})
        if run['status'] not in TERMINAL:
            raise HTTPException(409,'Publication is still running')
        db.execute('UPDATE project_work SET active=false WHERE id=%s',(wid,))
        return {'stopped':True}

    @router.post('/runner/publication')
    async def publication(body: Publication, paired=Depends(runner)):
        row = scoped(body.work_id, paired)
        if row['approved_sha'] != body.sha or not row['publish_approved']:
            raise HTTPException(409, 'Publication is not approved for this commit')
        if body.state == 'publishing' and row['publication_submission'] == 'cancelled':
            raise HTTPException(409,'Publication cancelled; only read-only reconciliation is allowed')
        if body.state == 'published' and not body.pr_url:
            raise HTTPException(422,'A published result requires its GitHub PR URL')
        if row['publication'].get('state') == 'published' and body.state != 'published':
            return {'recorded':True,'state':'published'}
        if body.pr_url:
            repo = project(row['project_id'])['repo_url'].removesuffix('.git').replace('git@github.com:', 'https://github.com/')
            if not re.fullmatch(re.escape(repo) + r'/pull/[0-9]+', body.pr_url):
                raise HTTPException(422, 'PR must belong to the managed repository')
        db.execute('UPDATE project_work SET publication = %s WHERE id = %s',
                   (Jsonb(body.model_dump(mode='json', exclude={'work_id'})), row['id']))
        return {'recorded': True}

    # These two SDK-compatible paths deliberately proxy only the assigned project queue/task.
    @router.get('/runner/conductor/tasks/poll/{task_type}')
    async def poll(task_type: str, paired=Depends(runner)):
        if task_type not in {CODE_TASK, PUBLISH_TASK}:
            raise HTTPException(404, 'Task type not available')
        task = await engine.request('GET', f'tasks/poll/{task_type}', params={'workerid': str(paired['id']), 'domain': str(paired['id'])})
        if task:
            row = scoped(uuid.UUID(task['inputData']['work_id']), paired)
            field = 'workflow_id' if task_type == CODE_TASK else 'publication_workflow_id'
            if str(task['workflowInstanceId']) != row[field]:
                raise HTTPException(409, 'Execution mismatch')
            column = 'task_id' if task_type == CODE_TASK else 'publication_task_id'
            db.execute(f'UPDATE project_work SET {column} = %s WHERE id = %s', (task['taskId'], row['id']))
        return task

    @router.post('/runner/conductor/tasks')
    async def task_update(body: RunnerResult, paired=Depends(runner)):
        row = db.one('SELECT * FROM project_work WHERE (task_id = %s OR publication_task_id = %s) AND runner_id = %s AND project_id = %s',
                     (str(body.taskId),str(body.taskId), paired['id'], paired['project_id']))
        expected = (row['publication_workflow_id'] if row and row['publication_task_id'] == str(body.taskId) else row['workflow_id'] if row else None)
        if not row or str(body.workflowInstanceId) != expected:
            raise HTTPException(404, 'Task not found')
        payload = body.model_dump(mode='json')
        payload['workerId'] = str(paired['id'])
        payload['outputData'] = redact(payload['outputData'])
        if len(json.dumps(payload)) > 100000:
            raise HTTPException(413, 'Result too large')
        result = await engine.request('POST', 'tasks', json=payload)
        if body.status in {'COMPLETED', 'FAILED'}:
            db.execute("UPDATE project_work SET active=false WHERE id=%s AND (publication_task_id=%s OR publication_submission='draft')",(row['id'],str(body.taskId)))
        return result

    return router
