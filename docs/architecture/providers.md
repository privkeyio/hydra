# Provider Architecture Documentation

## Overview

The Hydra provider architecture has been consolidated into a unified, extensible system that eliminates code duplication and provides a consistent interface for all LLM providers. This document describes the architecture, design decisions, and usage patterns.

## Architecture Components

### 1. Base Provider Interface (`base_provider.py`)

The `BaseProvider` class defines the comprehensive interface that all providers must implement:

```python
class BaseProvider(LLMProvider):
    """Extended abstract base class for all LLM providers."""
    
    # Core generation methods
    def generate(prompt: str, **kwargs) -> str
    def generate_code(prompt: str, context: Dict, **kwargs) -> str
    def generate_streaming(prompt: str, **kwargs) -> Iterator[str]
    
    # Session management
    def create_session(session_id: str, **kwargs) -> Session
    def attach_session(session_id: str) -> Session
    def list_sessions() -> List[Session]
    def kill_session(session_id: str) -> bool
    
    # Model management
    def list_models() -> List[ModelInfo]
    def select_model(model_identifier: str) -> bool
    def get_model_mapping() -> Dict[str, str]
    
    # Output handling
    def parse_response(response: str) -> ParsedResponse
    def extract_code_blocks(response: str) -> List[CodeBlock]
    
    # Interactive features
    def supports_interactive() -> bool
    def wait_for_prompt(timeout: int) -> bool
    def send_interactive_command(command: str) -> Optional[str]
    
    # File operations
    def intercept_file_operation(operation: FileOperation) -> bool
    def supports_file_interception() -> bool
```

### 2. Unified Claude Provider (`claude_unified.py`)

Consolidates all Claude implementations (CLI, tmux, enhanced) into a single configurable provider:

- **Simple Mode**: Basic CLI execution for straightforward tasks
- **Tmux Mode**: Full interactive sessions with real-time streaming
- **Enhanced Mode**: Advanced features with file operation interception

Configuration example:
```python
# Simple mode
config = LLMConfig(
    provider_type="claude",
    model="smart",
    extra_params={"mode": "simple"}
)

# Tmux mode (interactive)
config = LLMConfig(
    provider_type="claude",
    model="smart",
    extra_params={
        "mode": "tmux",
        "tmux_timeout": 300
    }
)

# Enhanced mode
config = LLMConfig(
    provider_type="claude",
    model="smart",
    extra_params={
        "mode": "enhanced",
        "file_interception": True,
        "session_persistence": True
    }
)
```

### 3. Configuration Manager (`config_manager.py`)

Centralized configuration management with profiles:

```python
# Provider profiles stored in ~/.config/hydra/providers.json
{
    "profiles": {
        "claude_tmux": {
            "provider_type": "claude",
            "model": "smart",
            "extra_params": {
                "mode": "tmux",
                "tmux_timeout": 300
            },
            "priority": 3,
            "enabled": true
        },
        "openai_gpt4": {
            "provider_type": "openai",
            "model": "gpt-4-turbo-preview",
            "api_key": "***",
            "priority": 1,
            "enabled": true
        }
    },
    "default_profile": "claude_tmux",
    "fallback_chain": ["claude_tmux", "claude_enhanced", "openai_gpt4"]
}
```

### 4. Unified Factory (`unified_factory.py`)

Factory pattern for creating providers with intelligent selection:

```python
from hydra.providers.unified_factory import get_provider_factory

factory = get_provider_factory()

# Create specific provider
provider = factory.create_provider("claude_tmux")

# Create with fallback support
provider = factory.create_with_fallback("claude_tmux")

# Get best provider for task
provider = factory.get_best_provider_for_task(
    "interactive",
    context_window=100000
)
```

### 5. Migration Support (`migration.py`)

Backward compatibility and migration utilities:

```python
# Automatic migration of old configurations
from hydra.providers.migration import ProviderMigrator

old_config = {
    "provider": "claude_cli",
    "model": "sonnet",
    "claude_path": "/usr/local/bin/claude"
}

new_config = ProviderMigrator.migrate_config(old_config)
# Result: {"profile": "claude_simple", "model": "sonnet", ...}

# Legacy import compatibility
from hydra.providers.claude_cli import ClaudeCLIProvider  # Still works!
```

## Design Patterns

### 1. Strategy Pattern
Different provider implementations (Claude, OpenAI, Venice) implement the same interface, allowing runtime selection based on requirements.

### 2. Factory Pattern
The `UnifiedProviderFactory` handles provider instantiation with configuration management and caching.

### 3. Chain of Responsibility
Fallback chains ensure reliable provider availability even when primary providers fail.

### 4. Singleton Pattern
Configuration and factory instances are managed as singletons to ensure consistency.

### 5. Adapter Pattern
Legacy wrapper classes adapt old provider interfaces to the new architecture.

## Key Benefits

### 1. Code Consolidation
- Reduced from 2200+ lines across 3 Claude providers to ~800 lines in unified provider
- Eliminated duplicate session management, output parsing, and error handling code
- Shared utilities and common functionality

