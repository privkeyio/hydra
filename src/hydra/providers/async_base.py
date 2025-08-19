"""Async base class for LLM providers with proper async/await patterns."""

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

from hydra.providers.base import LLMConfig


class AsyncLLMProvider(ABC):
    """Async base class for LLM providers using async/await patterns."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self.validate_config()

    @abstractmethod
    def validate_config(self):
        """Validate provider-specific configuration."""
        pass

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """Asynchronously generate a response from the LLM."""
        pass

    @abstractmethod
    async def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Asynchronously generate a JSON response from the LLM."""
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Asynchronously list available models for this provider."""
        pass

    @abstractmethod
    async def stream_generate(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Stream response chunks from the LLM."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        pass

    @property
    def model(self) -> str:
        """Return the current model."""
        if isinstance(self.config, dict):
            return self.config.get("model", "unknown")
        return self.config.model

    @asynccontextmanager
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session for HTTP requests."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector
            )
        yield self._session

    async def close(self):
        """Close the HTTP session and cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def __repr__(self):
        if isinstance(self.config, dict):
            model = self.config.get("model", "unknown")
        else:
            model = self.config.model
        return f"{self.name}(model={model})"


class AsyncBatchProvider(AsyncLLMProvider):
    """Base class for providers that support batch operations."""

    @abstractmethod
    async def generate_batch(
        self,
        prompts: List[str],
        **kwargs
    ) -> List[str]:
        """Generate responses for multiple prompts concurrently."""
        pass

    async def generate_batch_with_fallback(
        self,
        prompts: List[str],
        max_concurrent: int = 5,
        **kwargs
    ) -> List[str]:
        """Generate batch responses with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_semaphore(prompt: str) -> str:
            async with semaphore:
                return await self.generate(prompt, **kwargs)

        tasks = [generate_with_semaphore(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks, return_exceptions=False)
