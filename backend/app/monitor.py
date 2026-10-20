"""Background health collector. Runs inside the API process and never relies on browsers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from .connectors import USER_AGENT, probe_http
from .security import resolve_public
from .store import Store

log = logging.getLogger('orchestra.monitor')

COLLECTOR_LOCK = 918273  # one collector per database, across replicas


async def deliver_alerts(store: Store, incident: dict, allow_private: bool = False) -> None:
    for alert in store.eligible_alerts(incident):
        try:
            target = store.secrets.open(alert['target'])
            resolve_public(target, allow_private=allow_private)
        except Exception as exc:
            store.record_notification(incident['id'], alert['id'], 'failed',
                                      f'webhook target rejected: {type(exc).__name__}')
            continue
        payload = {
            'event': 'incident.opened',
            'incident': {
                'id': str(incident['id']), 'title': incident['title'],
                'severity': incident['severity'], 'openedAt': incident['opened_at'],
                'projectId': str(incident['project_id']),
                'serviceId': str(incident['service_id']),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={'User-Agent': USER_AGENT}) as client:
                response = await client.post(target, json=payload)
            ok = 200 <= response.status_code < 300
            store.record_notification(incident['id'], alert['id'],
                                      'sent' if ok else 'failed',
                                      None if ok else f'HTTP {response.status_code}')
        except httpx.HTTPError as exc:
            store.record_notification(incident['id'], alert['id'], 'failed', type(exc).__name__)


async def check_service(store: Store, settings, service: dict) -> dict:
    """Probe one service, persist the observation and apply state/incident transitions."""
    result = await probe_http(
        service['health_url'],
        timeout=float(service['timeout_seconds']),
        expected_status=int(service['expected_status']),
        allow_private=settings.http_check_allow_private,
    )
    observation = store.record_observation(
        service['id'], status=result.status, source=result.source,
        latency_ms=result.latency_ms, http_status=result.http_status,
        message=result.message, evidence=result.evidence,
    )
    updated = store.apply_observation(service, observation)
    previous, current = updated['_previous_status'], updated['current_status']
    store.recompute_project_status(service['project_id'])
    if current != previous:
        log.info('service %s %s -> %s', service['name'], previous, current)
        if current in ('down', 'degraded'):
            incident, created = store.open_incident(updated, observation)
            if created and incident:
                await deliver_alerts(store, incident, settings.http_check_allow_private)
        elif current == 'healthy' and previous in ('down', 'degraded'):
            store.resolve_incidents_for_service(
                service['id'],
                f'Automatically recovered: {observation["message"] or "healthy response"}',
            )
    return {'observation': observation, 'service': updated, 'previousStatus': previous}


class Collector:
    def __init__(self, store: Store, settings):
        self.store = store
        self.settings = settings
        self._stopped = asyncio.Event()
        self._last_prune: datetime | None = None

    async def run(self) -> None:
        log.info('monitoring collector started (tick=%ss)', self.settings.monitor_tick_seconds)
        while not self._stopped.is_set():
            try:
                await self.tick()
            except Exception:  # keep the collector alive; never crash the API
                log.exception('monitoring tick failed')
            try:
                await asyncio.wait_for(self._stopped.wait(), self.settings.monitor_tick_seconds)
            except asyncio.TimeoutError:
                continue
        log.info('monitoring collector stopped')

    def stop(self) -> None:
        self._stopped.set()

    async def tick(self) -> int:
        with self.store.db.connection() as conn:
            acquired = conn.execute(
                'SELECT pg_try_advisory_lock(%s) AS ok', (COLLECTOR_LOCK,)
            ).fetchone()['ok']
            if not acquired:
                return 0
            try:
                checked = await self._run_due()
            finally:
                conn.execute('SELECT pg_advisory_unlock(%s)', (COLLECTOR_LOCK,))
            self._prune_if_due()
            return checked

    def _prune_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_prune and (now - self._last_prune).total_seconds() < 3600:
            return
        self._last_prune = now
        try:
            log.info('retention prune %s', self.store.prune())
        except Exception:
            log.exception('retention prune failed')

    async def _run_due(self) -> int:
        services = self.store.due_services(limit=max(5, self.settings.monitor_concurrency * 5))
        if not services:
            return 0
        semaphore = asyncio.Semaphore(self.settings.monitor_concurrency)

        async def guarded(service):
            async with semaphore:
                try:
                    await check_service(self.store, self.settings, service)
                except Exception:
                    log.exception('check failed for service %s', service['id'])

        await asyncio.gather(*(guarded(s) for s in services))
        return len(services)


async def main() -> None:  # pragma: no cover - manual runtime entrypoint
    import logging as _logging

    from .db import Database
    from .security import SecretBox
    from .settings import Settings

    _logging.basicConfig(level=_logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    settings = Settings()
    db = Database(settings)
    db.initialize()
    store = Store(db, settings, SecretBox.from_settings(settings))
    await Collector(store, settings).run()


if __name__ == '__main__':  # pragma: no cover
    asyncio.run(main())
