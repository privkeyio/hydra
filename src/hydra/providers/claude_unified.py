"""Unified Claude Provider - Consolidates all Claude implementations.

This module provides a single, configurable Claude provider that replaces
claude_cli.py, claude_tmux.py, and claude_cli_enhanced.py with a unified
interface that supports all modes through configuration.
"""

import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import orjson

from hydra.prompts.injection import (
    InjectionContext,
    InjectorRegistry,
    initialize_default_injectors,
)
from hydra.safety.claude_file_interceptor import ClaudeFileInterceptor
from hydra.utils.claude_path import get_claude_cli_path

from .base_provider import (
    BaseProvider,
    CodeBlock,
    FileOperation,
    FileOperationType,
    ModelInfo,
    ParsedResponse,
    Session,
    SessionState,
)


class ClaudeMode(Enum):
    """Claude provider execution modes."""

    SIMPLE = "simple"  # Basic CLI mode (replaces claude_cli.py)
    TMUX = "tmux"  # Interactive tmux mode (replaces claude_tmux.py)
    ENHANCED = "enhanced"  # Enhanced with file operations


@dataclass
class ClaudeSession:
    """Extended session state for Claude provider."""

    id: str
    mode: ClaudeMode
    working_dir: Path
    context_files: Dict[str, str] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    tmux_session: Optional[str] = None
    process: Optional[subprocess.Popen] = None
    output_buffer: List[str] = field(default_factory=list)


