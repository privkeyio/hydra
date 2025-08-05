#!/usr/bin/env python3

import os

from hydra_sdk import HydraClient


def main():
    api_key = os.getenv("HYDRA_API_KEY")
    if not api_key:
        print("Please set HYDRA_API_KEY environment variable")
        return

    client = HydraClient(
        api_key=api_key,
        base_url=os.getenv("HYDRA_BASE_URL", "http://localhost:8000")
    )

    try:
        print("Getting cache statistics...")
        stats = client.get_cache_stats()
        print(f"Memory used: {stats.memory_used}")
        print(f"Total keys: {stats.total_keys}")
        print(f"Cache hit rate: {stats.cache_hit_rate:.2%}")
        print(f"Connected clients: {stats.connected_clients}")
        print()

        print("Testing cache with repeated requests...")

        prompt = "Create a Python function to sort a list using quicksort"

        print("First request (cache miss expected)...")
        task1 = client.generate_code(prompt, language="python")
        status1 = client.wait_for_completion(task1.task_id)
        cached1 = status1.result.get("cached", False) if status1.result else False
        print(f"Cached: {cached1}")

        print("Second request (cache hit expected)...")
        task2 = client.generate_code(prompt, language="python")
        status2 = client.wait_for_completion(task2.task_id)
        cached2 = status2.result.get("cached", False) if status2.result else False
        print(f"Cached: {cached2}")

        print("\nCache statistics after operations:")
        stats = client.get_cache_stats()
        print(f"Cache hit rate: {stats.cache_hit_rate:.2%}")
        print()

        print("Invalidating code cache...")
        result = client.invalidate_cache("code")
        print(f"Success: {result.success}")
        print(f"Keys deleted: {result.keys_deleted}")
        print(f"Message: {result.message}")

        print("\nCache statistics after invalidation:")
        stats = client.get_cache_stats()
        print(f"Total keys: {stats.total_keys}")
        print(f"Cache hit rate: {stats.cache_hit_rate:.2%}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
