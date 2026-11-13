"""Review local coding-agent sessions for wasted steps. Nothing leaves this machine.

Reads Claude Code transcripts (~/.claude/projects) and OpenCode sessions for the given
project directories (default: the current directory)."""
import argparse
from datetime import datetime,timedelta,timezone
import json
import re
import sys

from . import claude_code,opencode
from .report import build,render


def since(value):
    if value=='all': return None
    match=re.fullmatch(r'(\d+)([dh])',value)
    if not match: raise argparse.ArgumentTypeError('use a number of days or hours, such as 30d or 12h, or all')
    amount=int(match.group(1))
    return datetime.now(timezone.utc)-(timedelta(days=amount) if match.group(2)=='d' else timedelta(hours=amount))


def collect(args):
    sessions=[]
    if args.source in ('all','claude-code'): sessions+=claude_code.load(args.claude_dir)
    if args.source in ('all','opencode'):
        for path in args.opencode_export: sessions+=opencode.load_exports(path)
        if not args.opencode_export:
            for directory in args.opencode_project or ['.']: sessions+=opencode.load_project(directory)
    if args.since: sessions=[s for s in sessions if s.ended and s.ended>=args.since]
    if args.session: sessions=[s for s in sessions if s.id.startswith(args.session)]
    return [s for s in sessions if s.steps]


def main(argv=None):
    parser=argparse.ArgumentParser(prog='orchestra-review',description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source',choices=['all','claude-code','opencode'],default='all')
    parser.add_argument('--since',type=since,default=None,help='only sessions active within this window, such as 30d (default: all)')
    parser.add_argument('--claude-dir',default=claude_code.default_root(),help='Claude Code projects directory')
    parser.add_argument('--opencode-project',action='append',help='project directory whose OpenCode sessions to read; repeatable')
    parser.add_argument('--opencode-export',action='append',default=[],help='OpenCode export file or directory of them; repeatable')
    parser.add_argument('--session',help='only sessions whose id starts with this')
    parser.add_argument('--top',type=int,default=10)
    parser.add_argument('--json',action='store_true',help='print the full result as JSON')
    args=parser.parse_args(argv)
    data=build(collect(args),top=args.top)
    print(json.dumps(data,indent=2) if args.json else render(data))
    return 0


if __name__=='__main__': sys.exit(main())
