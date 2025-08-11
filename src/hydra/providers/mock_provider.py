"""Mock LLM provider for testing."""
from typing import Any, Dict, Iterator, List

from .base import LLMConfig
from .base_provider import BaseProvider


class MockProvider(BaseProvider):
    """Mock provider that returns predictable responses for testing."""

    def __init__(self, config: LLMConfig, fail_mode: bool = False):
        """Initialize mock provider.
        
        Args:
            config: Provider configuration
            fail_mode: If True, operations will fail for error testing
        
        """
        super().__init__(config)
        self.fail_mode = fail_mode
        self.call_history: List[Dict[str, Any]] = []
        self.response_overrides: Dict[str, str] = {}

    def validate_config(self):
        """Mock provider always validates successfully."""
        if self.fail_mode:
            raise ValueError("Mock provider in fail mode")

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a mock response."""
        # Track call
        self.call_history.append({
            "method": "generate",
            "prompt": prompt,
            "kwargs": kwargs
        })

        if self.fail_mode:
            raise RuntimeError("Mock provider configured to fail")

        # Check for overrides
        if prompt in self.response_overrides:
            return self.response_overrides[prompt]

        prompt_lower = prompt.lower()
        if ("plan" in prompt_lower and "subtask" in prompt_lower and
            "code" not in prompt_lower):
            return (
                '{"plan": "Mock plan", '
                '"subtasks": ["Mock subtask 1", "Mock subtask 2"]}'
            )
        elif ("generate python code" in prompt_lower or "code" in prompt_lower or
              "function" in prompt_lower or "hello world" in prompt_lower):
            return ("def hello_world():\n    print('Hello, World!')\n"
                    "    return 'Hello, World!'")
        elif "fibonacci" in prompt_lower:
            return """def fibonacci(n):
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b"""
        else:
            return "Mock response for: " + prompt[:50]

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a mock JSON response."""
        self.call_history.append({
            "method": "generate_json",
            "prompt": prompt,
            "kwargs": kwargs
        })

        if self.fail_mode:
            raise RuntimeError("Mock provider configured to fail")

        return {
            "plan": "Mock plan from JSON",
            "subtasks": ["Mock JSON subtask"],
            "code": "def mock_json_function(): pass"
        }

    def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate streaming mock response."""
        self.call_history.append({
            "method": "generate_streaming",
            "prompt": prompt,
            "kwargs": kwargs
        })

        if self.fail_mode:
            raise RuntimeError("Mock provider configured to fail")

        response = self.generate(prompt, **kwargs)
        # Simulate streaming by yielding chunks
        words = response.split()
        for word in words:
            yield word + " "

    def list_models(self) -> List[str]:
        """Return mock models."""
        return ["mock-model-1", "mock-model-2", "mock-fast", "mock-smart"]

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "mock"

    def set_response_override(self, prompt: str, response: str):
        """Set a custom response for a specific prompt.
        
        Args:
            prompt: The prompt to override
            response: The response to return
        
        """
        self.response_overrides[prompt] = response

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get the history of calls made to this provider.
        
        Returns:
            List of call records
        
        """
        return self.call_history

    def reset(self):
        """Reset the provider state."""
        self.call_history.clear()
        self.response_overrides.clear()
        self.fail_mode = False
