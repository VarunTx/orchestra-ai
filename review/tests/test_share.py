"""Shares must carry counts and scrubbed causes only; combining counts each person once per cause."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]))

from orchestra_review import cli,share
from orchestra_review.model import Session,Step


def test_scrub_removes_paths_files_urls_emails_and_secrets():
    text=('cannot open /Users/alex/secret-project/notes.txt and ~/x/y, C:\\Users\\a\\b.py, report_q3.pdf, '
          'see https://intra.example/a?b=1 or alex@corp.com with API_KEY=hunter2')
    clean=share.scrub(text)
    for leaked in ('alex','secret-project','notes.txt','report_q3','intra.example','corp.com','hunter2','Users'):
        assert leaked not in clean
    assert share.scrub("ModuleNotFoundError: No module named 'fitz'")=="ModuleNotFoundError: No module named 'fitz'"


def session(sid,title,project,command,error):
    s=Session(source='claude-code',id=sid,title=title,project=project,started=datetime(2026,11,1,tzinfo=timezone.utc),models=['m'])
    s.steps=[Step(index=1,tool='Bash',kind='shell',target=command,ok=False,error=error),
             Step(index=2,tool='Bash',kind='shell',target='python3 -c "import fitz"',ok=True)]
    return s


def test_summary_holds_no_identifying_fields():
    error="Traceback\nModuleNotFoundError: No module named 'fitz'"
    sessions=[session('sid-123','Acme launch plan','/Users/alex/acme','cd /Users/alex/acme && python3 secret_tool.py',error),
              session('sid-456','Payroll fix','/Users/alex/payroll','python3 /Users/alex/payroll/run.py',error)]
    data=share.summary(sessions)
    text=json.dumps(data)
    for leaked in ('sid-123','Acme','acme','Payroll','alex','secret_tool','run.py'):
        assert leaked not in text
    assert data['months']==['2026-11'] and data['recurring_failed_steps']==2
    assert data['causes']==[{'category':'missing-python-module','tool':'shell','cause':"ModuleNotFoundError: No module named 'fitz'",
                             'sessions_hit':2,'sessions_tried':2,'failed_steps':2}]


def test_combine_counts_each_person_once_per_cause(tmp_path):
    cause={'category':'zsh-empty-glob','tool':'shell','cause':'(eval):#: no matches found: <path>','sessions_hit':2,'sessions_tried':5,'failed_steps':3}
    base={'orchestra_review_share':1,'sessions':10,'steps':100,'failed_steps':6,'recurring_failed_steps':3}
    paths=[]
    for n in range(3):
        path=tmp_path/f'p{n}.json';path.write_text(json.dumps({**base,'causes':[cause] if n<2 else []}));paths.append(path)
    data=share.combine(share.load(paths))
    assert data['people']==3 and data['sessions']==30
    assert data['causes'][0]['people']==2 and data['causes'][0]['sessions_hit']==4 and data['by_category']=={'zsh-empty-glob':6}
    bad=tmp_path/'bad.json';bad.write_text('{"sessions": 1}')
    with pytest.raises(ValueError,match='not an orchestra-review share'): share.load([bad])


def test_cli_share_previews_on_stderr_and_prints_json_on_stdout(tmp_path,capsys):
    project=tmp_path/'claude'/'p';project.mkdir(parents=True)
    for n in (1,2):
        lines=[{'type':'assistant','timestamp':'2026-11-01T10:00:00Z','cwd':'/Users/alex/acme','message':{'id':f'm{n}','content':[
                   {'type':'tool_use','id':'t','name':'Bash','input':{'command':'ls /Users/alex/acme/*.zzz'}}]}},
               {'type':'user','timestamp':'2026-11-01T10:00:01Z','message':{'content':[
                   {'type':'tool_result','tool_use_id':'t','content':'Exit code 1\n(eval):1: no matches found: /Users/alex/acme/*.zzz','is_error':True}]}}]
        (project/f's{n}.jsonl').write_text('\n'.join(json.dumps(x) for x in lines))
    assert cli.main(['share','--claude-dir',str(tmp_path/'claude'),'--source','claude-code'])==0
    out,err=capsys.readouterr()
    data=json.loads(out)
    assert 'Review it before sending' in err and 'alex' not in out and 'alex' not in err
    assert data['causes'][0]['category']=='zsh-empty-glob' and data['causes'][0]['sessions_hit']==2
