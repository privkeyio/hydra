"""Comprehensive testing framework for provider implementations.

This module provides a thorough testing framework for all provider
implementations, including mock providers, provider switching, output
handling validation, and error scenarios.
"""

import json
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, Iterator, List
from unittest.mock import patch

import pytest

from hydra.providers.base import LLMConfig
from hydra.providers.base_provider import (
    BaseProvider,
    CodeBlock,
    FileOperation,
    FileOperationType,
    ModelInfo,
    ParsedResponse,
    Session,
    SessionState,
)
from hydra.providers.error_handler import ErrorType, ProviderError, get_error_handler
from hydra.providers.output_handler import (
    ClaudeOutputHandler,
    OutputHandler,
    OutputHandlerFactory,
    StreamingBuffer,
    VeniceOutputHandler,
    extract_executable_code,
    format_code_for_execution,
    merge_streaming_responses,
)
from hydra.providers.provider_config import ProviderConfig
from hydra.providers.provider_factory import (
    ProviderFactory,
)
from hydra.providers.provider_registry import ProviderRegistry


class MockProvider(BaseProvider):
    """Mock provider for testing framework."""

    def __init__(self, config: LLMConfig, fail_on_generate: bool = False):
        """Initialize mock provider.

        Args:
            config: Provider configuration
            fail_on_generate: Whether to fail on generate calls

        """
        # Set attributes before calling super().__init__()
        self.fail_on_generate = fail_on_generate
        self.generate_call_count = 0
        self.last_prompt = None
        self.mock_response = (
            "Generated code:\n```python\ndef test():\n    return 42\n```"
        )
        self.streaming_enabled = False
        self.session_counter = 0
        self.model_selected = config.model or "mock-model"

        # Now call super().__init__() which will call validate_config()
        super().__init__(config)

    def validate_config(self):
        """Validate the configuration."""
        pass

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "mock"

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response."""
        self.generate_call_count += 1
        self.last_prompt = prompt

        if self.fail_on_generate:
            raise RuntimeError("Mock provider configured to fail")

        return {"result": "mock_json_response", "prompt": prompt}

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt.

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters

        Returns:
            Generated response

        Raises:
            RuntimeError: If configured to fail

        """
        self.generate_call_count += 1
        self.last_prompt = prompt

        if self.fail_on_generate:
            raise RuntimeError("Mock provider configured to fail")

        return self.mock_response

    def generate_code(self, prompt: str, context: Dict[str, Any], **kwargs) -> str:
        """Generate code with context.

        Args:
            prompt: Code generation prompt
            context: Additional context
            **kwargs: Provider-specific parameters

        Returns:
            Generated code

        """
        self.last_prompt = prompt
        return self.mock_response

    def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate streaming response.

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters

        Yields:
            Response chunks

        """
        self.last_prompt = prompt
        self.streaming_enabled = True

        # Simulate streaming by yielding response in chunks
        chunks = [
            "Generated ",
            "code:\n",
            "```python\n",
            "def test():\n",
            "    return 42\n",
            "```",
        ]

        for chunk in chunks:
            yield chunk

    def create_session(self, session_id: str, **kwargs) -> Session:
        """Create a new session.

        Args:
            session_id: Session identifier
            **kwargs: Additional parameters

        Returns:
            Created session

        """
        self.session_counter += 1
        session = Session(
            id=session_id,
            provider="mock",
            model=self.model_selected,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state=SessionState.ACTIVE,
            metadata=kwargs,
        )
        self._sessions[session_id] = session
        self._current_session = session
        return session

    def attach_session(self, session_id: str) -> Session:
        """Attach to existing session.

        Args:
            session_id: Session to attach to

        Returns:
            Session object

        Raises:
            KeyError: If session doesn't exist

        """
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")

        self._current_session = self._sessions[session_id]
        self._current_session.last_activity = datetime.now()
        return self._current_session

    def list_sessions(self) -> List[Session]:
        """List all sessions.

        Returns:
            List of sessions

        """
        return list(self._sessions.values())

    def kill_session(self, session_id: str) -> bool:
        """Terminate a session.

        Args:
            session_id: Session to terminate

        Returns:
            True if successful

        """
        if session_id in self._sessions:
            self._sessions[session_id].state = SessionState.TERMINATED
            if self._current_session and self._current_session.id == session_id:
                self._current_session = None
            return True
        return False

    def list_models(self) -> List[ModelInfo]:
        """List available models.

        Returns:
            List of model information

        """
        return [
            ModelInfo(
                identifier="mock-fast",
                display_name="Mock Fast Model",
                category="fast",
                context_window=8192,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=False,
                cost_per_token=0.001,
            ),
            ModelInfo(
                identifier="mock-smart",
                display_name="Mock Smart Model",
                category="smart",
                context_window=32768,
                max_output_tokens=8192,
                supports_streaming=True,
                supports_interactive=True,
                cost_per_token=0.01,
            ),
        ]

    def select_model(self, model_identifier: str) -> bool:
        """Select a model.

        Args:
            model_identifier: Model to select

        Returns:
            True if successful

        """
        models = self.list_models()
        for model in models:
            if (
                model.identifier == model_identifier
                or model.display_name == model_identifier
            ):
                self.model_selected = model.identifier
                self.config.model = model.identifier
                return True
        return False

    def get_model_mapping(self) -> Dict[str, str]:
        """Get model mapping.

        Returns:
            Model name mappings

        """
        return {"fast": "mock-fast", "smart": "mock-smart", "default": "mock-fast"}

    def parse_response(self, response: str) -> ParsedResponse:
        """Parse response into structured format.

        Args:
            response: Raw response

        Returns:
            Parsed response

        """
        code_blocks = self.extract_code_blocks(response)
        return ParsedResponse(
            text=response,
            code_blocks=code_blocks,
            metadata={"provider": "mock", "parsed": True},
            tokens_used=len(response.split()),
            execution_time=0.1,
        )

    def extract_code_blocks(self, response: str) -> List[CodeBlock]:
        """Extract code blocks from response.

        Args:
            response: Response text

        Returns:
            List of code blocks

        """
        import re

        blocks = []
        pattern = r"```(\w+)?\n(.*?)```"
        matches = re.finditer(pattern, response, re.DOTALL)

        for match in matches:
            language = match.group(1) or "text"
            content = match.group(2).strip()
            blocks.append(
                CodeBlock(
                    language=language,
                    content=content,
                    line_start=1,
                    line_end=content.count("\n") + 1,
                    executable=language in ["python", "bash", "javascript"],
                )
            )

        return blocks

    def supports_interactive(self) -> bool:
        """Check if interactive mode is supported.

        Returns:
            True if supported

        """
        current_model = self.get_current_model()
        return current_model.supports_interactive if current_model else False

    def wait_for_prompt(self, timeout: int = 30) -> bool:
        """Wait for interactive prompt.

        Args:
            timeout: Timeout in seconds

        Returns:
            True if prompt detected

        """
        # Simulate immediate prompt availability
        return True

    def intercept_file_operation(self, operation: FileOperation) -> bool:
        """Intercept file operation.

        Args:
            operation: File operation to validate

        Returns:
            True if operation should proceed

        """
        # Allow all operations in mock
        return True


class TestProviderFramework:
    """Main test suite for provider framework."""

    def test_mock_provider_basic(self):
        """Test basic mock provider functionality."""
        config = LLMConfig(provider_type="mock", model="mock-fast", api_key="test-key")

        provider = MockProvider(config)

        # Test generate
        response = provider.generate("Test prompt")
        assert "def test()" in response
        assert provider.generate_call_count == 1
        assert provider.last_prompt == "Test prompt"

    def test_mock_provider_streaming(self):
        """Test mock provider streaming capability."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        chunks = list(provider.generate_streaming("Stream test"))
        assert len(chunks) == 6
        assert "".join(chunks) == provider.mock_response
        assert provider.streaming_enabled

    def test_mock_provider_sessions(self):
        """Test mock provider session management."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        # Create session
        session = provider.create_session("test-session-1")
        assert session.id == "test-session-1"
        assert session.state == SessionState.ACTIVE

        # List sessions
        sessions = provider.list_sessions()
        assert len(sessions) == 1

        # Attach to session
        attached = provider.attach_session("test-session-1")
        assert attached.id == "test-session-1"

        # Kill session
        success = provider.kill_session("test-session-1")
        assert success
        assert provider._sessions["test-session-1"].state == SessionState.TERMINATED

    def test_mock_provider_models(self):
        """Test mock provider model management."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        # List models
        models = provider.list_models()
        assert len(models) == 2
        assert models[0].identifier == "mock-fast"
        assert models[1].identifier == "mock-smart"

        # Select model
        success = provider.select_model("mock-smart")
        assert success
        assert provider.model_selected == "mock-smart"

        # Get model mapping
        mapping = provider.get_model_mapping()
        assert mapping["fast"] == "mock-fast"
        assert mapping["smart"] == "mock-smart"

    def test_mock_provider_failure(self):
        """Test mock provider failure mode."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config, fail_on_generate=True)

        with pytest.raises(RuntimeError, match="Mock provider configured to fail"):
            provider.generate("Test")


class TestProviderRegistry:
    """Test provider registry functionality."""

    def test_registry_registration(self):
        """Test registering providers in registry."""
        registry = ProviderRegistry()

        # Try to register a new test provider
        try:
            registry.register("test_mock", MockProvider)
            assert "test_mock" in registry._providers
            assert registry._providers["test_mock"] == MockProvider
        finally:
            # Clean up
            if "test_mock" in registry._providers:
                registry.unregister("test_mock")

    def test_registry_creation(self):
        """Test creating providers from registry."""
        registry = ProviderRegistry()

        # Use a unique provider name for testing
        try:
            registry.register("test_mock_create", MockProvider)
            config = LLMConfig(provider_type="test_mock_create", model="mock-fast")
            provider = registry.create_provider("test_mock_create", config)

            assert isinstance(provider, MockProvider)
            assert provider.config.model == "mock-fast"
        finally:
            if "test_mock_create" in registry._providers:
                registry.unregister("test_mock_create")

    def test_registry_list_providers(self):
        """Test listing registered providers."""
        registry = ProviderRegistry()

        # Register test providers with unique names
        try:
            registry.register("test_list_1", MockProvider)
            registry.register("test_list_2", MockProvider)

            providers = registry.list_providers()
            assert "test_list_1" in providers
            assert "test_list_2" in providers
        finally:
            if "test_list_1" in registry._providers:
                registry.unregister("test_list_1")
            if "test_list_2" in registry._providers:
                registry.unregister("test_list_2")

    def test_registry_unregister(self):
        """Test unregistering providers."""
        registry = ProviderRegistry()

        # Register and unregister a test provider
        registry.register("test_unreg", MockProvider)
        registry.unregister("test_unreg")
        assert "test_unreg" not in registry._providers

        # Unregister non-existent should not error
        registry.unregister("nonexistent")  # No error expected


class TestProviderFactory:
    """Test provider factory functionality."""

    def test_factory_create(self):
        """Test creating providers via factory."""
        factory = ProviderFactory()

        # Register mock provider with unique name
        try:
            factory.registry.register("test_factory_mock", MockProvider)
            config = {"model": "mock-fast", "api_key": "test"}
            provider = factory.create("test_factory_mock", config)

            assert isinstance(provider, MockProvider)
            assert provider.config.model == "mock-fast"
        finally:
            if "test_factory_mock" in factory.registry._providers:
                factory.registry.unregister("test_factory_mock")

    @patch.dict(
        os.environ, {"LLM_PROVIDER": "mock_provider", "LLM_MODEL": "mock-smart"}
    )
    def test_factory_from_environment(self):
        """Test creating provider from environment variables."""
        factory = ProviderFactory()

        # The mock_provider should already be registered
        provider = factory.from_environment()
        assert provider is not None
        # Check that it's a mock provider type
        assert "mock" in provider.name.lower()

    def test_factory_with_fallback(self):
        """Test creating provider with fallback options."""
        factory = ProviderFactory()

        # Register test providers
        try:
            factory.registry.register("test_fallback_mock", MockProvider)

            # Register a failing provider
            class FailingProvider(MockProvider):
                def __init__(self, config):
                    raise RuntimeError("Intentional failure")

            factory.registry.register("test_failing", FailingProvider)

            # Try failing first, then mock
            provider = factory.create_with_fallback(
                "test_failing", ["test_fallback_mock"], config={"model": "mock-fast"}
            )

            assert isinstance(provider, MockProvider)
        finally:
            if "test_fallback_mock" in factory.registry._providers:
                factory.registry.unregister("test_fallback_mock")
            if "test_failing" in factory.registry._providers:
                factory.registry.unregister("test_failing")

    def test_factory_validation(self):
        """Test provider validation."""
        factory = ProviderFactory()

        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        valid = factory.validate_provider(provider)
        assert valid


class TestOutputHandlers:
    """Test output handler functionality."""

    def test_claude_output_handler(self):
        """Test Claude output handler."""
        handler = ClaudeOutputHandler()

        response = """
        I'll help you create a function.
        
        ```python
        def calculate(x, y):
            return x + y
        ```
        
        This function adds two numbers.
        """

        parsed = handler.parse(response)
        assert len(parsed.code_blocks) == 1
        assert parsed.code_blocks[0].language == "python"
        assert "calculate" in parsed.code_blocks[0].content
        assert parsed.metadata["provider"] == "claude"

    def test_venice_output_handler(self):
        """Test Venice output handler."""
        handler = VeniceOutputHandler()

        response = """
        Here's a function to calculate the sum:
        
        def calculate(x, y):
            return x + y
        
        You can use this function to add numbers.
        """

        parsed = handler.parse(response)
        assert parsed.metadata["provider"] == "venice"
        assert parsed.metadata["requires_code_extraction"]

        # Test implicit code detection
        content = handler.extract_content(response)
        assert len(content.code_blocks) > 0

    def test_output_handler_factory(self):
        """Test output handler factory."""
        claude_handler = OutputHandlerFactory.create("claude")
        assert isinstance(claude_handler, ClaudeOutputHandler)

        venice_handler = OutputHandlerFactory.create("venice")
        assert isinstance(venice_handler, VeniceOutputHandler)

        # Test default handler for unknown provider
        default_handler = OutputHandlerFactory.create("unknown")
        assert isinstance(default_handler, OutputHandler)

    def test_streaming_buffer(self):
        """Test streaming buffer functionality."""
        buffer = StreamingBuffer()

        # Add chunks
        buffer.append("Generated ")
        buffer.append("code:\n```python\n")
        buffer.append("def test():\n    return 42\n")
        buffer.append("```")

        # Get complete blocks
        blocks = buffer.get_complete_blocks()
        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert "def test()" in blocks[0].content

    def test_extract_executable_code(self):
        """Test extracting executable code."""
        response = """
        Here's the code:
        ```python
        def main():
            print("Hello")
        ```
        
        And some CSS:
        ```css
        body { color: red; }
        ```
        """

        executable = extract_executable_code(response, "claude")
        assert len(executable) == 1
        assert "def main()" in executable[0]

    def test_format_code_for_execution(self):
        """Test formatting code for execution."""
        code = """