class ClaudeUnifiedProvider(BaseProvider):
    """Unified Claude provider with configurable execution modes.

    This provider consolidates all Claude implementations into a single,
    configurable provider that supports:
    - Simple CLI mode for basic interactions
    - Tmux mode for full interactivity
    - Enhanced mode with file operation handling

    Configuration:
        mode: ClaudeMode - Execution mode (simple, tmux, enhanced)
        claude_path: str - Path to Claude CLI executable
        tmux_timeout: int - Timeout for tmux operations (default: 300)
        max_retries: int - Maximum retry attempts (default: 3)
        file_interception: bool - Enable file operation interception (default: True)
        session_persistence: bool - Enable session save/restore (default: False)
    """

    def __init__(self, config):
        """Initialize unified Claude provider."""
        # Setup configuration before calling super().__init__
        # which will call validate_config
        self.config = config
        self._setup_configuration()
        self._sessions: Dict[str, ClaudeSession] = {}
        self._current_session: Optional[ClaudeSession] = None
        self._file_interceptor: Optional[ClaudeFileInterceptor] = None
        self._output_thread: Optional[threading.Thread] = None
        self._stop_output = threading.Event()

        # Initialize prompt injection system
        self._injector_registry = InjectorRegistry()
        if not self._injector_registry.injectors:
            initialize_default_injectors()

        # Now call super().__init__ which will validate
        super().__init__(config)

    def _setup_configuration(self):
        """Setup provider configuration from config and environment."""
        # Determine execution mode
        mode_str = self.config.extra_params.get(
            "mode", os.environ.get("CLAUDE_MODE", "tmux")
        )
        self.mode = ClaudeMode(mode_str.lower())

        # Claude CLI path
        self.claude_path = self.config.extra_params.get(
            "claude_path", os.environ.get("CLAUDE_CLI_PATH", get_claude_cli_path())
        )

        # Tmux configuration
        self.tmux_timeout = self.config.extra_params.get("tmux_timeout", 300)
        self.max_retries = self.config.extra_params.get("max_retries", 3)

        # Feature flags
        self.file_interception = self.config.extra_params.get(
            "file_interception", True
        )
        self.session_persistence = self.config.extra_params.get(
            "session_persistence", False
        )

        # Initialize file interceptor if enabled
        if self.file_interception and self.mode == ClaudeMode.ENHANCED:
            self._file_interceptor = ClaudeFileInterceptor()

    def validate_config(self):
        """Validate provider configuration."""
        # Check Claude CLI availability
        if not Path(self.claude_path).exists():
            # Try to find Claude in PATH
            try:
                result = subprocess.run(
                    ["which", "claude"], capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    self.claude_path = result.stdout.decode().strip()
                else:
                    raise ValueError(f"Claude CLI not found at: {self.claude_path}")
            except subprocess.TimeoutExpired:
                raise ValueError(
                    "Claude CLI not accessible. Please set 'claude_path' or ensure 'claude' is in PATH"
                )

        # Check tmux availability for tmux mode
        if self.mode == ClaudeMode.TMUX:
            try:
                subprocess.run(["tmux", "-V"], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise ValueError(
                    "tmux is required for tmux mode. Please install tmux or use a different mode"
                ) from e

    @property
    def name(self) -> str:
        """Provider name with mode suffix."""
        return f"claude_{self.mode.value}"

    # Core Generation Methods
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response based on configured mode."""
        if self.mode == ClaudeMode.SIMPLE:
            return self._generate_simple(prompt, **kwargs)
        elif self.mode == ClaudeMode.TMUX:
            return self._generate_tmux(prompt, **kwargs)
        else:  # ENHANCED
            return self._generate_enhanced(prompt, **kwargs)

    def _generate_simple(self, prompt: str, **kwargs) -> str:
        """Generate using simple CLI mode."""
        # Prepare temporary file with prompt
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp_file:
            tmp_file.write(prompt)
            tmp_path = tmp_file.name

        try:
            # Build command
            cmd = [self.claude_path]

            # Add model parameter
            if self.config.model:
                model_mapping = self.get_model_mapping()
                model_id = model_mapping.get(self.config.model, self.config.model)
                cmd.extend(["--model", model_id])

            # Add prompt file
            cmd.append(tmp_path)

            # Add additional parameters
            if kwargs.get("max_tokens"):
                cmd.extend(["--max-tokens", str(kwargs["max_tokens"])])

            # Execute command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=kwargs.get("timeout", 300),
                cwd=kwargs.get("cwd", os.getcwd()),
            )

            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI error: {result.stderr}")

            # Clean and return output
            return self._clean_claude_output(result.stdout)

        finally:
            # Cleanup temporary file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _generate_tmux(self, prompt: str, **kwargs) -> str:
        """Generate using tmux interactive mode."""
        session_id = kwargs.get("session_id", str(uuid.uuid4()))

        # Create or attach to session
        if session_id not in self._sessions:
            session = self.create_session(session_id, **kwargs)
        else:
            session = self.attach_session(session_id)

        # Send prompt to tmux session
        self._send_to_tmux(session.tmux_session, prompt)

        # Wait for and capture response
        response = self._capture_tmux_output(
            session.tmux_session, timeout=kwargs.get("timeout", self.tmux_timeout)
        )

        # Update session history
        session.history.append({"prompt": prompt, "response": response})
        session.last_accessed = time.time()

        return response

    def _generate_enhanced(self, prompt: str, **kwargs) -> str:
        """Generate using enhanced mode with file operations."""
        session_id = kwargs.get("session_id", str(uuid.uuid4()))

        # Get or create session
        if session_id not in self._sessions:
            session = self.create_session(session_id, **kwargs)
        else:
            session = self._sessions[session_id]

        # Add context files if provided
        if "context_files" in kwargs:
            session.context_files.update(kwargs["context_files"])

        # Prepare enhanced prompt with context
        enhanced_prompt = self._prepare_enhanced_prompt(prompt, session)

        # Execute with file interception if enabled
        if self._file_interceptor:
            with self._file_interceptor.intercept():
                response = self._execute_enhanced(enhanced_prompt, session, **kwargs)
        else:
            response = self._execute_enhanced(enhanced_prompt, session, **kwargs)

        # Update session
        session.history.append({"prompt": prompt, "response": response})
        session.last_accessed = time.time()

        return response

    def _prepare_enhanced_prompt(
        self, prompt: str, session: ClaudeSession
    ) -> str:
        """Prepare prompt with enhanced context."""
        parts = []

        # Add context files
        if session.context_files:
            parts.append("=== Context Files ===")
            for path, content in session.context_files.items():
                parts.append(f"\n--- {path} ---")
                parts.append(content)
            parts.append("\n=== End Context ===\n")

        # Add working directory info
        parts.append(f"Working Directory: {session.working_dir}")

        # Add the actual prompt
        parts.append(f"\n{prompt}")

        return "\n".join(parts)

    def _execute_enhanced(
        self, prompt: str, session: ClaudeSession, **kwargs
    ) -> str:
        """Execute enhanced prompt with subprocess management."""
        # Create temporary prompt file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp_file:
            tmp_file.write(prompt)
            tmp_path = tmp_file.name

        try:
            # Build command
            cmd = [self.claude_path]

            # Add model
            if self.config.model:
                model_mapping = self.get_model_mapping()
                model_id = model_mapping.get(self.config.model, self.config.model)
                cmd.extend(["--model", model_id])

            cmd.append(tmp_path)

            # Start process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                cwd=str(session.working_dir),
                bufsize=1,
            )

            session.process = process

            # Start output capture thread
            self._start_output_capture(session)

            # Wait for completion
            stdout, stderr = process.communicate(
                timeout=kwargs.get("timeout", 300)
            )

            if process.returncode != 0:
                raise RuntimeError(f"Claude process failed: {stderr}")

            # Stop output capture
            self._stop_output.set()

            # Get captured output
            response = "\n".join(session.output_buffer)
            session.output_buffer.clear()

            return self._clean_claude_output(response or stdout)

        except subprocess.TimeoutExpired:
            process.kill()
            raise TimeoutError("Claude response timed out")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            session.process = None

    def _start_output_capture(self, session: ClaudeSession):
        """Start thread to capture process output."""
        if session.process and session.process.stdout:

            def capture_output():
                while not self._stop_output.is_set():
                    line = session.process.stdout.readline()
                    if line:
                        session.output_buffer.append(line.rstrip())
                    elif session.process.poll() is not None:
                        break

            self._stop_output.clear()
            self._output_thread = threading.Thread(target=capture_output)
            self._output_thread.daemon = True
            self._output_thread.start()

    def generate_code(self, prompt: str, context: Dict[str, Any], **kwargs) -> str:
        """Generate code with context awareness."""
        # Use injection system for code generation prompts
        injection_context = InjectionContext(
            operation="code_generation",
            provider=self.name,
            model=self.config.model,
            user_prompt=prompt,
            variables=context,
            metadata={"context": context}
        )

        injected_prompt = self._inject_prompts(injection_context)
        return self.generate(injected_prompt, **kwargs)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from the LLM."""
        # Use injection system for JSON generation
        injection_context = InjectionContext(
            operation="json_generation",
            provider=self.name,
            model=self.config.model,
            user_prompt=prompt,
            metadata={"format": "json"}
        )

        injected_prompt = self._inject_prompts(injection_context)
        response = self.generate(injected_prompt, **kwargs)

        # Try to parse the response as JSON
        try:
            # Remove any markdown formatting if present
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            return orjson.loads(response)
        except (orjson.JSONDecodeError, IndexError) as e:
            # If parsing fails, return a dict with the raw response
            return {"raw_response": response, "error": str(e)}

    def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate streaming response for real-time output."""
        if self.mode != ClaudeMode.TMUX:
            # For non-tmux modes, yield complete response
            yield self.generate(prompt, **kwargs)
            return

        # For tmux mode, stream output
        session_id = kwargs.get("session_id", str(uuid.uuid4()))

        if session_id not in self._sessions:
            session = self.create_session(session_id, **kwargs)
        else:
            session = self._sessions[session_id]

        # Send prompt
        self._send_to_tmux(session.tmux_session, prompt)

        # Stream output
        last_size = 0
        timeout = time.time() + kwargs.get("timeout", self.tmux_timeout)

        while time.time() < timeout:
            output = self._get_tmux_buffer(session.tmux_session)
            if len(output) > last_size:
                yield output[last_size:]
                last_size = len(output)

            # Check if Claude is ready for next input
            if self._is_claude_ready(output):
                break

            time.sleep(0.1)

    # Session Management
    def create_session(self, session_id: str, **kwargs) -> Session:
        """Create a new provider session."""
        working_dir = Path(kwargs.get("working_dir", os.getcwd()))

        session = ClaudeSession(
            id=session_id,
            mode=self.mode,
            working_dir=working_dir,
        )

        if self.mode == ClaudeMode.TMUX:
            # Create tmux session
            tmux_name = f"claude_{session_id[:8]}"
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", tmux_name],
                check=True,
            )
            session.tmux_session = tmux_name

            # Start Claude in tmux
            cmd = [self.claude_path]
            if self.config.model:
                model_mapping = self.get_model_mapping()
                model_id = model_mapping.get(self.config.model, self.config.model)
                cmd.extend(["--model", model_id])

            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_name, " ".join(cmd), "Enter"],
                check=True,
            )

            # Wait for Claude to be ready
            self.wait_for_prompt(timeout=30)

        self._sessions[session_id] = session
        self._current_session = session

        # Return base Session object
        return Session(
            id=session_id,
            provider=self.name,
            model=self.config.model,
            created_at=datetime.fromtimestamp(session.created_at),
            last_activity=datetime.fromtimestamp(session.last_accessed),
            state=SessionState.ACTIVE,
            metadata={"mode": self.mode.value, "working_dir": str(working_dir)},
        )

    def attach_session(self, session_id: str) -> Session:
        """Attach to existing session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self._sessions[session_id]
        self._current_session = session
        session.last_accessed = time.time()

        return Session(
            id=session_id,
            provider=self.name,
            model=self.config.model,
            created_at=datetime.fromtimestamp(session.created_at),
            last_activity=datetime.fromtimestamp(session.last_accessed),
            state=SessionState.ACTIVE,
            metadata={
                "mode": session.mode.value,
                "working_dir": str(session.working_dir),
            },
        )

    def list_sessions(self) -> List[Session]:
        """List all active sessions."""
        sessions = []
        for session_id, session in self._sessions.items():
            sessions.append(
                Session(
                    id=session_id,
                    provider=self.name,
                    model=self.config.model,
                    created_at=datetime.fromtimestamp(session.created_at),
                    last_activity=datetime.fromtimestamp(session.last_accessed),
                    state=SessionState.ACTIVE,
                    metadata={
                        "mode": session.mode.value,
                        "working_dir": str(session.working_dir),
                    },
                )
            )
        return sessions

    def kill_session(self, session_id: str) -> bool:
        """Terminate a session."""
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]

        # Kill tmux session if exists
        if session.tmux_session:
            try:
                subprocess.run(
                    ["tmux", "kill-session", "-t", session.tmux_session],
                    check=True,
                )
            except subprocess.CalledProcessError:
                pass

        # Kill process if exists
        if session.process:
            try:
                session.process.terminate()
                session.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                session.process.kill()

        del self._sessions[session_id]
        if self._current_session and self._current_session.id == session_id:
            self._current_session = None

        return True

    # Model Management
    def list_models(self) -> List[str]:
        """List available models for this provider."""
        # Return string list for base compatibility
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ]

    def list_models_detailed(self) -> List[ModelInfo]:
        """List available models with metadata."""
        return [
            ModelInfo(
                identifier="claude-3-5-sonnet-20241022",
                display_name="Claude 3.5 Sonnet",
                category="smart",
                context_window=200000,
                max_output_tokens=8192,
                supports_streaming=True,
                supports_interactive=self.mode == ClaudeMode.TMUX,
                cost_per_token=0.000003,
                metadata={"tier": "premium", "recommended": True},
            ),
            ModelInfo(
                identifier="claude-3-5-haiku-20241022",
                display_name="Claude 3.5 Haiku",
                category="fast",
                context_window=200000,
                max_output_tokens=8192,
                supports_streaming=True,
                supports_interactive=self.mode == ClaudeMode.TMUX,
                cost_per_token=0.0000008,
                metadata={"tier": "standard", "recommended": False},
            ),
        ]

    def select_model(self, model_identifier: str) -> bool:
        """Select a specific model by identifier."""
        models = self.list_models_detailed()
        for model in models:
            if (
                model.identifier == model_identifier
                or model.display_name == model_identifier
            ):
                self.config.model = model.identifier
                return True
        return False

    def get_model_mapping(self) -> Dict[str, str]:
        """Map generic model names to provider-specific identifiers."""
        return {
            "fast": "claude-3-5-haiku-20241022",
            "smart": "claude-3-5-sonnet-20241022",
            "balanced": "claude-3-5-sonnet-20241022",
            "haiku": "claude-3-5-haiku-20241022",
            "sonnet": "claude-3-5-sonnet-20241022",
        }

    # Output Handling
    def parse_response(self, response: str) -> ParsedResponse:
        """Parse provider-specific response format."""
        code_blocks = self.extract_code_blocks(response)

        return ParsedResponse(
            text=response,
            code_blocks=code_blocks,
            metadata={
                "mode": self.mode.value,
                "has_code": len(code_blocks) > 0,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def extract_code_blocks(self, response: str) -> List[CodeBlock]:
        """Extract code blocks from response."""
        code_blocks = []
        pattern = r"```(\w+)?\n(.*?)```"

        for match in re.finditer(pattern, response, re.DOTALL):
            language = match.group(1) or "text"
            content = match.group(2)

            # Get line numbers
            start = response[: match.start()].count("\n") + 1
            end = response[: match.end()].count("\n") + 1

            # Try to extract filename from comments
            filename = None
            first_line = content.split("\n")[0] if content else ""
            if "# " in first_line or "// " in first_line:
                filename_match = re.search(r"[#/]+\s*(\S+\.\w+)", first_line)
                if filename_match:
                    filename = filename_match.group(1)

            code_blocks.append(
                CodeBlock(
                    language=language,
                    content=content,
                    line_start=start,
                    line_end=end,
                    executable=language in ["python", "bash", "sh", "javascript"],
                    filename=filename,
                )
            )

        return code_blocks

    # Interactive Features
    def supports_interactive(self) -> bool:
        """Check if provider supports interactive mode."""
        return self.mode == ClaudeMode.TMUX

    def wait_for_prompt(self, timeout: int = 30) -> bool:
        """Wait for interactive prompt if supported."""
        if not self.supports_interactive() or not self._current_session:
            return False

        session = self._current_session
        if not session.tmux_session:
            return False

        start = time.time()
        while time.time() - start < timeout:
            output = self._get_tmux_buffer(session.tmux_session)
            if self._is_claude_ready(output):
                return True
            time.sleep(0.5)

        return False

    def send_interactive_command(self, command: str) -> Optional[str]:
        """Send command in interactive mode."""
        if not self.supports_interactive() or not self._current_session:
            return None

        session = self._current_session
        if not session.tmux_session:
            return None

        self._send_to_tmux(session.tmux_session, command)
        return self._capture_tmux_output(session.tmux_session)

    # File Operations
    def intercept_file_operation(self, operation: FileOperation) -> bool:
        """Intercept and validate file operations."""
        if not self._file_interceptor:
            return True  # Allow all operations if no interceptor

        # Use file interceptor to validate
        if operation.operation_type == FileOperationType.WRITE:
            return self._file_interceptor.should_allow_write(operation.path)
        elif operation.operation_type == FileOperationType.DELETE:
            return self._file_interceptor.should_allow_delete(operation.path)
        elif operation.operation_type == FileOperationType.CREATE:
            return self._file_interceptor.should_allow_create(operation.path)

        return True  # Allow reads by default

    def supports_file_interception(self) -> bool:
        """Check if provider supports file operation interception."""
        return self.file_interception and self.mode == ClaudeMode.ENHANCED

    # Helper Methods
    def _clean_claude_output(self, output: str) -> str:
        """Clean Claude output by removing interface artifacts."""
        lines = output.split("\n")
        cleaned = []

        for line in lines:
            # Skip UI elements
            if any(char in line for char in ["┃", "╭", "╰", "│", "├", "└", "─"]):
                continue
            # Skip system prompts
            if line.strip().startswith(("cwd:", "You:", "Claude:")):
                continue
            # Skip empty lines at start/end
            if not cleaned and not line.strip():
                continue

            cleaned.append(line)

        # Remove trailing empty lines
        while cleaned and not cleaned[-1].strip():
            cleaned.pop()

        return "\n".join(cleaned)

    def _send_to_tmux(self, session_name: str, text: str):
        """Send text to tmux session."""
        # Escape special characters
        text = text.replace("'", "'\"'\"'")
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, text, "Enter"],
            check=True,
        )

    def _capture_tmux_output(
        self, session_name: str, timeout: int = None
    ) -> str:
        """Capture output from tmux session."""
        if timeout is None:
            timeout = self.tmux_timeout

        start = time.time()
        last_output = ""

        while time.time() - start < timeout:
            output = self._get_tmux_buffer(session_name)

            # Check if output has stabilized
            if output == last_output and self._is_claude_ready(output):
                return self._clean_claude_output(output)

            last_output = output
            time.sleep(0.5)

        return self._clean_claude_output(last_output)

    def _get_tmux_buffer(self, session_name: str) -> str:
        """Get current tmux pane buffer."""
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""

    def _is_claude_ready(self, output: str) -> bool:
        """Check if Claude is ready for input."""
        # Look for common prompt indicators
        prompts = [
            "Human:",
            "You:",
            "> ",
            ">>> ",
            "claude>",
            "Ready for input",
            "What would you like",
        ]
        last_line = output.strip().split("\n")[-1] if output else ""
        return any(prompt in last_line for prompt in prompts)

    # Cleanup
    def cleanup(self) -> None:
        """Clean up provider resources."""
        # Kill all sessions
        for session_id in list(self._sessions.keys()):
            self.kill_session(session_id)

        # Stop output thread if running
        if self._output_thread and self._output_thread.is_alive():
            self._stop_output.set()
            self._output_thread.join(timeout=1)

        # Cleanup file interceptor
        if self._file_interceptor:
            self._file_interceptor.cleanup()

        super().cleanup()

    def _inject_prompts(self, context: InjectionContext) -> str:
        """Apply prompt injection based on context."""
        # Get production injector for execution operations
        if "execution" in context.operation:
            injector = self._injector_registry.get("production")
        elif "verification" in context.operation:
            injector = self._injector_registry.get("verification")
        elif "ticket" in context.operation:
            injector = self._injector_registry.get("ticket")
        else:
            # Use production as default for safety
            injector = self._injector_registry.get("production")

        if injector:
            return injector.inject(context)

        return context.user_prompt