### 2. Configuration Flexibility
- Single configuration file for all providers
- Profile-based management with priorities
- Environment-specific configurations
- Easy switching between modes

### 3. Improved Reliability
- Automatic fallback chains
- Graceful degradation when providers fail
- Retry logic with exponential backoff
- Comprehensive error handling

### 4. Better Performance
- Provider instance caching
- Session reuse and pooling
- Optimized provider selection based on task requirements
- Reduced initialization overhead

### 5. Backward Compatibility
- Legacy imports continue to work
- Automatic configuration migration
- Deprecation warnings guide users to new patterns
- Zero breaking changes for existing code

## Usage Examples

### Basic Usage

```python
from hydra.providers.unified_factory import create_provider

# Use default profile
provider = create_provider()
response = provider.generate("Write a hello world program")
```

### Advanced Usage

```python
from hydra.providers.config_manager import get_config_manager
from hydra.providers.unified_factory import get_provider_factory

# Configure providers
config_manager = get_config_manager()
config_manager.set_default_profile("claude_enhanced")
config_manager.set_fallback_chain(["claude_tmux", "openai_gpt4"])

# Create factory
factory = get_provider_factory()

# Get best provider for specific task
provider = factory.get_best_provider_for_task(
    "code_generation",
    context_window=150000,
    file_interception=True
)

# Generate with context
response = provider.generate_code(
    "Implement a binary search tree",
    context={"language": "python", "style": "functional"}
)
```

### Interactive Session

```python
# Create interactive session
provider = create_provider("claude_tmux")
session = provider.create_session("dev_session")

# Send commands
provider.send_interactive_command("analyze main.py")
provider.wait_for_prompt(timeout=30)

# Stream responses
for chunk in provider.generate_streaming("Explain the code"):
    print(chunk, end="")
```

### Migration from Old Architecture

```python
# Old code (still works!)
from hydra.providers.claude_cli import ClaudeCLIProvider
provider = ClaudeCLIProvider(config)

# New code (recommended)
from hydra.providers.unified_factory import create_provider
provider = create_provider("claude_simple")
```

## Provider Capabilities Matrix

| Provider | Interactive | Streaming | File Intercept | Session Persist | Code Exec |
|----------|------------|-----------|----------------|-----------------|-----------|
| Claude Simple | ❌ | ❌ | ❌ | ❌ | ❌ |
| Claude Tmux | ✅ | ✅ | ❌ | ❌ | ❌ |
| Claude Enhanced | ❌ | ❌ | ✅ | ✅ | ❌ |
| OpenAI | ❌ | ✅ | ❌ | ❌ | ❌ |
| Venice | ❌ | ✅ | ❌ | ❌ | ❌ |
| Mock | ❌ | ❌ | ❌ | ❌ | ❌ |

## Configuration Reference

### Global Settings

```json
{
    "global_settings": {
        "timeout": 300,           // Default timeout in seconds
        "max_retries": 3,         // Maximum retry attempts
        "enable_telemetry": false,// Telemetry collection
        "cache_responses": true   // Response caching
    }
}
```

### Profile Configuration

```json
{
    "profiles": {
        "profile_name": {
            "provider_type": "claude|openai|venice|mock",
            "model": "model_identifier",
            "api_key": "optional_api_key",
            "base_url": "optional_base_url",
            "extra_params": {
                // Provider-specific parameters
            },
            "environment": {
                // Environment variables to set
            },
            "enabled": true,
            "priority": 0  // Higher = preferred
        }
    }
}
```

### Claude-Specific Parameters

```json
{
    "extra_params": {
        "mode": "simple|tmux|enhanced",
        "claude_path": "/path/to/claude",
        "tmux_timeout": 300,
        "max_retries": 3,
        "file_interception": true,
        "session_persistence": false
    }
}
```

## Testing

The consolidated architecture maintains full backward compatibility. All existing tests continue to pass with the migration layer:

```bash
# Run provider tests
pytest tests/unit/test_providers.py -v

# Test migration
pytest tests/unit/test_provider_migration.py -v

# Test backward compatibility
pytest tests/integration/test_legacy_providers.py -v
```

## Future Enhancements

1. **Async/Await Support**: Convert providers to async for better performance
2. **Plugin System**: Allow third-party provider plugins
3. **Advanced Caching**: Implement intelligent response caching
4. **Monitoring**: Add OpenTelemetry instrumentation
5. **Load Balancing**: Distribute requests across multiple provider instances
6. **Cost Optimization**: Automatic model selection based on cost constraints

## Migration Timeline

1. **Phase 1** (Current): New architecture available, full backward compatibility
2. **Phase 2**: Deprecation warnings for old imports
3. **Phase 3**: Remove legacy provider files (keep wrappers)
4. **Phase 4**: Full migration to new architecture

## Conclusion

The consolidated provider architecture provides a clean, extensible foundation for LLM integration in Hydra. It eliminates code duplication, improves reliability, and maintains full backward compatibility while offering advanced features like automatic fallback, task-based selection, and unified configuration management.