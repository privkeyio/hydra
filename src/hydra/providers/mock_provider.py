"""Mock LLM provider for testing."""
from typing import Any, Dict, List

from .base import LLMConfig, LLMProvider


class MockProvider(LLMProvider):
    """Mock provider that returns predictable responses for testing."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)

    def validate_config(self):
        """Mock provider always validates successfully."""
        pass

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a mock response."""
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
        else:
            return "Mock response for: " + prompt[:50]

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a mock JSON response."""
        return {
            "plan": "Mock plan from JSON",
            "subtasks": ["Mock JSON subtask"],
            "code": "def mock_json_function(): pass"
        }

    def list_models(self) -> List[str]:
        """Return mock models."""
        return ["mock-model-1", "mock-model-2"]

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "mock"
