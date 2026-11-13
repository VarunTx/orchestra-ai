"""Turns sessions and findings into one structure, rendered as text or JSON."""
from collections import Counter
from pathlib import Path

from .detectors import by_signature,recurring,review,wasted
from .fixes import exposure,fix_id,suggest
from .instructions import global_files,governed,markers,measure
from .redact import redact

TITLES={'repeated_failure':'Blind retry','unchanged_repeat':'Unchanged repeat','failure_streak':'Failure streak'}


def short(text,limit=110):
    text=' '.join(redact(text or '').split())
    return text if len(text)<=limit else text[:limit-1]+'…'


def build(sessions,top=10,model=None,model_url=None,instruction_files=()):
    findings=[f for s in sessions for f in review(s)]
    steps=sum(len(s.steps) for s in sessions)
    failed=sum(1 for s in sessions for x in s.steps if x.ok is False)
    blocked=sum(1 for s in sessions for x in s.steps if x.blocked)
    unknown=sum(1 for s in sessions for x in s.steps if x.ok is None and not x.blocked)
    repeats=recurring(sessions)
    waste=wasted(findings)
    usage=Counter()
    for s in sessions:
        if s.usage.known:
            for key in ('input','output','reasoning','cache_read','cache_write'): usage[key]+=getattr(s.usage,key)
    priced=[s for s in sessions if s.cost_usd is not None]
    prompt_side=usage['input']+usage['cache_read']+usage['cache_write']
    times=[t for s in sessions for t in (s.started,s.ended) if t]
    ranked=sorted(findings,key=lambda f:(-len(f.wasted),-len(f.steps)))
    return {
        'sessions':len(sessions),
        'by_source':dict(Counter(s.source for s in sessions)),
        'period':[min(times).isoformat(),max(times).isoformat()] if times else None,
        'steps':steps,'failed_steps':failed,'blocked_steps':blocked,'unknown_outcome_steps':unknown,
        'wasted_steps':len(waste),
        'wasted_share':round(len(waste)/steps,4) if steps else None,
        'tokens':dict(usage) if usage else None,
        'cache_read_share':round(usage['cache_read']/prompt_side,4) if prompt_side else None,
        'recorded_cost_usd':round(sum(s.cost_usd for s in priced),4) if priced else None,
        'sessions_without_cost':len(sessions)-len(priced),
        'skipped_lines':sum(s.skipped_lines for s in sessions),
        'findings':[finding_row(f) for f in ranked[:top]],
        'finding_counts':dict(Counter(f.kind for f in findings)),
        'recurring_failed_steps':sum(len(v) for _,hits in repeats for v in hits.values()),
        'recurring':[recurring_row(key,hits,suggest(key,hits,model,model_url)) for key,hits in repeats[:top]],
        'fixes_in_place':fixes_in_place(sessions,instruction_files),
        'top_sessions':[session_row(s,findings) for s in sorted(sessions,key=lambda s:-len(s.steps))[:top]],
    }


def finding_row(f):
    return {'kind':f.kind,'source':f.session.source,'session':f.session.id,'title':f.session.title,
            'target':short(f.target,200),'steps':f.steps,'wasted_steps':f.wasted,'error':short(f.error,200) if f.error else None}


def recurring_row(key,hits,fix):
    first=next(iter(hits.values()))[0]
    return {'kind':key[0],'cause':short(key[1],160),'sessions':len(hits),'failed_steps':sum(map(len,hits.values())),
            'example':short(first.target,200),'fix':{'id':fix.id,'line':fix.line,'source':fix.source,'note':fix.note}}


def instruction_paths(sessions,extra=()):
    paths=[*global_files().values(),*map(Path,extra)]
    for project in sorted({s.project for s in sessions if s.project}):
        paths+=[Path(project)/'AGENTS.md',Path(project)/'CLAUDE.md']
    unique=[]
    for path in paths:
        if path.expanduser().resolve() not in [p.expanduser().resolve() for p in unique]: unique.append(path)
    return unique


def fixes_in_place(sessions,extra=()):
    signatures=by_signature(sessions)
    hits={fix_id(key):set(by_session) for key,by_session in signatures.items()}
    keys={fix_id(key):key for key in signatures}
    rows=[]
    for path in instruction_paths(sessions,extra):
        for fid,added in markers(path):
            tools={x.tool for steps in signatures[keys[fid]].values() for x in steps} if fid in keys else None
            tried=exposure(keys[fid],tools) if fid in keys else None  # unknown when the mistake is absent from these logs
            rows.append({'file':str(path),**measure(fid,added,governed(path,sessions),hits,tried)})
    return rows


