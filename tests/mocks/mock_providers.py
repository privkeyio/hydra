"""Comprehensive mock providers for testing different AI providers."""

import json
import random
import time
from typing import Any, Dict, List, Optional

from hydra.providers.base import LLMConfig, LLMProvider


class MockLLMProvider(LLMProvider):
    """Enhanced mock LLM provider with configurable responses and error simulation."""

    def __init__(self, config: LLMConfig, responses: Optional[Dict[str, str]] = None):
        # Initialize attributes before calling super() since validate_config() is called
        self.responses = responses or {}
        self.call_count = 0
        self.call_history = []
        self.error_rate = 0.0
        self.response_delay = 0.0
        self.should_fail = False
        super().__init__(config)

    def validate_config(self):
        """Always validates successfully unless configured to fail."""
        if self.should_fail:
            raise ValueError("Mock validation failure")

    def set_error_rate(self, rate: float):
        """Set probability of random failures (0.0 to 1.0)."""
        self.error_rate = max(0.0, min(1.0, rate))

    def set_response_delay(self, delay: float):
        """Set artificial delay for response simulation."""
        self.response_delay = max(0.0, delay)

    def _simulate_error(self):
        """Randomly simulate errors based on error_rate."""
        if random.random() < self.error_rate:
            raise Exception(f"Mock error simulation (call #{self.call_count})")

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate mock response with error simulation."""
        self.call_count += 1
        self.call_history.append(
            {"type": "generate", "prompt": prompt, "kwargs": kwargs}
        )

        if self.response_delay > 0:
            time.sleep(self.response_delay)

        self._simulate_error()

        # Check for specific response patterns
        for pattern, response in self.responses.items():
            if pattern.lower() in prompt.lower():
                return response

        # Default responses based on prompt content
        prompt_lower = prompt.lower()

        if "error" in prompt_lower or "fail" in prompt_lower:
            return "Mock error response: Something went wrong"
        elif "code" in prompt_lower or "function" in prompt_lower:
            return self._generate_mock_code(prompt_lower)
        elif "plan" in prompt_lower:
            return self._generate_mock_plan()
        elif "json" in prompt_lower:
            return json.dumps(
                {"mock": "json_response", "prompt_hash": hash(prompt) % 1000}
            )
        else:
            return f"Mock response #{self.call_count} for: {prompt[:50]}..."

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate mock JSON response."""
        self.call_count += 1
        self.call_history.append(
            {"type": "generate_json", "prompt": prompt, "kwargs": kwargs}
        )

        if self.response_delay > 0:
            time.sleep(self.response_delay)

        self._simulate_error()

        return {
            "mock_response": True,
            "call_count": self.call_count,
            "prompt_preview": prompt[:50],
            "plan": "Mock JSON plan",
            "subtasks": [f"Mock subtask {i}" for i in range(1, 4)],
            "code": "def mock_function(): return 'mock'",
        }

    def list_models(self) -> List[str]:
        """Return mock models list."""
        return [f"mock-model-{i}" for i in range(1, 6)]

    def _generate_mock_code(self, prompt: str) -> str:
        """Generate appropriate mock code based on prompt."""
        if "hello" in prompt and "world" in prompt:
            return """def hello_world():
    print("Hello, World!")
    return "Hello, World!\""""
        elif "fibonacci" in prompt:
            return """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)"""
        elif "sort" in prompt:
            return """def sort_list(items):
    return sorted(items)"""
        else:
            return """def mock_function():
    # Mock code generation
    return "mock_result\""""

    def _generate_mock_plan(self) -> str:
        """Generate mock planning response."""
        return """Mock Planning Response:
1. Analyze the requirements
2. Design the solution
3. Implement the code
4. Test the implementation
5. Document the results"""

    @property
    def name(self) -> str:
        return "mock_llm"


class MockClaudeProvider(MockLLMProvider):
    """Mock Claude provider with Claude-specific behaviors."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.session_active = False
        self.session_id = None

    def start_session(self) -> str:
        """Mock session start."""
        self.session_active = True
        self.session_id = f"mock-claude-session-{int(time.time())}"
        return self.session_id

    def end_session(self):
        """Mock session end."""
        self.session_active = False
        self.session_id = None

    def execute_command(self, command: str) -> Dict[str, Any]:
        """Mock command execution."""
        return {
            "success": True,
            "output": f"Mock output for: {command}",
            "session_id": self.session_id,
            "active": self.session_active,
        }

    @property
    def name(self) -> str:
        return "mock_claude"


class MockOpenAIProvider(MockLLMProvider):
    """Mock OpenAI provider with OpenAI-specific behaviors."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_calls = 0
        self.tokens_used = 0

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate with token tracking."""
        response = super().generate(prompt, **kwargs)
        self.api_calls += 1
        self.tokens_used += len(prompt.split()) + len(response.split())
        return response

    def get_usage_stats(self) -> Dict[str, int]:
        """Return mock usage statistics."""
        return {
            "api_calls": self.api_calls,
            "tokens_used": self.tokens_used,
            "cost_estimate": self.tokens_used * 0.0001,
        }

    @property
    def name(self) -> str:
        return "mock_openai"


class MockAnthropicProvider(MockLLMProvider):
    """Mock Anthropic provider with Anthropic-specific behaviors."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.safety_filters = True

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate with safety filtering."""
        if self.safety_filters and (
            "unsafe" in prompt.lower() or "dangerous" in prompt.lower()
        ):
            return "I cannot provide assistance with unsafe or dangerous requests."
        return super().generate(prompt, **kwargs)

    def set_safety_filters(self, enabled: bool):
        """Enable/disable mock safety filters."""
        self.safety_filters = enabled

    @property
    def name(self) -> str:
        return "mock_anthropic"


def create_mock_provider(
    provider_type: str, config: Optional[LLMConfig] = None
) -> MockLLMProvider:
    """Factory function to create mock providers."""
    if config is None:
        config = LLMConfig(
            provider_type=provider_type, model=f"{provider_type}-test-model"
        )

    provider_map = {
        "claude": MockClaudeProvider,
        "openai": MockOpenAIProvider,
        "anthropic": MockAnthropicProvider,
        "mock": MockLLMProvider,
    }

    provider_class = provider_map.get(provider_type.lower(), MockLLMProvider)
    return provider_class(config)


def get_mock_providers() -> Dict[str, MockLLMProvider]:
    """Get a dictionary of all available mock providers."""
    providers = {}
    for provider_type in ["claude", "openai", "anthropic", "mock"]:
        providers[provider_type] = create_mock_provider(provider_type)
    return providers
