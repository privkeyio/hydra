"""Centralized error messages for provider system."""

from typing import Optional


class ErrorMessages:
    """User-friendly error messages for different scenarios."""

    # Provider initialization errors
    PROVIDER_NOT_FOUND = (
        "Provider '{provider}' not found. Available providers: {available}.\n"
        "Install missing providers or use 'hydra provider list' to see options."
    )

    PROVIDER_INIT_FAILED = (
        "Failed to initialize {provider} provider.\n"
        "{details}\n"
        "Check your configuration and try again."
    )

    MISSING_DEPENDENCY = (
        "{provider} provider requires {dependency} to be installed.\n"
        "Install it with: {install_command}"
    )

    # Authentication errors
    MISSING_API_KEY = (
        "{provider} requires an API key.\n"
        "Set it with: export {env_var}='your-api-key'\n"
        "Get your API key from: {url}"
    )

    INVALID_API_KEY = (
        "Invalid API key for {provider}.\n"
        "Check your {env_var} environment variable.\n"
        "Ensure the key is active and has the correct permissions."
    )

    AUTHENTICATION_FAILED = (
        "Authentication failed for {provider}.\n"
        "{reason}\n"
        "Verify your credentials and try again."
    )

    # Network errors
    CONNECTION_FAILED = (
        "Unable to connect to {provider} service.\n"
        "Check your internet connection and firewall settings.\n"
        "If using a proxy, ensure it's properly configured."
    )

    TIMEOUT = (
        "Request to {provider} timed out after {timeout}s.\n"
        "The service may be experiencing high load.\n"
        "Try again or increase the timeout setting."
    )

    DNS_RESOLUTION_FAILED = (
        "Unable to resolve {provider} hostname.\n"
        "Check your network configuration and DNS settings."
    )

    # Rate limiting
    RATE_LIMIT_EXCEEDED = (
        "Rate limit exceeded for {provider}.\n"
        "Wait {retry_after}s before retrying.\n"
        "Consider upgrading your plan for higher limits."
    )

    QUOTA_EXCEEDED = (
        "Usage quota exceeded for {provider}.\n"
        "Current usage: {current}/{limit}\n"
        "Upgrade your plan or wait for quota reset."
    )

    # Model errors
    MODEL_NOT_FOUND = (
        "Model '{model}' not available in {provider}.\n"
        "Available models: {available}\n"
        "Use 'hydra provider list-models' to see all options."
    )

    MODEL_ACCESS_DENIED = (
        "Access denied to model '{model}' in {provider}.\n"
        "This model may require special permissions or a paid plan.\n"
        "Contact support or upgrade your account."
    )

    # Session errors
    SESSION_NOT_FOUND = (
        "Session '{session_id}' not found in {provider}.\n"
        "The session may have expired or been terminated.\n"
        "Create a new session with 'hydra session create'."
    )

    SESSION_EXPIRED = (
        "Session '{session_id}' has expired.\n"
        "Sessions expire after {timeout} of inactivity.\n"
        "Create a new session to continue."
    )

    SESSION_LIMIT_REACHED = (
        "Maximum concurrent sessions ({limit}) reached for {provider}.\n"
        "Close existing sessions or upgrade your plan."
    )

    # Resource errors
    OUT_OF_MEMORY = (
        "Insufficient memory to process request.\n"
        "Request size: {request_size}, Available: {available}\n"
        "Try reducing the request size or freeing up memory."
    )

    DISK_SPACE_LOW = (
        "Insufficient disk space for operation.\n"
        "Required: {required}, Available: {available}\n"
        "Free up disk space and try again."
    )

    # Input validation errors
    PROMPT_TOO_LONG = (
        "Prompt exceeds maximum length for {provider}.\n"
        "Current: {current} tokens, Maximum: {maximum}\n"
        "Reduce prompt size or use a model with larger context."
    )

    INVALID_PARAMETERS = (
        "Invalid parameters for {provider}.\n"
        "{details}\n"
        "Check the documentation for valid parameter values."
    )

    # File operation errors
    FILE_ACCESS_DENIED = (
        "Access denied to file: {path}\n" "Check file permissions and ownership."
    )

    FILE_NOT_FOUND = "File not found: {path}\n" "Verify the file path and try again."

    FILE_OPERATION_FAILED = (
        "File operation '{operation}' failed.\n" "Path: {path}\n" "Reason: {reason}"
    )

    # Fallback messages
    FALLBACK_INITIATED = (
        "Primary provider {primary} failed.\n"
        "Switching to fallback provider: {fallback}"
    )

    NO_FALLBACK_AVAILABLE = (
        "All providers have failed.\n"
        "Attempted providers: {providers}\n"
        "Check your configuration and provider status."
    )

    # Recovery messages
    PROVIDER_RECOVERED = "Provider {provider} has recovered and is operational."

    RETRYING_REQUEST = (
        "Retrying request to {provider}.\n" "Attempt {attempt}/{max_attempts}"
    )

    # Generic messages
    UNKNOWN_ERROR = (
        "An unexpected error occurred with {provider}.\n"
        "Error: {error}\n"
        "Check logs for more details."
    )

    PROVIDER_UNAVAILABLE = (
        "{provider} is currently unavailable.\n"
        "Status: {status}\n"
        "Try again later or use an alternative provider."
    )

    @classmethod
    def format(cls, message_key: str, **kwargs) -> str:
        """Format an error message with provided values.

        Args:
            message_key: Key of the message template
            **kwargs: Values to format into the message

        Returns:
            Formatted error message

        """
        message_template = getattr(cls, message_key, cls.UNKNOWN_ERROR)
        try:
            return message_template.format(**kwargs)
        except KeyError as e:
            return f"Error formatting message: missing key {e}"

    @classmethod
    def get_help_url(cls, provider: str, error_type: str) -> Optional[str]:
        """Get help URL for specific error type.

        Args:
            provider: Provider name
            error_type: Type of error

        Returns:
            Help URL if available

        """
        help_urls = {
            "venice": {
                "api_key": "https://venice.ai/docs/api-keys",
                "models": "https://venice.ai/docs/models",
                "limits": "https://venice.ai/docs/rate-limits",
            },
            "anthropic": {
                "api_key": "https://console.anthropic.com/api-keys",
                "models": "https://docs.anthropic.com/models",
                "limits": "https://docs.anthropic.com/rate-limits",
            },
            "openai": {
                "api_key": "https://platform.openai.com/api-keys",
                "models": "https://platform.openai.com/docs/models",
                "limits": "https://platform.openai.com/docs/rate-limits",
            },
        }

        provider_urls = help_urls.get(provider, {})
        return provider_urls.get(error_type)

    @classmethod
    def get_install_command(cls, dependency: str) -> str:
        """Get installation command for a dependency.

        Args:
            dependency: Dependency name

        Returns:
            Installation command

        """
        install_commands = {
            "tmux": "sudo apt-get install tmux",
            "openai": "pip install openai",
            "anthropic": "pip install anthropic",
            "aiohttp": "pip install aiohttp",
            "requests": "pip install requests",
            "pydantic": "pip install pydantic",
        }

        return install_commands.get(dependency, f"pip install {dependency}")

    @classmethod
    def get_env_var(cls, provider: str) -> str:
        """Get environment variable name for provider API key.

        Args:
            provider: Provider name

        Returns:
            Environment variable name

        """
        env_vars = {
            "venice": "VENICE_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "claude_tmux": "CLAUDE_CLI_PATH",
        }

        return env_vars.get(provider, f"{provider.upper()}_API_KEY")


