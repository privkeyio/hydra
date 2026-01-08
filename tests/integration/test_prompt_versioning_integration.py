"""Integration tests for prompt versioning system."""

import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from hydra.prompts.versioning import (
    PromptMetrics,
    PromptVersionManager,
    get_version_manager,
    record_prompt_usage,
)


class TestVersionSwitchingWithoutRestart:
    """Test version switching without application restart."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        yield db_path
        
        Path(db_path).unlink(missing_ok=True)
    
    def test_version_switching_runtime(self, temp_db):
        """Test switching between versions at runtime without restart."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        # Create multiple versions
        versions = {}
        for i in range(3):
            content = {
                "prompts": {
                    "test_prompt": {
                        "template": f"Version {i+1}: Hello {{name}}!",
                        "variables": ["name"]
                    }
                }
            }
            version_id = manager.create_version(content, f"v{i+1}.0")
            versions[f"v{i+1}.0"] = content
        
        # Test accessing different versions without restart
        for version_id, expected_content in versions.items():
            version_info = manager.get_version(version_id)
            assert version_info is not None
            assert version_info.content == expected_content
            
            # Test using version in context manager
            with manager.test_version(version_id) as test_version:
                assert test_version.content == expected_content
                # Simulate usage without affecting global state
                template = test_version.content["prompts"]["test_prompt"]["template"]
                assert f"Version {version_id[1]}" in template
        
        manager.cleanup()
    
    def test_ab_testing_runtime_switching(self, temp_db):
        """Test A/B testing with runtime variant switching."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        # Create A/B test
        variants = {
            "control": "Standard greeting: Hello {name}",
            "test_a": "Friendly greeting: Hi {name}! 😊",
            "test_b": "Professional greeting: Good day, {name}."
        }
        
        ab_test = manager.create_ab_test("runtime_test", variants)
        
        # Test that users get consistent variants across multiple calls
        test_users = ["user_001", "user_002", "user_003"]
        user_variants = {}
        
        # First assignment
        for user in test_users:
            variant = manager.get_ab_test_variant("runtime_test", user)
            user_variants[user] = variant
            assert variant in variants.keys()
        
        # Verify consistency across multiple calls (simulating runtime usage)
        for _ in range(5):
            for user in test_users:
                variant = manager.get_ab_test_variant("runtime_test", user)
                assert variant == user_variants[user], f"Variant changed for {user}"
        
        # Test that all variants are being assigned
        all_users = [f"user_{i:03d}" for i in range(100)]
        assigned_variants = set()
        
        for user in all_users:
            variant = manager.get_ab_test_variant("runtime_test", user)
            assigned_variants.add(variant)
        
        # Should have all variants assigned across 100 users
        assert len(assigned_variants) == len(variants)
        
        manager.cleanup()
    
    def test_metrics_collection_runtime(self, temp_db):
        """Test metrics collection during runtime operations."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        # Simulate continuous metrics collection
        prompt_names = ["prompt_a", "prompt_b", "prompt_c"]
        variants = ["control", "test"]
        
        # Record metrics over time
        for minute in range(10):  # Simulate 10 minutes of operation
            for prompt in prompt_names:
                for variant in variants:
                    # Different performance patterns for each variant
                    if variant == "control":
                        execution_time = 2.0 + (minute * 0.1)  # Getting slower
                        success_rate = max(0.5, 1.0 - (minute * 0.05))  # Declining
                    else:
                        execution_time = max(1.0, 2.0 - (minute * 0.1))  # Getting faster
                        success_rate = min(1.0, 0.7 + (minute * 0.03))  # Improving
                    
                    # Record multiple calls per minute
                    for call in range(5):
                        success = call / 5.0 < success_rate
                        
                        metrics = PromptMetrics(
                            prompt_name=prompt,
                            variant=variant,
                            execution_time=execution_time + (call * 0.1),
                            success=success,
                            timestamp=datetime.now() - timedelta(minutes=10-minute)
                        )
                        
                        manager.record_metrics(metrics)
        
        # Flush all metrics
        manager.flush_metrics()
        
        # Analyze performance trends for each prompt/variant
        for prompt in prompt_names:
            for variant in variants:
                # Get recent performance (last 5 minutes)
                recent_perf = manager.get_prompt_performance(
                    prompt, variant, timedelta(minutes=5)
                )
                
                # Get overall performance
                overall_perf = manager.get_prompt_performance(prompt, variant)
                
                assert recent_perf["total_count"] > 0
                assert overall_perf["total_count"] > recent_perf["total_count"]
                
                # Test variant should show improvement over time
                if variant == "test":
                    suggestions = manager.get_optimization_suggestions(prompt)
                    # Should have fewer high-severity suggestions for test variant
                    high_severity = [s for s in suggestions if s["severity"] == "high"]
                    assert len(high_severity) <= 1  # At most 1 high severity issue
        
        manager.cleanup()
    
    def test_hot_reload_simulation(self, temp_db):
        """Test hot reload simulation without actual file changes."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=True)
        
        # Track reload events
        reload_events = []
        
        def track_reload(file_path):
            reload_events.append(file_path)
        
        manager.add_reload_callback(track_reload)
        
        # Simulate file changes
        test_files = [
            "/fake/prompts.yaml",
            "/fake/config.json",
            "/fake/templates.yml"
        ]
        
        for file_path in test_files:
            manager._handle_file_change(file_path)
        
        # Verify all reload events were captured
        assert len(reload_events) == len(test_files)
        assert all(file in reload_events for file in test_files)
        
        manager.cleanup()
    
    def test_performance_optimization_feedback_loop(self, temp_db):
        """Test performance optimization feedback loop."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        # Create initial version with poor performance
        poor_content = {
            "prompts": {
                "slow_prompt": {
                    "template": "Very long and complex prompt that takes a long time to process: {data}",
                    "variables": ["data"]
                }
            }
        }
        
        version_v1 = manager.create_version(poor_content, "v1.0")
        
        # Record poor performance metrics
        for i in range(20):
            metrics = PromptMetrics(
                prompt_name="slow_prompt",
                execution_time=5.0 + i * 0.2,  # Very slow and getting worse
                success=i % 4 == 0  # 25% success rate
            )
            manager.record_metrics(metrics)
        
        manager.flush_metrics()
        
        # Get optimization suggestions
        suggestions = manager.get_optimization_suggestions("slow_prompt")
        
        # Should have multiple high-severity suggestions
        high_severity = [s for s in suggestions if s["severity"] == "high"]
        assert len(high_severity) >= 1
        
        # Create optimized version based on feedback
        optimized_content = {
            "prompts": {
                "slow_prompt": {
                    "template": "Quick prompt: {data}",
                    "variables": ["data"]
                }
            }
        }
        
        version_v2 = manager.create_version(optimized_content, "v2.0")
        
        # Record improved performance metrics
        for i in range(20):
            metrics = PromptMetrics(
                prompt_name="slow_prompt",
                variant="v2",
                execution_time=1.0 + i * 0.05,  # Much faster
                success=i % 5 != 0  # 80% success rate
            )
            manager.record_metrics(metrics)
        
        manager.flush_metrics()
        
        # Compare performance between versions
        v1_perf = manager.get_prompt_performance("slow_prompt", "default")
        v2_perf = manager.get_prompt_performance("slow_prompt", "v2")
        
        # V2 should be significantly better
        assert v2_perf["success_rate"] > v1_perf["success_rate"]
        assert v2_perf["avg_execution_time"] < v1_perf["avg_execution_time"]
        
        # Update version performance metrics
        manager.update_version_performance(
            version_v1,
            performance_score=0.3,  # Poor score
            usage_count=v1_perf["total_count"],
            success_rate=v1_perf["success_rate"],
            avg_execution_time=v1_perf["avg_execution_time"]
        )
        
        manager.update_version_performance(
            version_v2,
            performance_score=0.9,  # Excellent score
            usage_count=v2_perf["total_count"],
            success_rate=v2_perf["success_rate"],
            avg_execution_time=v2_perf["avg_execution_time"]
        )
        
        # Verify version performance tracking
        v1_info = manager.get_version(version_v1)
        v2_info = manager.get_version(version_v2)
        
        assert v2_info.performance_score > v1_info.performance_score
        assert v2_info.success_rate > v1_info.success_rate
        
        manager.cleanup()


