"""Async OpenAI provider implementation using aiohttp."""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List

from hydra.providers.async_base import AsyncLLMProvider

logger = logging.getLogger(__name__)


class AsyncOpenAIProvider(AsyncLLMProvider):
    """Async OpenAI provider using aiohttp for better performance."""

    BASE_URL = "https://api.openai.com/v1"
    MODELS = [
        "gpt-4-turbo-preview",
        "gpt-4-1106-preview",
        "gpt-4",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
        "gpt-3.5-turbo-1106"
    ]

    def validate_config(self):
        """Validate OpenAI-specific configuration."""
        if not self.config.api_key:
            raise ValueError("OpenAI API key is required")
        if not self.config.model:
            self.config.model = "gpt-3.5-turbo"
        if self.config.model not in self.MODELS:
            logger.warning(f"Unknown model {self.config.model}, using anyway")

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "AsyncOpenAI"

    async def _make_request(
        self,
        endpoint: str,
        data: Dict[str, Any],
    ) -> Any:
        """Make an async HTTP request to OpenAI API."""
        url = f"{self.config.base_url or self.BASE_URL}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

        async with self.get_session() as session:
            async with session.post(
                url,
                json=data,
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def _make_stream_request(
        self,
        endpoint: str,
        data: Dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Make an async streaming HTTP request to OpenAI API."""
        url = f"{self.config.base_url or self.BASE_URL}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

        async with self.get_session() as session:
            async with session.post(
                url,
                json=data,
                headers=headers
            ) as response:
                response.raise_for_status()
                async for line in response.content:
                    if line:
                        yield line

    async def generate(self, prompt: str, **kwargs) -> str:
        """Asynchronously generate a response from GPT."""
        messages = kwargs.get("messages", [{"role": "user", "content": prompt}])

        data = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }

        response = await self._make_request("chat/completions", data)

        if response.get("choices"):
            return response["choices"][0]["message"]["content"]
        return ""

    async def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Asynchronously generate a JSON response from GPT."""
        json_prompt = f"{prompt}\n\nRespond with valid JSON only, no other text."

        # Use JSON mode if available
        kwargs["response_format"] = {"type": "json_object"}

        response = await self.generate(json_prompt, **kwargs)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError(f"Failed to parse JSON from response: {response}")

    async def stream_generate(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Stream response chunks from GPT."""
        messages = kwargs.get("messages", [{"role": "user", "content": prompt}])

        data = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": True
        }

        async for chunk in self._make_request("chat/completions", data, stream=True):
            # Parse SSE format
            if chunk.startswith(b"data: "):
                chunk_data = chunk[6:].decode('utf-8').strip()
                if chunk_data and chunk_data != "[DONE]":
                    try:
                        event = json.loads(chunk_data)
                        if event.get("choices"):
                            delta = event["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                    except json.JSONDecodeError:
                        continue

    async def list_models(self) -> List[str]:
        """List available OpenAI models."""
        try:
            response = await self._make_request("models", {}, stream=False)
            models = [model["id"] for model in response.get("data", [])]
            return models if models else self.MODELS.copy()
        except Exception:
            return self.MODELS.copy()

    async def generate_batch(
        self,
        prompts: List[str],
        max_concurrent: int = 10,
        **kwargs
    ) -> List[str]:
        """Generate responses for multiple prompts concurrently."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_limit(prompt: str) -> str:
            async with semaphore:
                try:
                    return await self.generate(prompt, **kwargs)
                except Exception as e:
                    logger.error(f"Error generating response: {e}")
                    return f"Error: {str(e)}"

        tasks = [generate_with_limit(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks)
