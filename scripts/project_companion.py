"""One companion supervising explicitly paired profiles. Config and credentials stay local.

Usage: python scripts/project_companion.py --profiles /private/path/profiles.json
Each profile: name,url,repo,state,checks,token_env,provider_key_env,allow_model_calls.
A profile starts its existing durable runner; separate state directories are required.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles',required=True)
    args=parser.parse_args()
    profiles=json.loads(Path(args.profiles).read_text())
    states=[str(Path(p['state']).resolve()) for p in profiles]
    if len(set(states))!=len(states):
        raise ValueError('Each paired project needs its own durable state directory')
    children=[]
    try:
        for p in profiles:
            env=dict(os.environ)
            env['ORCHESTRA_RUNNER_TOKEN']=os.environ[p['token_env']]
            env['DEEPSEEK_API_KEY']=os.environ.get(p['provider_key_env'],'')
            if p.get('github_token_env'):
                env['GH_TOKEN']=os.environ[p['github_token_env']]
            if p.get('gh_config_dir'):
                env['GH_CONFIG_DIR']=p['gh_config_dir']
            command=[sys.executable,str(Path(__file__).with_name('project_runner.py'))]
            for field in ['url','repo','state','checks']:
                command += ['--'+field,p[field]]
            if p.get('allow_model_calls',False): command.append('--allow-model-calls')
            children.append(subprocess.Popen(command,env=env))
        while all(p.poll() is None for p in children): time.sleep(1)
    finally:
        for p in children:
            if p.poll() is None: p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()

if __name__=='__main__': main()
