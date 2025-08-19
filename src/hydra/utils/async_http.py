"""Async HTTP utilities using aiohttp instead of requests."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientError, ClientTimeout

logger = logging.getLogger(__name__)


class AsyncHTTPClient:
    """Async HTTP client with connection pooling and retry logic."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 0.3
    ):
        self.base_url = base_url
        self.timeout = ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self):
        """Ensure we have an active session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                enable_cleanup_closed=True
            )
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector
            )

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _retry_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """Execute request with retry logic."""
        await self._ensure_session()

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                async with self._session.request(method, url, **kwargs) as response:
                    response.raise_for_status()
                    return response
            except (ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = self.backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e}")

        raise last_exception

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Perform async GET request."""
        url = urljoin(self.base_url, endpoint) if self.base_url else endpoint

        async with await self._retry_request(
            "GET",
            url,
            params=params,
            headers=headers
        ) as response:
            return await response.json()

    async def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Perform async POST request."""
        url = urljoin(self.base_url, endpoint) if self.base_url else endpoint

        kwargs = {"headers": headers}
        if json_data is not None:
            kwargs["json"] = json_data
        elif data is not None:
            kwargs["data"] = data

        async with await self._retry_request("POST", url, **kwargs) as response:
            return await response.json()

    async def put(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Perform async PUT request."""
        url = urljoin(self.base_url, endpoint) if self.base_url else endpoint

        kwargs = {"headers": headers}
        if json_data is not None:
            kwargs["json"] = json_data
        elif data is not None:
            kwargs["data"] = data

        async with await self._retry_request("PUT", url, **kwargs) as response:
            return await response.json()

    async def delete(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Perform async DELETE request."""
        url = urljoin(self.base_url, endpoint) if self.base_url else endpoint

        async with await self._retry_request(
            "DELETE",
            url,
            headers=headers
        ) as response:
            return await response.json()

    async def fetch_batch(
        self,
        urls: List[str],
        max_concurrent: int = 10
    ) -> List[Union[Dict[str, Any], Exception]]:
        """Fetch multiple URLs concurrently."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_limit(url: str) -> Union[Dict[str, Any], Exception]:
            async with semaphore:
                try:
                    return await self.get(url)
                except Exception as e:
                    logger.error(f"Error fetching {url}: {e}")
                    return e

        tasks = [fetch_with_limit(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)


# Convenience functions for simple async HTTP operations
async def async_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """Simple async GET request."""
    async with AsyncHTTPClient(timeout=timeout) as client:
        return await client.get(url, params=params, headers=headers)


async def async_post(
    url: str,
    json_data: Optional[Dict[str, Any]] = None,
    data: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """Simple async POST request."""
    async with AsyncHTTPClient(timeout=timeout) as client:
        return await client.post(url, json_data=json_data, data=data, headers=headers)


async def async_fetch_batch(
    urls: List[str],
    max_concurrent: int = 10,
    timeout: int = 30
) -> List[Union[Dict[str, Any], Exception]]:
    """Fetch multiple URLs concurrently."""
    async with AsyncHTTPClient(timeout=timeout) as client:
        return await client.fetch_batch(urls, max_concurrent=max_concurrent)
