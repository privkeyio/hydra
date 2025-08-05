"""Redis caching layer for Hydra system."""

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis
from redis.connection import ConnectionPool


class CacheConfig:
    """Cache configuration."""

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
        self.code_ttl = int(os.getenv("CACHE_CODE_TTL", "3600"))  # 1 hour
        self.task_ttl = int(os.getenv("CACHE_TASK_TTL", "1800"))  # 30 minutes
        self.api_ttl = int(os.getenv("CACHE_API_TTL", "300"))     # 5 minutes
        self.max_memory = os.getenv("CACHE_MAX_MEMORY", "256mb")
        self.key_prefix = os.getenv("CACHE_KEY_PREFIX", "hydra:")


class HydraCache:
    """Redis-based caching system for Hydra."""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.pool = ConnectionPool.from_url(
            self.config.redis_url,
            decode_responses=True,
            max_connections=20
        )
        self.redis_client = redis.Redis(connection_pool=self.pool)
        self._setup_memory_limits()

    def _setup_memory_limits(self):
        """Configure Redis memory limits."""
        try:
            self.redis_client.config_set("maxmemory", self.config.max_memory)
            self.redis_client.config_set("maxmemory-policy", "allkeys-lru")
        except redis.exceptions.ResponseError:
            pass

    def _make_key(self, category: str, key: str) -> str:
        """Generate cache key with prefix."""
        return f"{self.config.key_prefix}{category}:{key}"

    def _hash_prompt(self, prompt: str, **kwargs) -> str:
        """Generate hash for prompt and parameters."""
        data = {"prompt": prompt, **kwargs}
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def _serialize(self, data: Any) -> str:
        """Serialize data for storage."""
        return json.dumps({
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
            "type": type(data).__name__
        })

    def _deserialize(self, data: str) -> Any:
        """Deserialize data from storage."""
        try:
            parsed = json.loads(data)
            return parsed["data"]
        except (json.JSONDecodeError, KeyError):
            return None

    def get_code_cache(self, prompt: str, language: Optional[str] = None,
                      max_tokens: Optional[int] = None) -> Optional[str]:
        """Get cached generated code."""
        cache_key = self._hash_prompt(
            prompt,
            language=language,
            max_tokens=max_tokens
        )
        key = self._make_key("code", cache_key)

        try:
            cached = self.redis_client.get(key)
            if cached:
                return self._deserialize(cached)
        except redis.exceptions.RedisError:
            pass
        return None

    def set_code_cache(self, prompt: str, code: str, language: Optional[str] = None,
                      max_tokens: Optional[int] = None,
                      ttl: Optional[int] = None) -> bool:
        """Cache generated code."""
        cache_key = self._hash_prompt(
            prompt,
            language=language,
            max_tokens=max_tokens
        )
        key = self._make_key("code", cache_key)
        ttl = ttl or self.config.code_ttl

        try:
            serialized = self._serialize(code)
            return self.redis_client.setex(key, ttl, serialized)
        except redis.exceptions.RedisError:
            return False

    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get cached task result."""
        key = self._make_key("task", task_id)

        try:
            cached = self.redis_client.get(key)
            if cached:
                return self._deserialize(cached)
        except redis.exceptions.RedisError:
            pass
        return None

    def set_task_result(self, task_id: str, result: Dict[str, Any],
                       ttl: Optional[int] = None) -> bool:
        """Cache task result."""
        key = self._make_key("task", task_id)
        ttl = ttl or self.config.task_ttl

        try:
            serialized = self._serialize(result)
            return self.redis_client.setex(key, ttl, serialized)
        except redis.exceptions.RedisError:
            return False

    def get_api_response(self, endpoint: str,
                        params_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached API response."""
        key = self._make_key("api", f"{endpoint}:{params_hash}")

        try:
            cached = self.redis_client.get(key)
            if cached:
                return self._deserialize(cached)
        except redis.exceptions.RedisError:
            pass
        return None

    def set_api_response(self, endpoint: str, params_hash: str,
                        response: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Cache API response."""
        key = self._make_key("api", f"{endpoint}:{params_hash}")
        ttl = ttl or self.config.api_ttl

        try:
            serialized = self._serialize(response)
            return self.redis_client.setex(key, ttl, serialized)
        except redis.exceptions.RedisError:
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache keys matching pattern."""
        full_pattern = self._make_key("*", pattern)
        try:
            keys = self.redis_client.keys(full_pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except redis.exceptions.RedisError:
            return 0

    def invalidate_code_cache(self) -> int:
        """Invalidate all code cache."""
        return self.invalidate_pattern("code:*")

    def invalidate_task_cache(self, task_id: Optional[str] = None) -> int:
        """Invalidate task cache."""
        if task_id:
            key = self._make_key("task", task_id)
            try:
                return self.redis_client.delete(key)
            except redis.exceptions.RedisError:
                return 0
        else:
            return self.invalidate_pattern("task:*")

    def invalidate_api_cache(self, endpoint: Optional[str] = None) -> int:
        """Invalidate API cache."""
        if endpoint:
            return self.invalidate_pattern(f"api:{endpoint}:*")
        else:
            return self.invalidate_pattern("api:*")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            info = self.redis_client.info("memory")
            keyspace = self.redis_client.info("keyspace")

            total_keys = 0
            for db_info in keyspace.values():
                if isinstance(db_info, dict) and "keys" in db_info:
                    total_keys += db_info["keys"]

            return {
                "memory_used": info.get("used_memory_human", "unknown"),
                "memory_peak": info.get("used_memory_peak_human", "unknown"),
                "total_keys": total_keys,
                "connected_clients": self.redis_client.info("clients").get(
                    "connected_clients", 0),
                "cache_hit_rate": self._calculate_hit_rate(),
                "uptime_seconds": self.redis_client.info("server").get(
                    "uptime_in_seconds", 0)
            }
        except redis.exceptions.RedisError:
            return {"error": "Unable to retrieve cache stats"}

    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        try:
            stats = self.redis_client.info("stats")
            hits = stats.get("keyspace_hits", 0)
            misses = stats.get("keyspace_misses", 0)
            total = hits + misses
            return (hits / total * 100) if total > 0 else 0.0
        except (redis.exceptions.RedisError, ZeroDivisionError):
            return 0.0

    def warm_cache(self, patterns: List[str]) -> Dict[str, int]:
        """Warm cache with common patterns."""
        results = {}

        common_prompts = [
            "Create a Python function that",
            "Write a REST API endpoint for",
            "Generate a React component that",
            "Implement a database query to",
            "Create a unit test for"
        ]

        for pattern in patterns:
            count = 0
            for prompt in common_prompts:
                if pattern.lower() in prompt.lower():
                    cache_key = self._hash_prompt(prompt)
                    key = self._make_key("warm", cache_key)
                    try:
                        self.redis_client.setex(
                            key,
                            self.config.code_ttl,
                            self._serialize({"warmed": True, "pattern": pattern})
                        )
                        count += 1
                    except redis.exceptions.RedisError:
                        continue
            results[pattern] = count

        return results

    def health_check(self) -> Dict[str, Any]:
        """Check cache health."""
        try:
            start_time = datetime.utcnow()
            self.redis_client.ping()
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return {
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "redis_version": self.redis_client.info("server").get(
                    "redis_version", "unknown")
            }
        except redis.exceptions.RedisError as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    def close(self):
        """Close cache connections."""
        try:
            self.redis_client.close()
        except Exception:
            pass


_cache_instance = None


def get_cache() -> HydraCache:
    """Get or create global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = HydraCache()
    return _cache_instance


def reset_cache(config: Optional[CacheConfig] = None) -> HydraCache:
    """Reset global cache instance."""
    global _cache_instance
    if _cache_instance:
        _cache_instance.close()
    _cache_instance = HydraCache(config)
    return _cache_instance