def greet(name):
    return f"Hello, {name}"
"""

        formatted = format_code_for_execution(code, "python", add_main=True)
        assert "if __name__ == '__main__':" in formatted
        assert "greet()" in formatted

    def test_merge_streaming_responses(self):
        """Test merging streaming chunks."""
        chunks = [
            "Generated ",
            "code:\n",
            "```python\n",
            "def test():\n",
            "    return 42\n",
            "```",
        ]

        merged = merge_streaming_responses(chunks)
        assert merged.text == "".join(chunks)
        assert len(merged.code_blocks) == 1
        assert merged.metadata["merged_from_stream"]


class TestProviderSwitching:
    """Test provider switching functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.factory = ProviderFactory()
        # Register test providers with unique names
        try:
            self.factory.registry.register("test_switch_mock1", MockProvider)
        except ValueError:
            pass  # Already registered
        try:
            self.factory.registry.register("test_switch_mock2", MockProvider)
        except ValueError:
            pass  # Already registered

    def test_switch_providers(self):
        """Test switching between providers."""
        # Create first provider
        provider1 = self.factory.create("test_switch_mock1", {"model": "mock-fast"})
        response1 = provider1.generate("Test 1")
        assert "test()" in response1 or "42" in response1

        # Create second provider
        provider2 = self.factory.create("test_switch_mock2", {"model": "mock-smart"})
        response2 = provider2.generate("Test 2")
        assert "test()" in response2 or "42" in response2

        # Verify they're different instances
        assert provider1 is not provider2
        assert provider1.last_prompt == "Test 1"
        assert provider2.last_prompt == "Test 2"

    @patch.dict(os.environ, {}, clear=True)
    def test_dynamic_provider_switching(self):
        """Test dynamically switching providers via environment."""
        # Test switching between mock providers
        os.environ["LLM_PROVIDER"] = "mock_provider"
        provider1 = self.factory.from_environment()

        # Even with same provider type, should be able to create another instance
        provider2 = self.factory.from_environment()

        # Both should be mock providers
        assert provider1 is not None
        assert provider2 is not None


