"""Unit tests for capability negotiation system."""
import time
from unittest.mock import Mock, patch

import pytest

from hydra.providers.capability_manager import (
    CapabilityCache,
    CapabilityManager,
    CapabilitySubstitution,
    ProviderComposition,
    ProviderScore,
    TaskRequirement,
)
from hydra.providers.interactive_base import ProviderCapability, ProviderConfig


class MockProvider:
    """Mock provider for testing."""
    
    def __init__(self, name: str, capabilities: set):
        self.name = name
        self._capabilities = capabilities
        self.detect_calls = 0
    
    def detect_capabilities(self):
        self.detect_calls += 1
        return self._capabilities
    
    def get_capabilities(self):
        return self._capabilities


class TestTaskRequirement:
    """Test TaskRequirement dataclass."""
    
    def test_creation(self):
        req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS},
            preferred_capabilities={ProviderCapability.STREAMING_RESPONSE}
        )
        assert req.required_capabilities == {ProviderCapability.FILE_OPERATIONS}
        assert req.preferred_capabilities == {ProviderCapability.STREAMING_RESPONSE}
        assert req.minimum_providers == 1
    
    def test_serialization(self):
        req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION},
            preferred_capabilities={ProviderCapability.STREAMING_RESPONSE},
            task_type="file_task",
            metadata={"priority": "high"}
        )
        
        data = req.to_dict()
        restored = TaskRequirement.from_dict(data)
        
        assert restored.required_capabilities == req.required_capabilities
        assert restored.preferred_capabilities == req.preferred_capabilities
        assert restored.task_type == req.task_type
        assert restored.metadata == req.metadata


class TestCapabilityCache:
    """Test CapabilityCache dataclass."""
    
    def test_expiration(self):
        cache = CapabilityCache(
            provider_name="test_provider",
            capabilities={ProviderCapability.FILE_OPERATIONS},
            last_probed=time.time() - 400,  # 400 seconds ago
            cache_ttl=300  # 5 minute TTL
        )
        
        assert cache.is_expired()
    
    def test_not_expired(self):
        cache = CapabilityCache(
            provider_name="test_provider",
            capabilities={ProviderCapability.FILE_OPERATIONS},
            last_probed=time.time() - 100,  # 100 seconds ago
            cache_ttl=300  # 5 minute TTL
        )
        
        assert not cache.is_expired()
    
    def test_serialization(self):
        cache = CapabilityCache(
            provider_name="test_provider",
            capabilities={ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION},
            last_probed=time.time(),
            probe_count=5,
            cache_ttl=600
        )
        
        data = cache.to_dict()
        restored = CapabilityCache.from_dict(data)
        
        assert restored.provider_name == cache.provider_name
        assert restored.capabilities == cache.capabilities
        assert restored.probe_count == cache.probe_count
        assert restored.cache_ttl == cache.cache_ttl


class TestCapabilitySubstitution:
    """Test CapabilitySubstitution fallback strategy."""
    
    def test_successful_substitution(self):
        strategy = CapabilitySubstitution()
        
        # Create provider with substitute capability
        provider = MockProvider("test", {ProviderCapability.TASK_EXECUTION})
        
        # Missing streaming capability but has substitute
        missing = {ProviderCapability.STREAMING_RESPONSE}
        task_req = TaskRequirement(required_capabilities=missing)
        
        result = strategy.apply(missing, [provider], task_req)
        
        assert result == [provider]
    
    def test_failed_substitution(self):
        strategy = CapabilitySubstitution()
        
        # Create provider without substitute capability
        provider = MockProvider("test", {ProviderCapability.FILE_OPERATIONS})
        
        # Missing capability with no substitute available
        missing = {ProviderCapability.STREAMING_RESPONSE}
        task_req = TaskRequirement(required_capabilities=missing)
        
        result = strategy.apply(missing, [provider], task_req)
        
        assert result is None


