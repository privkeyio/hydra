"""Venice AI provider implementation with production features."""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import orjson
from openai import APIConnectionError, APIError, AsyncOpenAI, OpenAI, RateLimitError
from openai import Timeout as OpenAITimeout

from hydra.action_executor import (
    Action,
    ActionType,
    ExecutionContext,
    FileOperationsExecutor,
    ResponseParser,
)
from hydra.prompts import get_system_prompt, optimize_prompt
from hydra.providers.base import LLMConfig
from hydra.providers.base_provider import (
    BaseProvider,
    CodeBlock,
    FileOperation,
    ModelInfo,
    ParsedResponse,
    Session,
    SessionState,
)
from hydra.providers.session_manager import get_session_manager
from hydra.token_tracker import get_token_tracker

logger = logging.getLogger(__name__)


class VeniceProvider(BaseProvider):
    """Venice AI provider implementation using OpenAI-compatible API.

    Venice provides access to various open-source models through an
    OpenAI-compatible interface, making it easy to integrate with
    existing tooling.
    """

    # Provider type identifier
    PROVIDER_TYPE = "venice_api"

    # Venice model mappings with coding-optimized models
    VENICE_MODELS = {
        "qwen-2.5-coder-32b": {
            "display_name": "Qwen 2.5 Coder 32B",
            "category": "smart",
            "context_window": 32768,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.0000002,
        },
        "llama-3.1-8b": {
            "display_name": "Llama 3.1 8B",
            "category": "fast",
            "context_window": 131072,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000005,
        },
        "llama-3.1-70b": {
            "display_name": "Llama 3.1 70B",
            "category": "balanced",
            "context_window": 131072,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000035,
        },
        "llama-3.1-405b": {
            "display_name": "Llama 3.1 405B",
            "category": "smart",
            "context_window": 131072,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000275,
        },
        "llama-3.3-70b": {
            "display_name": "Llama 3.3 70B",
            "category": "balanced",
            "context_window": 131072,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.00000035,
        },
        "deepseek-coder-v2-lite": {
            "display_name": "DeepSeek Coder V2 Lite",
            "category": "smart",
            "context_window": 128000,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.0000002,
        },
        "qwen-2.5-qwq-32b": {
            "display_name": "Qwen 2.5 QwQ 32B",
            "category": "smart",
            "context_window": 32768,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.0000002,
        },
        "venice-uncensored": {
            "display_name": "Venice Uncensored",
            "category": "balanced",
            "context_window": 32768,
            "max_output_tokens": 4096,
            "supports_streaming": True,
            "supports_interactive": False,
            "cost_per_token": 0.0000001,
        },
    }

    # Model name mappings for compatibility
    MODEL_MAPPINGS = {
        # Generic names to Venice models
        "fast": "llama-3.1-8b",
        "balanced": "llama-3.3-70b",
        "smart": "qwen-2.5-coder-32b",
        "coder": "qwen-2.5-coder-32b",
        # Claude compatibility mappings
        "opus": "qwen-2.5-coder-32b",
        "sonnet": "llama-3.3-70b",
    }

    def validate_config(self):
        """Validate Venice-specific configuration."""
        # Get API key from config or environment
        if not self.config.api_key:
            self.config.api_key = os.getenv("VENICE_API_KEY")

        if not self.config.api_key:
            raise ValueError("Venice provider requires api_key (set VENICE_API_KEY)")

        # Set default Venice values
        if not self.config.base_url:
            self.config.base_url = "https://api.venice.ai/api/v1"

        # Default to coding model if not specified
        if not self.config.model:
            self.config.model = "qwen-2.5-coder-32b"

        # Map model name if needed
        self._resolve_model_name()

    def __init__(self, config: LLMConfig):
        super().__init__(config)

        # Get session manager for connection pooling
        self.session_manager = get_session_manager()

        # Initialize token tracker
        self.token_tracker = get_token_tracker()
        self.ticket_id: Optional[int] = None
        self.session_id: Optional[int] = None

        # Configure retry settings with exponential backoff
        self.max_retries = config.extra_params.get("max_retries", 3)
        self.base_delay = config.extra_params.get("base_delay", 1.0)
        self.max_delay = config.extra_params.get("max_delay", 60.0)
        self.backoff_factor = config.extra_params.get("backoff_factor", 2.0)

        # Request/response logging settings
        self.log_requests = config.extra_params.get("log_requests", True)
        self.log_responses = config.extra_params.get("log_responses", False)
        self.log_dir = Path(config.extra_params.get("log_dir", ".hydra/logs"))
        if self.log_requests or self.log_responses:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # Timeout settings
        self.request_timeout = config.extra_params.get("request_timeout", 120)
        self.stream_timeout = config.extra_params.get("stream_timeout", 300)

        # OpenAI clients with timeout configuration
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.request_timeout,
            max_retries=0,  # We handle retries ourselves
        )
        self.async_client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.request_timeout,
            max_retries=0,  # We handle retries ourselves
        )

        # Statistics tracking
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retries": 0,
            "total_tokens": 0,
        }

        logger.info(f"Venice provider initialized with model: {self.config.model}")

    def _resolve_model_name(self) -> None:
        """Resolve model name using mappings."""
        model = self.config.model

        # Check if it's a generic name that needs mapping
        if model in self.MODEL_MAPPINGS:
            self.config.model = self.MODEL_MAPPINGS[model]
            logger.debug(f"Mapped model {model} to {self.config.model}")

    @property
    def name(self) -> str:
        return "venice"

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate a response from Venice AI with retry logic and error handling."""
        self.stats["total_requests"] += 1

        # Check budget before making request
        estimated_tokens = self.token_tracker.count_tokens(prompt, "venice") + 1000
        budget_ok, message = self.token_tracker.check_budget_available(
            estimated_tokens, self.config.model
        )
        if not budget_ok:
            raise ValueError(f"Token budget exceeded: {message}")

        # Merge kwargs with config
        temperature = kwargs.get("temperature", self.config.temperature)
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)

        # Add concise system message
        messages = [
            {"role": "system", "content": get_system_prompt("code")},
            {"role": "user", "content": optimize_prompt(prompt, "code_gen")},
        ]

        # Log request if enabled
        if self.log_requests:
            self._log_request(messages, temperature, max_tokens)

        # Filter out conflicting parameters from extra_params
        filtered_extra_params = {
            k: v
            for k, v in self.config.extra_params.items()
            if k
            not in [
                "temperature",
                "max_tokens",
                "model",
                "messages",
                "max_retries",
                "base_delay",
                "max_delay",
                "backoff_factor",
                "log_requests",
                "log_responses",
                "log_dir",
                "request_timeout",
                "stream_timeout",
            ]
        }

        # Execute with retry logic
        response_content = self._execute_with_retry(
            lambda: self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **filtered_extra_params,
            ),
            operation_name="generate",
        )

        # Extract content from response
        if hasattr(response_content, "choices"):
            content = response_content.choices[0].message.content
            # Get usage data if available
            usage_data = (
                response_content.usage if hasattr(response_content, "usage") else None
            )
        else:
            content = response_content
            usage_data = None

        # Track token usage
        if usage_data:
            # Use actual token counts from Venice/OpenAI API
            input_tokens = usage_data.prompt_tokens
            output_tokens = usage_data.completion_tokens
        else:
            # Estimate if not provided
            input_tokens = self.token_tracker.count_tokens(str(messages), "venice")
            output_tokens = self.token_tracker.count_tokens(content, "venice")

        # Track usage
        self.token_tracker.track_usage(
            provider="venice",
            model=self.config.model,
            prompt=prompt,
            response=content,
            ticket_id=self.ticket_id,
            session_id=self.session_id,
            metadata={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "actual_input_tokens": input_tokens if usage_data else None,
                "actual_output_tokens": output_tokens if usage_data else None,
            },
        )

        # Log response if enabled
        if self.log_responses:
            self._log_response(content)

        self.stats["successful_requests"] += 1
        return content

    def _execute_with_retry(self, operation, operation_name: str = "operation"):
        """Execute an operation with exponential backoff retry logic.

        Args:
            operation: Callable to execute
            operation_name: Name for logging

        Returns:
            Operation result

        Raises:
            Exception: After all retries exhausted

        """
        last_exception = None
        delay = self.base_delay

        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(
                        f"Retry {attempt}/{self.max_retries} for {operation_name}"
                    )
                    self.stats["retries"] += 1

                return operation()

            except RateLimitError as e:
                last_exception = e
                if attempt < self.max_retries:
                    # Use retry-after header if available
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after:
                        wait_time = min(float(retry_after), self.max_delay)
                    else:
                        wait_time = min(delay, self.max_delay)

                    logger.warning(
                        f"Rate limit hit for {operation_name}, waiting {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    delay *= self.backoff_factor

            except (APIConnectionError, OpenAITimeout) as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = min(delay, self.max_delay)
                    logger.warning(
                        f"Connection error for {operation_name}: {e}, "
                        f"waiting {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    delay *= self.backoff_factor

            except APIError as e:
                last_exception = e
                # Check if it's a retryable error (5xx status codes)
                if hasattr(e, "status_code") and e.status_code >= 500:
                    if attempt < self.max_retries:
                        wait_time = min(delay, self.max_delay)
                        logger.warning(
                            f"Server error {e.status_code} for {operation_name}, "
                            f"waiting {wait_time:.1f}s"
                        )
                        time.sleep(wait_time)
                        delay *= self.backoff_factor
                        continue

                # Non-retryable API error
                logger.error(f"Non-retryable API error for {operation_name}: {e}")
                self.stats["failed_requests"] += 1
                raise

            except Exception as e:
                # Unexpected error, don't retry
                logger.error(f"Unexpected error for {operation_name}: {e}")
                self.stats["failed_requests"] += 1
                raise

        # All retries exhausted
        self.stats["failed_requests"] += 1
        error_msg = f"All retries exhausted for {operation_name}: {last_exception}"
        logger.error(error_msg)
        raise Exception(error_msg) from last_exception

    def _log_request(self, messages: List[Dict], temperature: float, max_tokens: int):
        """Log request details for debugging and monitoring."""
        try:
            timestamp = datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            log_file = (
                self.log_dir / f"requests_{datetime.now().strftime('%Y%m%d')}.jsonl"
            )
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            logger.debug(f"Failed to log request: {e}")

    def _log_response(self, content: str):
        """Log response details for debugging and monitoring."""
        try:
            timestamp = datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "model": self.config.model,
                "content": content[:1000] if content else None,  # Truncate
                "content_length": len(content) if content else 0,
            }

            log_file = (
                self.log_dir / f"responses_{datetime.now().strftime('%Y%m%d')}.jsonl"
            )
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            logger.debug(f"Failed to log response: {e}")

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a JSON response from Venice AI."""
        # Add JSON instruction to prompt
        json_prompt = optimize_prompt(f"{prompt}\nJSON only.", "json_gen")

        response = self.generate(json_prompt, **kwargs)

        # Try to extract JSON from response
        try:
            # Clean up common issues
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            return orjson.loads(response.strip())
        except orjson.JSONDecodeError as e:
            # Fallback: try to find JSON in the response
            import re

            json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
            if json_match:
                try:
                    return orjson.loads(json_match.group())
                except orjson.JSONDecodeError:
                    pass

            raise ValueError(
                f"Failed to parse JSON response: {e}\nResponse: {response}"
            ) from e

    def generate_code(self, prompt: str, context: Dict[str, Any], **kwargs) -> str:
        """Generate code using Venice's coding-optimized models.

        Args:
            prompt: Code generation prompt
            context: Additional context (files, dependencies, etc.)
            **kwargs: Additional parameters

        Returns:
            Generated code

        """
        # Build enhanced prompt with context
        enhanced_prompt = self._build_code_prompt(prompt, context)

        # Generate response
        response = self.generate(enhanced_prompt, **kwargs)

        # Extract code from response
        code_blocks = self.extract_code_blocks(response)

        if code_blocks:
            # Return the main code block
            return code_blocks[0].content

        # If no code blocks found, assume entire response is code
        return response.strip()

    def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate streaming response from Venice with proper error handling.

        Args:
            prompt: Input prompt
            **kwargs: Additional generation parameters

        Yields:
            Chunks of generated text

        """
        self.stats["total_requests"] += 1
        messages = self._prepare_messages(prompt, **kwargs)

        # Log request if enabled
        if self.log_requests:
            self._log_request(
                messages,
                kwargs.get("temperature", self.config.temperature),
                kwargs.get("max_tokens", self.config.max_tokens),
            )

        # Create stream with timeout
        stream = None
        buffer = []

        try:
            # Use longer timeout for streaming
            self.client.timeout = self.stream_timeout

            stream = self._execute_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    temperature=kwargs.get("temperature", self.config.temperature),
                    stream=True,
                ),
                operation_name="streaming_generate",
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    buffer.append(content)
                    yield content

            # Log complete response if enabled
            if self.log_responses and buffer:
                self._log_response("".join(buffer))

            self.stats["successful_requests"] += 1

        except Exception as e:
            self.stats["failed_requests"] += 1
            logger.error(f"Venice streaming error: {e}")
            raise
        finally:
            # Restore original timeout
            if hasattr(self, "client"):
                self.client.timeout = self.request_timeout

    def _prepare_messages(self, prompt: str, **kwargs) -> List[Dict[str, str]]:
        """Prepare messages for Venice API.

        Args:
            prompt: User prompt
            **kwargs: Additional parameters

        Returns:
            List of message dictionaries

        """
        messages = []

        # Add system message for code generation
        system_prompt = kwargs.get("system_prompt", self._get_default_system_prompt())
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add conversation history if provided
        history = kwargs.get("history", [])
        messages.extend(history)

        # Add current prompt
        messages.append({"role": "user", "content": prompt})

        return messages

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for Venice."""
        return get_system_prompt("code")

    def _build_code_prompt(self, prompt: str, context: Dict[str, Any]) -> str:
        """Build enhanced prompt for code generation.

        Args:
            prompt: Original prompt
            context: Additional context

        Returns:
            Enhanced prompt

        """
        parts = []

        # Add context about files if provided
        if "files" in context:
            parts.append("# Context Files:")
            for file_path, content in context["files"].items():
                parts.append(f"\n## {file_path}")
                parts.append("```")
                parts.append(content[:1000])  # Limit context size
                if len(content) > 1000:
                    parts.append("... (truncated)")
                parts.append("```")
            parts.append("")

        # Add dependencies if provided
        if "dependencies" in context:
            parts.append("# Dependencies:")
            parts.append(", ".join(context["dependencies"]))
            parts.append("")

        # Add the main prompt
        parts.append("# Task:")
        parts.append(prompt)
        parts.append("")
        parts.append("Working code.")

        return "\n".join(parts)

    def list_models(self) -> List[ModelInfo]:
        """List available Venice models with metadata.

        Returns:
            List of available models

        """
        models = []

        for model_id, info in self.VENICE_MODELS.items():
            models.append(
                ModelInfo(
                    identifier=model_id,
                    display_name=info["display_name"],
                    category=info["category"],
                    context_window=info["context_window"],
                    max_output_tokens=info["max_output_tokens"],
                    supports_streaming=info["supports_streaming"],
                    supports_interactive=info["supports_interactive"],
                    cost_per_token=info.get("cost_per_token"),
                    metadata={"provider": "venice"},
                )
            )

        return models

    def select_model(self, model_identifier: str) -> bool:
        """Select a specific model.

        Args:
            model_identifier: Model to select

        Returns:
            True if model selected successfully

        """
        # Check if it's a generic name
        if model_identifier in self.MODEL_MAPPINGS:
            model_identifier = self.MODEL_MAPPINGS[model_identifier]

        # Check if model is available
        if model_identifier not in self.VENICE_MODELS:
            logger.warning(f"Model {model_identifier} not in known models")

        self.config.model = model_identifier
        logger.info(f"Selected Venice model: {model_identifier}")
        return True

    def get_model_mapping(self) -> Dict[str, str]:
        """Get model name mappings.

        Returns:
            Dictionary mapping generic names to Venice models

        """
        return self.MODEL_MAPPINGS.copy()

    def parse_response(self, response: str) -> ParsedResponse:
        """Parse Venice response.

        Args:
            response: Raw response text

        Returns:
            Parsed response with metadata

        """
        code_blocks = self.extract_code_blocks(response)

        return ParsedResponse(
            text=response,
            code_blocks=code_blocks,
            metadata={
                "provider": "venice",
                "model": self.config.model,
                "timestamp": datetime.now().isoformat(),
                "requires_code_extraction": len(code_blocks) > 0,
            },
        )

    def _format_code_prompt(self, prompt: str) -> str:
        """Format a prompt for code generation.

        Args:
            prompt: The original prompt

        Returns:
            Formatted prompt for code generation

        """
        return f"Code for: {prompt}\nUse code blocks."

    def extract_code_blocks(self, response: str) -> List[CodeBlock]:
        """Extract code blocks from response.

        Args:
            response: Response text containing code

        Returns:
            List of extracted code blocks

        """
        code_blocks = []

        # Find markdown code blocks
        pattern = r"```(\w+)?\n(.*?)```"
        matches = re.finditer(pattern, response, re.DOTALL)

        for _i, match in enumerate(matches):
            language = match.group(1) or "text"
            content = match.group(2).strip()

            # Determine if executable based on language
            executable_languages = {
                "python",
                "py",
                "javascript",
                "js",
                "typescript",
                "ts",
                "bash",
                "sh",
                "shell",
                "ruby",
                "rb",
                "go",
                "rust",
                "rs",
                "java",
                "cpp",
                "c",
                "cs",
                "php",
                "perl",
                "lua",
            }

            code_blocks.append(
                CodeBlock(
                    language=language,
                    content=content,
                    line_start=response[: match.start()].count("\n") + 1,
                    line_end=response[: match.end()].count("\n") + 1,
                    executable=language.lower() in executable_languages,
                    filename=None,
                )
            )

        # If no markdown blocks found, check for inline code patterns
        if not code_blocks:
            # Look for common code patterns
            code_patterns = [
                "def ",
                "class ",
                "function ",
                "import ",
                "const ",
                "var ",
                "let ",
            ]
            if any(pattern in response for pattern in code_patterns):
                # Treat entire response as code
                code_blocks.append(
                    CodeBlock(
                        language="text",
                        content=response.strip(),
                        line_start=1,
                        line_end=response.count("\n") + 1,
                        executable=True,
                        filename=None,
                    )
                )

        return code_blocks

    # Session Management (Venice doesn't support persistent sessions)
    def create_session(self, session_id: str, **kwargs) -> Session:
        """Create a new session (stateless for Venice).

        Args:
            session_id: Session identifier
            **kwargs: Additional parameters

        Returns:
            Session object

        """
        session = Session(
            id=session_id,
            provider="venice",
            model=self.config.model,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state=SessionState.ACTIVE,
            metadata=kwargs,
        )

        self._sessions[session_id] = session
        self._current_session = session

        return session

    def attach_session(self, session_id: str) -> Session:
        """Attach to session (stateless for Venice).

        Args:
            session_id: Session identifier

        Returns:
            Session object

        """
        if session_id in self._sessions:
            self._current_session = self._sessions[session_id]
            self._current_session.last_activity = datetime.now()
            return self._current_session

        # Create new session if doesn't exist
        return self.create_session(session_id)

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

    # Interactive Features (not supported by Venice)
    def supports_interactive(self) -> bool:
        """Check if provider supports interactive mode.

        Returns:
            False (Venice is API-based)

        """
        return False

    def wait_for_prompt(self, timeout: int = 30) -> bool:
        """Wait for interactive prompt (not supported).

        Args:
            timeout: Timeout in seconds

        Returns:
            False (not supported)

        """
        return False

    # File Operations
    def intercept_file_operation(self, operation: FileOperation) -> bool:
        """Intercept file operations (basic validation only).

        Args:
            operation: File operation to validate

        Returns:
            True if operation should proceed

        """
        # Basic safety checks
        forbidden_paths = ["/etc", "/sys", "/proc", "/boot"]

        for forbidden in forbidden_paths:
            if operation.path.startswith(forbidden):
                logger.warning(f"Blocked file operation on {operation.path}")
                return False

        return True

    # Venice-specific prompt templates
    def preprocess_prompt(self, prompt: str) -> str:
        """Preprocess prompt for Venice.

        Args:
            prompt: Original prompt

        Returns:
            Preprocessed prompt optimized for Venice

        """
        # Add code generation hints if detected
        code_keywords = ["write", "create", "implement", "function", "class", "code"]

        if any(keyword in prompt.lower() for keyword in code_keywords):
            # Add code generation instruction
            prompt = f"{prompt}\nWorking code. Comment complex parts."

        return prompt

    def postprocess_response(self, response: str) -> str:
        """Postprocess Venice response.

        Args:
            response: Raw response

        Returns:
            Cleaned response

        """
        # Remove any potential prompt leakage
        if "Please provide" in response or "Here is" in response:
            lines = response.split("\n")
            # Remove common preamble lines
            phrases = ["Please", "Here", "I'll", "Let me"]
            while lines and any(phrase in lines[0] for phrase in phrases):
                lines.pop(0)
            response = "\n".join(lines)

        return response.strip()

    def handle_error(self, error: Exception) -> Optional[str]:
        """Handle Venice-specific errors.

        Args:
            error: Exception that occurred

        Returns:
            Error message or None

        """
        error_str = str(error)

        if "api_key" in error_str.lower():
            return (
                "Venice API key is invalid or not set. "
                "Please check VENICE_API_KEY environment variable."
            )

        if "rate_limit" in error_str.lower():
            return "Venice API rate limit exceeded. Please wait before retrying."

        if "model" in error_str.lower():
            return f"Model {self.config.model} not available. Please check model name."

        # Let other errors propagate
        return None

    async def generate_async(self, prompt: str, **kwargs) -> str:
        """Generate a response asynchronously with retry logic."""
        self.stats["total_requests"] += 1

        temperature = kwargs.get("temperature", self.config.temperature)
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)

        messages = [
            {"role": "system", "content": get_system_prompt("code")},
            {"role": "user", "content": optimize_prompt(prompt, "code_gen")},
        ]

        # Log request if enabled
        if self.log_requests:
            self._log_request(messages, temperature, max_tokens)

        # Filter out conflicting parameters from extra_params
        filtered_extra_params = {
            k: v
            for k, v in self.config.extra_params.items()
            if k
            not in [
                "temperature",
                "max_tokens",
                "model",
                "messages",
                "max_retries",
                "base_delay",
                "max_delay",
                "backoff_factor",
                "log_requests",
                "log_responses",
                "log_dir",
                "request_timeout",
                "stream_timeout",
            ]
        }

        # Execute with async retry logic
        response = await self._execute_async_with_retry(
            lambda: self.async_client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **filtered_extra_params,
            ),
            operation_name="async_generate",
        )

        content = response.choices[0].message.content

        # Log response if enabled
        if self.log_responses:
            self._log_response(content)

        self.stats["successful_requests"] += 1
        return content

    async def _execute_async_with_retry(
        self, operation, operation_name: str = "operation"
    ):
        """Execute an async operation with exponential backoff retry logic.

        Args:
            operation: Async callable to execute
            operation_name: Name for logging

        Returns:
            Operation result

        Raises:
            Exception: After all retries exhausted

        """
        last_exception = None
        delay = self.base_delay

        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(
                        f"Retry {attempt}/{self.max_retries} for {operation_name}"
                    )
                    self.stats["retries"] += 1

                return await operation()

            except RateLimitError as e:
                last_exception = e
                if attempt < self.max_retries:
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after:
                        wait_time = min(float(retry_after), self.max_delay)
                    else:
                        wait_time = min(delay, self.max_delay)

                    logger.warning(
                        f"Rate limit hit for {operation_name}, waiting {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    delay *= self.backoff_factor

            except (APIConnectionError, OpenAITimeout) as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = min(delay, self.max_delay)
                    logger.warning(
                        f"Connection error for {operation_name}: {e}, "
                        f"waiting {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    delay *= self.backoff_factor

            except APIError as e:
                last_exception = e
                if hasattr(e, "status_code") and e.status_code >= 500:
                    if attempt < self.max_retries:
                        wait_time = min(delay, self.max_delay)
                        logger.warning(
                            f"Server error {e.status_code} for {operation_name}, "
                            f"waiting {wait_time:.1f}s"
                        )
                        await asyncio.sleep(wait_time)
                        delay *= self.backoff_factor
                        continue

                logger.error(f"Non-retryable API error for {operation_name}: {e}")
                self.stats["failed_requests"] += 1
                raise

            except Exception as e:
                logger.error(f"Unexpected error for {operation_name}: {e}")
                self.stats["failed_requests"] += 1
                raise

        self.stats["failed_requests"] += 1
        error_msg = f"All retries exhausted for {operation_name}: {last_exception}"
        logger.error(error_msg)
        raise Exception(error_msg) from last_exception

    async def generate_batch_async(self, prompts: List[str], **kwargs) -> List[str]:
        """Generate responses for multiple prompts in batch."""
        tasks = []
        for prompt in prompts:
            task = self.generate_async(prompt, **kwargs)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error strings
        final_results = []
        for result in results:
            if isinstance(result, Exception):
                final_results.append(f"Error: {str(result)}")
            else:
                final_results.append(result)

        return final_results

    def execute_ticket(
        self, ticket_content: str, working_directory: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Execute a ticket by generating Venice response and executing actions.

        This method integrates the action executor with Venice to enable
        non-interactive execution of file operations and commands.

        Args:
            ticket_content: The ticket description/requirements
            working_directory: Directory to execute actions in
            **kwargs: Additional parameters for generation

        Returns:
            Dictionary containing execution results with keys:
                - success: Whether all actions succeeded
                - actions_executed: Number of actions executed
                - results: List of action results
                - response: The Venice response text
                - errors: List of any errors encountered

        """
        start_time = time.time()
        working_dir = Path(working_directory) if working_directory else Path.cwd()

        # Initialize execution tracking
        execution_result = {
            "success": True,
            "actions_executed": 0,
            "results": [],
            "response": "",
            "errors": [],
            "execution_time": 0.0,
        }

        try:
            # Build enhanced prompt for Venice
            prompt = self._build_ticket_prompt(ticket_content)

            # Generate response from Venice
            logger.info("Generating Venice response for ticket execution")
            response = self.generate(prompt, **kwargs)
            execution_result["response"] = response

            # Parse response to extract actions
            logger.info("Parsing Venice response for actions")
            actions = self._parse_venice_response(response)

            if not actions:
                logger.warning("No actions extracted from Venice response")
                execution_result["errors"].append(
                    "No executable actions found in response"
                )
                return execution_result

            logger.info(f"Extracted {len(actions)} actions from Venice response")

            # Create execution context
            context = ExecutionContext(
                working_directory=working_dir,
                dry_run=kwargs.get("dry_run", False),
                max_retries=kwargs.get("max_retries", 3),
                timeout=kwargs.get("timeout", 300),
                rollback_on_failure=kwargs.get("rollback_on_failure", True),
                session_id=kwargs.get("session_id"),
            )

            # Initialize file executor
            executor = FileOperationsExecutor(context)

            # Execute actions
            for action in actions:
                try:
                    # Validate action first
                    if not executor.validate(action):
                        error_msg = (
                            f"Action validation failed: {action.type.name} "
                            f"on {action.target}"
                        )
                        logger.warning(error_msg)
                        execution_result["errors"].append(error_msg)
                        continue

                    # Execute the action
                    logger.info(
                        f"Executing action: {action.type.name} on {action.target}"
                    )
                    result = executor.execute(action)

                    # Track result
                    execution_result["results"].append(
                        {
                            "action_type": action.type.name,
                            "target": action.target,
                            "success": result.success,
                            "output": result.output,
                            "error": result.error,
                            "execution_time": result.execution_time,
                        }
                    )

                    if result.success:
                        execution_result["actions_executed"] += 1
                    else:
                        execution_result["success"] = False
                        if result.error:
                            execution_result["errors"].append(result.error)

                        # Handle rollback if enabled
                        if context.rollback_on_failure:
                            logger.info("Rolling back due to action failure")
                            executor.rollback()
                            break

                except Exception as e:
                    error_msg = f"Failed to execute action {action.type.name}: {str(e)}"
                    logger.error(error_msg)
                    execution_result["errors"].append(error_msg)
                    execution_result["success"] = False

                    if context.rollback_on_failure:
                        executor.rollback()
                        break

        except Exception as e:
            error_msg = f"Ticket execution failed: {str(e)}"
            logger.error(error_msg)
            execution_result["errors"].append(error_msg)
            execution_result["success"] = False

        # Calculate execution time
        execution_result["execution_time"] = time.time() - start_time

        # Log summary
        logger.info(
            f"Ticket execution completed: success={execution_result['success']}, "
            f"actions={execution_result['actions_executed']}, "
            f"time={execution_result['execution_time']:.2f}s"
        )

        return execution_result

    def _build_ticket_prompt(self, ticket_content: str) -> str:
        """Build an enhanced prompt for ticket execution.

        Args:
            ticket_content: The ticket requirements

        Returns:
            Enhanced prompt for Venice

        """
        prompt_parts = [
            "Implement:",
            ticket_content,
            "",
            "Provide:",
            "1. Code files (```lang:path format)",
            "2. Commands (bash blocks)",
            "3. Working code",
        ]

        return "\n".join(prompt_parts)

    def _parse_venice_response(self, response: str) -> List[Action]:
        """Parse Venice response to extract actions.

        This method handles Venice-specific response formats and converts
        them into executable actions.

        Args:
            response: The Venice response text

        Returns:
            List of parsed actions

        """
        parser = ResponseParser(
            validate_actions=True,
            allow_dangerous=False,
            max_actions=100,
        )

        try:
            # First try standard parsing
            actions = parser.parse(response)

            # If no actions found, try Venice-specific patterns
            if not actions:
                actions = self._extract_venice_specific_actions(response)

            # Enhance actions with Venice metadata
            for action in actions:
                action.metadata["provider"] = "venice"
                action.metadata["model"] = self.config.model

            return actions

        except Exception as e:
            logger.error(f"Failed to parse Venice response: {e}")
            # Try fallback parsing
            return self._fallback_parse_venice_response(response)

    def _extract_venice_specific_actions(self, response: str) -> List[Action]:
        """Extract actions using Venice-specific patterns.

        Args:
            response: The Venice response

        Returns:
            List of extracted actions

        """
        actions = []

        # Pattern for code blocks with file paths (e.g., ```python:src/main.py)
        file_pattern = r"```(?:(\w+):)?([^\n]+)\n(.*?)```"
        matches = re.finditer(file_pattern, response, re.DOTALL)

        for match in matches:
            language = match.group(1) or "text"
            potential_path = match.group(2).strip()
            content = match.group(3).strip()

            # Check if this looks like a file path
            if self._is_valid_file_path(potential_path):
                action = Action(
                    type=ActionType.CREATE_FILE,
                    target=potential_path,
                    content=content,
                    metadata={
                        "language": language,
                        "source": "venice_parser",
                    },
                )
                actions.append(action)
            # Check if it's a shell command
            elif language in ["bash", "sh", "shell"]:
                # Parse individual commands from the block
                commands = content.split("\n")
                for cmd in commands:
                    cmd = cmd.strip()
                    if cmd and not cmd.startswith("#"):
                        action = Action(
                            type=ActionType.RUN_COMMAND,
                            target=cmd,
                            metadata={"source": "venice_parser"},
                        )
                        actions.append(action)

        return actions

    def _fallback_parse_venice_response(self, response: str) -> List[Action]:
        """Fallback parser for Venice responses.

        This method tries to extract any recognizable patterns when
        standard parsing fails.

        Args:
            response: The Venice response

        Returns:
            List of actions (may be empty)

        """
        actions = []

        # Try to find any code blocks
        code_blocks = self.extract_code_blocks(response)

        for block in code_blocks:
            # Try to determine if this is a file or command
            if block.filename:
                action = Action(
                    type=ActionType.CREATE_FILE,
                    target=block.filename,
                    content=block.content,
                    metadata={
                        "language": block.language,
                        "source": "venice_fallback",
                    },
                )
                actions.append(action)
            elif block.language in ["bash", "sh", "shell"]:
                # Treat as commands
                for line in block.content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        action = Action(
                            type=ActionType.RUN_COMMAND,
                            target=line,
                            metadata={"source": "venice_fallback"},
                        )
                        actions.append(action)

        return actions

    def _is_valid_file_path(self, path: str) -> bool:
        """Check if a string looks like a valid file path.

        Args:
            path: String to check

        Returns:
            True if it looks like a file path

        """
        # Basic checks for file path patterns
        if not path or len(path) > 255:
            return False

        # Check for file extensions
        if "." in path:
            ext = path.split(".")[-1]
            # Common code file extensions
            valid_extensions = {
                "py",
                "js",
                "ts",
                "jsx",
                "tsx",
                "java",
                "cpp",
                "c",
                "h",
                "go",
                "rs",
                "rb",
                "php",
                "cs",
                "swift",
                "kt",
                "scala",
                "html",
                "css",
                "scss",
                "json",
                "xml",
                "yaml",
                "yml",
                "md",
                "txt",
                "sh",
                "bash",
                "sql",
                "dockerfile",
                "makefile",
            }
            if ext.lower() in valid_extensions:
                return True

        # Check for path separators
        if "/" in path or "\\" in path:
            return True

        return False

    def parse_response_for_actions(self, response: str) -> Tuple[List[Dict], List[str]]:
        """Parse Venice response for file operations and commands.

        This is a compatibility method that returns results in a simpler format.

        Args:
            response: The Venice response

        Returns:
            Tuple of (file_operations, commands) where:
                - file_operations: List of dicts with 'path' and 'content'
                - commands: List of command strings

        """
        actions = self._parse_venice_response(response)

        file_operations = []
        commands = []

        for action in actions:
            if action.type in [ActionType.CREATE_FILE, ActionType.MODIFY_FILE]:
                file_operations.append(
                    {
                        "path": action.target,
                        "content": action.content or "",
                        "operation": action.type.name.lower(),
                    }
                )
            elif action.type == ActionType.RUN_COMMAND:
                commands.append(action.target)

        return file_operations, commands

    def set_tracking_context(
        self, ticket_id: Optional[int] = None, session_id: Optional[int] = None
    ) -> None:
        """Set context for token tracking.

        Args:
            ticket_id: Optional ticket ID for tracking
            session_id: Optional session ID for tracking

        """
        self.ticket_id = ticket_id
        self.session_id = session_id

    def cleanup(self) -> None:
        """Clean up provider resources."""
        super().cleanup()

        # Log final statistics
        logger.info(
            f"Venice provider stats: requests={self.stats['total_requests']}, "
            f"successful={self.stats['successful_requests']}, "
            f"failed={self.stats['failed_requests']}, "
            f"retries={self.stats['retries']}"
        )

        # Close HTTP session for this provider
        try:
            self.session_manager.close_session("venice")
        except Exception as e:
            logger.debug(f"Failed to close session: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics.

        Returns:
            Dictionary of statistics

        """
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset provider statistics."""
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retries": 0,
            "total_tokens": 0,
        }
