"""Read-only Conductor telemetry: Prometheus counters plus per-queue depth.

Everything here is measured by the engine itself. Nothing is estimated, and a
missing series is reported as zero-with-context or as unavailable — never faked.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

METRIC_LINE = re.compile(
    r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>\S+)$'
)
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def parse_prometheus(text: str) -> list[tuple[str, dict[str, str], float]]:
    samples = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = METRIC_LINE.match(line)
        if not match:
            continue
        try:
            value = float(match.group('value'))
        except ValueError:
            continue
        labels = dict(LABEL.findall(match.group('labels') or ''))
        samples.append((match.group('name'), labels, value))
    return samples


def _sum(samples, name: str, **labels) -> float:
    total = 0.0
    for metric, sample_labels, value in samples:
        if metric != name:
            continue
        if any(sample_labels.get(key) != expected for key, expected in labels.items()):
            continue
        total += value
    return total


def summarise(samples, task_names: list[str]) -> dict:
    failures: dict[str, float] = {}
    for metric, labels, value in samples:
        if metric == 'workflow_failure_total':
            status = labels.get('status', 'UNKNOWN')
            failures[status] = failures.get(status, 0) + value
    execution_count = _sum(samples, 'task_execution_seconds_count')
    execution_sum = _sum(samples, 'task_execution_seconds_sum')
    wait_count = _sum(samples, 'task_queue_wait_seconds_count')
    wait_sum = _sum(samples, 'task_queue_wait_seconds_sum')
    heap_used = sum(value for metric, labels, value in samples
                    if metric == 'jvm_memory_used_bytes' and labels.get('area') == 'heap')
    heap_max = sum(value for metric, labels, value in samples
                   if metric == 'jvm_memory_max_bytes' and labels.get('area') == 'heap')
    polls = {labels.get('taskType'): value for metric, labels, value in samples
             if metric == 'task_poll_total' and labels.get('taskType') in task_names}
    return {
        'workflow_failures': {key: int(value) for key, value in sorted(failures.items())},
        'workflow_start_success': int(_sum(samples, 'workflow_start_success_total')),
        'tasks_in_flight': int(_sum(samples, 'tasks_in_workflow')),
        'task_poll_total': {key: int(value) for key, value in sorted(polls.items())},
        'task_execution_ms': round(execution_sum / execution_count * 1000, 1) if execution_count else None,
        'task_queue_wait_ms': round(wait_sum / wait_count * 1000, 1) if wait_count else None,
        'heap_used_mb': round(heap_used / 1024 / 1024, 1) if heap_used else None,
        'heap_max_mb': round(heap_max / 1024 / 1024, 1) if heap_max else None,
        'uptime_seconds': round(_sum(samples, 'process_uptime_seconds'), 1),
    }


async def collect(settings, engine, task_names: list[str]) -> dict:
    """Fetch engine metrics and queue depth. Returns `available: false` with a reason on failure."""
    sampled_at = datetime.now(timezone.utc).isoformat()
    metrics_url = settings.conductor_metrics_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(metrics_url)
        if response.status_code != 200 or not response.text:
            return {'available': False, 'sampled_at': sampled_at,
                    'error': f'metrics endpoint returned HTTP {response.status_code}', 'source': metrics_url}
        summary = summarise(parse_prometheus(response.text), task_names)
    except httpx.HTTPError as exc:
        return {'available': False, 'sampled_at': sampled_at,
                'error': f'engine metrics unreachable ({type(exc).__name__})', 'source': metrics_url}

    queues = []
    for name in task_names:
        try:
            depth = await engine.request('GET', 'tasks/queue/size', params={'taskType': name})
            queues.append({'task': name, 'depth': int(depth or 0)})
        except HTTPException:
            queues.append({'task': name, 'depth': None})
    summary.update({'available': True, 'sampled_at': sampled_at, 'source': metrics_url, 'queues': queues})
    return summary
