"""Comprehensive tests for error handling and fallback mechanisms."""

import logging
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

from hydra.providers.base import LLMConfig
from hydra.providers.error_handler import (
    ErrorCategory,
    ErrorSeverity,
    ProviderError,
    ProviderErrorHandler,
    RetryConfig,
    get_error_handler
)
from hydra.providers.error_messages import ErrorMessages, ProviderHints, format_error_with_hints
from hydra.providers.fallback_provider import FallbackProvider
from hydra.providers.factory import LLMProviderFactory
from hydra.providers.retry_utils import (
    CircuitBreaker,
    RetryableOperation,
    exponential_backoff,
    with_retry
)


class TestProviderErrorHandler(unittest.TestCase):
    """Test provider error handling functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.error_handler = ProviderErrorHandler()

    def test_error_categorization(self):
        """Test error categorization logic."""
        test_cases = [
            (ValueError("API key not found"), ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL),
            (ConnectionError("Connection refused"), ErrorCategory.NETWORK, ErrorSeverity.HIGH),
            (Exception("Rate limit exceeded"), ErrorCategory.API_LIMIT, ErrorSeverity.MEDIUM),
            (TimeoutError("Request timed out"), ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM),
            (Exception("Model not found"), ErrorCategory.MODEL_UNAVAILABLE, ErrorSeverity.HIGH),
            (Exception("tmux session error"), ErrorCategory.SESSION, ErrorSeverity.MEDIUM),
            (MemoryError("Out of memory"), ErrorCategory.RESOURCE, ErrorSeverity.HIGH),
            (ValueError("Invalid request"), ErrorCategory.INVALID_REQUEST, ErrorSeverity.LOW),
            (Exception("Provider init failed"), ErrorCategory.INITIALIZATION, ErrorSeverity.CRITICAL),
            (Exception("Unknown error"), ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM),
        ]

        for error, expected_category, expected_severity in test_cases:
            category, severity = self.error_handler._categorize_error(error)
            self.assertEqual(category, expected_category, f"Failed for error: {error}")
            self.assertEqual(severity, expected_severity, f"Failed for error: {error}")

    def test_user_friendly_messages(self):
        """Test generation of user-friendly error messages."""
        test_cases = [
            (ErrorCategory.AUTHENTICATION, "Authentication failed"),
            (ErrorCategory.NETWORK, "Network connection error"),
            (ErrorCategory.API_LIMIT, "API rate limit reached"),
            (ErrorCategory.TIMEOUT, "Request timed out"),
            (ErrorCategory.MODEL_UNAVAILABLE, "requested model is not available"),
            (ErrorCategory.SESSION, "Session management error"),
            (ErrorCategory.RESOURCE, "Resource limit exceeded"),
            (ErrorCategory.INVALID_REQUEST, "Invalid request format"),
            (ErrorCategory.INITIALIZATION, "Provider initialization failed"),
        ]

        for category, expected_substring in test_cases:
            error = Exception("Test error")
            message = self.error_handler._get_user_friendly_message(category, error)
            self.assertIn(expected_substring, message)

    def test_error_logging(self):
        """Test error logging with appropriate levels."""
        with self.assertLogs('hydra.providers.error_handler', level='DEBUG') as cm:
            test_errors = [
                ProviderError("test", ErrorCategory.NETWORK, ErrorSeverity.CRITICAL, "Critical error"),
                ProviderError("test", ErrorCategory.TIMEOUT, ErrorSeverity.HIGH, "High error"),
                ProviderError("test", ErrorCategory.API_LIMIT, ErrorSeverity.MEDIUM, "Medium error"),
                ProviderError("test", ErrorCategory.INVALID_REQUEST, ErrorSeverity.LOW, "Low error"),
                ProviderError("test", ErrorCategory.UNKNOWN, ErrorSeverity.WARNING, "Warning"),
            ]

            for error in test_errors:
                self.error_handler._log_error(error)

            # Check that appropriate log levels were used
            self.assertTrue(any('CRITICAL' in record for record in cm.output))
            self.assertTrue(any('ERROR' in record for record in cm.output))
            self.assertTrue(any('WARNING' in record for record in cm.output))
            self.assertTrue(any('INFO' in record for record in cm.output))

    def test_retry_logic(self):
        """Test retry decision logic."""
        retryable_error = ProviderError(
            "test", ErrorCategory.NETWORK, ErrorSeverity.HIGH, "Network error"
        )
        non_retryable_error = ProviderError(
            "test", ErrorCategory.INVALID_REQUEST, ErrorSeverity.LOW, "Bad request"
        )

        self.assertTrue(retryable_error.is_retryable())
        self.assertFalse(non_retryable_error.is_retryable())

        # Test max retries
        retryable_error.retry_count = 10
        self.assertFalse(self.error_handler.should_retry(retryable_error))

    def test_fallback_provider_selection(self):
        """Test fallback provider selection."""
        self.error_handler.set_fallback_providers(['claude', 'venice', 'mock'])

        # Test normal fallback progression
        self.assertEqual(self.error_handler.get_fallback_provider('claude'), 'venice')
        self.assertEqual(self.error_handler.get_fallback_provider('venice'), 'mock')
        self.assertIsNone(self.error_handler.get_fallback_provider('mock'))

        # Test unknown provider
        self.assertEqual(self.error_handler.get_fallback_provider('unknown'), 'claude')

    def test_provider_health_tracking(self):
        """Test provider health status tracking."""
        # Add some errors
        for i in range(3):
            error = self.error_handler.handle_error(
                provider='test_provider',
                error=Exception("Test error"),
                context={'test': True}
            )

        health = self.error_handler.get_provider_health('test_provider')
        self.assertEqual(health['error_count'], 3)
        self.assertIsNotNone(health['last_error'])

        # Test healthy provider
        health = self.error_handler.get_provider_health('healthy_provider')
        self.assertEqual(health['status'], 'healthy')
        self.assertEqual(health['error_count'], 0)

    def test_custom_error_handlers(self):
        """Test registration and execution of custom error handlers."""
        handler_called = False

        def custom_handler(error: ProviderError):
            nonlocal handler_called
            handler_called = True

        self.error_handler.register_handler(ErrorCategory.NETWORK, custom_handler)
        
        # Trigger a network error
        self.error_handler.handle_error(
            provider='test',
            error=ConnectionError("Test connection error"),
            context={}
        )

        self.assertTrue(handler_called)


class TestRetryUtils(unittest.TestCase):
    """Test retry utility functions."""

    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        # Test without jitter
        delay = exponential_backoff(0, base_delay=1.0, max_delay=10.0, jitter=False)
        self.assertEqual(delay, 1.0)

        delay = exponential_backoff(1, base_delay=1.0, max_delay=10.0, jitter=False)
        self.assertEqual(delay, 2.0)

        delay = exponential_backoff(2, base_delay=1.0, max_delay=10.0, jitter=False)
        self.assertEqual(delay, 4.0)

        # Test max delay limit
        delay = exponential_backoff(10, base_delay=1.0, max_delay=10.0, jitter=False)
        self.assertEqual(delay, 10.0)

        # Test with jitter
        delay = exponential_backoff(1, base_delay=1.0, max_delay=10.0, jitter=True)
        self.assertTrue(1.0 <= delay <= 3.0)  # 2.0 * (0.5 to 1.5)

    @patch('time.sleep')
    def test_with_retry_decorator(self, mock_sleep):
        """Test retry decorator."""
        call_count = 0

        @with_retry(max_retries=3, provider_name='test')
        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"

        result = failing_function()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # 2 retries

    def test_circuit_breaker(self):
        """Test circuit breaker functionality."""
        breaker = CircuitBreaker('test', failure_threshold=2, recovery_timeout=0.1)

        # Successful calls don't open circuit
        breaker.call(lambda: "success")
        self.assertEqual(breaker.state, 'closed')

        # Failures open circuit after threshold
        for _ in range(2):
            with self.assertRaises(Exception):
                breaker.call(lambda: (_ for _ in ()).throw(Exception("fail")))

        self.assertEqual(breaker.state, 'open')

        # Circuit is open, calls are rejected
        with self.assertRaises(Exception) as cm:
            breaker.call(lambda: "success")
        self.assertIn("Circuit breaker is open", str(cm.exception))

        # Wait for recovery timeout
        time.sleep(0.15)

        # Circuit should be half-open, allowing limited calls
        result = breaker.call(lambda: "success")
        self.assertEqual(result, "success")
        self.assertEqual(breaker.state, 'closed')

    def test_retryable_operation_context(self):
        """Test RetryableOperation context manager."""
        operation = RetryableOperation('test', 'test_op', max_retries=2)
        
        call_count = 0

        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network error")
            return "success"

        with patch('time.sleep'):
            result = operation.execute(failing_then_success)
            self.assertEqual(result, "success")
            self.assertEqual(call_count, 2)


class TestFallbackProvider(unittest.TestCase):
    """Test fallback provider functionality."""

    @patch('hydra.providers.factory.LLMProviderFactory.create')
    def test_fallback_initialization(self, mock_create):
        """Test fallback provider initialization."""
        config = LLMConfig(
            provider_type='fallback',
            extra_params={'fallback_providers': ['claude', 'venice', 'mock']}
        )

        # Mock provider creation
        mock_provider = MagicMock()
        mock_provider.validate_config = MagicMock()
        mock_create.return_value = mock_provider

        provider = FallbackProvider(config)
        self.assertEqual(provider.provider_names, ['claude', 'venice', 'mock'])
        self.assertEqual(provider._current_provider_index, 0)

    @patch('hydra.providers.factory.LLMProviderFactory.create')
    def test_fallback_on_error(self, mock_create):
        """Test automatic fallback on provider error."""
        config = LLMConfig(
            provider_type='fallback',
            extra_params={'fallback_providers': ['failing', 'working']}
        )

        # Create mock providers
        failing_provider = MagicMock()
        failing_provider.generate.side_effect = Exception("Provider failed")
        
        working_provider = MagicMock()
        working_provider.generate.return_value = "success"

        # Setup factory to return appropriate providers
        def create_provider(conf):
            if conf.provider_type == 'failing':
                return failing_provider
            return working_provider

        mock_create.side_effect = create_provider

        provider = FallbackProvider(config)
        
        # Should fallback to working provider
        result = provider.generate("test prompt")
        self.assertEqual(result, "success")

    @patch('hydra.providers.factory.LLMProviderFactory.create')
    def test_all_providers_fail(self, mock_create):
        """Test behavior when all providers fail."""
        config = LLMConfig(
            provider_type='fallback',
            extra_params={'fallback_providers': ['fail1', 'fail2']}
        )

        # All providers fail
        failing_provider = MagicMock()
        failing_provider.generate.side_effect = Exception("Provider failed")
        mock_create.return_value = failing_provider

        provider = FallbackProvider(config)
        
        # Should raise exception when all fail
        with self.assertRaises(Exception) as cm:
            provider.generate("test prompt")
        self.assertIn("All providers failed", str(cm.exception))

    @patch('hydra.providers.factory.LLMProviderFactory.create')
    def test_provider_health_tracking(self, mock_create):
        """Test provider health tracking in fallback."""
        config = LLMConfig(
            provider_type='fallback',
            extra_params={'fallback_providers': ['provider1', 'provider2']}
        )

        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        provider = FallbackProvider(config)
        
        # Get provider status
        status = provider.get_provider_status()
        self.assertIn('current_provider', status)
        self.assertIn('providers', status)

    @patch('hydra.providers.factory.LLMProviderFactory.create')
    def test_provider_reset(self, mock_create):
        """Test provider reset functionality."""
        config = LLMConfig(
            provider_type='fallback',
            extra_params={'fallback_providers': ['provider1', 'provider2']}
        )

        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        provider = FallbackProvider(config)
        
        # Initialize some providers
        provider._providers['provider1'] = mock_provider
        provider._provider_health['provider1'] = 'unhealthy'
        
        # Reset specific provider
        provider.reset_provider('provider1')
        self.assertNotIn('provider1', provider._providers)
        self.assertNotIn('provider1', provider._provider_health)
        
        # Reset all providers
        provider._providers['provider2'] = mock_provider
        provider.reset_provider()
        self.assertEqual(len(provider._providers), 0)
        self.assertEqual(provider._current_provider_index, 0)


class TestErrorMessages(unittest.TestCase):
    """Test error message formatting."""

    def test_message_formatting(self):
        """Test error message template formatting."""
        message = ErrorMessages.format(
            'PROVIDER_NOT_FOUND',
            provider='test_provider',
            available='claude, venice, mock'
        )
        self.assertIn('test_provider', message)
        self.assertIn('claude, venice, mock', message)

    def test_help_url_retrieval(self):
        """Test help URL retrieval for providers."""
        url = ErrorMessages.get_help_url('venice', 'api_key')
        self.assertIn('venice.ai', url)

        url = ErrorMessages.get_help_url('anthropic', 'models')
        self.assertIn('anthropic.com', url)

        url = ErrorMessages.get_help_url('unknown', 'api_key')
        self.assertIsNone(url)

    def test_install_command_generation(self):
        """Test install command generation."""
        cmd = ErrorMessages.get_install_command('tmux')
        self.assertIn('tmux', cmd)

        cmd = ErrorMessages.get_install_command('unknown_package')
        self.assertEqual(cmd, 'pip install unknown_package')

    def test_env_var_names(self):
        """Test environment variable name generation."""
        self.assertEqual(ErrorMessages.get_env_var('venice'), 'VENICE_API_KEY')
        self.assertEqual(ErrorMessages.get_env_var('anthropic'), 'ANTHROPIC_API_KEY')
        self.assertEqual(ErrorMessages.get_env_var('claude_tmux'), 'CLAUDE_CLI_PATH')
        self.assertEqual(ErrorMessages.get_env_var('unknown'), 'UNKNOWN_API_KEY')

    def test_hints_retrieval(self):
        """Test hint retrieval for error types."""
        hints = ProviderHints.get_hints('rate_limit')
        self.assertTrue(len(hints) > 0)
        self.assertIn('backoff', ' '.join(hints).lower())

        hints = ProviderHints.get_hints('authentication')
        self.assertTrue(len(hints) > 0)
        self.assertIn('api key', ' '.join(hints).lower())

    def test_format_error_with_hints(self):
        """Test formatting error with hints."""
        message = format_error_with_hints(
            "Rate limit exceeded",
            "rate_limit",
            "venice"
        )
        self.assertIn("Rate limit exceeded", message)
        self.assertIn("Suggestions:", message)
        # Help URL is optional, so check if it exists in the message
        if "For more help:" in message:
            self.assertIn("venice.ai", message)


class TestProviderFactory(unittest.TestCase):
    """Test provider factory with error handling."""

    def test_factory_unknown_provider(self):
        """Test factory handling of unknown provider."""
        factory = LLMProviderFactory()
        config = LLMConfig(provider_type='nonexistent')

        with self.assertRaises(ValueError) as cm:
            factory.create(config)
        self.assertIn('Unknown provider type', str(cm.exception))

    @patch('hydra.providers.factory.ProviderRegistry.get')
    def test_factory_initialization_failure(self, mock_get):
        """Test factory handling of provider initialization failure."""
        # Mock a provider class that fails to initialize
        mock_provider_class = Mock(side_effect=Exception("Init failed"))
        mock_get.return_value = mock_provider_class

        factory = LLMProviderFactory()
        config = LLMConfig(provider_type='failing')

        with self.assertRaises(Exception) as cm:
            factory.create(config)
        self.assertIn('Failed to initialize provider', str(cm.exception))

    @patch('hydra.providers.factory.ProviderRegistry.get')
    def test_factory_auto_fallback(self, mock_get):
        """Test factory auto-fallback on critical errors."""
        # Mock a provider class that fails critically
        mock_provider_class = Mock(side_effect=Exception("Critical failure"))
        mock_get.return_value = mock_provider_class

        factory = LLMProviderFactory()
        config = LLMConfig(
            provider_type='failing',
            extra_params={'auto_fallback': True}
        )

        # Should create fallback provider instead
        with patch('hydra.providers.fallback_provider.FallbackProvider') as mock_fallback:
            mock_fallback_instance = MagicMock()
            mock_fallback.return_value = mock_fallback_instance
            
            result = factory.create(config)
            self.assertEqual(result, mock_fallback_instance)
            mock_fallback.assert_called_once()


class TestIntegration(unittest.TestCase):
    """Integration tests for error handling system."""

    @patch('hydra.providers.factory.ProviderRegistry.get')
    def test_end_to_end_error_handling(self, mock_get):
        """Test complete error handling flow."""
        # Create a mock provider that fails then succeeds
        call_count = {'count': 0}

        class TestProvider:
            def __init__(self, config):
                self.config = config

            def generate(self, prompt, **kwargs):
                call_count['count'] += 1
                if call_count['count'] < 3:
                    raise ConnectionError("Network error")
                return "Success after retries"

            def validate_config(self):
                pass

        mock_get.return_value = TestProvider

        # Create provider with retry logic
        factory = LLMProviderFactory()
        config = LLMConfig(provider_type='test')
        provider = factory.create(config)

        # Wrap with retry decorator
        @with_retry(max_retries=3, provider_name='test')
        def generate_with_retry(prompt):
            return provider.generate(prompt)

        with patch('time.sleep'):  # Speed up test
            result = generate_with_retry("Test prompt")
            self.assertEqual(result, "Success after retries")
            self.assertEqual(call_count['count'], 3)

    def test_error_handler_singleton(self):
        """Test error handler singleton pattern."""
        handler1 = get_error_handler()
        handler2 = get_error_handler()
        self.assertIs(handler1, handler2)

    def test_retry_config(self):
        """Test retry configuration."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=2.0,
            max_delay=60.0,
            exponential_base=3.0,
            jitter=False  # Disable jitter for predictable testing
        )

        # Test delay calculation without jitter
        delay = config.get_delay(0)
        self.assertEqual(delay, 2.0)  # initial_delay * (3.0 ** 0) = 2.0

        delay = config.get_delay(10)
        self.assertEqual(delay, 60.0)  # Should be capped at max_delay
        
        # Test with jitter
        config.jitter = True
        delay = config.get_delay(0)
        self.assertTrue(1.0 <= delay <= 3.0)  # With jitter: 2.0 * (0.5 to 1.5)


if __name__ == '__main__':
    unittest.main()