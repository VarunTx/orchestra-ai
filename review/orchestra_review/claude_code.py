"""Claude Code keeps one JSONL transcript per session (and per subagent) under ~/.claude/projects."""
import json
import os
from pathlib import Path
import re

from .model import Session,Step,digest,iso_time,kind_of,tail,target_of

EXIT=re.compile(r'^Exit code (\d+)')
# Refusals by the harness or the user are not the agent failing at its task.
BLOCKED=('<tool_use_error>Blocked','Permission for this command was denied','The server-side auto mode classifier',
         "The user doesn't want to proceed")


def default_root():
    base=os.environ.get('CLAUDE_CONFIG_DIR')
    return Path(base)/'projects' if base else Path.home()/'.claude'/'projects'


def load(root):
    root=Path(root)
    return [read(path) for path in sorted(root.rglob('*.jsonl'))] if root.is_dir() else []


def result_text(content):
    if isinstance(content,str): return content
    if isinstance(content,list):
        return '\n'.join(p.get('text','') for p in content if isinstance(p,dict) and p.get('type')=='text')
    return None


def read(path):
    path=Path(path)
    # Subagents write their own file; keep them apart so their steps never interleave with the parent's.
    sid=path.stem if path.parent.name!='subagents' else path.parents[1].name+'/'+path.stem
    s=Session(source='claude-code',id=sid)
    pending={};counted=set()
    with path.open(encoding='utf-8',errors='replace') as lines:
        for line in lines:
            try: entry=json.loads(line)
            except ValueError: s.skipped_lines+=1;continue
            if not isinstance(entry,dict): s.skipped_lines+=1;continue
            kind=entry.get('type');at=iso_time(entry.get('timestamp'))
            if kind in ('assistant','user'):
                s.seen(at)
                if entry.get('cwd') and not s.project: s.project=entry['cwd']
            message=entry.get('message') if isinstance(entry.get('message'),dict) else {}
            if kind=='assistant':
                model=message.get('model')
                if model and model!='<synthetic>': s.model(model)
                usage=message.get('usage')
                # Streaming writes one entry per content block, each repeating the message's usage.
                if isinstance(usage,dict) and message.get('id') not in counted:
                    counted.add(message.get('id'))
                    s.usage.add(input=usage.get('input_tokens'),output=usage.get('output_tokens'),
                                cache_read=usage.get('cache_read_input_tokens'),cache_write=usage.get('cache_creation_input_tokens'))
                for part in message.get('content') or []:
                    if isinstance(part,dict) and part.get('type')=='tool_use':
                        tool=str(part.get('name',''))
                        step=Step(index=len(s.steps)+1,tool=tool,kind=kind_of(tool),target=target_of(tool,part.get('input')),at=at)
                        s.steps.append(step);pending[part.get('id')]=step
            elif kind=='user':
                content=message.get('content')
                if isinstance(content,str):
                    if not entry.get('isMeta') and not entry.get('isCompactSummary'): s.prompts+=1
                    continue
                for part in content or []:
                    if not isinstance(part,dict): continue
                    if part.get('type')=='tool_result' and part.get('tool_use_id') in pending:
                        step=pending.pop(part['tool_use_id'])
                        text=result_text(part.get('content'))
                        step.digest=digest(text)
                        result=entry.get('toolUseResult') if isinstance(entry.get('toolUseResult'),dict) else {}
                        if entry.get('toolDenialKind') or result.get('interrupted') or (text or '').startswith(BLOCKED):
                            step.blocked=True;continue
                        step.ok=not part.get('is_error')
                        if not step.ok:
                            step.error=tail(text)
                            code=EXIT.match(text or '')
                            if code: step.exit_code=int(code.group(1))
                    elif part.get('type')=='text' and not entry.get('isMeta') and not entry.get('toolUseResult'):
                        s.prompts+=1
            elif kind=='custom-title' and entry.get('customTitle'):
                s.title=entry['customTitle']
            elif kind=='cost-state' and isinstance(entry.get('totalCostUSD'),(int,float)):
                s.cost_usd=float(entry['totalCostUSD'])
    return s
