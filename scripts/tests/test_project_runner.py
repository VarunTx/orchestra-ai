"""Deterministic runner tests. The fake agent never contacts any model/provider."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import os
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location('project_runner', Path(__file__).parents[1] / 'project_runner.py')
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)


def local_runner(tmp_path):
    runner = runner_module.Runner.__new__(runner_module.Runner)
    runner.root = tmp_path / 'state'
    runner.root.mkdir()
    runner.ledger = runner_module.Ledger(runner.root / 'journal.sqlite3')
    runner.update = Mock()
    runner.request = Mock()
    return runner


def test_redelivery_does_not_relaunch_interrupted_session(tmp_path):
    runner = local_runner(tmp_path)
    runner.ledger.reserve('work')
    runner.ledger.save('work', 'running', {'session_id': 'original'})
    runner.process(SimpleNamespace(input_data={'work_id': 'work'}, task_id='redelivery', workflow_instance_id='wf'))
    runner.request.assert_not_called()
    assert runner.ledger.get('work')[1]['session_id'] == 'original'


def test_lost_completion_ack_replays_results_only(tmp_path):
    runner = local_runner(tmp_path)
    runner.ledger.reserve('work')
    runner.ledger.save('work', 'finished', {'work': 'work', 'task': 'task', 'workflow': 'wf', 'artifacts': {'tests_passed': True}})
    runner.request.side_effect = [None, {'execution_status': 'RUNNING'}, None, {'execution_status': 'COMPLETED'}, None]
    runner.update.side_effect = RuntimeError('lost ACK')
    with pytest.raises(RuntimeError):
        runner.recover()
    assert runner.ledger.get('work')[0] == 'finished'
    runner.recover()
    assert runner.ledger.get('work')[0] == 'reported'
    assert runner.update.call_count == 1


def test_publication_checks_commit_before_any_remote_write(tmp_path, monkeypatch):
    runner = local_runner(tmp_path)
    runner.ledger.reserve('work')
    runner.ledger.save('work', 'reported', {'tree': str(tmp_path)})
    runner.request.return_value = {'approved_sha': 'a' * 40, 'publish_approved': True}
    monkeypatch.setattr(runner_module, 'git', lambda repo, *args: 'b' * 40 if args[0] == 'rev-parse' else '')
    with pytest.raises(RuntimeError, match='Exact clean commit'):
        runner.publish('work')
    assert runner.request.call_count == 1


@pytest.mark.skipif(sys.platform != 'darwin' or os.environ.get('RUN_NATIVE_RUNNER_TEST') != 'true', reason='opt-in macOS sandbox/process integration')
def test_real_worktree_process_and_offline_checks_without_a_model(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args], cwd=repo, text=True).strip()
    git('init', '-b', 'main')
    (repo / 'README.md').write_text('Synthetic runner fixture\n')
    git('add', '.')
    git('commit', '-m', 'fixture')
    git('remote', 'add', 'origin', 'https://github.com/example/fixture.git')
    fake = tmp_path / 'fake-opencode'
    fake.write_text('#!/usr/bin/env python3\nimport json\nfrom pathlib import Path\nPath("change.txt").write_text("local fixture")\nprint(json.dumps({"type":"text","sessionID":"fixture-session","part":{"text":"Deterministic fixture completed"}}))\n')
    fake.chmod(0o700)
    checks = tmp_path / 'checks.json'
    checks.write_text(json.dumps([{'name': 'offline check', 'directory': '.', 'argv': [sys.executable, '-c', 'print("passed")']},{'name':'Whitespace','directory':'.','argv':['git','diff','--check']}]))
    runner = local_runner(tmp_path)
    runner.args = SimpleNamespace(allow_model_calls=True, repo=str(repo), opencode=str(fake), checks=str(checks))
    runner.request.return_value = {'model_approved': True, 'repo_url': 'https://github.com/example/fixture',
                                   'repo_branch': 'main', 'request': 'Synthetic fixture', 'acceptance': 'Checks pass',
                                   'title': 'Fixture change', 'execution_status': 'RUNNING', 'submission': 'submitted'}
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'synthetic-key-never-used')
    task = SimpleNamespace(input_data={'work_id': 'fixture-work'}, task_id='fixture-task', workflow_instance_id='fixture-wf')
    runner.process(task)
    state, data = runner.ledger.get('fixture-work')
    assert state == 'finished'
    assert data['artifacts']['tests_passed']
    assert data['artifacts']['session_id'] == 'fixture-session'
    assert 'change.txt' in data['artifacts']['changed_files']
    assert data['artifacts']['head_sha'] != data['artifacts']['base_sha']
    assert not data['artifacts']['dirty']
    # Same task delivered again cannot run the process or alter the commit.
    runner.request.reset_mock()
    runner.process(task)
    runner.request.assert_not_called()


def test_cancelled_delivery_never_launches_model(tmp_path):
    runner = local_runner(tmp_path)
    runner.request.return_value = {'execution_status': 'TERMINATED', 'submission': 'cancelled'}
    runner.process(SimpleNamespace(input_data={'work_id': 'cancelled'}, task_id='task', workflow_instance_id='wf'))
    assert runner.ledger.get('cancelled')[0] == 'finished'
    assert runner.ledger.get('cancelled')[1]['artifacts']['tests_passed'] is False


def test_literal_credentials_are_scrubbed_from_agent_evidence(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'synthetic-sensitive-value')
    assert runner_module.redact({'summary': 'synthetic-sensitive-value'})['summary'] == '[redacted]'


def test_sdk_gateway_url_does_not_append_an_extra_api_segment(tmp_path, monkeypatch):
    monkeypatch.setenv('ORCHESTRA_RUNNER_TOKEN', 'synthetic-runner-credential')
    instance = runner_module.Runner(SimpleNamespace(state=str(tmp_path), url='http://127.0.0.1:8000'))
    assert instance.tasks.api_client.configuration.host == 'http://127.0.0.1:8000/api/runner/conductor'
    instance.api.close()
    instance.lock.close()


def test_publication_redelivery_reconciles_without_another_write(tmp_path):
    runner = local_runner(tmp_path)
    task = SimpleNamespace(input_data={'work_id':'work','sha':'a'*40},task_id='task',workflow_instance_id='wf')
    runner.publish = Mock(side_effect=RuntimeError('lost acknowledgement'))
    runner.recover_publications = Mock()
    runner.publication_task(task)
    assert runner.ledger.get('publish:work')[0]=='publication_uncertain'
    runner.publication_task(task)
    runner.publish.assert_called_once_with('work')
    runner.recover_publications.assert_called_once()


def test_lost_publication_completion_ack_does_not_push_again(tmp_path):
    runner=local_runner(tmp_path)
    data={'work':'work','task':'task','workflow':'wf'}
    runner.ledger.reserve('publish:work')
    runner.ledger.save('publish:work','publication_done',data)
    runner.update.side_effect=RuntimeError('lost task ack')
    with pytest.raises(RuntimeError):runner.recover_publications()
    assert runner.ledger.get('publish:work')[0]=='publication_done'
    runner.update.side_effect=None
    runner.recover_publications()
    assert runner.ledger.get('publish:work')[0]=='publication_reported'
    runner.request.assert_not_called()


def test_uncertain_publication_reconciles_exact_sha_via_read_only_github(tmp_path,monkeypatch):
    runner=local_runner(tmp_path)
    sha='a'*40
    runner.ledger.reserve('work')
    runner.ledger.save('work','reported',{'branch':'codex/work-unique'})
    runner.ledger.reserve('publish:work')
    runner.ledger.save('publish:work','publication_uncertain',{'work':'work','task':'task','workflow':'wf'})
    runner.request.return_value={'repo_url':'https://github.com/example/repo','approved_sha':sha,'publication_execution_status':'RUNNING'}
    query=Mock(return_value=json.dumps([{'url':'https://github.com/example/repo/pull/1','headRefOid':sha}]))
    monkeypatch.setattr(runner_module.subprocess,'check_output',query)
    runner.recover_publications()
    assert query.call_args.args[0][:3]==['gh','pr','list']
    assert runner.ledger.get('publish:work')[0]=='publication_reported'
    writes=[c for c in runner.request.call_args_list if c.args[0]=='POST']
    assert len(writes)==1 and writes[0].kwargs['json']['state']=='published'


def test_check_configuration_rejects_mutation_and_escaping_commands(tmp_path):
    with pytest.raises(RuntimeError,match='excluded'):
        runner_module.validate_check({'directory':'.','argv':['npm','run','deploy']},tmp_path)
    with pytest.raises(RuntimeError,match='excluded'):
        runner_module.validate_check({'directory':'.','argv':['bash','-c','echo unsafe']},tmp_path)
    with pytest.raises(RuntimeError,match='directory'):
        runner_module.validate_check({'directory':'..','argv':['git','diff','--check']},tmp_path)


def test_reservation_atomically_preserves_recovery_metadata(tmp_path):
    journal=runner_module.Ledger(tmp_path/'journal.sqlite3')
    metadata={'work':'work','task':'task','workflow':'workflow'}
    assert journal.reserve('work',metadata)
    restarted=runner_module.Ledger(tmp_path/'journal.sqlite3')
    assert restarted.get('work')==('reserved',metadata)
    assert not restarted.reserve('work',{'task':'duplicate'})
    assert restarted.get('work')[1]==metadata


def test_preparation_failure_is_reported_without_an_uncertain_model_session(tmp_path,monkeypatch):
    runner=local_runner(tmp_path)
    runner.args=SimpleNamespace(repo=str(tmp_path),allow_model_calls=True)
    runner.request.return_value={'model_approved':True,'repo_url':'https://github.com/example/expected','repo_branch':'main','execution_status':'RUNNING','submission':'submitted'}
    monkeypatch.setattr(runner_module,'git',lambda *args:'https://github.com/example/wrong')
    runner.process(SimpleNamespace(input_data={'work_id':'work'},task_id='task',workflow_instance_id='wf'))
    state,data=runner.ledger.get('work')
    assert state=='finished'
    assert not data['artifacts']['tests_passed']
    assert 'Preparation failed' in data['artifacts']['summary']


def test_disconnection_stops_process_and_retains_recoverable_failure(tmp_path,monkeypatch):
    runner=local_runner(tmp_path)
    checks=tmp_path/'checks.json';checks.write_text('[]')
    runner.args=SimpleNamespace(repo=str(tmp_path),allow_model_calls=True,opencode='/usr/bin/true',checks=str(checks))
    work={'model_approved':True,'repo_url':'https://github.com/example/repo','repo_branch':'main','execution_status':'RUNNING','submission':'submitted','request':'Synthetic offline fixture','acceptance':'Stop on disconnection','title':'Synthetic'}
    calls=0
    def request(method,path,**kw):
        nonlocal calls
        if method=='GET':
            calls+=1
            if calls>=3:raise runner_module.httpx.ConnectError('offline')
            return work
        return {}
    runner.request.side_effect=request
    def git(repo,*args):
        if args[0]=='remote':return work['repo_url']
        if args[0]=='rev-parse':return 'a'*40
        if args[:2]==('worktree','add'):Path(args[4]).mkdir()
        return ''
    monkeypatch.setattr(runner_module,'git',git)
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-never-used')
    monkeypatch.setattr(runner_module.time,'sleep',lambda _:None)
    process=SimpleNamespace(pid=123456,returncode=None)
    process.poll=lambda:process.returncode
    process.wait=lambda **kw:process.returncode
    monkeypatch.setattr(runner_module,'sandbox',lambda *args,**kw:[])
    launch=Mock(return_value=process);monkeypatch.setattr(runner_module.subprocess,'Popen',launch)
    def stop(pid,sig):process.returncode=-15
    kill=Mock(side_effect=stop);monkeypatch.setattr(runner_module.os,'killpg',kill)
    runner.process(SimpleNamespace(input_data={'work_id':'work'},task_id='task',workflow_instance_id='wf'))
    state,data=runner.ledger.get('work')
    assert state=='finished' and not data['artifacts']['tests_passed']
    assert launch.call_count==1 and kill.call_count==1
    runner.process(SimpleNamespace(input_data={'work_id':'work'},task_id='redelivery',workflow_instance_id='wf'))
    assert launch.call_count==1
