"""HTTP session management for providers with connection pooling."""

import logging
import os
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from hydra.cache import get_cache
from hydra.performance import pool_manager

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages HTTP sessions with connection pooling and reuse."""

    def __init__(self):
        self._sessions: Dict[str, requests.Session] = {}
        self._cache = get_cache()

    def get_session(self, provider: str) -> requests.Session:
        """Get or create a session for the specified provider.

        Args:
            provider: Provider name (venice, anthropic, openai, etc.)

        Returns:
            Configured requests.Session with connection pooling

        """
        if provider not in self._sessions:
            self._sessions[provider] = self._create_session(provider)
            logger.info(f"Created new HTTP session for provider: {provider}")
        else:
            logger.debug(f"Reusing existing HTTP session for provider: {provider}")

        return self._sessions[provider]

    def _create_session(self, provider: str) -> requests.Session:
        """Create a new HTTP session with connection pooling."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=100,
            max_retries=retry_strategy,
            pool_block=False,
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set provider-specific headers
        headers = self._get_provider_headers(provider)
        session.headers.update(headers)

        logger.info(f"HTTP session created for {provider} with connection pooling")
        return session

    def _get_provider_headers(self, provider: str) -> Dict[str, str]:
        """Get standard headers for a provider."""
        headers = {"User-Agent": "hydra-agents/1.0", "Content-Type": "application/json"}

        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                headers.update(
                    {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
                )
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        elif provider == "venice":
            api_key = os.getenv("VENICE_API_KEY")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

        return headers

    def close_session(self, provider: str):
        """Close a session for the specified provider."""
        if provider in self._sessions:
            self._sessions[provider].close()
            del self._sessions[provider]
            logger.debug(f"Closed HTTP session for provider: {provider}")

    def close_all_sessions(self):
        """Close all sessions."""
        for provider in list(self._sessions.keys()):
            self.close_session(provider)
        logger.info("Closed all HTTP sessions")

    async def get_async_session(self, provider: str):
        """Get async session from the global pool manager."""
        return await pool_manager.get_http_session()


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def cleanup_sessions():
    """Cleanup all sessions."""
    global _session_manager
    if _session_manager:
        _session_manager.close_all_sessions()
        _session_manager = None
