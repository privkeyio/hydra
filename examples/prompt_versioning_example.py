"""Example usage of the prompt versioning and hot-reload system."""

import json
import time
from datetime import datetime
from pathlib import Path

from hydra.prompts.versioning import (
    PromptMetrics,
    PromptVersionManager,
    create_prompt_version,
    get_ab_test_prompt,
    record_prompt_usage,
)


def demo_version_management():
    """Demonstrate version management capabilities."""
    print("=== Prompt Version Management Demo ===")
    
    # Create version manager
    manager = PromptVersionManager(enable_hot_reload=False)
    
    # Create initial version
    content_v1 = {
        "prompts": {
            "greeting": {
                "template": "Hello {name}, welcome to our service!",
                "variables": ["name"]
            },
            "farewell": {
                "template": "Goodbye {name}, thank you for using our service.",
                "variables": ["name"]
            }
        }
    }
    
    version_v1 = manager.create_version(content_v1, "v1.0")
    print(f"Created version: {version_v1}")
    
    # Create improved version
    content_v2 = {
        "prompts": {
            "greeting": {
                "template": "Hi {name}! 👋 Welcome to our amazing service!",
                "variables": ["name"]
            },
            "farewell": {
                "template": "See you later, {name}! 🚀 Thanks for choosing us.",
                "variables": ["name"]
            }
        }
    }
    
    version_v2 = manager.create_version(content_v2, "v2.0")
    print(f"Created version: {version_v2}")
    
    # List versions
    versions = manager.list_versions()
    print(f"\nAvailable versions: {len(versions)}")
    for v in versions:
        print(f"  - {v.version_id} (created: {v.timestamp.strftime('%Y-%m-%d %H:%M')})")
    
    # Demonstrate rollback
    print(f"\nRolling back to {version_v1}...")
    manager.rollback_to_version(version_v1)
    
    # Show rollback created new version
    versions_after_rollback = manager.list_versions()
    print(f"Versions after rollback: {len(versions_after_rollback)}")
    
    manager.cleanup()


def demo_ab_testing():
    """Demonstrate A/B testing capabilities."""
    print("\n=== A/B Testing Demo ===")
    
    manager = PromptVersionManager(enable_hot_reload=False)
    
    # Create A/B test
    variants = {
        "control": "Hello {name}, welcome to our service!",
        "friendly": "Hi there {name}! 😊 Welcome to our awesome service!",
        "professional": "Good day {name}. Welcome to our professional service platform."
    }
    
    ab_test = manager.create_ab_test("greeting_optimization", variants)
    print(f"Created A/B test: {ab_test.test_id}")
    print(f"Variants: {list(ab_test.variants.keys())}")
    print(f"Traffic split: {ab_test.traffic_split}")
    
    # Simulate user assignments
    test_users = [f"user_{i:03d}" for i in range(20)]
    
    print("\nUser variant assignments:")
    for user in test_users[:5]:  # Show first 5 users
        variant = manager.get_ab_test_variant("greeting_optimization", user)
        print(f"  {user} -> {variant}")
    
    # Test consistency (same user should get same variant)
    user = "user_001"
    variant1 = manager.get_ab_test_variant("greeting_optimization", user)
    variant2 = manager.get_ab_test_variant("greeting_optimization", user)
    print(f"\nConsistency check for {user}: {variant1} == {variant2} -> {variant1 == variant2}")
    
    manager.cleanup()


def demo_performance_tracking():
    """Demonstrate performance metrics tracking."""
    print("\n=== Performance Tracking Demo ===")
    
    manager = PromptVersionManager(enable_hot_reload=False)
    
    # Simulate prompt usage with metrics
    prompt_variants = ["control", "optimized", "experimental"]
    
    print("Simulating prompt usage...")
    for i in range(50):
        variant = prompt_variants[i % len(prompt_variants)]
        
        # Simulate different performance characteristics
        if variant == "control":
            execution_time = 2.0 + (i % 5) * 0.2  # 2.0-2.8s
            success = i % 4 != 0  # 75% success rate
        elif variant == "optimized":
            execution_time = 1.2 + (i % 3) * 0.1  # 1.2-1.4s
            success = i % 10 != 0  # 90% success rate
        else:  # experimental
            execution_time = 1.8 + (i % 6) * 0.3  # 1.8-3.3s
            success = i % 3 != 0  # 67% success rate
        
        metrics = PromptMetrics(
            prompt_name="greeting",
            variant=variant,
            execution_time=execution_time,
            success=success
        )
        
        manager.record_metrics(metrics)
    
    # Flush metrics to database
    manager.flush_metrics()
    
    # Show performance comparison
    print("\nPerformance comparison:")
    for variant in prompt_variants:
        perf = manager.get_prompt_performance("greeting", variant)
        print(f"  {variant}:")
        print(f"    Usage: {perf['total_count']}")
        print(f"    Success rate: {perf['success_rate']:.1%}")
        print(f"    Avg execution time: {perf['avg_execution_time']:.2f}s")
    
    manager.cleanup()


