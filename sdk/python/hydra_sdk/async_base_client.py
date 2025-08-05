import asyncio
import json
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp

from .exceptions import (
    HydraAPIError,
    HydraAuthenticationError,
    HydraRateLimitError,
    HydraTimeoutError,
)


class AsyncBaseClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: int = 60,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={"X-API-Key": self.api_key},
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._session:
            raise RuntimeError("Client must be used as async context manager")

        url = urljoin(self.base_url, endpoint.lstrip("/"))

        for attempt in range(self.max_retries + 1):
            try:
                async with self._session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                ) as response:

                    if response.status == 200:
                        return await response.json()
                    elif response.status == 401:
                        raise HydraAuthenticationError(401, "Invalid API key")
                    elif response.status == 429:
                        if attempt < self.max_retries:
                            delay = self._exponential_backoff(attempt)
                            await asyncio.sleep(delay)
                            continue
                        raise HydraRateLimitError(429, "Rate limit exceeded")
                    else:
                        error_msg = "Unknown error"
                        try:
                            error_data = await response.json()
                            error_msg = error_data.get("detail", str(error_data))
                        except (json.JSONDecodeError, aiohttp.ContentTypeError):
                            error_msg = await response.text() or f"HTTP {response.status}"

                        if attempt < self.max_retries and response.status >= 500:
                            delay = self._exponential_backoff(attempt)
                            await asyncio.sleep(delay)
                            continue

                        raise HydraAPIError(response.status, error_msg)

            except asyncio.TimeoutError:
                if attempt < self.max_retries:
                    delay = self._exponential_backoff(attempt)
                    await asyncio.sleep(delay)
                    continue
                raise HydraTimeoutError("Request timed out")
            except aiohttp.ClientError as e:
                if attempt < self.max_retries:
                    delay = self._exponential_backoff(attempt)
                    await asyncio.sleep(delay)
                    continue
                raise HydraAPIError(0, f"Request failed: {str(e)}")

    def _exponential_backoff(self, attempt: int) -> float:
        return self.retry_delay * (2 ** attempt)
