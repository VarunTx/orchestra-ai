"""Applied fixes live in instruction files with a dated marker, so later runs can measure whether they worked."""
from datetime import datetime,timezone
import os
from pathlib import Path
import re

# The time matters: sessions that started earlier the same day ran without the line.
MARKER=re.compile(r'<!-- orchestra-review:([0-9a-f]{8}) (\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}Z)?) -->')
MIN_AFTER=5  # below this many sessions after a fix, the comparison is reported as too early


def global_files():
    """The instruction file each agent reads in every project, keyed by the session source it governs."""
    claude=Path(os.environ['CLAUDE_CONFIG_DIR']) if os.environ.get('CLAUDE_CONFIG_DIR') else Path.home()/'.claude'
    opencode=Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'opencode'
    return {'claude-code':claude/'CLAUDE.md','opencode':opencode/'AGENTS.md'}


def markers(path):
    path=Path(path)
    if not path.is_file(): return []
    return [(m[1],stamp(m[2])) for m in MARKER.finditer(path.read_text(encoding='utf-8',errors='replace'))]


def stamp(text):
    return datetime.fromisoformat(text.replace('Z','+00:00')).replace(tzinfo=timezone.utc)


def apply(path,fixes,now=None):
    """Append each fix once; fixes already marked in the file are skipped. Returns the ids written."""
    path=Path(path)
    present={fid for fid,_ in markers(path)}
    new=[f for f in fixes if f.line and f.id not in present]
    if not new: return []
    now=(now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%MZ')
    text=path.read_text(encoding='utf-8') if path.is_file() else ''
    lines=''.join(f'- {f.line} <!-- orchestra-review:{f.id} {now} -->\n' for f in new)
    if text and not text.endswith('\n'): text+='\n'
    if 'orchestra-review:' not in text: text+=('\n' if text else '')+'## Known environment mistakes\n\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text+lines,encoding='utf-8')
    return [f.id for f in new]


def governed(path,sessions):
    """Sessions whose agent reads this file: a global file governs its agent; a project file governs its project."""
    path=Path(path).expanduser().resolve()
    for source,global_path in global_files().items():
        if path==global_path.expanduser().resolve(): return [s for s in sessions if s.source==source]
    root=str(path.parent)
    return [s for s in sessions if s.project and (s.project==root or s.project.startswith(root+os.sep))]


def measure(fid,added,sessions,hits_by_id,exposed=None):
    """How many governed sessions hit the mistake before and after the fix was added.
    With `exposed` (a step predicate), each side also counts the sessions that tried the action, and the verdict
    is judged on those alone: a session that never tried the action cannot show whether the fix worked."""
    hit=hits_by_id.get(fid,set())
    row={'id':fid,'added':added.strftime('%Y-%m-%dT%H:%MZ'),'exposure_known':exposed is not None}
    for side,group in (('before',[s for s in sessions if s.started and s.started<added]),
                       ('after',[s for s in sessions if s.started and s.started>=added])):
        hits=[s for s in group if (s.source,s.id) in hit]
        tried=[s for s in group if (s.source,s.id) in hit or any(exposed(x) for x in s.steps)] if exposed else None
        row[side]={'sessions':len(group),'tried':len(tried) if tried is not None else None,'hit':len(hits)}
    basis='tried' if exposed else 'sessions'
    after=row['after'][basis]
    row['verdict']=('too early' if after<MIN_AFTER else
                    'stopped' if row['after']['hit']==0 and row['before']['hit'] else
                    'still happening' if row['after']['hit'] else 'not seen before or after')
    return row
