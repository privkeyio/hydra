"""Tests for prompt versioning and hot-reload system."""

import json
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydra.prompts.versioning import (
    ABTestConfig,
    PromptMetrics,
    PromptVersionInfo,
    PromptVersionManager,
    create_prompt_version,
    get_ab_test_prompt,
    get_version_manager,
    record_prompt_usage,
)


class TestPromptVersionInfo:
    """Test PromptVersionInfo dataclass."""
    
    def test_initialization(self):
        """Test basic initialization."""
        version = PromptVersionInfo(
            version_id="test_v1",
            content_hash="abc123",
            timestamp=datetime.now(),
            content={"test": "data"}
        )
        
        assert version.version_id == "test_v1"
        assert version.content_hash == "abc123"
        assert version.performance_score == 0.0
        assert version.metadata == {}
    
    def test_with_metadata(self):
        """Test initialization with metadata."""
        metadata = {"author": "test", "purpose": "testing"}
        version = PromptVersionInfo(
            version_id="test_v1",
            content_hash="abc123",
            timestamp=datetime.now(),
            content={"test": "data"},
            metadata=metadata
        )
        
        assert version.metadata == metadata


class TestABTestConfig:
    """Test ABTestConfig dataclass."""
    
    def test_initialization(self):
        """Test basic initialization."""
        variants = {"control": "Hello {name}", "variant": "Hi {name}"}
        traffic_split = {"control": 0.5, "variant": 0.5}
        
        config = ABTestConfig(
            test_id="test_001",
            variants=variants,
            traffic_split=traffic_split
        )
        
        assert config.test_id == "test_001"
        assert config.variants == variants
        assert config.traffic_split == traffic_split
        assert config.active is True
        assert config.start_time is not None


class TestPromptMetrics:
    """Test PromptMetrics dataclass."""
    
    def test_initialization(self):
        """Test basic initialization."""
        metrics = PromptMetrics(
            prompt_name="test_prompt",
            execution_time=1.5,
            success=True
        )
        
        assert metrics.prompt_name == "test_prompt"
        assert metrics.variant == "default"
        assert metrics.execution_time == 1.5
        assert metrics.success is True
        assert metrics.timestamp is not None


