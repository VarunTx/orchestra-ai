import asyncio

import httpx

from app import connectors


def test_health_probe_deadline_bounds_slow_stream(monkeypatch):
    class SlowStream(httpx.AsyncByteStream):
        chunks = 0
        closed = False

        async def __aiter__(self):
            for _ in range(20):
                await asyncio.sleep(0.01)
                self.chunks += 1
                yield b'x'

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    client = httpx.AsyncClient(transport=transport)
    monkeypatch.setattr(connectors.httpx, 'AsyncClient', lambda **kwargs: client)
    monkeypatch.setattr(connectors, 'resolve_public', lambda url, **kwargs: url)
    result = asyncio.run(connectors.probe_http(
        'https://probe.example/health', timeout=0.05,
        expected_status=200, allow_private=False,
    ))
    assert result.status == 'down'
    assert 'within' in result.message
    assert stream.chunks < 20
    assert stream.closed


def test_slow_dns_is_unknown_without_blocking_event_loop(monkeypatch):
    import time

    def slow_resolve(url, **kwargs):
        time.sleep(0.2)
        return url

    requested = []
    transport = httpx.MockTransport(
        lambda request: (requested.append(request) or httpx.Response(200, content=b'ok')))
    client = httpx.AsyncClient(transport=transport)
    monkeypatch.setattr(connectors.httpx, 'AsyncClient', lambda **kwargs: client)
    monkeypatch.setattr(connectors, 'resolve_public', slow_resolve)

    async def scenario():
        heartbeat = asyncio.Event()
        asyncio.get_running_loop().call_later(0.01, heartbeat.set)
        started = time.monotonic()
        result = await connectors.probe_http(
            'https://probe.example/health', timeout=0.05,
            expected_status=200, allow_private=False,
        )
        elapsed = time.monotonic() - started
        try:
            assert result.status == 'unknown'
            assert 'resolution timed out' in result.message
            assert heartbeat.is_set()
            assert elapsed < 0.15
            assert requested == []
        finally:
            await client.aclose()

    asyncio.run(scenario())
