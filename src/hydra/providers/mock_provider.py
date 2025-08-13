"""Mock LLM provider for testing."""
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from .base import LLMConfig
from .base_provider import (
    BaseProvider,
    CodeBlock,
    FileOperation,
    ModelInfo,
    ParsedResponse,
    Session,
    SessionState,
)


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
        self._mock_sessions: Dict[str, Session] = {}
        self._current_model = "mock-model-1"

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

    def generate_code(
        self, prompt: str, context: Dict[str, Any], **kwargs
    ) -> str:
        """Generate code with context awareness."""
        self.call_history.append({
            "method": "generate_code",
            "prompt": prompt,
            "context": context,
            "kwargs": kwargs
        })
        
        if self.fail_mode:
            raise RuntimeError("Mock provider configured to fail")
            
        # Return basic code response
        return "def generated_function():\n    return 'Generated code'"

    def create_session(
        self, session_id: str, **kwargs
    ) -> Session:
        """Create a new provider session."""
        session = Session(
            id=session_id,
            provider="mock",
            model=self._current_model,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state=SessionState.ACTIVE,
            metadata=kwargs
        )
        self._mock_sessions[session_id] = session
        return session

    def attach_session(self, session_id: str) -> Session:
        """Attach to existing session."""
        if session_id in self._mock_sessions:
            session = self._mock_sessions[session_id]
            session.last_activity = datetime.now()
            return session
        raise ValueError(f"Session {session_id} not found")

    def list_sessions(self) -> List[Session]:
        """List all active sessions."""
        return [s for s in self._mock_sessions.values() 
                if s.state == SessionState.ACTIVE]

    def kill_session(self, session_id: str) -> bool:
        """Terminate a session."""
        if session_id in self._mock_sessions:
            self._mock_sessions[session_id].state = SessionState.TERMINATED
            return True
        return False

    def list_models(self) -> List[ModelInfo]:
        """Return mock models with full metadata."""
        return [
            ModelInfo(
                identifier="mock-model-1",
                display_name="Mock Model 1",
                category="fast",
                context_window=4096,
                max_output_tokens=1024,
                supports_streaming=True,
                supports_interactive=False,
                cost_per_token=0.001
            ),
            ModelInfo(
                identifier="mock-model-2",
                display_name="Mock Model 2",
                category="smart",
                context_window=8192,
                max_output_tokens=2048,
                supports_streaming=True,
                supports_interactive=True,
                cost_per_token=0.002
            ),
            ModelInfo(
                identifier="mock-fast",
                display_name="Mock Fast",
                category="fast",
                context_window=2048,
                max_output_tokens=512,
                supports_streaming=False,
                supports_interactive=False,
                cost_per_token=0.0005
            ),
            ModelInfo(
                identifier="mock-smart",
                display_name="Mock Smart",
                category="smart",
                context_window=16384,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=True,
                cost_per_token=0.003
            ),
        ]

    def select_model(self, model_identifier: str) -> bool:
        """Select a specific model by identifier."""
        available_models = [m.identifier for m in self.list_models()]
        if model_identifier in available_models:
            self._current_model = model_identifier
            return True
        return False

    def get_model_mapping(self) -> Dict[str, str]:
        """Map generic model names to provider-specific identifiers."""
        return {
            "fast": "mock-fast",
            "smart": "mock-smart",
            "balanced": "mock-model-1",
            "default": "mock-model-1",
        }

    def parse_response(self, response: str) -> ParsedResponse:
        """Parse provider-specific response format."""
        code_blocks = self.extract_code_blocks(response)
        return ParsedResponse(
            text=response,
            code_blocks=code_blocks,
            metadata={"provider": "mock"},
            tokens_used=len(response.split()),
            execution_time=0.1
        )

    def extract_code_blocks(self, response: str) -> List[CodeBlock]:
        """Extract code blocks from response."""
        blocks = []
        lines = response.split('\n')
        in_code = False
        code_start = 0
        code_lines = []
        language = "python"
        
        for i, line in enumerate(lines):
            if line.strip().startswith('```'):
                if not in_code:
                    in_code = True
                    code_start = i
                    # Extract language if specified
                    lang = line.strip()[3:].strip()
                    if lang:
                        language = lang
                else:
                    # End of code block
                    if code_lines:
                        blocks.append(CodeBlock(
                            language=language,
                            content='\n'.join(code_lines),
                            line_start=code_start,
                            line_end=i,
                            executable=True
                        ))
                    in_code = False
                    code_lines = []
                    language = "python"
            elif in_code:
                code_lines.append(line)
        
        # If no markdown blocks found, check for indented code
        if not blocks:
            for i, line in enumerate(lines):
                if line.startswith('def ') or line.startswith('class '):
                    # Found a function or class definition
                    code_lines = []
                    j = i
                    while j < len(lines) and (lines[j].strip() or j == i):
                        code_lines.append(lines[j])
                        j += 1
                    if code_lines:
                        blocks.append(CodeBlock(
                            language="python",
                            content='\n'.join(code_lines),
                            line_start=i,
                            line_end=j,
                            executable=True
                        ))
                    break
        
        return blocks

    def supports_interactive(self) -> bool:
        """Check if provider supports interactive mode."""
        return self._current_model in ["mock-model-2", "mock-smart"]

    def wait_for_prompt(self, timeout: int = 30) -> bool:
        """Wait for interactive prompt if supported."""
        if not self.supports_interactive():
            return False
        # Mock implementation - always return True for testing
        return True

    def intercept_file_operation(
        self, operation: FileOperation
    ) -> bool:
        """Intercept and validate file operations."""
        self.call_history.append({
            "method": "intercept_file_operation",
            "operation": operation
        })
        # Mock implementation - allow all operations unless in fail mode
        return not self.fail_mode

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
        self._mock_sessions.clear()
        self._current_model = "mock-model-1"