class TestProviderComposition:
    """Test ProviderComposition fallback strategy."""
    
    def test_successful_composition(self):
        strategy = ProviderComposition()
        
        # Create providers with different capabilities
        provider1 = MockProvider("test1", {ProviderCapability.FILE_OPERATIONS})
        provider2 = MockProvider("test2", {ProviderCapability.SHELL_EXECUTION})
        
        # Need both capabilities, allow multiple providers
        missing = {ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION}
        task_req = TaskRequirement(
            required_capabilities=missing,
            minimum_providers=2
        )
        
        result = strategy.apply(missing, [provider1, provider2], task_req)
        
        assert len(result) == 2
        assert provider1 in result
        assert provider2 in result
    
    def test_single_provider_requirement(self):
        strategy = ProviderComposition()
        
        provider1 = MockProvider("test1", {ProviderCapability.FILE_OPERATIONS})
        provider2 = MockProvider("test2", {ProviderCapability.SHELL_EXECUTION})
        
        missing = {ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION}
        task_req = TaskRequirement(
            required_capabilities=missing,
            minimum_providers=1  # Only allow single provider
        )
        
        result = strategy.apply(missing, [provider1, provider2], task_req)
        
        assert result is None


class TestCapabilityManager:
    """Test CapabilityManager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = CapabilityManager(cache_ttl=300)
        
        # Create mock providers
        self.provider1 = MockProvider("provider1", {
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.SHELL_EXECUTION
        })
        self.provider2 = MockProvider("provider2", {
            ProviderCapability.STREAMING_RESPONSE,
            ProviderCapability.SESSION_PERSISTENCE
        })
        self.provider3 = MockProvider("provider3", {
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.STREAMING_RESPONSE,
            ProviderCapability.SHELL_EXECUTION
        })
    
    def test_register_provider(self):
        self.manager.register_provider(self.provider1)
        assert self.provider1 in self.manager._providers
        
        # Don't register same provider twice
        self.manager.register_provider(self.provider1)
        assert self.manager._providers.count(self.provider1) == 1
    
    def test_unregister_provider(self):
        self.manager.register_provider(self.provider1)
        self.manager.unregister_provider(self.provider1)
        assert self.provider1 not in self.manager._providers
    
    def test_probe_provider_capabilities(self):
        capabilities = self.manager.probe_provider_capabilities(self.provider1)
        
        assert capabilities == {ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION}
        assert self.provider1.detect_calls == 1
        
        # Should use cache on second call
        capabilities2 = self.manager.probe_provider_capabilities(self.provider1)
        assert capabilities2 == capabilities
        assert self.provider1.detect_calls == 1  # No additional call
    
    def test_probe_with_force_refresh(self):
        # First call
        self.manager.probe_provider_capabilities(self.provider1)
        assert self.provider1.detect_calls == 1
        
        # Force refresh should bypass cache
        self.manager.probe_provider_capabilities(self.provider1, force_refresh=True)
        assert self.provider1.detect_calls == 2
    
    def test_score_provider(self):
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS},
            preferred_capabilities={ProviderCapability.SHELL_EXECUTION}
        )
        
        score = self.manager.score_provider(self.provider1, task_req)
        
        assert score.provider_name == "provider1"
        assert score.capability_score == 100.0  # Has required capability
        assert score.preference_score == 50.0   # Has preferred capability
        assert score.total_score == 150.0
        assert len(score.missing_required) == 0
        assert ProviderCapability.SHELL_EXECUTION in score.has_preferred
    
    def test_score_provider_missing_required(self):
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS, ProviderCapability.STREAMING_RESPONSE}
        )
        
        score = self.manager.score_provider(self.provider1, task_req)
        
        assert score.capability_score == 50.0  # Has 1 of 2 required
        assert ProviderCapability.STREAMING_RESPONSE in score.missing_required
    
    def test_select_providers_perfect_match(self):
        self.manager.register_provider(self.provider1)
        self.manager.register_provider(self.provider2)
        self.manager.register_provider(self.provider3)
        
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION}
        )
        
        selected = self.manager.select_providers(task_req)
        
        # provider3 has both capabilities, should be selected
        assert len(selected) == 1
        assert selected[0] == self.provider3
    
    def test_select_providers_fallback(self):
        self.manager.register_provider(self.provider1)
        self.manager.register_provider(self.provider2)
        
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.STREAMING_RESPONSE}
        )
        
        selected = self.manager.select_providers(task_req)
        
        # provider2 has streaming capability
        assert len(selected) == 1
        assert selected[0] == self.provider2
    
    def test_select_providers_no_match(self):
        self.manager.register_provider(self.provider1)
        
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.CONCURRENT_SESSIONS}  # No provider has this
        )
        
        selected = self.manager.select_providers(task_req)
        
        # Should return best available provider even if doesn't meet requirements
        assert len(selected) == 1
        assert selected[0] == self.provider1
    
    def test_select_providers_no_providers(self):
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS}
        )
        
        with pytest.raises(RuntimeError, match="No providers registered"):
            self.manager.select_providers(task_req)
    
    def test_get_provider_capabilities(self):
        self.manager.register_provider(self.provider1)
        
        # Should return None for unknown provider
        assert self.manager.get_provider_capabilities("unknown") is None
        
        # Should probe and return capabilities for known provider
        caps = self.manager.get_provider_capabilities("provider1")
        assert caps == {ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION}
    
    def test_refresh_all_capabilities(self):
        self.manager.register_provider(self.provider1)
        self.manager.register_provider(self.provider2)
        
        # Initial probe
        self.manager.probe_provider_capabilities(self.provider1)
        self.manager.probe_provider_capabilities(self.provider2)
        
        initial_calls1 = self.provider1.detect_calls
        initial_calls2 = self.provider2.detect_calls
        
        # Refresh all
        self.manager.refresh_all_capabilities()
        
        assert self.provider1.detect_calls > initial_calls1
        assert self.provider2.detect_calls > initial_calls2
    
    def test_cache_stats(self):
        self.manager.register_provider(self.provider1)
        
        # Initial probe (cache miss)
        self.manager.probe_provider_capabilities(self.provider1)
        
        # Second probe (cache hit)
        self.manager.probe_provider_capabilities(self.provider1)
        
        stats = self.manager.get_cache_stats()
        
        assert stats['total_entries'] == 1
        assert stats['active_entries'] == 1
        assert stats['probe_stats']['cache_hits'] == 1
        assert stats['probe_stats']['cache_misses'] == 1
        assert stats['cache_hit_rate'] == 50.0
    
    def test_clear_expired_cache(self):
        # Create expired cache entry manually
        expired_cache = CapabilityCache(
            provider_name="expired_provider",
            capabilities={ProviderCapability.FILE_OPERATIONS},
            last_probed=time.time() - 400,  # 400 seconds ago
            cache_ttl=300
        )
        self.manager._capability_cache["expired_provider"] = expired_cache
        
        # Create non-expired entry
        self.manager.probe_provider_capabilities(self.provider1)
        
        assert len(self.manager._capability_cache) == 2
        
        cleared = self.manager.clear_expired_cache()
        
        assert cleared == 1
        assert len(self.manager._capability_cache) == 1
        assert "provider1" in self.manager._capability_cache
    
    def test_cache_serialization(self):
        self.manager.register_provider(self.provider1)
        self.manager.probe_provider_capabilities(self.provider1)
        
        # Serialize
        data = self.manager.serialize_cache()
        
        # Create new manager and deserialize
        new_manager = CapabilityManager()
        new_manager.deserialize_cache(data)
        
        assert len(new_manager._capability_cache) == 1
        assert "provider1" in new_manager._capability_cache
        
        cache_entry = new_manager._capability_cache["provider1"]
        assert cache_entry.capabilities == {ProviderCapability.FILE_OPERATIONS, ProviderCapability.SHELL_EXECUTION}
    
    def test_fallback_strategy_management(self):
        initial_count = len(self.manager._fallback_strategies)
        
        # Add custom strategy
        custom_strategy = CapabilitySubstitution()
        custom_strategy.name = "custom"
        self.manager.add_fallback_strategy(custom_strategy)
        
        assert len(self.manager._fallback_strategies) == initial_count + 1
        
        # Remove strategy
        removed = self.manager.remove_fallback_strategy("custom")
        assert removed
        assert len(self.manager._fallback_strategies) == initial_count
        
        # Try to remove non-existent strategy
        removed = self.manager.remove_fallback_strategy("nonexistent")
        assert not removed


class TestIntegrationScenarios:
    """Integration tests for complex capability negotiation scenarios."""
    
    def setup_method(self):
        """Set up integration test fixtures."""
        self.manager = CapabilityManager()
        
        # Create providers with different capability profiles
        self.file_provider = MockProvider("file_provider", {
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.SESSION_PERSISTENCE
        })
        
        self.shell_provider = MockProvider("shell_provider", {
            ProviderCapability.SHELL_EXECUTION,
            ProviderCapability.TASK_EXECUTION
        })
        
        self.streaming_provider = MockProvider("streaming_provider", {
            ProviderCapability.STREAMING_RESPONSE,
            ProviderCapability.PROMPT_HANDLING
        })
        
        self.full_featured_provider = MockProvider("full_provider", {
            ProviderCapability.FILE_OPERATIONS,
            ProviderCapability.SHELL_EXECUTION,
            ProviderCapability.SESSION_PERSISTENCE,
            ProviderCapability.STREAMING_RESPONSE,
            ProviderCapability.TASK_EXECUTION
        })
        
        # Register all providers
        for provider in [self.file_provider, self.shell_provider, 
                        self.streaming_provider, self.full_featured_provider]:
            self.manager.register_provider(provider)
    
    def test_simple_task_selection(self):
        """Test selection for a simple file operation task."""
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS},
            task_type="file_edit"
        )
        
        selected = self.manager.select_providers(task_req)
        
        # Should select the full-featured provider as it scores highest
        assert len(selected) == 1
        assert selected[0] == self.full_featured_provider
    
    def test_complex_task_selection(self):
        """Test selection for a complex task requiring multiple capabilities."""
        task_req = TaskRequirement(
            required_capabilities={
                ProviderCapability.FILE_OPERATIONS,
                ProviderCapability.SHELL_EXECUTION,
                ProviderCapability.SESSION_PERSISTENCE
            },
            preferred_capabilities={ProviderCapability.STREAMING_RESPONSE}
        )
        
        selected = self.manager.select_providers(task_req)
        
        # Only full_featured_provider has all required + preferred
        assert len(selected) == 1
        assert selected[0] == self.full_featured_provider
    
    def test_fallback_composition_scenario(self):
        """Test fallback to provider composition when no single provider suffices."""
        # Temporarily remove full-featured provider
        self.manager.unregister_provider(self.full_featured_provider)
        
        task_req = TaskRequirement(
            required_capabilities={
                ProviderCapability.FILE_OPERATIONS,
                ProviderCapability.SHELL_EXECUTION
            },
            minimum_providers=2  # Allow composition
        )
        
        selected = self.manager.select_providers(task_req)
        
        # Should get composition of file_provider + shell_provider
        assert len(selected) == 2
        provider_names = {p.name for p in selected}
        assert "file_provider" in provider_names
        assert "shell_provider" in provider_names
    
    def test_caching_performance(self):
        """Test that caching improves performance for repeated queries."""
        task_req = TaskRequirement(
            required_capabilities={ProviderCapability.FILE_OPERATIONS}
        )
        
        # First selection - should probe all providers
        start_time = time.time()
        selected1 = self.manager.select_providers(task_req)
        first_duration = time.time() - start_time
        
        # Second selection - should use cache
        start_time = time.time()
        selected2 = self.manager.select_providers(task_req)
        second_duration = time.time() - start_time
        
        # Results should be identical
        assert selected1 == selected2
        
        # Cache stats should show hits
        stats = self.manager.get_cache_stats()
        assert stats['cache_hit_rate'] > 0