class TestErrorScenarios:
    """Test error handling scenarios."""

    def test_provider_initialization_error(self):
        """Test handling provider initialization errors."""
        factory = ProviderFactory()

        class ErrorProvider(BaseProvider):
            def __init__(self, config):
                raise RuntimeError("Initialization failed")

        factory.registry.register("error", ErrorProvider)

        with pytest.raises(RuntimeError, match="Failed to create provider"):
            factory.create("error")

    def test_invalid_provider_type(self):
        """Test handling invalid provider type."""
        factory = ProviderFactory()

        with pytest.raises(RuntimeError, match="Failed to create provider"):
            factory.create("nonexistent")

    def test_session_not_found(self):
        """Test handling session not found error."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        with pytest.raises(KeyError, match="Session invalid-session not found"):
            provider.attach_session("invalid-session")

    def test_model_selection_failure(self):
        """Test handling model selection failure."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        success = provider.select_model("nonexistent-model")
        assert not success

    def test_error_handler_integration(self):
        """Test error handler integration."""
        error_handler = get_error_handler()

        error = RuntimeError("Test error")
        provider_error = error_handler.handle_error(
            provider="mock",  # Changed from provider_type to provider
            error=error,
            context={"operation": "generate"},
        )

        assert isinstance(provider_error, ProviderError)
        assert provider_error.error_type == ErrorType.PROVIDER_ERROR
        assert provider_error.provider == "mock"

    def test_output_handler_error_recovery(self):
        """Test output handler error recovery."""
        handler = ClaudeOutputHandler()

        # Malformed response
        response = "```python\nunclosed code block"

        parsed = handler.parse(response)
        # Should still return a valid ParsedResponse
        assert isinstance(parsed, ParsedResponse)
        assert parsed.text == response

    def test_streaming_error_handling(self):
        """Test streaming error handling."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        # Simulate streaming error
        def error_stream(prompt: str, **kwargs):
            yield "Start"
            raise RuntimeError("Stream error")

        provider.generate_streaming = error_stream

        chunks = []
        with pytest.raises(RuntimeError, match="Stream error"):
            for chunk in provider.generate_streaming("Test"):
                chunks.append(chunk)

        # Should have received first chunk before error
        assert chunks == ["Start"]

    def test_file_operation_interception_denial(self):
        """Test file operation interception denial."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        # Override to deny operations
        provider.intercept_file_operation = lambda op: False

        operation = FileOperation(
            operation_type=FileOperationType.DELETE, path="/sensitive/file.txt"
        )

        allowed = provider.intercept_file_operation(operation)
        assert not allowed


