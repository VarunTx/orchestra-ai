"""A summary safe to send to someone else, and a way to combine several people's summaries.

A share carries counts and normalised causes only: no session ids, titles, projects, commands, paths, file names
or costs. Causes are scrubbed again here because error lines can quote paths and file names."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
import re

from .detectors import recurring,review,wasted
from .fixes import category,exposure
from .redact import redact

VERSION=1
SCRUB=[
    (re.compile(r'https?://\S+'),'<url>'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),'<email>'),
    (re.compile(r'[A-Za-z]:\\[^\s:\'"`]*'),'<path>'),
    (re.compile(r'(?:~|\.{0,2})/[^\s:\'"`]*'),'<path>'),
    (re.compile(r'\b[\w.-]+\.(?:md|txt|py|ts|tsx|js|jsx|json|pdf|docx?|xlsx?|csv|ya?ml|toml|sh|log|html?|png|jpe?g)\b',re.I),'<file>'),
]


def scrub(text):
    text=redact(text or '')
    for pattern,replacement in SCRUB: text=pattern.sub(replacement,text)
    return ' '.join(text.split())[:160]


def summary(sessions):
    findings=[f for s in sessions for f in review(s)]
    steps=sum(len(s.steps) for s in sessions)
    failed=sum(1 for s in sessions for x in s.steps if x.ok is False)
    repeats=recurring(sessions)
    causes=[]
    for key,hits in repeats:
        tried=exposure(key,{x.tool for steps in hits.values() for x in steps})
        attempted=sum(1 for s in sessions if (s.source,s.id) in hits or any(tried(x) for x in s.steps))
        causes.append({'category':category(key),'tool':key[0],'cause':scrub(key[1]),'sessions_hit':len(hits),
                       'sessions_tried':attempted,'failed_steps':sum(map(len,hits.values()))})
    months=sorted({s.started.strftime('%Y-%m') for s in sessions if s.started})
    return {'orchestra_review_share':VERSION,
            'created':datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'months':months,
            'agents':dict(Counter(s.source for s in sessions)),
            'models':sorted({m for s in sessions for m in s.models}),
            'sessions':len(sessions),'steps':steps,'failed_steps':failed,
            'blocked_steps':sum(1 for s in sessions for x in s.steps if x.blocked),
            'wasted_steps':len(wasted(findings)),
            'recurring_failed_steps':sum(c['failed_steps'] for c in causes),
            'causes':causes}


def preview(data):
    share=lambda n,d:f'{n/d:.0%}' if d else 'n/a'
    out=[f"This is everything the share contains. Review it before sending.",
         f"{data['sessions']} sessions ({', '.join(f'{k} {v}' for k,v in sorted(data['agents'].items()))}), "
         f"{data['steps']:,} tool calls, {data['failed_steps']} failed, "
         f"{data['recurring_failed_steps']} of them recurring ({share(data['recurring_failed_steps'],data['failed_steps'])})"]
    for c in data['causes']:
        out.append(f"  {c['category']:<22} {c['sessions_hit']}/{c['sessions_tried']} sessions — {c['cause']}")
    return '\n'.join(out)


def load(paths):
    shares=[]
    for path in paths:
        data=json.loads(open(path,encoding='utf-8').read())
        if data.get('orchestra_review_share')!=VERSION: raise ValueError(f'{path}: not an orchestra-review share (version {VERSION})')
        shares.append(data)
    return shares


def combine(shares):
    """Which causes show up for how many people. Each person counts once per cause."""
    people=defaultdict(lambda:{'people':0,'sessions_hit':0,'sessions_tried':0,'failed_steps':0})
    for data in shares:
        for c in data['causes']:
            row=people[(c['category'],c['tool'],c['cause'])]
            row['people']+=1
            for field in ('sessions_hit','sessions_tried','failed_steps'): row[field]+=c[field]
    totals={k:sum(d[k] for d in shares) for k in ('sessions','steps','failed_steps','recurring_failed_steps')}
    by_category=Counter()
    for (cat,_,_),row in people.items(): by_category[cat]+=row['failed_steps']
    causes=[{'category':cat,'tool':tool,'cause':cause,**row} for (cat,tool,cause),row in people.items()]
    causes.sort(key=lambda c:(-c['people'],-c['failed_steps']))
    return {'people':len(shares),**totals,'by_category':dict(by_category.most_common()),'causes':causes}


def render_combined(data):
    share=f"{data['recurring_failed_steps']/data['failed_steps']:.0%}" if data['failed_steps'] else 'n/a'
    out=[f"{data['people']} people · {data['sessions']} sessions · {data['steps']:,} tool calls · {data['failed_steps']} failed · "
         f"{data['recurring_failed_steps']} recurring ({share})",'','Failed steps by kind of mistake']
    out+=[f"  {cat:<22} {n}" for cat,n in data['by_category'].items()]
    out+=['','Causes, by how many people hit them']
    out+=[f"  {c['people']} people, {c['sessions_hit']}/{c['sessions_tried']} sessions — {c['cause']}" for c in data['causes'][:20]]
    return '\n'.join(out)
