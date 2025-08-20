"""Integration tests for provider prompt injection system.

Tests that all providers correctly use the new centralized prompt system
without regression in functionality.
"""

import pytest
from unittest.mock import Mock, patch

from hydra.providers.base import LLMConfig
from hydra.providers.mock_provider import MockProvider
from hydra.providers.provider_factory import get_factory
from hydra.prompts.injection import (
    InjectionContext,
    InjectorRegistry,
    initialize_default_injectors,
)


class TestProviderPromptInjection:
    """Test prompt injection across all providers."""
    
    def setup_method(self):
        """Setup test environment."""
        # Initialize injection system
        initialize_default_injectors()
        self.factory = get_factory()
    
    def test_mock_provider_injection(self):
        """Test MockProvider uses injection system."""
        config = LLMConfig(
            provider_type="mock",
            model="mock-model-1",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Test with injection enabled
        result = provider.generate(
            "test prompt",
            operation="code_execution",
            test_injection=True
        )
        
        # Check that injection was applied (recorded in call history)
        injection_calls = [
            call for call in provider.call_history 
            if call.get("method") == "_inject_prompts"
        ]
        assert len(injection_calls) > 0
        assert injection_calls[0]["context"]["operation"] == "code_execution"
    
    def test_mock_provider_json_injection(self):
        """Test MockProvider JSON generation with injection."""
        config = LLMConfig(
            provider_type="mock", 
            model="mock-model-1",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Test JSON generation with injection
        result = provider.generate_json(
            "generate json data",
            test_injection=True
        )
        
        # Verify injection was applied
        injection_calls = [
            call for call in provider.call_history
            if call.get("method") == "_inject_prompts"
        ]
        assert len(injection_calls) > 0
        assert injection_calls[0]["context"]["operation"] == "json_generation"
    
    def test_injection_context_creation(self):
        """Test that injection contexts are properly created."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Create injection context
        context = InjectionContext(
            operation="test_execution",
            provider="mock",
            model="test-model",
            user_prompt="test prompt",
            metadata={"test": True}
        )
        
        # Test injection
        result = provider._inject_prompts(context)
        
        # Verify injection was recorded
        injection_calls = [
            call for call in provider.call_history
            if call.get("method") == "_inject_prompts"
        ]
        assert len(injection_calls) > 0
        assert injection_calls[0]["context"]["operation"] == "test_execution"
    
    @pytest.mark.parametrize("operation,expected_suffix", [
        ("code_execution", ""),  # Production injector
        ("json_generation", "JSON only."),  # Special JSON handling
        ("ticket_generation", ""),  # Ticket injector
    ])
    def test_operation_specific_injection(self, operation, expected_suffix):
        """Test that different operations get appropriate injections."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model", 
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        context = InjectionContext(
            operation=operation,
            provider="mock",
            model="test-model",
            user_prompt="test prompt pass fail check verify",  # Include verification keywords
            metadata={}
        )
        
        result = provider._inject_prompts(context)
        
        if expected_suffix:
            assert result.endswith(expected_suffix)
    
    def test_provider_factory_initializes_injectors(self):
        """Test that provider factory initializes injection system."""
        # The factory should initialize injectors in __init__
        registry = InjectorRegistry()
        
        # Should have default injectors
        assert registry.get("production") is not None
        assert registry.get("verification") is not None
        assert registry.get("ticket") is not None
    
    def test_backward_compatibility(self):
        """Test that providers work without injection flags."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Test normal generation without injection flags
        result = provider.generate("test prompt")
        
        # Should work normally
        assert "Mock response for: test prompt" in result
        
        # Should not have injection calls
        injection_calls = [
            call for call in provider.call_history
            if call.get("method") == "_inject_prompts"
        ]
        assert len(injection_calls) == 0
    
    def test_injection_error_handling(self):
        """Test that injection errors don't break providers."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Create invalid context to trigger error handling
        with patch.object(provider, '_injector_registry') as mock_registry:
            mock_registry.get.return_value = None
            
            context = InjectionContext(
                operation="test_execution",
                provider="mock",
                model="test-model",
                user_prompt="test prompt",
                metadata={}
            )
            
            # Should fallback to original prompt
            result = provider._inject_prompts(context)
            assert result == "test prompt"


class TestProviderSpecificInjection:
    """Test provider-specific injection behaviors."""
    
    def test_mock_provider_records_injection_attempts(self):
        """Test that MockProvider records injection attempts for testing."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Generate with injection
        provider.generate(
            "test prompt",
            operation="code_execution",
            test_injection=True
        )
        
        # Check injection was recorded
        injection_calls = [
            call for call in provider.call_history
            if call.get("method") == "_inject_prompts"
        ]
        
        assert len(injection_calls) == 1
        call = injection_calls[0]
        assert call["context"]["operation"] == "code_execution"
        assert call["context"]["provider"] == "mock"
        assert call["context"]["model"] == "mock-model-1"  # MockProvider uses its own default model
    
    def test_provider_respects_injection_flags(self):
        """Test that providers only apply injection when requested."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Without injection flag
        provider.generate("test prompt")
        injection_calls_1 = [
            call for call in provider.call_history
            if call.get("method") == "_inject_prompts"
        ]
        
        provider.call_history.clear()
        
        # With injection flag
        provider.generate("test prompt", test_injection=True)
        injection_calls_2 = [
            call for call in provider.call_history
            if call.get("method") == "_inject_prompts"
        ]
        
        assert len(injection_calls_1) == 0
        assert len(injection_calls_2) == 1


class TestInjectionIntegration:
    """Test integration between injection system and providers."""
    
    def test_injector_registry_persistence(self):
        """Test that injector registry persists across provider instances."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        # Create multiple providers
        provider1 = MockProvider(config)
        provider2 = MockProvider(config)
        
        # Both should have access to the same registry
        registry1 = provider1._injector_registry
        registry2 = provider2._injector_registry
        
        # Should be the same singleton instance
        assert registry1 is registry2
        
        # Should have the same injectors
        assert registry1.get("production") is registry2.get("production")
    
    def test_injection_preserves_provider_functionality(self):
        """Test that injection doesn't break core provider functionality."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Test all core methods work with injection
        text_result = provider.generate("test", test_injection=True)
        json_result = provider.generate_json("test", test_injection=True)
        
        # Should still return expected types
        assert isinstance(text_result, str)
        assert isinstance(json_result, dict)
        
        # Should have recorded both operations
        generate_calls = [
            call for call in provider.call_history
            if call.get("method") == "generate"
        ]
        json_calls = [
            call for call in provider.call_history
            if call.get("method") == "generate_json"
        ]
        
        assert len(generate_calls) == 1
        assert len(json_calls) == 1


@pytest.mark.integration
class TestProviderRegressionTests:
    """Regression tests to ensure no functionality is broken."""
    
    def test_mock_provider_maintains_ticket_generation(self):
        """Test that ticket generation still works correctly."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Test ticket generation
        result = provider.generate("generate yaml tickets for calculator app")
        
        # Should still return YAML tickets
        assert "version: '1.0'" in result
        assert "tickets:" in result
        assert "Calculator App" in result
    
    def test_mock_provider_maintains_code_generation(self):
        """Test that code generation still works correctly."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Test code generation
        result = provider.generate("generate python code for hello world")
        
        # Should still return code
        assert "def hello_world():" in result
        assert "print('Hello, World!')" in result
    
    def test_provider_call_history_tracking(self):
        """Test that call history tracking is preserved."""
        config = LLMConfig(
            provider_type="mock",
            model="test-model",
            api_key="test"
        )
        
        provider = MockProvider(config)
        
        # Make several calls
        provider.generate("test 1")
        provider.generate_json("test 2")
        provider.generate("test 3", test_injection=True)
        
        # Should track all calls
        history = provider.get_call_history()
        
        generate_calls = [h for h in history if h.get("method") == "generate"]
        json_calls = [h for h in history if h.get("method") == "generate_json"]
        
        assert len(generate_calls) == 2
        assert len(json_calls) == 1
        
        # Should preserve prompt content
        assert any("test 1" in call.get("prompt", "") for call in generate_calls)
        assert any("test 2" in call.get("prompt", "") for call in json_calls)