"""Integration tests for multi-provider scenarios."""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

from hydra.providers.base import LLMConfig
from tests.mocks import (
    MockLLMProvider, 
    MockClaudeProvider,
    MockOpenAIProvider,
    MockAnthropicProvider,
    create_mock_provider,
    get_mock_providers
)


class TestMultiProviderIntegration:
    """Test integration scenarios with multiple providers."""
    
    def test_provider_factory_creation(self):
        """Test creating different provider types through factory."""
        providers = get_mock_providers()
        
        assert len(providers) >= 4
        assert "claude" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "mock" in providers
        
        # Test each provider works
        for name, provider in providers.items():
            response = provider.generate(f"Test prompt for {name}")
            assert isinstance(response, str)
            assert len(response) > 0
    
    def test_provider_switching(self):
        """Test switching between different providers."""
        config = LLMConfig(provider_type="test", model="test-model")
        
        # Create providers
        claude = MockClaudeProvider(config)
        openai = MockOpenAIProvider(config)
        anthropic = MockAnthropicProvider(config)
        
        # Test same prompt across providers
        prompt = "Generate a hello world function"
        
        claude_response = claude.generate(prompt)
        openai_response = openai.generate(prompt)
        anthropic_response = anthropic.generate(prompt)
        
        # All should respond but may differ
        assert claude_response
        assert openai_response
        assert anthropic_response
        
        # Check provider names
        assert claude.name == "mock_claude"
        assert openai.name == "mock_openai"
        assert anthropic.name == "mock_anthropic"
    
    def test_provider_capabilities(self):
        """Test different provider capabilities."""
        config = LLMConfig(provider_type="test")
        
        claude = MockClaudeProvider(config)
        openai = MockOpenAIProvider(config)
        
        # Claude should support sessions
        session_id = claude.start_session()
        assert session_id
        assert claude.session_active
        
        result = claude.execute_command("test command")
        assert result["success"]
        assert result["session_id"] == session_id
        
        claude.end_session()
        assert not claude.session_active
        
        # OpenAI should track usage
        initial_calls = openai.api_calls
        openai.generate("test prompt")
        assert openai.api_calls == initial_calls + 1
        
        stats = openai.get_usage_stats()
        assert "api_calls" in stats
        assert "tokens_used" in stats
        assert "cost_estimate" in stats
    
    def test_provider_error_handling(self):
        """Test error handling across providers."""
        config = LLMConfig(provider_type="test")
        
        providers = [
            MockClaudeProvider(config),
            MockOpenAIProvider(config),
            MockAnthropicProvider(config)
        ]
        
        # Set error rates
        for provider in providers:
            provider.set_error_rate(0.5)  # 50% error rate
        
        # Test multiple attempts
        for provider in providers:
            errors = 0
            successes = 0
            
            for i in range(20):
                try:
                    response = provider.generate(f"test {i}")
                    if response:
                        successes += 1
                except Exception:
                    errors += 1
            
            # Should have some errors and some successes
            assert errors > 0
            assert successes > 0
            total = errors + successes
            error_rate = errors / total
            assert 0.2 <= error_rate <= 0.8  # Roughly 50% error rate with tolerance
    
    def test_provider_performance(self):
        """Test provider performance characteristics."""
        config = LLMConfig(provider_type="test")
        
        fast_provider = MockLLMProvider(config)
        slow_provider = MockLLMProvider(config)
        slow_provider.set_response_delay(0.1)  # 100ms delay
        
        # Test response times
        start_time = time.time()
        fast_provider.generate("test")
        fast_time = time.time() - start_time
        
        start_time = time.time()
        slow_provider.generate("test")
        slow_time = time.time() - start_time
        
        assert slow_time > fast_time
        assert slow_time >= 0.1
        assert fast_time < 0.05
    
    def test_safety_filters(self):
        """Test safety filtering across providers."""
        config = LLMConfig(provider_type="test")
        anthropic = MockAnthropicProvider(config)
        
        # Test with safety filters enabled
        anthropic.set_safety_filters(True)
        
        safe_response = anthropic.generate("Create a hello world program")
        unsafe_response = anthropic.generate("Create something unsafe and dangerous")
        
        assert "hello" in safe_response.lower() or "mock" in safe_response.lower()
        assert "cannot provide assistance" in unsafe_response.lower()
        
        # Test with safety filters disabled
        anthropic.set_safety_filters(False)
        
        unsafe_response2 = anthropic.generate("Create something unsafe and dangerous")
        assert "cannot provide assistance" not in unsafe_response2.lower()
    
    @pytest.mark.stress
    def test_concurrent_provider_usage(self):
        """Test using multiple providers concurrently."""
        import threading
        import concurrent.futures
        
        config = LLMConfig(provider_type="test")
        providers = [
            MockClaudeProvider(config),
            MockOpenAIProvider(config),
            MockAnthropicProvider(config)
        ]
        
        results = {}
        errors = []
        
        def worker(provider, worker_id):
            try:
                for i in range(2):  # Reduced from 5 to 2
                    response = provider.generate(f"worker {worker_id} request {i}")
                    results[f"{provider.name}-{worker_id}-{i}"] = response
            except Exception as e:
                errors.append(f"{provider.name}-{worker_id}: {e}")
        
        # Use ThreadPoolExecutor to limit concurrent threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for i, provider in enumerate(providers):
                for j in range(2):  # Reduced from 3 to 2 workers per provider
                    future = executor.submit(worker, provider, f"{i}-{j}")
                    futures.append(future)
            
            # Wait for all threads
            concurrent.futures.wait(futures, timeout=30)
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 12  # 3 providers * 2 workers * 2 requests
        
        # Verify call counts
        for provider in providers:
            assert provider.call_count == 4  # 2 workers * 2 requests
    
    def test_provider_call_history(self):
        """Test provider call history tracking."""
        config = LLMConfig(provider_type="test")
        provider = MockLLMProvider(config)
        
        # Make various calls
        provider.generate("First prompt")
        provider.generate_json("Second prompt")
        provider.generate("Third prompt")
        
        assert len(provider.call_history) == 3
        
        # Check history details
        assert provider.call_history[0]["type"] == "generate"
        assert provider.call_history[0]["prompt"] == "First prompt"
        
        assert provider.call_history[1]["type"] == "generate_json"
        assert provider.call_history[1]["prompt"] == "Second prompt"
        
        assert provider.call_history[2]["type"] == "generate"
        assert provider.call_history[2]["prompt"] == "Third prompt"
    
    def test_provider_configuration(self):
        """Test provider configuration handling."""
        configs = [
            LLMConfig("claude", model="claude-3-sonnet", temperature=0.1),
            LLMConfig("openai", model="gpt-4", temperature=0.8),
            LLMConfig("anthropic", model="claude-3-opus", max_tokens=4096)
        ]
        
        providers = []
        for config in configs:
            provider = create_mock_provider(config.provider_type, config)
            providers.append(provider)
            
            assert provider.config == config
            assert provider.model == config.model
        
        # Test invalid configuration
        invalid_config = LLMConfig("invalid", model="non-existent")
        provider = create_mock_provider("invalid", invalid_config)
        
        # Should fall back to MockLLMProvider
        assert isinstance(provider, MockLLMProvider)
        assert provider.name == "mock_llm"