class TestPromptVersionManager:
    """Test PromptVersionManager class."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        yield db_path
        
        # Cleanup
        Path(db_path).unlink(missing_ok=True)
    
    @pytest.fixture
    def version_manager(self, temp_db):
        """Create version manager with temporary database."""
        return PromptVersionManager(
            db_path=temp_db,
            enable_hot_reload=False  # Disable for testing
        )
    
    def test_initialization(self, version_manager):
        """Test version manager initialization."""
        assert version_manager.db_path is not None
        assert not version_manager.enable_hot_reload
        assert version_manager._metrics_buffer == []
    
    def test_database_initialization(self, temp_db):
        """Test database table creation."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            assert "prompt_versions" in tables
            assert "ab_tests" in tables
            assert "prompt_metrics" in tables
    
    def test_create_version(self, version_manager):
        """Test version creation."""
        content = {"prompts": {"test": {"template": "Hello {name}"}}}
        
        version_id = version_manager.create_version(content)
        
        assert version_id is not None
        assert version_id.startswith("v")
        
        # Verify in database
        version_info = version_manager.get_version(version_id)
        assert version_info is not None
        assert version_info.content == content
    
    def test_create_version_with_custom_id(self, version_manager):
        """Test version creation with custom ID."""
        content = {"prompts": {"test": {"template": "Hello {name}"}}}
        custom_id = "custom_v1.0"
        
        version_id = version_manager.create_version(content, custom_id)
        
        assert version_id == custom_id
        
        version_info = version_manager.get_version(version_id)
        assert version_info.version_id == custom_id
    
    def test_get_nonexistent_version(self, version_manager):
        """Test getting non-existent version."""
        result = version_manager.get_version("nonexistent")
        assert result is None
    
    def test_list_versions(self, version_manager):
        """Test listing versions."""
        # Create multiple versions
        for i in range(3):
            content = {"prompts": {f"test_{i}": {"template": f"Hello {i}"}}}
            version_manager.create_version(content, f"test_v{i}")
        
        versions = version_manager.list_versions()
        
        assert len(versions) == 3
        # Should be sorted by timestamp (newest first)
        assert all(isinstance(v, PromptVersionInfo) for v in versions)
    
    def test_rollback_to_version(self, version_manager):
        """Test version rollback."""
        content = {"prompts": {"test": {"template": "Original"}}}
        version_id = version_manager.create_version(content, "original_v1")
        
        result = version_manager.rollback_to_version(version_id)
        
        assert result is True
        
        # Check rollback version was created
        versions = version_manager.list_versions()
        rollback_versions = [v for v in versions if "rollback" in v.version_id]
        assert len(rollback_versions) >= 1
    
    def test_rollback_nonexistent_version(self, version_manager):
        """Test rollback to non-existent version."""
        result = version_manager.rollback_to_version("nonexistent")
        assert result is False
    
    def test_delete_version(self, version_manager):
        """Test version deletion."""
        content = {"prompts": {"test": {"template": "Delete me"}}}
        version_id = version_manager.create_version(content)
        
        # Verify exists
        assert version_manager.get_version(version_id) is not None
        
        # Delete
        result = version_manager.delete_version(version_id)
        assert result is True
        
        # Verify deleted
        assert version_manager.get_version(version_id) is None
    
    def test_create_ab_test(self, version_manager):
        """Test A/B test creation."""
        variants = {"control": "Hello {name}", "variant": "Hi {name}"}
        
        ab_test = version_manager.create_ab_test("test_001", variants)
        
        assert ab_test.test_id == "test_001"
        assert ab_test.variants == variants
        assert sum(ab_test.traffic_split.values()) == pytest.approx(1.0)
    
    def test_ab_test_variant_assignment(self, version_manager):
        """Test A/B test variant assignment."""
        variants = {"control": "Hello {name}", "variant": "Hi {name}"}
        version_manager.create_ab_test("test_001", variants)
        
        # Same user should get same variant consistently
        user_id = "user_123"
        variant1 = version_manager.get_ab_test_variant("test_001", user_id)
        variant2 = version_manager.get_ab_test_variant("test_001", user_id)
        
        assert variant1 == variant2
        assert variant1 in variants.keys()
    
    def test_ab_test_nonexistent(self, version_manager):
        """Test A/B test with non-existent test."""
        result = version_manager.get_ab_test_variant("nonexistent", "user_123")
        assert result is None
    
    def test_record_metrics(self, version_manager):
        """Test metrics recording."""
        metrics = PromptMetrics(
            prompt_name="test_prompt",
            execution_time=1.5,
            success=True
        )
        
        version_manager.record_metrics(metrics)
        
        assert len(version_manager._metrics_buffer) == 1
        assert version_manager._metrics_buffer[0] == metrics
    
    def test_flush_metrics(self, version_manager):
        """Test metrics flushing to database."""
        metrics = PromptMetrics(
            prompt_name="test_prompt",
            execution_time=1.5,
            success=True
        )
        
        version_manager.record_metrics(metrics)
        version_manager.flush_metrics()
        
        assert len(version_manager._metrics_buffer) == 0
        
        # Verify in database
        performance = version_manager.get_prompt_performance("test_prompt")
        assert performance["total_count"] == 1
        assert performance["success_rate"] == 1.0
    
    def test_get_prompt_performance(self, version_manager):
        """Test prompt performance retrieval."""
        # Record some metrics
        for i in range(5):
            metrics = PromptMetrics(
                prompt_name="test_prompt",
                execution_time=1.0 + i * 0.1,
                success=i % 2 == 0  # Alternate success/failure
            )
            version_manager.record_metrics(metrics)
        
        version_manager.flush_metrics()
        
        performance = version_manager.get_prompt_performance("test_prompt")
        
        assert performance["total_count"] == 5
        assert performance["success_rate"] == 0.6  # 3 out of 5 successful
        assert performance["avg_execution_time"] == pytest.approx(1.2)
    
    def test_get_prompt_performance_with_time_window(self, version_manager):
        """Test prompt performance with time window."""
        # Record old metrics
        old_metrics = PromptMetrics(
            prompt_name="test_prompt",
            execution_time=1.0,
            success=True,
            timestamp=datetime.now() - timedelta(days=10)
        )
        version_manager.record_metrics(old_metrics)
        
        # Record recent metrics
        recent_metrics = PromptMetrics(
            prompt_name="test_prompt",
            execution_time=2.0,
            success=False
        )
        version_manager.record_metrics(recent_metrics)
        
        version_manager.flush_metrics()
        
        # Get performance for last 7 days (should only include recent)
        recent_performance = version_manager.get_prompt_performance(
            "test_prompt",
            time_window=timedelta(days=7)
        )
        
        assert recent_performance["total_count"] == 1
        assert recent_performance["success_rate"] == 0.0
        
        # Get all-time performance
        all_performance = version_manager.get_prompt_performance("test_prompt")
        assert all_performance["total_count"] == 2
    
    def test_get_optimization_suggestions(self, version_manager):
        """Test optimization suggestions generation."""
        # Record poor performance metrics
        for _ in range(10):
            metrics = PromptMetrics(
                prompt_name="poor_prompt",
                execution_time=6.0,  # Slow
                success=False  # Poor success rate
            )
            version_manager.record_metrics(metrics)
        
        version_manager.flush_metrics()
        
        suggestions = version_manager.get_optimization_suggestions("poor_prompt")
        
        assert len(suggestions) > 0
        
        # Should have suggestions for success rate and performance
        suggestion_types = [s["type"] for s in suggestions]
        assert "success_rate" in suggestion_types
        assert "performance" in suggestion_types
    
    def test_update_version_performance(self, version_manager):
        """Test updating version performance metrics."""
        content = {"prompts": {"test": {"template": "Hello"}}}
        version_id = version_manager.create_version(content)
        
        version_manager.update_version_performance(
            version_id=version_id,
            performance_score=0.85,
            usage_count=100,
            success_rate=0.9,
            avg_execution_time=1.5
        )
        
        version_info = version_manager.get_version(version_id)
        assert version_info.performance_score == 0.85
        assert version_info.usage_count == 100
        assert version_info.success_rate == 0.9
        assert version_info.avg_execution_time == 1.5
    
    def test_test_version_context_manager(self, version_manager):
        """Test version testing context manager."""
        content = {"prompts": {"test": {"template": "Hello"}}}
        version_id = version_manager.create_version(content)
        
        with version_manager.test_version(version_id) as version_info:
            assert version_info.version_id == version_id
            assert version_info.content == content
    
    def test_test_nonexistent_version_context_manager(self, version_manager):
        """Test context manager with non-existent version."""
        with pytest.raises(ValueError, match="Version nonexistent not found"):
            with version_manager.test_version("nonexistent"):
                pass
    
    def test_add_reload_callback(self, version_manager):
        """Test adding reload callback."""
        callback_called = []
        
        def test_callback(file_path):
            callback_called.append(file_path)
        
        version_manager.add_reload_callback(test_callback)
        
        # Simulate file change
        version_manager._handle_file_change("/test/path.yaml")
        
        assert len(callback_called) == 1
        assert callback_called[0] == "/test/path.yaml"
    
    def test_cleanup(self, version_manager):
        """Test cleanup method."""
        # Add some metrics
        metrics = PromptMetrics(prompt_name="test", execution_time=1.0, success=True)
        version_manager.record_metrics(metrics)
        
        version_manager.cleanup()
        
        # Metrics should be flushed
        assert len(version_manager._metrics_buffer) == 0