def session_row(s,findings):
    mine=[f for f in findings if f.session is s]
    return {'source':s.source,'session':s.id,'title':s.title,'project':s.project,'models':s.models,'steps':len(s.steps),
            'failed_steps':sum(1 for x in s.steps if x.ok is False),'wasted_steps':len(wasted(mine)),'cost_usd':s.cost_usd}


def number(n):
    return f'{n:,}'


def render(data):
    if not data['sessions']: return 'No agent sessions found.'
    out=[]
    period=f" · {data['period'][0][:10]} → {data['period'][1][:10]}" if data['period'] else ''
    sources=', '.join(f'{k} {v}' for k,v in sorted(data['by_source'].items()))
    out.append(f"Orchestra Review — {data['sessions']} sessions ({sources}){period}")
    share=f" ({data['wasted_share']:.1%})" if data['wasted_share'] is not None else ''
    out.append(f"Steps: {number(data['steps'])} tool calls · {number(data['failed_steps'])} failed · "
               f"{number(data['wasted_steps'])} wasted{share}")
    extra=[f"{number(data['blocked_steps'])} blocked by permissions or the user"]*bool(data['blocked_steps'])
    extra+=[f"{number(data['unknown_outcome_steps'])} with no recorded outcome"]*bool(data['unknown_outcome_steps'])
    if extra: out.append('       '+' · '.join(extra))
    if data['tokens']:
        t=data['tokens']
        cache=f" · cache reads are {data['cache_read_share']:.0%} of prompt tokens" if data['cache_read_share'] is not None else ''
        out.append(f"Tokens: {number(t['input'])} input · {number(t['output'])} output · {number(t['cache_read'])} cache read{cache}")
    cost=f"${data['recorded_cost_usd']:.2f} recorded" if data['recorded_cost_usd'] is not None else 'none recorded'
    out.append(f"Cost: {cost} by the agents themselves; {data['sessions_without_cost']} sessions have none (not estimated)")
    if data['by_source'].get('claude-code'): out.append("      Claude Code records its own list-price figure, which may not match a subscription bill")
    if data['skipped_lines']: out.append(f"Skipped {number(data['skipped_lines'])} unreadable log lines")
    out.append('')
    out.append('Top findings' if data['findings'] else 'No wasted steps found.')
    for i,f in enumerate(data['findings'],1):
        name=f['title'] or f['session'][:8]
        wasted=f", {len(f['wasted_steps'])} wasted" if f['wasted_steps'] else ''
        out.append(f"{i:>2}. {TITLES[f['kind']]} ×{len(f['steps'])}{wasted} — {f['source']} “{short(name,50)}”")
        out.append(f"    {f['target']}")
        out.append(f"    steps {', '.join(map(str,f['steps'][:12]))}{' …' if len(f['steps'])>12 else ''}")
        if f['error']: out.append(f"    error: {f['error']}")
    if data['recurring']:
        out.append('')
        out.append(f"Mistakes that recur across sessions: {number(data['recurring_failed_steps'])} failed steps "
                   f"(candidates for a line in AGENTS.md or CLAUDE.md)")
        for r in data['recurring']:
            out.append(f"  {r['sessions']} sessions, {r['failed_steps']} failures — {r['cause']}")
            out.append(f"    e.g. {short(r['example'],100)}")
            fix=r['fix']
            out.append(f"    fix [{fix['id']}, {fix['source']}]: {fix['line']}" if fix['line'] else f"    no fix: {fix['note']}")
        if any(r['fix']['line'] for r in data['recurring']):
            out.append('  Apply one with: orchestra-review apply <id> --to <instruction file>')
    if data['fixes_in_place']:
        out.append('')
        out.append('Fixes in place: sessions that hit the mistake / sessions that tried the action, before → after')
        for f in data['fixes_in_place']:
            side=lambda s:f"{s['hit']}/{s['tried']}" if s['tried'] is not None else f"{s['hit']}/{s['sessions']} (all sessions)"
            out.append(f"  [{f['id']}] {f['added']} {Path(f['file']).name}: {side(f['before'])} → {side(f['after'])} — {f['verdict']}")
    return '\n'.join(out)
