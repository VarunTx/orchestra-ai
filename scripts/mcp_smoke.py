"""Live stdio smoke test for the MCP server against a running control plane.

    CONTROL_PLANE_TOKEN=... python scripts/mcp_smoke.py [base_url]

Read-only: it lists tools and calls only the read tools.
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'


def _text(result) -> str:
    parts = [c.text for c in result.content if getattr(c, 'text', None)]
    return ' '.join(parts)


async def main() -> int:
    token = os.environ.get('CONTROL_PLANE_TOKEN', '')
    if not token:
        print('CONTROL_PLANE_TOKEN is required', file=sys.stderr)
        return 2
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'app.mcp_server'],
        env={**os.environ, 'CONTROL_PLANE_TOKEN': token, 'CONTROL_PLANE_URL': BASE},
        cwd='backend',
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f'connected: {info.server_info.name}')
            tools = await session.list_tools()
            print('tools:', ', '.join(sorted(t.name for t in tools.tools)))

            checks = [
                ('infrastructure_health', {}),
                ('list_executions', {'size': 3}),
                ('list_workflow_definitions', {}),
                ('list_incidents', {}),
            ]
            failures = 0
            for name, args in checks:
                result = await session.call_tool(name, args)
                status = 'ERROR' if result.is_error else 'ok'
                if result.is_error:
                    failures += 1
                payload = _text(result)
                print(f'{status:5} {name}: {payload[:240]}')

            denied = await session.call_tool(
                'start_diagnostic', {'service': 'smoke', 'logs': 'x' * 20})
            text = _text(denied)
            blocked = denied.is_error and 'MCP_ENABLE_WRITES' in text
            print(f'{"ok" if blocked else "FAIL":5} start_diagnostic gated: {text[:160]}')
            return 0 if failures == 0 and blocked else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
