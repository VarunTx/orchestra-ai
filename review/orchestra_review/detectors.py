"""Waste rules. Each is narrow on purpose: every flagged step must be defensible from the transcript alone."""
from collections import defaultdict
from dataclasses import dataclass,field
import re

REPEAT_MIN=3
REPEAT_WINDOW=15
STREAK_MIN=4
REPEATABLE={'shell','read','search','web'}  # edits and harness tools legitimately repeat with identical output


@dataclass
class Finding:
    kind:str
    session:object
    target:str
    steps:list[int]
    wasted:list[int]=field(default_factory=list)
    error:str|None=None


def changes_state(step):
    return step.kind=='edit' or (step.kind in ('shell','other') and step.ok is not False)


def repeated_failures(s):
    """A retry is wasted when it fails with the same output and nothing in between could have changed the result.
    Fix-and-rerun loops (edit, then run the tests again) are never counted."""
    groups=defaultdict(list)
    for step in s.steps:
        if step.ok is False: groups[(step.kind,step.target)].append(step)
    found=[]
    for (kind,target),group in groups.items():
        blind=[later.index for earlier,later in zip(group,group[1:])
               if later.digest==earlier.digest and not any(changes_state(x) for x in s.steps[earlier.index:later.index-1])]
        if blind: found.append(Finding('repeated_failure',s,target,[x.index for x in group],blind,group[-1].error))
    return found


def unchanged_repeats(s):
    groups=defaultdict(list)
    for step in s.steps:
        if step.ok and step.kind in REPEATABLE and step.digest: groups[(step.tool,step.target,step.digest)].append(step.index)
    found=[]
    for (tool,target,_),indices in groups.items():
        cluster=[]
        for index in indices+[None]:
            if index is not None and cluster and index-cluster[0]<REPEAT_WINDOW: cluster.append(index);continue
            if len(cluster)>=REPEAT_MIN: found.append(Finding('unchanged_repeat',s,target,cluster,cluster[1:]))
            cluster=[index] if index is not None else []
    return found


def failure_streaks(s):
    found=[];run=[]
    for step in s.steps+[None]:
        if step is not None and step.ok is False: run.append(step);continue
        if len(run)>=STREAK_MIN:
            found.append(Finding('failure_streak',s,run[0].target,[x.index for x in run],[],run[-1].error))
        run=[]
    return found


def review(s):
    return repeated_failures(s)+unchanged_repeats(s)+failure_streaks(s)


def wasted(findings):
    return {(f.session.source,f.session.id,i) for f in findings for i in f.wasted}


VOLATILE=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+',re.I)


def signature(step):
    """Two failures are the same mistake when their last error line matches, ignoring ids and numbers.
    The last line is where shells and tracebacks put the actual cause."""
    last=next((line.strip() for line in reversed((step.error or '').splitlines()) if line.strip()),'')
    last=re.sub(r'={2,}','==',VOLATILE.sub('#',last.lstrip('…')))[:160]
    if len(last)<12 or re.fullmatch(r'Exit(ed with)? code #',last): return None  # says nothing about the cause
    return (step.kind,last)


def by_signature(sessions):
    """Every failed step with a usable signature, grouped by signature and then by session."""
    seen=defaultdict(lambda:defaultdict(list))
    for s in sessions:
        for step in s.steps:
            key=signature(step) if step.ok is False else None
            if key: seen[key][(s.source,s.id)].append(step)
    return seen


def recurring(sessions,minimum=2):
    """Mistakes seen in at least `minimum` sessions, with every failed step that matched them."""
    return sorted(((key,hits) for key,hits in by_signature(sessions).items() if len(hits)>=minimum),
                  key=lambda item:(-len(item[1]),-sum(map(len,item[1].values()))))
