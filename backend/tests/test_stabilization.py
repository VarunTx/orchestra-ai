from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from test_lifecycle import client, OWNER, seed, assign, SHA, reset
from app.main import db, engine
from conftest import requires_db

@requires_db
def test_draft_can_be_saved_and_edited_without_runner():
    pid = client.post('/api/projects', headers=OWNER, json={'name': 'Generic repository', 'repo_url': 'https://github.com/example/repo'}).json()['id']
    response = client.post(f'/api/projects/{pid}/work', headers=OWNER, json={'title': 'Draft change', 'request': 'Update the documentation', 'acceptance': 'Documentation builds cleanly'})
    assert response.status_code == 201
    wid = response.json()['id']
    assert client.patch(f'/api/work/{wid}', headers=OWNER, json={'title': 'Edited draft'}).status_code == 200
    assert client.post(f'/api/work/{wid}/start', headers=OWNER).status_code == 409

@requires_db
def test_identical_evidence_redelivery_preserves_approval(monkeypatch):
    _, pair, request = seed()
    _, _, headers = assign(request, pair)
    monkeypatch.setattr(engine, 'request', AsyncMock(return_value={'status': 'COMPLETED'}))
    payload = {'work_id': request['id'], 'data': {'head_sha': SHA, 'tests_passed': True, 'dirty': False}}
    assert client.post('/api/runner/artifacts', headers=headers, json=payload).status_code == 200
    assert client.post(f"/api/work/{request['id']}/approve", headers=OWNER, json={'sha': SHA, 'approve_publication': True}).status_code == 200
    assert client.post('/api/runner/artifacts', headers=headers, json=payload).status_code == 200
    assert db.one('SELECT approved_sha FROM project_work WHERE id = %s', (request['id'],))['approved_sha'] == SHA

@requires_db
def test_history_filters_unowned_runs_before_pagination(monkeypatch):
    known, orphan = str(uuid4()), str(uuid4())
    pid, _, work = seed()
    db.execute('UPDATE project_work SET workflow_id = %s WHERE id = %s', (known, work['id']))
    async def request(method, path, **kwargs):
        if path == 'workflow/search':
            return {'totalHits': 2, 'results': [{'workflowId': orphan, 'workflowType': 'project_change'}, {'workflowId': known, 'workflowType': 'project_change'}]}
        return {'workflowId': known, 'workflowName': 'project_change', 'status': 'COMPLETED'}
    monkeypatch.setattr(engine, 'request', request)
    result = client.get('/api/executions?size=1', headers=OWNER).json()
    assert result['totalHits'] == 1
    assert result['results'][0]['workflowId'] == known
    assert client.get(f'/api/executions/{known}', headers=OWNER).status_code == 200
    client.delete(f'/api/projects/{pid}', headers=OWNER)
    assert client.get(f'/api/executions/{known}', headers=OWNER).status_code == 200

@requires_db
def test_stale_status_is_exclusive_and_last_known_preserved():
    pid, _, _ = seed()
    service = db.one('SELECT id FROM services WHERE project_id=%s LIMIT 1', (pid,))['id']
    db.execute("UPDATE services SET current_status='healthy',last_checked_at=now()-interval '1 hour' WHERE id=%s", (service,))
    from app.main import store
    s = store.get_service(service)
    assert s['current_status'] == 'unknown'
    assert s['last_known_status'] == 'healthy'
    assert s['evidence_state'] == 'stale'
    p = store.get_project(pid)
    assert p['healthy_count'] == 0
    assert p['unknown_count'] == 2

@requires_db
def test_public_github_connection_requires_explicit_project_scope(monkeypatch):
    from app.connectors import GitHubConnector, ProviderSnapshot
    monkeypatch.setattr(GitHubConnector, '_get', AsyncMock(return_value={}))
    monkeypatch.setattr(GitHubConnector, 'collect_repo', AsyncMock(return_value=ProviderSnapshot(notes='public read')))
    pid, _, _ = seed()
    other = client.post('/api/projects', headers=OWNER, json={'name':'Other repo','repo_url':'https://github.com/example/other'}).json()['id']
    response = client.post('/api/connectors', headers=OWNER, json={'provider':'github','name':'Public GitHub','project_ids':[pid]})
    assert response.status_code == 201
    connector = response.json()['id']
    assert client.post(f'/api/connectors/{connector}/validate', headers=OWNER).status_code == 200
    assert client.post(f'/api/connectors/{connector}/sync', headers=OWNER).status_code == 200
    GitHubConnector.collect_repo.assert_awaited_once_with('https://github.com/example/lifecycle-fixture')

