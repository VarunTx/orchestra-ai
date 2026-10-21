"""Opt-in local Conductor contract test. No agent/model execution or cloud mutation."""
import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from conductor.client.http.api_client import ApiClient
from conductor.client.http.models.task_result import TaskResult
from app.main import app, settings, db

pytestmark = pytest.mark.skipif(os.environ.get('ORCHESTRA_ENGINE_TEST') != 'true', reason='set ORCHESTRA_ENGINE_TEST=true against local Compose only')


def test_real_project_work_queue_completion_and_cancellation(monkeypatch):
    assert settings.conductor_url.startswith('http://conductor:'), 'local Compose only'
    monkeypatch.setattr(settings, 'monitor_enabled', False)
    owner = {'Authorization': 'Bearer ' + settings.control_plane_token}
    with TestClient(app) as client:
        project = client.post('/api/projects', headers=owner, json={'name': 'Local contract ' + str(uuid4())[:8],
                              'repo_url': 'https://github.com/VarunTx/aws_hackathon'}).json()
        pid = project['id']
        pair = client.post(f'/api/projects/{pid}/runners', headers=owner, json={'name': 'deterministic test worker'}).json()
        runner = {'X-Runner-Token': pair['token']}
        assert client.post('/api/runner/preflight',headers=runner,json={'checks':[{'name':'Synthetic local contract','ok':True,'detail':'No model calls'}],'publication_ready':True}).status_code==200
        def create():
            return client.post(f'/api/projects/{pid}/work', headers=owner, json={
                'runner_id': pair['id'], 'title': 'Local contract only', 'request': 'Test the real Conductor queue',
                'acceptance': 'No model calls, complete task through SDK contract', 'model_approved': True}).json()
        request = create()
        start = client.post(f"/api/work/{request['id']}/start", headers=owner)
        assert start.status_code == 200, start.text
        workflow = start.json()['workflow_id']
        # Simulate a lost start response and reconcile through the real correlation endpoint.
        db.execute("UPDATE project_work SET workflow_id = NULL, submission = 'uncertain' WHERE id = %s", (request['id'],))
        reconciled = client.post(f"/api/work/{request['id']}/reconcile", headers=owner)
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()['workflow_id'] == workflow
        try:
            task = None
            for _ in range(30):
                response = client.get('/api/runner/conductor/tasks/poll/cp_project_code', headers=runner)
                assert response.status_code == 200, response.text
                task = response.json()
                if task:
                    break
                time.sleep(.2)
            assert task and task['workflowInstanceId'] == workflow
            def update(status):
                payload = ApiClient().sanitize_for_serialization(TaskResult(
                    workflow_instance_id=task['workflowInstanceId'], task_id=task['taskId'], status=status,
                    output_data={'contract_test': True}, callback_after_seconds=0))
                result = client.post('/api/runner/conductor/tasks', headers=runner, json=payload)
                assert result.status_code == 200, result.text
            update('IN_PROGRESS')
            update('COMPLETED')
            for _ in range(30):
                result = client.get(f"/api/work/{request['id']}", headers=owner).json()
                if result['execution']['status'] == 'COMPLETED':
                    break
                time.sleep(.2)
            assert result['execution']['status'] == 'COMPLETED'
            sha='a'*40
            assert client.post('/api/runner/artifacts',headers=runner,json={'work_id':request['id'],'data':{'head_sha':sha,'tests_passed':True,'dirty':False}}).status_code==200
            assert client.post(f"/api/work/{request['id']}/approve",headers=owner,json={'sha':sha,'approve_publication':True}).status_code==200
            published=client.post(f"/api/work/{request['id']}/publish",headers=owner)
            assert published.status_code==201,published.text
            db.execute("UPDATE project_work SET publication_workflow_id=NULL,publication_submission='uncertain' WHERE id=%s",(request['id'],))
            reconciled_publication=client.post(f"/api/work/{request['id']}/publication/reconcile",headers=owner)
            assert reconciled_publication.status_code==200,reconciled_publication.text
            assert reconciled_publication.json()['publication_workflow_id']==published.json()['workflow_id']
            for _ in range(30):
                task=client.get('/api/runner/conductor/tasks/poll/cp_project_publish',headers=runner).json()
                if task:break
                time.sleep(.2)
            assert task['inputData']['sha']==sha
            assert task['workflowInstanceId']==published.json()['workflow_id']
            update('COMPLETED')  # Synthetic queue completion; no git or GitHub write.
            cancelled = create()
            assert client.post(f"/api/work/{cancelled['id']}/start", headers=owner).status_code == 200
            assert client.post(f"/api/work/{cancelled['id']}/cancel", headers=owner).status_code == 200
            assert client.get(f"/api/work/{cancelled['id']}", headers=owner).json()['execution']['status'] == 'TERMINATED'
        finally:
            client.delete(f'/api/projects/{pid}', headers=owner)
