import json
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

from .exceptions import (
    HydraAPIError,
    HydraAuthenticationError,
    HydraRateLimitError,
    HydraTimeoutError,
)


class BaseClient:
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
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = urljoin(self.base_url, endpoint.lstrip("/"))

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    raise HydraAuthenticationError(401, "Invalid API key")
                elif response.status_code == 429:
                    if attempt < self.max_retries:
                        delay = self._exponential_backoff(attempt)
                        time.sleep(delay)
                        continue
                    raise HydraRateLimitError(429, "Rate limit exceeded")
                else:
                    error_msg = "Unknown error"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("detail", str(error_data))
                    except json.JSONDecodeError:
                        error_msg = response.text or f"HTTP {response.status_code}"

                    if attempt < self.max_retries and response.status_code >= 500:
                        delay = self._exponential_backoff(attempt)
                        time.sleep(delay)
                        continue

                    raise HydraAPIError(response.status_code, error_msg)

            except requests.exceptions.Timeout:
                if attempt < self.max_retries:
                    delay = self._exponential_backoff(attempt)
                    time.sleep(delay)
                    continue
                raise HydraTimeoutError("Request timed out")
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries:
                    delay = self._exponential_backoff(attempt)
                    time.sleep(delay)
                    continue
                raise HydraAPIError(0, f"Request failed: {str(e)}")

    def _exponential_backoff(self, attempt: int) -> float:
        return self.retry_delay * (2**attempt)