@requires_db
def test_preflight_fails_before_reserving_run(monkeypatch):
    _, pair, request = seed()
    db.execute("UPDATE project_runners SET diagnostics='{}'::jsonb WHERE id=%s", (pair['id'],))
    mock = AsyncMock()
    monkeypatch.setattr(engine,'request',mock)
    response=client.post(f"/api/work/{request['id']}/start", headers=OWNER)
    assert response.status_code == 409
    assert not db.one('SELECT active FROM project_work WHERE id=%s',(request['id'],))['active']
    mock.assert_not_awaited()

@requires_db
def test_publication_is_separate_approved_conductor_task(monkeypatch):
    pid,pair,request=seed()
    assign(request,pair)
    wid=str(uuid4())
    db.execute("UPDATE project_work SET active=false,approved_sha=%s,publish_approved=true,artifacts=%s::jsonb WHERE id=%s",(SHA,'{"head_sha":"'+SHA+'","tests_passed":true,"dirty":false}',request['id']))
    mock=AsyncMock(return_value=wid)
    monkeypatch.setattr(engine,'request',mock)
    response=client.post(f"/api/work/{request['id']}/publish", headers=OWNER)
    assert response.status_code == 201
    assert mock.call_args.kwargs['json']['name']=='project_publication'
    assert mock.call_args.kwargs['json']['input']['sha']==SHA
    assert client.post(f"/api/work/{request['id']}/publish",headers=OWNER).status_code==409
    assert mock.call_count==1

@requires_db
def test_local_webhook_receiver_and_outage_recovery(monkeypatch):
    import asyncio, json, threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from app.main import store, settings
    from app.monitor import check_service
    from app.api_resources import ConnectorIn
    events=[]
    class Receiver(BaseHTTPRequestHandler):
        code=200
        def log_message(self,*args): pass
        def do_GET(self):
            self.send_response(type(self).code);self.end_headers();self.wfile.write(json.dumps({'sha':SHA}).encode() if self.path=='/version' else b'local synthetic health')
        def do_POST(self):
            events.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(204);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Receiver)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(settings,'http_check_allow_private',True)
    pid,_,_=seed()
    base=f'http://127.0.0.1:{server.server_port}'
    service=store.create_service({'project_id':pid,'name':'Synthetic receiver','kind':'api','health_url':base,'failure_threshold':1,'recovery_threshold':1})
    store.create_alert({'name':'Local receiver','target':base,'project_id':pid,'min_severity':'minor','cooldown_seconds':0})
    try:
        from app.lifecycle import version_probe
        assert asyncio.run(version_probe(base+'/version',SHA,True))['status']=='matched'
        assert asyncio.run(version_probe(base+'/version','b'*40,True))['status']=='mismatch'
        Receiver.code=503
        assert asyncio.run(version_probe(base+'/version',SHA,True))['status']=='unknown'
        Receiver.code=200
        assert asyncio.run(check_service(store,settings,store.get_service(service['id'])))['service']['current_status']=='healthy'
        Receiver.code=503
        assert asyncio.run(check_service(store,settings,store.get_service(service['id'])))['service']['current_status']=='down'
        assert len(events)==1 and events[0]['event']=='incident.opened'
        deliveries=client.get('/api/notifications',headers=OWNER)
        assert deliveries.status_code==200 and deliveries.json()[0]['status']=='sent'
        Receiver.code=200
        asyncio.run(check_service(store,settings,store.get_service(service['id'])))
        assert not store.list_incidents(project_id=pid,status='active')
    finally:server.shutdown();server.server_close();thread.join(timeout=2)

