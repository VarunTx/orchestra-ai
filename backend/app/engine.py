import asyncio
import httpx
from fastapi import HTTPException


class Engine:
    def __init__(self, url: str):
        self.client = httpx.AsyncClient(base_url=url.rstrip('/') + '/', timeout=12)

    async def close(self):
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs):
        # Never retry mutations: an ambiguous response may already have started a workflow.
        attempts = 3 if method == 'GET' else 1
        for attempt in range(attempts):
            try:
                response = await self.client.request(method, path.lstrip('/'), **kwargs)
                if response.status_code >= 500 and attempt < attempts - 1:
                    await asyncio.sleep(.2 * (attempt + 1))
                    continue
                if response.is_error:
                    status = response.status_code if response.status_code in (400, 404, 409) else 502
                    raise HTTPException(status, 'Conductor rejected the request' if status != 404 else 'Execution or definition not found')
                if not response.content:
                    return None
                try:
                    return response.json()
                except ValueError:
                    return response.text.strip('"')
            except httpx.RequestError:
                if attempt == attempts - 1:
                    raise HTTPException(503, 'Conductor is unavailable. Check infrastructure and retry.')
                await asyncio.sleep(.2 * (attempt + 1))
