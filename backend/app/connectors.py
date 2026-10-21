"""Connector adapters. All provider calls are read-only and never touch browser code."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from psycopg.types.json import Jsonb

from .security import UnsafeTarget, resolve_public

USER_AGENT = 'OrchestraAI/2.0 (+self-hosted control plane)'
HTTP_TIMEOUT = 10.0
MAX_BODY = 2048


@dataclass
class ProbeResult:
    status: str
    source: str = 'http'
    latency_ms: int | None = None
    http_status: int | None = None
    message: str = ''
    evidence: dict[str, Any] = field(default_factory=dict)


def _classify(code: int, expected: int) -> str:
    if code == expected:
        return 'healthy'
    if 200 <= code < 300:
        return 'degraded'
    return 'down'


async def probe_http(url: str, *, timeout: float, expected_status: int,
                     allow_private: bool) -> ProbeResult:
    """Perform one bounded health check with SSRF protection and no redirects."""
    try:
        target = resolve_public(url, allow_private=allow_private)
    except UnsafeTarget as exc:
        # The target is unusable, which is a monitoring problem, not an application failure.
        return ProbeResult('unknown', message=f'check not performed: {exc}')
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False,
                                     headers={'User-Agent': USER_AGENT}) as client:
            async with client.stream('GET', target) as response:
                body = 0
                async for chunk in response.aiter_bytes():
                    body += len(chunk)
                    if body >= MAX_BODY:
                        break
                elapsed = int((time.monotonic() - started) * 1000)
                status = _classify(response.status_code, expected_status)
                message = f'HTTP {response.status_code} in {elapsed} ms'
                if 300 <= response.status_code < 400:
                    message += ' (redirects are not followed)'
                return ProbeResult(
                    status, latency_ms=elapsed, http_status=response.status_code,
                    message=message,
                    evidence={'content_type': response.headers.get('content-type', ''),
                              'bytes_read': body, 'redirected': 300 <= response.status_code < 400},
                )
    except httpx.TimeoutException:
        return ProbeResult('down', latency_ms=int((time.monotonic() - started) * 1000),
                           message=f'no response within {timeout:.0f}s')
    except httpx.HTTPError as exc:
        return ProbeResult('down', latency_ms=int((time.monotonic() - started) * 1000),
                           message=f'request failed: {type(exc).__name__}')


class ConnectorError(RuntimeError):
    """Provider failure. The message is safe to store and show."""


@dataclass
class ProviderSnapshot:
    services: list[dict] = field(default_factory=list)
    ci_runs: list[dict] = field(default_factory=list)
    pull_requests: list[dict] = field(default_factory=list)
    notes: str = ''


class RailwayConnector:
    """Railway public GraphQL API. Read-only; requires a project or account token."""

    provider = 'railway'
    endpoint = 'https://backboard.railway.app/graphql/v2'

    def __init__(self, token: str, endpoint: str | None = None):
        self.token = token
        self.endpoint = endpoint or self.endpoint

    async def _query(self, query: str, variables: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
        }) as client:
            try:
                response = await client.post(self.endpoint, json={'query': query, 'variables': variables or {}})
            except httpx.HTTPError as exc:
                raise ConnectorError(f'Railway request failed ({type(exc).__name__})') from None
        if response.status_code in (401, 403):
            raise ConnectorError('Railway rejected the token (HTTP %s)' % response.status_code)
        if response.status_code == 429:
            raise ConnectorError('Railway rate limit reached')
        if response.status_code >= 400:
            raise ConnectorError(f'Railway returned HTTP {response.status_code}')
        payload = response.json()
        if payload.get('errors'):
            first = payload['errors'][0].get('message', 'unknown error')
            raise ConnectorError(f'Railway API error: {first[:200]}')
        return payload.get('data') or {}

    async def validate(self) -> dict:
        data = await self._query('query { me { id name } }')
        me = data.get('me') or {}
        return {'account': me.get('name') or me.get('id') or 'unknown'}

    async def collect(self) -> ProviderSnapshot:
        query = """
        query {
          me {
            projects {
              edges { node {
                id name
                services { edges { node { id name } } }
                environments { edges { node { id name } } }
              } }
            }
          }
        }
        """
        data = await self._query(query)
        projects = (((data.get('me') or {}).get('projects') or {}).get('edges')) or []
        services: list[dict] = []
        for edge in projects:
            node = edge.get('node') or {}
            environments = [e['node']['name'] for e in ((node.get('environments') or {}).get('edges') or [])]
            for service_edge in ((node.get('services') or {}).get('edges') or []):
                service = service_edge.get('node') or {}
                services.append({
                    'externalId': service.get('id'),
                    'name': service.get('name') or 'Railway service',
                    'project': node.get('name'),
                    'projectId': node.get('id'),
                    'environments': environments,
                })
        return ProviderSnapshot(services=services,
                                notes='Railway reports service inventory; per-service health is not exposed by this query.')


class GitHubConnector:
    """GitHub REST API. Public read-only metadata, commits and workflow runs."""

    provider = 'github'
    endpoint = 'https://api.github.com'

    def __init__(self, token: str = '', endpoint: str | None = None):
        self.token = token
        self.endpoint = endpoint or self.endpoint

    def _headers(self) -> dict:
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': USER_AGENT,
                   'X-GitHub-Api-Version': '2022-11-28'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    async def _get(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=self._headers()) as client:
            try:
                response = await client.get(self.endpoint + path)
            except httpx.HTTPError as exc:
                raise ConnectorError(f'GitHub request failed ({type(exc).__name__})') from None
        if response.status_code == 404:
            raise ConnectorError('GitHub repository not found or not accessible')
        if response.status_code in (401, 403):
            remaining = response.headers.get('x-ratelimit-remaining', '')
            if remaining == '0':
                raise ConnectorError('GitHub rate limit exhausted for this token')
            raise ConnectorError(f'GitHub rejected the request (HTTP {response.status_code})')
        if response.status_code >= 400:
            raise ConnectorError(f'GitHub returned HTTP {response.status_code}')
        return response.json()

    async def validate(self) -> dict:
        if not self.token:
            await self._get('/rate_limit')
            return {'account': 'Public repositories (unauthenticated)'}
        user = await self._get('/user')
        return {'account': user.get('login', 'unknown')}

    @staticmethod
    def repo_path(repo_url: str) -> str:
        slug = repo_url.rstrip('/').removesuffix('.git')
        for prefix in ('https://github.com/', 'http://github.com/', 'git@github.com:'):
            if slug.startswith(prefix):
                slug = slug[len(prefix):]
                break
        parts = slug.split('/')
        if len(parts) < 2 or not all(parts[:2]):
            raise ConnectorError('Repository URL must look like https://github.com/owner/name')
        return f'{parts[0]}/{parts[1]}'

    async def collect_repo(self, repo_url: str) -> ProviderSnapshot:
        repo = self.repo_path(repo_url)
        meta = await self._get(f'/repos/{repo}')
        commits = await self._get(f'/repos/{repo}/commits?per_page=10')
        runs = await self._get(f'/repos/{repo}/actions/runs?per_page=10')
        pulls = await self._get(f'/repos/{repo}/pulls?state=all&per_page=20')
        deployments = []
        for run in (runs.get('workflow_runs') or []):
            deployments.append({
                'externalId': 'github-run-' + str(run.get('id')),
                'version': run.get('head_branch'),
                'commitSha': run.get('head_sha', ''),
                'status': run.get('conclusion') or run.get('status') or 'unknown',
                'url': run.get('html_url'),
                'deployedAt': run.get('updated_at'),
                'detail': {'workflow': run.get('name'), 'event': run.get('event')},
            })
        return ProviderSnapshot(
            ci_runs=deployments,
            pull_requests=[{'number':p.get('number'),'title':p.get('title'),'state':p.get('state'),'draft':p.get('draft'),'url':p.get('html_url'),'head_sha':(p.get('head') or {}).get('sha'),'updated_at':p.get('updated_at')} for p in pulls],
            notes=f"{meta.get('full_name')}: default branch {meta.get('default_branch')}, "
                  f"{len(commits)} recent commits, {len(deployments)} workflow runs. "
                  f"Latest commit {commits[0]['sha'][:7] if commits else 'none'}.",
        )


async def verify_generic_webhook(url: str) -> None:
    resolve_public(url, allow_private=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def jsonb(value: dict) -> Jsonb:
    return Jsonb(value)


CONNECTOR_TYPES = {'railway': RailwayConnector, 'github': GitHubConnector}