@requires_db
def test_permitted_definition_can_run_and_unknown_inputs_cannot(monkeypatch):
    from app.definitions import workflow
    definition=workflow('manual_verified',False)
    db.execute('INSERT INTO registered_definitions(name,version) VALUES (%s,1) ON CONFLICT DO NOTHING',('manual_verified',))
    async def request(method,path,**kwargs):
        if method=='GET':return definition
        return str(uuid4())
    monkeypatch.setattr(engine,'request',request)
    path='/api/workflows/definitions/manual_verified/1/run'
    inputs={'service':'Synthetic','severity':'low','logs':'Local safe diagnostic','failure_mode':'none','delay_seconds':0}
    assert client.post(path,headers=OWNER,json={'inputs':inputs}).status_code==201
    assert client.post(path,headers=OWNER,json={'inputs':{**inputs,'unexpected':'x'}}).status_code==422
    assert client.post('/api/workflows/definitions/project_change/1/run',headers=OWNER,json={'inputs':{}}).status_code==404
    definition['tasks'][1]['name']='cp_analyze_incident'
    assert client.post(path,headers=OWNER,json={'inputs':inputs}).status_code==409

@requires_db
def test_definition_rejects_undeclared_and_forward_references(monkeypatch):
    from app.definitions import workflow
    definition=workflow('invalid_refs',False)
    definition['tasks'][0]['inputParameters']['logs']='${workflow.secrets.api_key}'
    assert client.post('/api/workflows/definitions',headers=OWNER,json={'definition':definition}).status_code==422
    definition['tasks'][0]['inputParameters']['logs']='${report.output}'
    assert client.post('/api/workflows/definitions',headers=OWNER,json={'definition':definition}).status_code==422

@requires_db
def test_late_coding_completion_cannot_release_publication_reservation(monkeypatch):
    _,pair,request=seed()
    workflow,task,headers=assign(request,pair)
    db.execute("UPDATE project_work SET publication_submission='submitted',publication_workflow_id=%s WHERE id=%s",(str(uuid4()),request['id']))
    monkeypatch.setattr(engine,'request',AsyncMock(return_value={'status':'COMPLETED'}))
    response=client.post('/api/runner/conductor/tasks',headers=headers,json={'taskId':task,'workflowInstanceId':workflow,'status':'COMPLETED'})
    assert response.status_code==200
    assert db.one('SELECT active FROM project_work WHERE id=%s',(request['id'],))['active']

@requires_db
def test_verification_label_preserves_project_provenance(monkeypatch):
    pid,pair,request=seed()
    workflow,_,_=assign(request,pair)
    monkeypatch.setattr(engine,'request',AsyncMock(return_value={'workflowId':workflow,'workflowName':'project_change','status':'COMPLETED'}))
    path=f'/api/executions/{workflow}/record-kind'
    assert client.patch(path,json={'record_kind':'verification'}).status_code==401
    assert client.patch(path,headers=OWNER,json={'record_kind':'verification'}).status_code==200
    link=db.one('SELECT * FROM execution_links WHERE workflow_id=%s',(workflow,))
    assert str(link['project_id'])==pid and link['record_kind']=='verification'
    assert client.delete(f'/api/projects/{pid}',headers=OWNER).status_code==409

@requires_db
def test_uncertain_publication_reconciliation_restores_durable_association(monkeypatch):
    from fastapi import HTTPException
    pid,pair,request=seed()
    assign(request,pair)
    db.execute("UPDATE projects SET record_kind='verification' WHERE id=%s",(pid,))
    db.execute("UPDATE project_work SET active=false,approved_sha=%s,publish_approved=true,artifacts=%s::jsonb WHERE id=%s",(SHA,'{"head_sha":"'+SHA+'"}',request['id']))
    monkeypatch.setattr(engine,'request',AsyncMock(side_effect=HTTPException(503,'Lost scheduling acknowledgement')))
    assert client.post(f"/api/work/{request['id']}/publish",headers=OWNER).status_code==503
    workflow=str(uuid4())
    monkeypatch.setattr(engine,'request',AsyncMock(return_value=[{'workflowId':workflow}]))
    assert client.post(f"/api/work/{request['id']}/publication/reconcile",headers=OWNER).status_code==200
    association=db.one('SELECT * FROM execution_links WHERE workflow_id=%s',(workflow,))
    assert association and str(association['project_id'])==pid and association['record_kind']=='verification'