class TestGlobalFunctions:
    """Test global convenience functions."""
    
    @pytest.fixture(autouse=True)
    def reset_global_manager(self):
        """Reset global manager before each test."""
        import hydra.prompts.versioning
        hydra.prompts.versioning._global_version_manager = None
        yield
        if hydra.prompts.versioning._global_version_manager:
            hydra.prompts.versioning._global_version_manager.cleanup()
        hydra.prompts.versioning._global_version_manager = None
    
    @patch('hydra.prompts.versioning.PromptVersionManager')
    def test_get_version_manager(self, mock_manager_class):
        """Test global version manager getter."""
        mock_instance = MagicMock()
        mock_manager_class.return_value = mock_instance
        
        # First call should create instance
        manager1 = get_version_manager(enable_hot_reload=False)
        assert manager1 == mock_instance
        mock_manager_class.assert_called_once_with(enable_hot_reload=False)
        
        # Second call should return same instance
        manager2 = get_version_manager()
        assert manager2 == mock_instance
        # Should not call constructor again
        assert mock_manager_class.call_count == 1
    
    @patch('hydra.prompts.versioning.get_version_manager')
    def test_record_prompt_usage(self, mock_get_manager):
        """Test record_prompt_usage function."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        
        record_prompt_usage(
            prompt_name="test_prompt",
            execution_time=1.5,
            success=True,
            variant="test_variant",
            metadata={"key": "value"}
        )
        
        mock_manager.record_metrics.assert_called_once()
        metrics = mock_manager.record_metrics.call_args[0][0]
        
        assert metrics.prompt_name == "test_prompt"
        assert metrics.execution_time == 1.5
        assert metrics.success is True
        assert metrics.variant == "test_variant"
        assert metrics.metadata == {"key": "value"}
    
    @patch('hydra.prompts.versioning.get_version_manager')
    def test_create_prompt_version(self, mock_get_manager):
        """Test create_prompt_version function."""
        mock_manager = MagicMock()
        mock_manager.create_version.return_value = "test_version_id"
        mock_get_manager.return_value = mock_manager
        
        content = {"prompts": {"test": {"template": "Hello"}}}
        result = create_prompt_version(content, "custom_id")
        
        assert result == "test_version_id"
        mock_manager.create_version.assert_called_once_with(content, "custom_id")
    
    @patch('hydra.prompts.versioning.get_version_manager')
    def test_get_ab_test_prompt(self, mock_get_manager):
        """Test get_ab_test_prompt function."""
        mock_manager = MagicMock()
        mock_manager.get_ab_test_variant.return_value = "variant_a"
        mock_manager._ab_tests = {
            "test_001": ABTestConfig(
                test_id="test_001",
                variants={"variant_a": "Hello A", "variant_b": "Hello B"},
                traffic_split={"variant_a": 0.5, "variant_b": 0.5}
            )
        }
        mock_get_manager.return_value = mock_manager
        
        result = get_ab_test_prompt("test_001", "user_123", "Default")
        
        assert result == "Hello A"
        mock_manager.get_ab_test_variant.assert_called_once_with("test_001", "user_123")
    
    @patch('hydra.prompts.versioning.get_version_manager')
    def test_get_ab_test_prompt_no_test(self, mock_get_manager):
        """Test get_ab_test_prompt with no active test."""
        mock_manager = MagicMock()
        mock_manager.get_ab_test_variant.return_value = None
        mock_get_manager.return_value = mock_manager
        
        result = get_ab_test_prompt("nonexistent", "user_123", "Default")
        
        assert result == "Default"


class TestHotReload:
    """Test hot-reload functionality."""
    
    @patch('hydra.prompts.versioning.WATCHDOG_AVAILABLE', True)
    @patch('hydra.prompts.versioning.Observer')
    def test_setup_watchers(self, mock_observer_class):
        """Test file watcher setup."""
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer
        
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PromptVersionManager(
                enable_hot_reload=True,
                watch_directories=[temp_dir]
            )
            
            mock_observer.schedule.assert_called()
            mock_observer.start.assert_called()
            
            manager.cleanup()
            mock_observer.stop.assert_called()
    
    @patch('hydra.prompts.versioning.WATCHDOG_AVAILABLE', False)
    def test_setup_watchers_no_watchdog(self, capsys):
        """Test watcher setup when watchdog not available."""
        manager = PromptVersionManager(enable_hot_reload=True)
        
        captured = capsys.readouterr()
        assert "watchdog not available" in captured.out.lower()
        
        manager.cleanup()


class TestIntegration:
    """Integration tests for complete workflows."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        yield db_path
        
        Path(db_path).unlink(missing_ok=True)
    
    def test_complete_version_lifecycle(self, temp_db):
        """Test complete version management lifecycle."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        # Create initial version
        content_v1 = {"prompts": {"greeting": {"template": "Hello {name}"}}}
        version_v1 = manager.create_version(content_v1, "v1.0")
        
        # Create updated version
        content_v2 = {"prompts": {"greeting": {"template": "Hi {name}!"}}}
        version_v2 = manager.create_version(content_v2, "v2.0")
        
        # List versions
        versions = manager.list_versions()
        assert len(versions) == 2
        
        # Test rollback
        assert manager.rollback_to_version(version_v1)
        
        # Verify rollback created new version
        versions_after_rollback = manager.list_versions()
        assert len(versions_after_rollback) == 3
        
        manager.cleanup()
    
    def test_ab_test_with_metrics(self, temp_db):
        """Test A/B testing with performance metrics."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        # Create A/B test
        variants = {"control": "Hello {name}", "test": "Hi there {name}!"}
        ab_test = manager.create_ab_test("greeting_test", variants)
        
        # Simulate usage and record metrics
        for i in range(20):
            user_id = f"user_{i}"
            variant = manager.get_ab_test_variant("greeting_test", user_id)
            
            # Simulate better performance for test variant
            success = variant == "test" or i % 3 == 0
            execution_time = 1.0 if variant == "test" else 1.5
            
            metrics = PromptMetrics(
                prompt_name="greeting",
                variant=variant,
                execution_time=execution_time,
                success=success
            )
            manager.record_metrics(metrics)
        
        manager.flush_metrics()
        
        # Check performance for each variant
        control_perf = manager.get_prompt_performance("greeting", "control")
        test_perf = manager.get_prompt_performance("greeting", "test")
        
        assert control_perf["total_count"] > 0
        assert test_perf["total_count"] > 0
        
        # Test variant should perform better
        assert test_perf["success_rate"] >= control_perf["success_rate"]
        assert test_perf["avg_execution_time"] <= control_perf["avg_execution_time"]
        
        manager.cleanup()
    
    def test_optimization_suggestions_workflow(self, temp_db):
        """Test optimization suggestions workflow."""
        manager = PromptVersionManager(db_path=temp_db, enable_hot_reload=False)
        
        # Record poor performance metrics
        for i in range(50):
            metrics = PromptMetrics(
                prompt_name="slow_prompt",
                execution_time=8.0,  # Very slow
                success=i % 5 == 0,  # 20% success rate
                timestamp=datetime.now() - timedelta(minutes=i)
            )
            manager.record_metrics(metrics)
        
        manager.flush_metrics()
        
        # Get suggestions
        suggestions = manager.get_optimization_suggestions("slow_prompt")
        
        # Should have multiple suggestions
        assert len(suggestions) >= 2
        
        # Check for expected suggestion types
        suggestion_types = {s["type"] for s in suggestions}
        assert "success_rate" in suggestion_types
        assert "performance" in suggestion_types
        
        # High severity suggestions should be present
        high_severity = [s for s in suggestions if s["severity"] == "high"]
        assert len(high_severity) > 0
        
        manager.cleanup()