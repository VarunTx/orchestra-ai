"""Outbound, project-scoped OpenCode runner. No model call without two explicit opt-ins.

See docs/PROJECT_MANAGEMENT.md. Uses the official Conductor SDK through a narrow gateway.
The ledger is deliberately at-most-once: uncertain sessions require human reconciliation.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time

import httpx
from conductor.client.configuration.configuration import Configuration
from conductor.client.http.api_client import ApiClient
from conductor.client.http.api.task_resource_api import TaskResourceApi
from conductor.client.http.models.task_result import TaskResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.lifecycle import redact as structural_redact
from app.runner_state import Ledger

TASK = 'cp_project_code'
TERMINAL = {'COMPLETED', 'FAILED', 'TIMED_OUT', 'TERMINATED'}



def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', '-c','core.fsmonitor=false', *args], cwd=repo,
                                   text=True, stderr=subprocess.DEVNULL,timeout=60).strip()


def validate_check(check, repo):
    argv=check.get('argv')
    if not isinstance(argv,list) or not argv or not all(isinstance(v,str) and v for v in argv):
        raise RuntimeError('Each check needs an explicit argument list')
    if Path(argv[0]).name == 'git' and argv != ['git','diff','--check']:
        raise RuntimeError('Only the built-in read-only git diff --check check is supported')
    forbidden={'deploy','migrate','migration','reset','rollback','destroy','delete','push'}
    if any(a.lower() in forbidden for a in argv) or Path(argv[0]).name in {'bash','sh','zsh','fish','curl','wget','ssh','docker','kubectl','terraform','railway','aws','gh'}:
        raise RuntimeError('Deployment, database mutation, publication and shell commands are excluded from runner checks')
    directory=(repo/check['directory']).resolve()
    if not directory.is_relative_to(repo) or not directory.is_dir() or not shutil.which(argv[0]):
        raise RuntimeError('Check directory or executable is unavailable')
    return directory


def clean_env(home, model=False):
    # Never pass Orchestra, GitHub, Cloudflare, AWS or n8n credentials to agent/test code.
    env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'TMPDIR': str(home / 'tmp'),
           'XDG_DATA_HOME': str(home / 'data'), 'XDG_CONFIG_HOME': str(home / 'config'),
           'XDG_CACHE_HOME': str(home / 'cache'), 'CI': 'true', 'GIT_TERMINAL_PROMPT': '0'}
    for name in ['tmp', 'data', 'config', 'cache']:
        (home / name).mkdir(parents=True, exist_ok=True)
    if model:
        env['DEEPSEEK_API_KEY'] = os.environ.get('DEEPSEEK_API_KEY', '')
    return env


def sandbox(worktree, home, network=False, executable=None):
    # Fail closed on unsupported hosts. Agent code cannot read the user's credentials or ledger.
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').exists():
        raise RuntimeError('This first runner requires macOS sandbox-exec; other platforms are disabled')
    def quoted(p):
        return json.dumps(str(Path(p).resolve()))
    runtime = Path(sys.executable).resolve().parents[1]
    node = Path(subprocess.check_output(['which', 'node'], text=True).strip()).resolve().parents[1]
    profile = '(version 1)(allow default)(deny file-read* (subpath ' + quoted(Path.home()) + '))'
    for path in [worktree, home, runtime, node, Path(__file__).resolve().parent.parent / '.venv']:
        profile += '(allow file-read* (subpath ' + quoted(path) + '))'
    if executable:
        profile += '(allow file-read* (literal ' + quoted(shutil.which(executable) or executable) + '))'
    profile += '(allow file-read-metadata)(deny file-write*)'
    for path in [worktree, home, '/dev']:
        profile += '(allow file-write* (subpath ' + quoted(path) + '))'
    if not network:
        profile += '(deny network*) (allow network* (local ip "localhost:*"))'
    return ['/usr/bin/sandbox-exec', '-p', profile]


def agent_config(home):
    # OpenCode v2 uses permissions/shell, not v1's permission/bash.
    # Policies prohibit project config from enabling shell, plugins, MCP or subagents.
    config = {'model': 'deepseek/deepseek-chat', 'permissions': [
        {'action': '*', 'resource': '*', 'effect': 'deny'},
        *[{'action': a, 'resource': '*', 'effect': 'allow'} for a in ['read', 'edit', 'glob', 'grep']],
        {'action': 'external_directory', 'resource': '*', 'effect': 'deny'},
        {'action': 'edit', 'resource': '*opencode*', 'effect': 'deny'},
        {'action': 'edit', 'resource': '.git*', 'effect': 'deny'},
        {'action': 'read', 'resource': '*.env*', 'effect': 'deny'},
    ], 'policies': [
        {'action': 'tool.use', 'resource': r, 'effect': 'deny'}
        for r in ['shell:*', 'subagent:*', 'webfetch:*', 'websearch:*', 'execute:*']],
        'plugins': []}
    dest = home / 'config' / 'opencode'
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'opencode.json').write_text(json.dumps(config))


def redact(value):
    safe = structural_redact(value)
    sensitive = [v for k, v in os.environ.items() if re.search(r'token|password|secret|api.?key', k, re.I) and len(v) >= 8]
    def scrub(item):
        if isinstance(item, str):
            for secret in sensitive:
                item = item.replace(secret, '[redacted]')
        elif isinstance(item, dict):
            return {k: scrub(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [scrub(v) for v in item]
        return item
    return scrub(safe)


class Runner:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.state).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.lock = (self.root / 'runner.lock').open('w')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.ledger = Ledger(self.root / 'ledger.sqlite3')
        token = os.environ['ORCHESTRA_RUNNER_TOKEN']
        url = args.url.rstrip('/')
        if not (url.startswith('https://') or url.startswith('http://127.0.0.1:') or url.startswith('http://localhost:')):
            raise RuntimeError('Runner requires HTTPS except on localhost')
        self.api = httpx.Client(base_url=url + '/api/', headers={'X-Runner-Token': token}, timeout=20)
        self.tasks = TaskResourceApi(ApiClient(Configuration(server_api_url=url + '/api/runner/conductor'),
                                              header_name='X-Runner-Token', header_value=token))

    def request(self, method, path, **kw):
        response = self.api.request(method, path, **kw)
        response.raise_for_status()
        return response.json()

    def preflight(self):
        profile = self.request('GET','runner/profile')
        checks = []
        def check(name, run, detail):
            try:
                ok = bool(run())
            except Exception:
                ok = False
            checks.append({'name':name,'ok':ok,'detail': 'Ready' if ok else detail})
        repo = Path(self.args.repo).resolve()
        check('Repository', lambda: git(repo,'remote','get-url','origin').removesuffix('.git').replace('git@github.com:','https://github.com/') == profile['repo_url'].removesuffix('.git'), 'Clone the paired GitHub repository and set its origin correctly')
        def remote_access():
            env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_SSH_COMMAND':'ssh -o BatchMode=yes'}
            return subprocess.run(['git','-c','core.hooksPath=/dev/null','ls-remote','--exit-code','origin','HEAD'],cwd=repo,env=env,capture_output=True,timeout=10).returncode==0
        check('Repository access',remote_access,'Grant this laptop read access to the paired repository; Git authentication must work without prompts')
        def project_configuration():
            tracked=git(repo,'ls-files','-s').splitlines()
            return not any(line.startswith('120000 ') or any(part in {'.opencode','opencode.json','opencode.jsonc'} for part in line.split('\t')[-1].split('/')) for line in tracked)
        check('Project configuration',project_configuration,'Review and remove tracked symlinks or project OpenCode configuration before managed coding')
        check('Base branch', lambda: git(repo,'rev-parse','--verify',profile['repo_branch']+'^{commit}'), 'Fetch or create the configured local branch')
        def opencode_supported():
            if not shutil.which(self.args.opencode): return False
            home=self.root/'preflight-home'
            result=subprocess.run([self.args.opencode,'run','--help'],env=clean_env(home),capture_output=True,text=True,timeout=20)
            return result.returncode==0 and all(flag in result.stdout for flag in ['--standalone','--format','--model'])
        check('OpenCode', opencode_supported, 'Install a compatible OpenCode CLI with run --standalone --format --model support')
        check('Provider', lambda: os.environ.get('DEEPSEEK_API_KEY'), 'Set DEEPSEEK_API_KEY on this laptop')
        check('Model permission', lambda: self.args.allow_model_calls, 'Start companion with --allow-model-calls only after choosing your usage limit')
        check('Sandbox', lambda: sys.platform=='darwin' and Path('/usr/bin/sandbox-exec').exists(), 'This runner currently requires macOS sandbox-exec')
        check('Local tools', lambda: all(shutil.which(t) for t in ['git','node','npm']), 'Install git, Node and npm')
        def valid_checks():
            config = json.loads(Path(self.args.checks).read_text())
            return bool(config) and all(c.get('name') and validate_check(c,repo) for c in config)
        check('Check commands', valid_checks, 'Configure a nonempty trusted checks JSON file with valid directories and executables')
        publication_ready = bool(shutil.which('gh'))
        if publication_ready:
            publication_ready = subprocess.run(['gh','auth','status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode == 0
        result = self.request('POST','runner/preflight',json={'checks':checks,'publication_ready':publication_ready})
        return result['ready']

    def publication_task(self, task):
        wid = task.input_data['work_id']
        key = 'publish:' + wid
        data = {'work':wid,'task':task.task_id,'workflow':task.workflow_instance_id}
        if not self.ledger.reserve(key,data):
            self.recover_publications()
            return
        # Reserve durably before any git or GitHub write. Redelivery only reconciles.
        self.ledger.save(key,'publication_reserved',data)
        try:
            self.update(data,'IN_PROGRESS')
            self.publish(wid)
            self.ledger.save(key,'publication_done',data)
            self.update(data,'COMPLETED')
            self.ledger.save(key,'publication_reported',data)
        except Exception:
            self.ledger.save(key,'publication_uncertain',data)
            # Preserve the reservation until read-only GitHub reconciliation succeeds.

    def recover_publications(self):
        for key,state,data in self.ledger.entries():
            if not key.startswith('publish:') or state=='publication_reported':
                continue
            if state=='publication_done':
                self.update(data,'COMPLETED'); self.ledger.save(key,'publication_reported',data); continue
            work = self.request('GET',f"runner/work/{data['work']}")
            saved = self.ledger.get(data['work'])
            if not saved:
                continue
            branch = saved[1]['branch']
            # Query all states because a PR may have been merged/closed after an acknowledgment was lost.
            raw = subprocess.check_output(['gh','pr','list','--repo',work['repo_url'],'--head',branch,'--state','all','--json','url,headRefOid'],text=True,timeout=20)
            matches = [p for p in json.loads(raw) if p.get('headRefOid')==work['approved_sha']]
            if len(matches)==1:
                self.request('POST','runner/publication',json={'work_id':data['work'],'sha':work['approved_sha'],'state':'published','pr_url':matches[0]['url']})
                self.ledger.save(key,'publication_done',data)
                if work.get('publication_execution_status') in TERMINAL:
                    self.request('POST',f"runner/publication/stopped/{data['work']}")
                else:
                    self.update(data,'COMPLETED')
                self.ledger.save(key,'publication_reported',data)
            else:
                self.request('POST','runner/publication',json={'work_id':data['work'],'sha':work['approved_sha'],'state':'unknown'})
                if work.get('publication_execution_status') in TERMINAL:
                    self.request('POST',f"runner/publication/stopped/{data['work']}")
                    self.ledger.save(key,'publication_reported',data)
                else:
                    self.update(data,'IN_PROGRESS')

    def update(self, data, status):
        self.tasks.update_task(TaskResult(workflow_instance_id=data['workflow'], task_id=data['task'],
                                         status=status, output_data={'work_id': data['work']},
                                         callback_after_seconds=0))

    def process(self, task):
        try:
            self._process(task)
        except Exception as error:
            wid=task.input_data['work_id']
            saved=self.ledger.get(wid)
            if saved and saved[0] in {'reserved','checking'}:
                data=saved[1]
                phase='Preparation' if saved[0]=='reserved' else 'Evidence/check collection'
                data['artifacts']={'phase':'failed','tests_passed':False,'summary':f'{phase} failed ({type(error).__name__}). Inspect the local checkout, dependency installation and check configuration. No automatic model retry is allowed.'}
                self.ledger.save(wid,'finished',data)
            else:
                # Launching/running may have made a paid call. Keep the uncertain reservation.
                raise

    def _process(self, task):
        wid = task.input_data['work_id']
        data = {'work': wid, 'task': task.task_id, 'workflow': task.workflow_instance_id}
        if not self.ledger.reserve(wid,data):
            # Task redelivery cannot relaunch the agent, even after a process crash.
            return
        self.ledger.save(wid, 'reserved', data)
        work = self.request('GET', f'runner/work/{wid}')
        if work.get('execution_status') in TERMINAL or work.get('submission') == 'cancelled':
            data['artifacts'] = {'summary': 'Cancelled before agent launch', 'tests_passed': False}
            self.ledger.save(wid, 'finished', data)
            return
        if not self.args.allow_model_calls or not work['model_approved']:
            data['artifacts'] = {'summary': 'Model calls not enabled on this runner', 'tests_passed': False}
            self.ledger.save(wid, 'finished', data)
            return
        repo = Path(self.args.repo).resolve()
        remote = git(repo, 'remote', 'get-url', 'origin').removesuffix('.git').replace('git@github.com:', 'https://github.com/')
        if remote != work['repo_url'].removesuffix('.git').replace('git@github.com:', 'https://github.com/').replace('http://github.com/', 'https://github.com/'):
            raise RuntimeError('Paired repository does not match this checkout')
        if not os.environ.get('DEEPSEEK_API_KEY'):
            raise RuntimeError('DEEPSEEK_API_KEY is required; no provider call was made')
        base = git(repo, 'rev-parse', '--verify', f"{work['repo_branch']}^{{commit}}")
        tree = self.root / ('work-' + wid)
        branch = 'codex/work-' + wid
        git(repo, 'worktree', 'add', '-b', branch, str(tree), base)
        home = self.root / ('agent-' + wid)
        home.mkdir(mode=0o700)
        env = clean_env(home, model=True)
        agent_config(home)
        # Reject repository-supplied executable config before launching. Instructions remain data.
        forbidden = [p for p in tree.rglob('*') if '.git' not in p.parts and
                     (p.name in {'opencode.json', 'opencode.jsonc', '.opencode'} or p.is_symlink())]
        if forbidden:
            raise RuntimeError('Remove/review project OpenCode configuration and symlinks before managed execution')
        prompt = (f"Implement this request in this worktree only. Do not publish, deploy, call application APIs, "
                  f"or modify credentials. Shell tools are disabled; tests run separately.\n"
                  f"Request: {work['request']}\nAcceptance: {work['acceptance']}")
        # Install only locked dependencies with lifecycle scripts disabled, before agent edits.
        checks_config = json.loads(Path(self.args.checks).read_text())
        for directory_name in sorted({c['directory'] for c in checks_config}):
            directory = (tree / directory_name).resolve()
            if not directory.is_relative_to(tree):
                raise RuntimeError('Check path escapes worktree')
            if (directory / 'package-lock.json').exists():
                self.update(data, 'IN_PROGRESS')
                subprocess.run(sandbox(tree, home, network=True) + ['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
                               cwd=directory, env=clean_env(home), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=90)
        current = self.request('GET', f'runner/work/{wid}')
        if current['execution_status'] in TERMINAL or current['submission'] == 'cancelled':
            data['artifacts'] = {'summary': 'Cancelled before agent launch', 'tests_passed': False}
            self.ledger.save(wid, 'finished', data)
            return
        output = home / 'session.jsonl'
        self.ledger.save(wid,'launching',data)
        with output.open('w') as stream:
            process = subprocess.Popen(sandbox(tree, home, network=True,executable=self.args.opencode) + [self.args.opencode, 'run', '--standalone',
                                       '--model', 'deepseek/deepseek-chat', '--format', 'json', prompt],
                                       cwd=tree, env=env, stdout=stream, stderr=stream, start_new_session=True)
            data.update({'pid': process.pid, 'tree': str(tree), 'base_sha': base, 'branch': branch})
            self.ledger.save(wid, 'running', data)
            deadline = time.monotonic() + work.get("model_budget_seconds",600)
            disconnected = False
            while process.poll() is None:
                time.sleep(5)
                try:
                    current = self.request('GET', f'runner/work/{wid}')
                    stop = current['execution_status'] in TERMINAL or current['submission'] == 'cancelled'
                    self.update(data, 'IN_PROGRESS')
                    self.request('POST', 'runner/artifacts', json={'work_id': wid, 'data': {
                        'phase': 'coding', 'summary': 'OpenCode is working in the isolated worktree',
                        'base_sha': base, 'branch': branch, 'tests_passed': False}})
                except Exception:
                    stop, disconnected = True, True
                if stop or time.monotonic() > deadline:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    break
        self.ledger.save(wid,'checking',data)
        # Raw transcripts stay local. Upload only a bounded text summary and session identifier.
        session, summary = None, ''
        for line in output.read_text(errors='replace').splitlines():
            try:
                event = json.loads(line)
                session = event.get('sessionID') or event.get('sessionId') or session
                part = event.get('part') or {}
                if event.get('type') == 'text':
                    summary = str(part.get('text') or event.get('text') or '')[-4000:]
            except ValueError:
                continue
        changed = git(tree, 'diff', '--name-only', base).splitlines()
        changed += git(tree, 'ls-files', '--others', '--exclude-standard').splitlines()
        checks = []
        self.request('POST','runner/artifacts',json={'work_id':wid,'data':{'phase':'checks','summary':'Running configured local checks','tests_passed':False}})
        # Trusted commands are configured locally; never accept commands from server/task output.
        for check in checks_config:
            directory = validate_check(check,tree)
            if process.returncode != 0 or disconnected:
                break
            current = self.request('GET', f'runner/work/{wid}')
            if current['execution_status'] in TERMINAL:
                break
            self.update(data, 'IN_PROGRESS')
            # This fixed host operation already runs to collect review evidence. It reads
            # Git metadata without exposing that metadata to untrusted test code.
            command = ['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','diff','--no-ext-diff','--no-textconv','--check'] if check['argv']==['git','diff','--check'] else sandbox(tree,home)+check['argv']
            try:
                result = subprocess.run(command, cwd=directory,env=clean_env(home),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90)
            except subprocess.TimeoutExpired:
                checks.append({'name':check['name'],'passed':False,'output':'Check timed out after 90 seconds'})
                break
            checks.append({'name': check['name'], 'passed': result.returncode == 0,
                           'output': redact(result.stdout[-4000:])})
        if any(Path(name).name.startswith('.env') or any(piece in {'.aws', '.ssh', '.opencode'} for piece in Path(name).parts)
               or Path(name).suffix in {'.pem', '.key'} for name in changed):
            raise RuntimeError('Credential/configuration files require manual review; no commit or publication was made')
        # Commit locally after tests so approval can bind to an immutable object. Hooks are disabled.
        git(tree, 'add', '--all')
        git(tree, '-c', 'user.name=Orchestra Runner', '-c', 'user.email=runner@orchestra.local',
            'commit', '--allow-empty', '-m', work['title'])
        head = git(tree, 'rev-parse', 'HEAD')
        data['artifacts'] = redact({'base_sha': base, 'head_sha': head, 'branch': branch,
                                   'session_id': session, 'summary': summary or (f'OpenCode exited with status {process.returncode}. Check the local transcript and provider configuration; no automatic retry.' if process.returncode else 'See local session transcript'),
                                   'changed_files': sorted(set(changed)), 'diff': git(tree, 'diff', '--no-ext-diff', base, head)[:20000], 'checks': checks,
                                   'tests_passed': len(checks) == len(checks_config) and bool(checks) and all(c['passed'] for c in checks) and process.returncode == 0 and not disconnected,
                                   'dirty': bool(git(tree, 'status', '--porcelain'))})
        self.ledger.save(wid, 'finished', data)

    def recover(self):
        for wid, state, data in self.ledger.entries():
            if wid.startswith('publish:'):
                continue
            if state in {'reserved', 'launching','running','checking'}:
                # Never assume a process died with the runner. Keep project reserved until the
                # operator stops/reconciles it; automatic reruns would risk duplicate model calls.
                print(f'{wid}: interrupted/uncertain; inspect local process and worktree, then use resolve', flush=True)
                continue
            if state != 'finished':
                continue
            self.request('POST', 'runner/artifacts', json={'work_id': wid, 'data': data['artifacts']})
            work = self.request('GET', f'runner/work/{wid}')
            if work['execution_status'] not in TERMINAL:
                self.update(data, 'COMPLETED' if data['artifacts'].get('tests_passed') else 'FAILED')
            self.request('POST', f'runner/stopped/{wid}')
            self.ledger.save(wid, 'reported', data)

    def publish(self, wid):
        saved = self.ledger.get(wid)
        if not saved or saved[0] != 'reported':
            raise RuntimeError('No completed local evidence for this work request')
        data = saved[1]
        work = self.request('GET', f'runner/work/{wid}')
        tree = Path(data['tree'])
        sha = git(tree, 'rev-parse', 'HEAD')
        if git(tree, 'status', '--porcelain') or sha != work['approved_sha'] or not work['publish_approved']:
            raise RuntimeError('Exact clean commit must be approved for publication')
        if work['publication'].get('state') in {'publishing', 'unknown', 'published'}:
            raise RuntimeError('Publication already attempted; reconcile on GitHub before retrying')
        payload = {'work_id': wid, 'sha': sha, 'state': 'publishing'}
        self.request('POST', 'runner/publication', json=payload)
        try:
            git(tree, 'push', 'origin', f"{sha}:refs/heads/{data['branch']}")
            current=self.request('GET',f'runner/work/{wid}')
            if current.get('publication_execution_status') in TERMINAL or current.get('publication_submission')=='cancelled':
                raise RuntimeError('Publication interrupted after push; reconcile GitHub without another write')
            body = self.root / ('pr-' + wid + '.md')
            body.write_text('Implements: ' + work['title'] + '\n\n' + work['acceptance'] + '\n\nValidation evidence is recorded in Orchestra.\n')
            url = subprocess.check_output(['gh', 'pr', 'create', '--repo', work['repo_url'],
                                          '--head', data['branch'], '--base', work['repo_branch'],
                                          '--title', work['title'], '--body-file', str(body), '--draft'],
                                         cwd=tree, text=True,timeout=30).strip()
            self.request('POST', 'runner/publication', json={**payload, 'state': 'published', 'pr_url': url})
        except Exception:
            self.request('POST', 'runner/publication', json={**payload, 'state': 'unknown'})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--state', required=True)
    parser.add_argument('--checks', required=True, help='Trusted local JSON check commands; see docs')
    parser.add_argument('--opencode', default='opencode')
    parser.add_argument('--allow-model-calls', action='store_true')
    parser.add_argument('--publish', metavar='WORK_ID', help='Publish an exact, server-approved commit; explicit operator action')
    parser.add_argument('--resolve', metavar='WORK_ID', help='After manually stopping orphan processes, record an interrupted run as failed')
    args = parser.parse_args()
    runner = Runner(args)
    if args.publish:
        runner.publish(args.publish)
        return
    if args.resolve:
        saved = runner.ledger.get(args.resolve)
        if not saved or saved[0] not in {'reserved','launching','running','checking'}:
            raise RuntimeError('No interrupted session to reconcile')
        data = saved[1]
        data['artifacts'] = {'summary': 'Operator reconciled interrupted session; no automatic retry', 'tests_passed': False}
        runner.ledger.save(args.resolve, 'finished', data)
        runner.recover()
        return
    while True:
        try:
            runner.recover()
            runner.recover_publications()
            ready = runner.preflight()
            publication = runner.tasks.poll('cp_project_publish')
            if publication:
                runner.publication_task(publication)
                continue
            if not ready:
                time.sleep(5)
                continue
            task = runner.tasks.poll(TASK)
            if task:
                runner.process(task)
            else:
                time.sleep(5)
        except KeyboardInterrupt:
            return
        except Exception as error:
            # Keep exception contents/credentials out of console output.
            print(f'runner waiting: {type(error).__name__}; inspect local state before retrying', flush=True)
            time.sleep(10)


if __name__ == '__main__':
    main()
