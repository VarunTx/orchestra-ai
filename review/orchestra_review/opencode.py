"""OpenCode sessions, read through its own export command or from saved export files."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .model import Session,Step,digest,kind_of,ms_time,tail,target_of


def available():
    return shutil.which('opencode') is not None


def load_project(directory,timeout=60):
    """Every session OpenCode lists for one project directory; empty when OpenCode is absent."""
    if not available(): return []
    listed=subprocess.run(['opencode','session','list','--format','json','-n','1000'],cwd=directory,
                          capture_output=True,text=True,timeout=timeout)
    if listed.returncode!=0: return []
    sessions=[]
    for row in json.loads(listed.stdout or '[]'):
        # Large exports arrive truncated through a pipe; a file receives all of it.
        with tempfile.TemporaryFile() as out:
            exported=subprocess.run(['opencode','session','export',row['id']],cwd=directory,
                                    stdout=out,stderr=subprocess.DEVNULL,timeout=timeout)
            if exported.returncode!=0: continue
            out.seek(0)
            try: s=parse(json.loads(out.read()))
            except ValueError: continue
        s.project=s.project or row.get('directory')
        sessions.append(s)
    return sessions


def load_exports(path):
    path=Path(path)
    files=sorted(path.glob('*.json')) if path.is_dir() else [path]
    return [parse(json.loads(f.read_text(encoding='utf-8'))) for f in files]


def output_text(content):
    if not isinstance(content,list): return None
    return '\n'.join(p.get('text','') for p in content if isinstance(p,dict) and p.get('type')=='text')


def parse(export):
    info=export.get('info') or {}
    s=Session(source='opencode',id=str(info.get('id','')),title=info.get('title'))
    costs=[]
    for message in export.get('messages') or []:
        if not isinstance(message,dict): s.skipped_lines+=1;continue
        times=message.get('time') or {}
        s.seen(ms_time(times.get('created')))
        if message.get('type')=='user': s.prompts+=1
        if message.get('type')!='assistant': continue
        model=message.get('model') or {}
        s.model(model.get('id') if isinstance(model,dict) else model)
        tokens=message.get('tokens')
        if isinstance(tokens,dict):
            cache=tokens.get('cache') or {}
            s.usage.add(input=tokens.get('input'),output=tokens.get('output'),reasoning=tokens.get('reasoning'),
                        cache_read=cache.get('read'),cache_write=cache.get('write'))
        if isinstance(message.get('cost'),(int,float)): costs.append(message['cost'])
        for part in message.get('content') or []:
            if not isinstance(part,dict) or part.get('type')!='tool': continue
            state=part.get('state') or {};meta=state.get('metadata') or {}
            tool=str(part.get('name',''))
            text=output_text(state.get('content'))
            code=meta.get('exit') if isinstance(meta.get('exit'),int) else None
            if state.get('status')=='error' or (code is not None and code!=0): ok=False
            elif state.get('status')=='completed' and meta.get('status') in (None,'completed'): ok=True
            else: ok=None
            step=Step(index=len(s.steps)+1,tool=tool,kind=kind_of(tool),target=target_of(tool,state.get('input')),
                      ok=ok,exit_code=code,digest=digest(text),at=ms_time((part.get('time') or {}).get('created')))
            if ok is False: step.error=tail(text) or (str(state['error'])[:240] if state.get('error') else None)
            s.steps.append(step)
    if isinstance(info.get('cost'),(int,float)): s.cost_usd=float(info['cost'])
    elif costs: s.cost_usd=float(sum(costs))
    return s