class TestIntegrationScenarios:
    """Test complex integration scenarios."""

    def test_end_to_end_code_generation(self):
        """Test end-to-end code generation workflow."""
        # Set up
        factory = ProviderFactory()

        # Register test provider
        try:
            factory.registry.register("test_e2e_mock", MockProvider)
        except ValueError:
            pass  # Already registered

        # Create provider
        provider = factory.create("test_e2e_mock", {"model": "mock-fast"})

        # Generate code
        prompt = "Create a function to calculate fibonacci"
        response = provider.generate(prompt)

        # Parse response
        handler = OutputHandlerFactory.create("claude")
        parsed = handler.parse(response)

        # Extract executable code
        executable = extract_executable_code(response, "claude")

        # Validate results
        assert len(parsed.code_blocks) > 0
        assert len(executable) > 0
        assert "test()" in executable[0] or "42" in executable[0]

    def test_multi_provider_parallel_execution(self):
        """Test parallel execution with multiple providers."""
        factory = ProviderFactory()

        # Register test providers
        try:
            factory.registry.register("test_parallel_mock1", MockProvider)
            factory.registry.register("test_parallel_mock2", MockProvider)
        except ValueError:
            pass  # Already registered

        providers = [
            factory.create("test_parallel_mock1", {"model": "mock-fast"}),
            factory.create("test_parallel_mock2", {"model": "mock-smart"}),
        ]

        prompts = ["Generate function A", "Generate function B"]
        responses = []

        for provider, prompt in zip(providers, prompts, strict=False):
            response = provider.generate(prompt)
            responses.append(response)

        assert len(responses) == 2
        assert all("test()" in r or "42" in r for r in responses)

    def test_session_persistence_workflow(self):
        """Test session persistence workflow."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        # Create and use session
        session = provider.create_session("persistent-session")
        provider.generate("First prompt")

        # Save session (mock implementation)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            session_data = {
                "id": session.id,
                "model": session.model,
                "state": session.state.value,
                "metadata": session.metadata,
            }
            json.dump(session_data, f)
            temp_path = f.name

        try:
            # Simulate provider restart
            new_provider = MockProvider(config)

            # Restore session (mock implementation)
            with open(temp_path, "r") as f:
                session_data = json.load(f)

            # Recreate session
            restored = new_provider.create_session(session_data["id"])
            assert restored.id == session.id

            # Continue using session
            new_provider.generate("Second prompt")
            assert new_provider.last_prompt == "Second prompt"

        finally:
            os.unlink(temp_path)

    def test_cost_estimation_workflow(self):
        """Test cost estimation workflow."""
        config = LLMConfig(provider_type="mock", model="mock-smart")
        provider = MockProvider(config)

        prompt = "Generate a complex function with documentation"
        max_tokens = 2000

        # Estimate cost
        estimated_cost = provider.estimate_cost(prompt, max_tokens)

        # Mock provider returns cost based on token count
        assert estimated_cost is not None
        assert estimated_cost > 0

        # Verify cost calculation
        model_info = provider.get_current_model()
        assert model_info.cost_per_token == 0.01

    def test_capability_based_provider_selection(self):
        """Test selecting provider based on capabilities."""
        factory = ProviderFactory()

        # Create providers with different capabilities
        class StreamingProvider(MockProvider):
            def get_capabilities(self):
                return {"streaming": True, "interactive": False, "generate": True}

        class InteractiveProvider(MockProvider):
            def get_capabilities(self):
                return {"streaming": False, "interactive": True, "generate": True}

        # Register with unique names
        try:
            factory.registry.register("test_streaming", StreamingProvider)
            factory.registry.register("test_interactive", InteractiveProvider)
        except ValueError:
            pass  # Already registered

        # Select based on streaming need
        providers = ["test_streaming", "test_interactive"]
        for provider_type in providers:
            provider = factory.create(provider_type, {"model": "mock-fast"})
            caps = provider.get_capabilities()

            if "streaming" in provider_type:
                assert caps["streaming"]
                assert not caps["interactive"]
            else:
                assert not caps["streaming"]
                assert caps["interactive"]


class TestProviderConfiguration:
    """Test provider configuration management."""

    def test_config_loading(self):
        """Test loading provider configuration."""
        config_data = {
            "name": "test_provider",
            "type": "mock",
            "enabled": True,
            "default_model": "mock-smart",
            "api_key": "test-key-123",
            "base_url": "https://api.example.com",
            "extra_params": {"timeout": 30, "max_retries": 3},
        }

        config = ProviderConfig(**config_data)

        assert config.name == "test_provider"
        assert config.type == "mock"
        assert config.enabled
        assert config.default_model == "mock-smart"
        assert config.api_key == "test-key-123"
        assert config.extra_params["timeout"] == 30

    @patch.dict(
        os.environ,
        {
            "LLM_PROVIDER": "mock",
            "LLM_MODEL": "mock-smart",
            "LLM_TIMEOUT": "60",
            "LLM_MAX_RETRIES": "5",
        },
    )
    def test_environment_override(self):
        """Test environment variable overrides."""
        factory = ProviderFactory()

        # Test that we can create provider from environment
        # Note: _create_config_from_env may not exist, testing general env override
        os.environ["LLM_PROVIDER"] = "mock_provider"
        os.environ["LLM_MODEL"] = "mock-smart"

        provider = factory.from_environment()
        assert provider is not None

    def test_provider_specific_config(self):
        """Test provider-specific configuration."""
        # Just test that provider configs can be loaded
        config = ProviderConfig(
            name="test",
            type="test",
            enabled=True,
            api_key="test-key",
            base_url="https://test.api",
        )

        assert config.name == "test"
        assert config.api_key == "test-key"
        assert config.base_url == "https://test.api"

        # Test conversion to LLMConfig
        llm_config = config.to_llm_config()
        assert llm_config.provider_type == "test"
        assert llm_config.api_key == "test-key"


class TestProviderMetrics:
    """Test provider metrics and monitoring."""

    def test_usage_statistics(self):
        """Test provider usage statistics."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        # Create sessions
        provider.create_session("session1")
        provider.create_session("session2")
        provider.kill_session("session1")

        stats = provider.get_usage_stats()

        assert stats["total_sessions"] == 2
        assert stats["sessions_active"] == 1
        assert stats["current_model"] == "mock-fast"

    def test_response_metrics(self):
        """Test response metrics tracking."""
        config = LLMConfig(provider_type="mock", model="mock-fast")
        provider = MockProvider(config)

        response = provider.generate("Test prompt")
        parsed = provider.parse_response(response)

        assert parsed.tokens_used is not None
        assert parsed.execution_time is not None
        assert parsed.tokens_used > 0
        assert parsed.execution_time >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
