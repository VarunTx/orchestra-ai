"""Profile supervision tests: no child process or provider is actually started."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

spec=importlib.util.spec_from_file_location('project_companion',Path(__file__).parents[1]/'project_companion.py')
companion=importlib.util.module_from_spec(spec)
spec.loader.exec_module(companion)


def test_companion_rejects_shared_journal_before_starting(tmp_path,monkeypatch):
    config=tmp_path/'profiles.json'
    config.write_text(json.dumps([{'state':str(tmp_path/'shared')},{'state':str(tmp_path/'shared')}]))
    monkeypatch.setattr(companion.sys,'argv',['companion','--profiles',str(config)])
    start=Mock();monkeypatch.setattr(companion.subprocess,'Popen',start)
    with pytest.raises(ValueError,match='own durable state'):
        companion.main()
    start.assert_not_called()


def test_companion_uses_each_explicit_profile_credentials_and_journal(tmp_path,monkeypatch):
    profiles=[]
    for name in ['first','second']:
        profiles.append({'name':name,'url':'http://127.0.0.1:8000','repo':str(tmp_path/name),'state':str(tmp_path/(name+'-state')),'checks':str(tmp_path/(name+'-checks.json')),'token_env':name+'_RUNNER','provider_key_env':name+'_MODEL','github_token_env':name+'_GITHUB','allow_model_calls':False})
        for suffix in ['RUNNER','MODEL','GITHUB']:monkeypatch.setenv(name+'_'+suffix,'synthetic-'+name+'-'+suffix)
    config=tmp_path/'profiles.json';config.write_text(json.dumps(profiles))
    monkeypatch.setattr(companion.sys,'argv',['companion','--profiles',str(config)])
    child=SimpleNamespace(poll=lambda:0,wait=lambda **kw:0)
    start=Mock(return_value=child);monkeypatch.setattr(companion.subprocess,'Popen',start)
    companion.main()
    assert start.call_count==2
    for call,name in zip(start.call_args_list,['first','second']):
        assert call.kwargs['env']['ORCHESTRA_RUNNER_TOKEN']=='synthetic-'+name+'-RUNNER'
        assert call.kwargs['env']['DEEPSEEK_API_KEY']=='synthetic-'+name+'-MODEL'
        assert call.kwargs['env']['GH_TOKEN']=='synthetic-'+name+'-GITHUB'
        assert str(tmp_path/(name+'-state')) in call.args[0]
        assert '--allow-model-calls' not in call.args[0]