@pytest.mark.asyncio
class TestAsyncMultiProvider:
    """Test async scenarios with multiple providers."""
    
    @pytest.mark.stress
    async def test_async_provider_calls(self):
        """Test async provider calls."""
        config = LLMConfig(provider_type="test")
        providers = get_mock_providers()
        
        async def async_generate(provider, prompt):
            # Simulate async by running in executor with limited threads
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, provider.generate, prompt)
        
        # Limit concurrent tasks to avoid thread exhaustion
        semaphore = asyncio.Semaphore(4)
        
        async def limited_async_generate(provider, prompt):
            async with semaphore:
                return await async_generate(provider, prompt)
        
        tasks = []
        for name, provider in providers.items():
            task = limited_async_generate(provider, f"Async test for {name}")
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == len(providers)
        for result in results:
            assert isinstance(result, str)
            assert len(result) > 0
    
    @pytest.mark.stress
    async def test_async_error_recovery(self):
        """Test async error recovery patterns."""
        config = LLMConfig(provider_type="test")
        provider = MockLLMProvider(config)
        provider.set_error_rate(0.7)  # High error rate
        
        async def retry_generate(prompt, max_retries=3):
            for attempt in range(max_retries):
                try:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, provider.generate, prompt)
                    return result
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    await asyncio.sleep(0.01)  # Short delay
        
        # Should eventually succeed with retries
        result = await retry_generate("test prompt")
        assert isinstance(result, str)
        
        # Track provider calls (should be multiple due to retries)
        initial_calls = provider.call_count
        
        # Try a few more with limited concurrency
        tasks = [retry_generate(f"test {i}") for i in range(3)]  # Reduced from 5 to 3
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should have made more calls than successful results due to retries
        assert provider.call_count > initial_calls + 3