class TestGlobalManagerIntegration:
    """Test integration with global manager instance."""
    
    @pytest.fixture(autouse=True)
    def reset_global_manager(self):
        """Reset global manager before each test."""
        import hydra.prompts.versioning
        hydra.prompts.versioning._global_version_manager = None
        yield
        if hydra.prompts.versioning._global_version_manager:
            hydra.prompts.versioning._global_version_manager.cleanup()
        hydra.prompts.versioning._global_version_manager = None
    
    def test_global_manager_persistence(self):
        """Test that global manager persists across function calls."""
        # First access should create manager
        manager1 = get_version_manager(enable_hot_reload=False)
        
        # Create version through manager
        content = {"prompts": {"test": {"template": "Test {value}"}}}
        version_id = manager1.create_version(content)
        
        # Second access should return same manager with persisted data
        manager2 = get_version_manager()
        
        assert manager1 is manager2
        
        # Should be able to access previously created version
        version_info = manager2.get_version(version_id)
        assert version_info is not None
        assert version_info.content == content
        
        manager1.cleanup()
    
    def test_convenience_functions_integration(self):
        """Test integration of convenience functions with global manager."""
        # Use convenience function to record usage
        record_prompt_usage(
            prompt_name="integration_test",
            execution_time=1.5,
            success=True,
            variant="test_variant",
            metadata={"test": True}
        )
        
        # Access global manager to verify data was recorded
        manager = get_version_manager()
        manager.flush_metrics()
        
        perf = manager.get_prompt_performance("integration_test", "test_variant")
        
        assert perf["total_count"] == 1
        assert perf["success_rate"] == 1.0
        assert perf["avg_execution_time"] == 1.5
        
        manager.cleanup()
    
    def test_cross_function_version_access(self):
        """Test accessing versions across different function calls."""
        from hydra.prompts.versioning import create_prompt_version
        
        # Create version using convenience function
        content = {"prompts": {"cross_test": {"template": "Cross function test: {data}"}}}
        version_id = create_prompt_version(content, "cross_v1")
        
        # Access through different interface
        manager = get_version_manager()
        version_info = manager.get_version(version_id)
        
        assert version_info is not None
        assert version_info.version_id == "cross_v1"
        assert version_info.content == content
        
        # Test rollback through manager
        assert manager.rollback_to_version(version_id)
        
        # Verify rollback version exists
        versions = manager.list_versions()
        rollback_versions = [v for v in versions if "rollback" in v.version_id]
        assert len(rollback_versions) >= 1
        
        manager.cleanup()