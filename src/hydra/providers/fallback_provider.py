"""Fallback provider implementation for automatic provider switching."""

import logging
from typing import Any, Dict, Iterator, List, Optional

from .base import LLMConfig, LLMProvider
from .base_provider import (
    BaseProvider,
    CodeBlock,
    FileOperation,
    ModelInfo,
    ParsedResponse,
    Session,
)
from .error_handler import ErrorSeverity, get_error_handler
from .factory import LLMProviderFactory

logger = logging.getLogger(__name__)


class FallbackProvider(BaseProvider):
    """Provider that automatically falls back to alternative providers on failure.

    This provider wraps multiple providers and automatically switches between
    them when errors occur, providing resilience and high availability.
    """

    def __init__(self, config: LLMConfig):
        """Initialize fallback provider with ordered list of providers.

        Args:
            config: Configuration with fallback_providers list

        """
        # Initialize attributes before calling super().__init__
        # Get fallback providers from config
        self.provider_names = config.extra_params.get('fallback_providers', [])
        if not self.provider_names:
            # Default fallback order
            self.provider_names = ['claude_tmux', 'venice', 'mock']

        # Initialize providers lazily
        self._providers: Dict[str, LLMProvider] = {}
        self._current_provider_index = 0
        self._factory = LLMProviderFactory()
        self._error_handler = get_error_handler()

        # Set fallback list in error handler
        self._error_handler.set_fallback_providers(self.provider_names)

        # Track provider health
        self._provider_health: Dict[str, str] = {}

        # Now call super().__init__ after all attributes are initialized
        super().__init__(config)

        # Initialize first provider after super().__init__
        self._ensure_current_provider()

    @property
    def name(self) -> str:
        """Get provider name."""
        return "fallback"

    @property
    def current_provider(self) -> Optional[LLMProvider]:
        """Get current active provider."""
        if self._current_provider_index < len(self.provider_names):
            provider_name = self.provider_names[self._current_provider_index]
            return self._providers.get(provider_name)
        return None

    def _ensure_current_provider(self) -> bool:
        """Ensure current provider is initialized.

        Returns:
            True if provider is available

        """
        if self.current_provider:
            return True

        while self._current_provider_index < len(self.provider_names):
            provider_name = self.provider_names[self._current_provider_index]

            if provider_name not in self._providers:
                if not self._initialize_provider(provider_name):
                    self._current_provider_index += 1
                    continue

            # Check provider health
            health = self._error_handler.get_provider_health(provider_name)
            if health['status'] == 'unhealthy':
                logger.warning(f"Provider {provider_name} is unhealthy, skipping")
                self._current_provider_index += 1
                continue

            return True

        return False

    def _initialize_provider(self, provider_name: str) -> bool:
        """Initialize a specific provider.

        Args:
            provider_name: Name of provider to initialize

        Returns:
            True if initialization successful

        """
        try:
            logger.info(f"Initializing fallback provider: {provider_name}")

            # Create provider-specific config
            provider_config = LLMConfig(
                provider_type=provider_name,
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                extra_params=self.config.extra_params
            )

            # Create provider instance
            provider = self._factory.create(provider_config)
            self._providers[provider_name] = provider

            # Validate provider is working
            if hasattr(provider, 'validate_config'):
                provider.validate_config()

            logger.info(f"Successfully initialized {provider_name}")
            return True

        except Exception as e:
            error = self._error_handler.handle_error(
                provider=provider_name,
                error=e,
                context={'initialization': True}
            )
            logger.error(f"Failed to initialize {provider_name}: {error}")
            return False

    def _fallback_to_next(self) -> bool:
        """Switch to next available provider.

        Returns:
            True if fallback successful

        """
        current_name = self.provider_names[self._current_provider_index] if self._current_provider_index < len(self.provider_names) else 'none'
        logger.warning(f"Falling back from {current_name}")

        self._current_provider_index += 1

        if self._ensure_current_provider():
            new_name = self.provider_names[self._current_provider_index]
            logger.info(f"Switched to fallback provider: {new_name}")
            return True

        logger.error("No more fallback providers available")
        return False

    def _execute_with_fallback(self, method_name: str, *args, **kwargs) -> Any:
        """Execute method with automatic fallback.

        Args:
            method_name: Method name to execute on provider
            *args: Method arguments
            **kwargs: Method keyword arguments

        Returns:
            Method result

        Raises:
            Exception: If all providers fail

        """
        last_error = None

        while self._ensure_current_provider():
            provider = self.current_provider
            provider_name = self.provider_names[self._current_provider_index]

            try:
                # Execute method on current provider
                method = getattr(provider, method_name)
                result = method(*args, **kwargs)

                # Success - reset health if needed
                if self._provider_health.get(provider_name) != 'healthy':
                    self._provider_health[provider_name] = 'healthy'
                    logger.info(f"Provider {provider_name} recovered")

                return result

            except Exception as e:
                # Handle error
                error = self._error_handler.handle_error(
                    provider=provider_name,
                    error=e,
                    context={'method': method_name}
                )
                last_error = error

                # Check if error is severe enough for fallback
                if error.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
                    self._provider_health[provider_name] = 'unhealthy'

                    if not self._fallback_to_next():
                        break

                elif error.is_retryable():
                    # For retryable errors, try the same provider again
                    logger.info(f"Retrying {method_name} on {provider_name}")
                    continue

                else:
                    # Non-retryable, non-critical error - propagate
                    raise

        # All providers failed
        if last_error:
            raise Exception(
                f"All providers failed for {method_name}. "
                f"Last error: {last_error}"
            )
        else:
            raise Exception(f"No providers available for {method_name}")

    # Implement all abstract methods with fallback logic

    def validate_config(self):
        """Validate configuration of current provider."""
        # During initialization, we might not have providers yet
        if hasattr(self, '_providers'):
            self._execute_with_fallback('validate_config')
        # If we're still initializing, validation will happen when provider is created

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response with fallback."""
        return self._execute_with_fallback('generate', prompt, **kwargs)

    def generate_json(self, prompt: str, schema: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Generate JSON response with fallback."""
        return self._execute_with_fallback('generate_json', prompt, schema, **kwargs)

    def generate_code(self, prompt: str, context: Dict[str, Any], **kwargs) -> str:
        """Generate code with fallback."""
        return self._execute_with_fallback('generate_code', prompt, context, **kwargs)

    def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate streaming response with fallback."""
        return self._execute_with_fallback('generate_streaming', prompt, **kwargs)

    def create_session(self, session_id: str, **kwargs) -> Session:
        """Create session with fallback."""
        return self._execute_with_fallback('create_session', session_id, **kwargs)

    def attach_session(self, session_id: str) -> Session:
        """Attach to session with fallback."""
        return self._execute_with_fallback('attach_session', session_id)

    def list_sessions(self) -> List[Session]:
        """List sessions from current provider."""
        if self.current_provider:
            return self.current_provider.list_sessions()
        return []

    def kill_session(self, session_id: str) -> bool:
        """Kill session in current provider."""
        if self.current_provider:
            return self.current_provider.kill_session(session_id)
        return False

    def list_models(self) -> List[ModelInfo]:
        """List models from all available providers."""
        all_models = []
        for provider_name in self.provider_names:
            if provider_name in self._providers:
                try:
                    models = self._providers[provider_name].list_models()
                    # Tag models with provider
                    for model in models:
                        model.metadata['provider'] = provider_name
                    all_models.extend(models)
                except Exception:
                    pass
        return all_models

    def select_model(self, model_identifier: str) -> bool:
        """Select model on current provider."""
        return self._execute_with_fallback('select_model', model_identifier)

    def get_model_mapping(self) -> Dict[str, str]:
        """Get model mappings from all providers."""
        mappings = {}
        for provider_name in self.provider_names:
            if provider_name in self._providers:
                try:
                    provider_mappings = self._providers[provider_name].get_model_mapping()
                    # Prefix with provider name to avoid conflicts
                    for key, value in provider_mappings.items():
                        mappings[f"{provider_name}:{key}"] = value
                        # Also add unprefixed for convenience
                        if key not in mappings:
                            mappings[key] = value
                except Exception:
                    pass
        return mappings

    def parse_response(self, response: str) -> ParsedResponse:
        """Parse response using current provider."""
        return self._execute_with_fallback('parse_response', response)

    def extract_code_blocks(self, response: str) -> List[CodeBlock]:
        """Extract code blocks using current provider."""
        return self._execute_with_fallback('extract_code_blocks', response)

    def supports_interactive(self) -> bool:
        """Check if any provider supports interactive mode."""
        for provider_name in self.provider_names:
            if provider_name in self._providers:
                try:
                    if self._providers[provider_name].supports_interactive():
                        return True
                except Exception:
                    pass
        return False

    def wait_for_prompt(self, timeout: int = 30) -> bool:
        """Wait for prompt with fallback."""
        return self._execute_with_fallback('wait_for_prompt', timeout)

    def intercept_file_operation(self, operation: FileOperation) -> bool:
        """Intercept file operation with current provider."""
        if self.current_provider:
            return self.current_provider.intercept_file_operation(operation)
        return True

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers.

        Returns:
            Dictionary with provider health and status

        """
        status = {
            'current_provider': self.provider_names[self._current_provider_index] if self._current_provider_index < len(self.provider_names) else None,
            'providers': {}
        }

        for i, provider_name in enumerate(self.provider_names):
            health = self._error_handler.get_provider_health(provider_name)
            status['providers'][provider_name] = {
                'initialized': provider_name in self._providers,
                'health': health['status'],
                'error_count': health['error_count'],
                'is_current': i == self._current_provider_index
            }

        return status

    def reset_provider(self, provider_name: Optional[str] = None):
        """Reset a specific provider or all providers.

        Args:
            provider_name: Provider to reset, or None for all

        """
        if provider_name:
            # Reset specific provider
            if provider_name in self._providers:
                del self._providers[provider_name]
            self._error_handler.clear_history(provider_name)
            self._provider_health.pop(provider_name, None)
            logger.info(f"Reset provider: {provider_name}")
        else:
            # Reset all
            self._providers.clear()
            self._error_handler.clear_history()
            self._provider_health.clear()
            self._current_provider_index = 0
            logger.info("Reset all providers")

    def cleanup(self):
        """Clean up all provider resources."""
        for provider in self._providers.values():
            try:
                provider.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up provider: {e}")
        self._providers.clear()
        super().cleanup()