def demo_optimization_suggestions():
    """Demonstrate optimization suggestions."""
    print("\n=== Optimization Suggestions Demo ===")
    
    manager = PromptVersionManager(enable_hot_reload=False)
    
    # Simulate poor performing prompt
    print("Creating metrics for a poorly performing prompt...")
    for i in range(30):
        metrics = PromptMetrics(
            prompt_name="slow_prompt",
            execution_time=8.0 + (i % 5),  # Very slow (8-12s)
            success=i % 5 == 0  # Poor success rate (20%)
        )
        manager.record_metrics(metrics)
    
    # Simulate good performing prompt
    print("Creating metrics for a well performing prompt...")
    for i in range(100):
        metrics = PromptMetrics(
            prompt_name="fast_prompt",
            execution_time=0.8 + (i % 3) * 0.1,  # Fast (0.8-1.0s)
            success=i % 20 != 0  # Good success rate (95%)
        )
        manager.record_metrics(metrics)
    
    manager.flush_metrics()
    
    # Get suggestions for both prompts
    print("\nOptimization suggestions:")
    
    for prompt_name in ["slow_prompt", "fast_prompt"]:
        suggestions = manager.get_optimization_suggestions(prompt_name)
        print(f"\n{prompt_name}:")
        if suggestions:
            for i, suggestion in enumerate(suggestions, 1):
                print(f"  {i}. [{suggestion['severity'].upper()}] {suggestion['type']}")
                print(f"     {suggestion['message']}")
        else:
            print("  No suggestions - prompt is performing well!")
    
    manager.cleanup()


def demo_hot_reload():
    """Demonstrate hot-reload capabilities."""
    print("\n=== Hot Reload Demo ===")
    
    # Note: This demo shows how to set up hot reload
    # In practice, you'd have actual files being watched
    
    manager = PromptVersionManager(enable_hot_reload=True)
    
    # Add reload callback
    def on_file_change(file_path):
        print(f"🔄 File changed: {file_path}")
        print("   Prompt system would reload configurations now")
    
    manager.add_reload_callback(on_file_change)
    
    print("Hot reload enabled. File changes would trigger callbacks.")
    print("In a real scenario, editing YAML files would trigger reloads.")
    
    # Simulate file change
    manager._handle_file_change("/fake/path/prompts.yaml")
    
    manager.cleanup()


def demo_convenience_functions():
    """Demonstrate convenience functions."""
    print("\n=== Convenience Functions Demo ===")
    
    # Create version using convenience function
    content = {
        "prompts": {
            "simple": {
                "template": "Simple prompt: {message}",
                "variables": ["message"]
            }
        }
    }
    
    version_id = create_prompt_version(content)
    print(f"Created version using convenience function: {version_id}")
    
    # Record usage using convenience function
    record_prompt_usage(
        prompt_name="simple",
        execution_time=1.5,
        success=True,
        metadata={"source": "demo"}
    )
    print("Recorded usage using convenience function")
    
    # Test A/B testing convenience function
    from hydra.prompts.versioning import get_version_manager
    manager = get_version_manager()
    manager.create_ab_test("simple_test", {
        "v1": "Hello {name}",
        "v2": "Hi {name}!"
    })
    
    prompt = get_ab_test_prompt("simple_test", "demo_user", "Default prompt")
    print(f"A/B test prompt for demo_user: {prompt}")
    
    manager.cleanup()


if __name__ == "__main__":
    """Run all demonstrations."""
    print("Prompt Versioning System Demonstration")
    print("=" * 50)
    
    demo_version_management()
    demo_ab_testing()
    demo_performance_tracking()
    demo_optimization_suggestions()
    demo_hot_reload()
    demo_convenience_functions()
    
    print("\n" + "=" * 50)
    print("Demo completed! Check the examples above to see")
    print("how to integrate the versioning system into your application.")