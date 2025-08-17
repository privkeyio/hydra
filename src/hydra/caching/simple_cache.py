"""Simple LRU and file-based caching utilities for Hydra."""

import functools
import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


class FileMetaCache:
    """Cache with file modification time checking."""

    def __init__(self, max_size: int = 128):
        """Initialize cache with maximum size.

        Args:
            max_size: Maximum number of cached items

        """
        self.max_size = max_size
        self._cache: Dict[str, Tuple[Any, float, float]] = {}
        self._access_order = []

    def get(self, key: str, file_path: Optional[str] = None) -> Optional[Any]:
        """Get cached value if file hasn't been modified.

        Args:
            key: Cache key
            file_path: File path to check modification time

        Returns:
            Cached value if valid, None otherwise

        """
        if key not in self._cache:
            return None

        value, cached_time, file_mtime = self._cache[key]

        # Check if file has been modified
        if file_path and os.path.exists(file_path):
            current_mtime = os.path.getmtime(file_path)
            if current_mtime > file_mtime:
                # File modified, invalidate cache
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return None

        # Update access order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        return value

    def set(self, key: str, value: Any, file_path: Optional[str] = None) -> None:
        """Cache a value with optional file modification time.

        Args:
            key: Cache key
            value: Value to cache
            file_path: File path to track modification time

        """
        current_time = time.time()
        file_mtime = 0.0

        if file_path and os.path.exists(file_path):
            file_mtime = os.path.getmtime(file_path)

        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]

        self._cache[key] = (value, current_time, file_mtime)

        # Update access order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def clear(self) -> None:
        """Clear all cached items."""
        self._cache.clear()
        self._access_order.clear()


def lru_cache_with_bypass(maxsize: int = 128, typed: bool = False):
    """LRU cache decorator that can be bypassed via environment variable.

    Args:
        maxsize: Maximum cache size
        typed: Whether to consider types in cache key

    Returns:
        Decorator function

    """

    def decorator(func: Callable) -> Callable:
        # Check if caching is disabled
        if os.getenv("NO_CACHE", "").lower() in ("1", "true", "yes"):
            # Return unwrapped function if caching disabled
            return func

        # Apply LRU cache
        cached_func = functools.lru_cache(maxsize=maxsize, typed=typed)(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Allow bypassing cache at runtime
            if kwargs.pop("_no_cache", False):
                return func(*args, **kwargs)
            return cached_func(*args, **kwargs)

        # Expose cache info and clear methods
        wrapper.cache_info = cached_func.cache_info
        wrapper.cache_clear = cached_func.cache_clear

        return wrapper

    return decorator


def get_cache_key(*args, **kwargs) -> str:
    """Generate cache key from arguments.

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Cache key string

    """
    # Create deterministic string from args and kwargs
    key_data = str(args) + str(sorted(kwargs.items()))
    return hashlib.md5(key_data.encode()).hexdigest()


def file_cache(cache_dir: Optional[str] = None):
    """File-based cache decorator with mtime checking.

    Args:
        cache_dir: Directory to store cache files

    Returns:
        Decorator function

    """
    if cache_dir is None:
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "hydra")

    def decorator(func: Callable) -> Callable:
        # Check if caching is disabled
        if os.getenv("NO_CACHE", "").lower() in ("1", "true", "yes"):
            return func

        # Ensure cache directory exists
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Allow bypassing cache at runtime
            if kwargs.pop("_no_cache", False):
                return func(*args, **kwargs)

            # Generate cache key
            cache_key = get_cache_key(*args, **kwargs)
            cache_file = os.path.join(cache_dir, f"{func.__name__}_{cache_key}.cache")

            # Check if cached result exists and is valid
            if os.path.exists(cache_file):
                try:
                    import pickle

                    with open(cache_file, "rb") as f:
                        result = pickle.load(f)
                    return result
                except (pickle.PickleError, EOFError):
                    # Cache file corrupted, remove it
                    os.remove(cache_file)

            # Call function and cache result
            result = func(*args, **kwargs)

            try:
                import pickle

                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)
            except pickle.PickleError:
                # Failed to cache, but return result
                pass

            return result

        return wrapper

    return decorator


# Global file meta cache instance
_file_meta_cache: Optional[FileMetaCache] = None


def get_file_meta_cache() -> FileMetaCache:
    """Get global file meta cache instance.

    Returns:
        File meta cache instance

    """
    global _file_meta_cache
    if _file_meta_cache is None:
        _file_meta_cache = FileMetaCache(max_size=64)
    return _file_meta_cache