class ProviderHints:
    """Helpful hints for resolving provider issues."""

    HINTS = {
        "rate_limit": [
            "Space out your requests with delays",
            "Use exponential backoff for retries",
            "Consider caching responses when possible",
            "Upgrade to a higher tier for increased limits",
        ],
        "timeout": [
            "Increase the timeout value in configuration",
            "Check if the provider service is operational",
            "Try using a simpler or shorter prompt",
            "Consider using a faster model variant",
        ],
        "authentication": [
            "Verify your API key is correctly set",
            "Check if the key has expired or been revoked",
            "Ensure you're using the correct environment variable",
            "Confirm your account has necessary permissions",
        ],
        "model_access": [
            "Check if the model requires special access",
            "Verify your account tier supports this model",
            "Try using an alternative model",
            "Contact support for access requests",
        ],
        "network": [
            "Check your internet connection",
            "Verify firewall and proxy settings",
            "Try using a different network",
            "Check if the service is down",
        ],
    }

    @classmethod
    def get_hints(cls, error_type: str) -> list[str]:
        """Get hints for resolving an error type.

        Args:
            error_type: Type of error

        Returns:
            List of helpful hints

        """
        return cls.HINTS.get(error_type, [])


def format_error_with_hints(message: str, error_type: str, provider: str) -> str:
    """Format error message with helpful hints.

    Args:
        message: Base error message
        error_type: Type of error for hints
        provider: Provider name

    Returns:
        Formatted message with hints

    """
    lines = [message]

    # Add hints if available
    hints = ProviderHints.get_hints(error_type)
    if hints:
        lines.append("\nSuggestions:")
        for i, hint in enumerate(hints, 1):
            lines.append(f"  {i}. {hint}")

    # Add help URL if available
    help_url = ErrorMessages.get_help_url(provider, error_type)
    if help_url:
        lines.append(f"\nFor more help: {help_url}")

    return "\n".join(lines)
