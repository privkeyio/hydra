"""Abstract base class for LLM providers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    provider_type: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout: int = 30
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.validate_config()

    @abstractmethod
    def validate_config(self):
        """Validate provider-specific configuration."""
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from the LLM."""
        pass

    @abstractmethod
    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from the LLM."""
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """List available models for this provider."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        pass

    @property
    def model(self) -> str:
        """Return the current model."""
        # Handle both LLMConfig and dict configurations
        if isinstance(self.config, dict):
            return self.config.get('model', 'unknown')
        return self.config.model

    def __repr__(self):
        # Handle both LLMConfig and dict configurations
        if isinstance(self.config, dict):
            model = self.config.get('model', 'unknown')
        else:
            model = self.config.model
        return f"{self.name}(model={model})"
