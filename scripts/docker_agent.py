"""Push local Docker container health to Orchestra AI.

Runs on the machine that owns the Docker daemon. It only reads `docker ps` and
posts observations; it never accepts commands from the platform.

    ORCHESTRA_URL=http://127.0.0.1:8000 \
    AGENT_TOKEN=<docker connector token> \
    AGENT_INTERVAL=30 \
    python3 scripts/docker_agent.py

Container names are reported as agent keys. Link a service to a key by setting
`external_ref` to {"agentKey": "<container name>"}.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import httpx

ORCHESTRA_URL = os.getenv('ORCHESTRA_URL', 'http://127.0.0.1:8000').rstrip('/')
AGENT_TOKEN = os.environ['AGENT_TOKEN']
INTERVAL = max(10, int(os.getenv('AGENT_INTERVAL', '30')))
PREFIX = os.getenv('AGENT_PREFIX', '')


def containers() -> list[dict]:
    result = subprocess.run(
        ['docker', 'ps', '-a', '--format', '{{json .}}'],
        capture_output=True, text=True, check=True, timeout=20,
    )
    found = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        name = row.get('Names') or row.get('ID', '')
        status = row.get('Status', '')
        healthy = 'Up' in status and 'unhealthy' not in status.lower()
        found.append({
            'agent_key': name,
            'status': 'healthy' if healthy else 'down',
            'message': status[:500] or 'no container status',
        })
    return found


def main() -> int:
    if not AGENT_TOKEN:
        print('AGENT_TOKEN is required', file=sys.stderr)
        return 2
    headers = {'X-Agent-Token': AGENT_TOKEN, 'Content-Type': 'application/json'}
    with httpx.Client(base_url=ORCHESTRA_URL, timeout=15) as client:
        while True:
            try:
                for observation in containers():
                    if PREFIX and not observation['agent_key'].startswith(PREFIX):
                        continue
                    response = client.post('/api/agent/observations', json=observation, headers=headers)
                    if response.status_code == 404:
                        print(f"skip {observation['agent_key']}: no linked service", flush=True)
                    elif response.status_code >= 400:
                        print(f"rejected {observation['agent_key']}: HTTP {response.status_code}", flush=True)
                    else:
                        print(f"sent {observation['agent_key']} -> {response.json().get('status')}", flush=True)
            except subprocess.CalledProcessError as exc:
                print(f'docker ps failed: {exc}', file=sys.stderr, flush=True)
            except httpx.HTTPError as exc:
                print(f'orchestra unreachable: {type(exc).__name__}', file=sys.stderr, flush=True)
            time.sleep(INTERVAL)


if __name__ == '__main__':
    raise SystemExit(main())
