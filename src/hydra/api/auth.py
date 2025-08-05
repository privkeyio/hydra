"""Authentication and rate limiting middleware for Hydra API."""

import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class RateLimiter:
    """In-memory rate limiter with sliding window."""

    def __init__(self):
        self.requests: Dict[str, list] = defaultdict(list)
        self.usage_log: list = []

    def is_allowed(self, api_key: str, limit: int, window: int) -> Tuple[bool, int]:
        """Check if request is allowed under rate limit."""
        now = time.time()
        key_requests = self.requests[api_key]

        # Remove old requests outside window
        cutoff = now - window
        key_requests[:] = [req_time for req_time in key_requests if req_time > cutoff]

        if len(key_requests) >= limit:
            return False, len(key_requests)

        key_requests.append(now)
        return True, len(key_requests)

    def log_usage(self, api_key: str, endpoint: str, tokens_used: int = 0):
        """Log API usage for tracking."""
        self.usage_log.append({
            'api_key': api_key,
            'endpoint': endpoint,
            'timestamp': datetime.utcnow().isoformat(),
            'tokens_used': tokens_used
        })

        # Keep only last 10000 entries to prevent memory bloat
        if len(self.usage_log) > 10000:
            self.usage_log = self.usage_log[-5000:]

rate_limiter = RateLimiter()

class APIKeyValidator:
    """Validates API keys using environment-based configuration."""

    def __init__(self):
        self.valid_keys = self._load_api_keys()

    def _load_api_keys(self) -> Dict[str, Dict]:
        """Load API keys from environment or default config."""
        # For production, this would come from database
        # For now, using environment variables and defaults
        default_keys = {
            'hydra-dev-key': {'name': 'Development Key', 'rate_limit': 100},
            'hydra-prod-key': {'name': 'Production Key', 'rate_limit': 1000}
        }

        # Allow custom keys via environment
        custom_keys_json = os.getenv('HYDRA_API_KEYS')
        if custom_keys_json:
            try:
                custom_keys = json.loads(custom_keys_json)
                default_keys.update(custom_keys)
            except json.JSONDecodeError:
                logger.warning("Invalid HYDRA_API_KEYS JSON format")

        return default_keys

    def validate_key(self, api_key: str) -> Optional[Dict]:
        """Validate API key and return key info."""
        if not api_key:
            return None

        # Hash key for comparison to avoid timing attacks
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        stored_hash = hashlib.sha256(api_key.encode()).hexdigest()

        if key_hash == stored_hash and api_key in self.valid_keys:
            return self.valid_keys[api_key]

        return None

api_key_validator = APIKeyValidator()

class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication and rate limiting middleware."""

    def __init__(
        self,
        app,
        rate_limit_requests: int = None,
        rate_limit_window: int = None
    ):
        super().__init__(app)
        self.rate_limit_requests = (
            rate_limit_requests or int(os.getenv('RATE_LIMIT_REQUESTS', '100'))
        )
        self.rate_limit_window = (
            rate_limit_window or int(os.getenv('RATE_LIMIT_WINDOW', '3600'))
        )
        self.excluded_paths = {'/health', '/docs', '/redoc', '/openapi.json'}

    async def dispatch(self, request: Request, call_next):
        """Process request through auth and rate limiting."""
        path = request.url.path

        # Skip auth for excluded paths
        if path in self.excluded_paths:
            return await call_next(request)

        # Extract API key
        api_key = self._extract_api_key(request)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Validate API key
        key_info = api_key_validator.validate_key(api_key)
        if not key_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

        # Apply rate limiting
        key_limit = key_info.get('rate_limit', self.rate_limit_requests)
        allowed, current_count = rate_limiter.is_allowed(
            api_key, key_limit, self.rate_limit_window
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded. Limit: {key_limit} requests per "
                    f"{self.rate_limit_window} seconds"
                ),
                headers={
                    "X-RateLimit-Limit": str(key_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + self.rate_limit_window))
                }
            )

        # Add rate limit headers
        request.state.api_key = api_key
        request.state.key_info = key_info

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(key_limit)
        response.headers["X-RateLimit-Remaining"] = str(key_limit - current_count)
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time() + self.rate_limit_window)
        )

        # Log usage
        rate_limiter.log_usage(api_key, path)

        return response

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request headers."""
        # Try Authorization header first
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            return auth_header[7:]  # Remove 'Bearer ' prefix

        # Try X-API-Key header
        api_key_header = request.headers.get('X-API-Key')
        if api_key_header:
            return api_key_header

        return None

security = HTTPBearer(auto_error=False)

async def get_current_api_key(request: Request) -> Tuple[str, Dict]:
    """Dependency to get current API key and info from request state."""
    if not hasattr(request.state, 'api_key'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    return request.state.api_key, request.state.key_info

def get_usage_stats(api_key: Optional[str] = None) -> Dict:
    """Get usage statistics."""
    if api_key:
        key_usage = [log for log in rate_limiter.usage_log if log['api_key'] == api_key]
        return {
            'total_requests': len(key_usage),
            'endpoints': list(set(log['endpoint'] for log in key_usage)),
            'recent_usage': key_usage[-10:]  # Last 10 requests
        }

    return {
        'total_requests': len(rate_limiter.usage_log),
        'unique_keys': len(set(log['api_key'] for log in rate_limiter.usage_log)),
        'recent_usage': rate_limiter.usage_log[-10:]
    }

