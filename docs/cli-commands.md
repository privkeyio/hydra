# Hydra CLI Commands Documentation

## Overview

The Hydra CLI provides comprehensive commands for multi-agent code generation, ticket management, and provider interaction. The CLI has been refactored into modular commands for better organization and maintainability.

## Global Options

All Hydra commands support these global options:

```bash
hydra [global-options] <command> [command-options]
```

### Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `--provider <name>` | Override default provider | From config/env |
| `--model <name>` | Override default model | Provider default |
| `--timeout <seconds>` | Request timeout | 300 |
| `--debug` | Enable debug output | false |
| `--config <path>` | Custom config file | ~/.hydra/config.yaml |
| `--no-cache` | Disable response caching | false |
| `--json` | Output in JSON format | false |

## Available Commands

- `ticket` - Ticket workflow operations (create, execute, run-all, auto)
- `parallel` - Execute tickets in parallel with dependency resolution
- `batch` - Execute tickets in optimized batches
- `verify` - Verify ticket completion and acceptance criteria
- `quality` - Run quality gates on ticket implementation
- `verify-parallel` - Verify results from parallel execution
- `claude` - Claude-specific session management
- `context` - Manage shared context between tickets
- `template` - Project template operations
- `run` - Direct execution commands

## Core Commands

### `hydra ticket`

Manage tickets for multi-agent execution.

```bash
hydra ticket <subcommand> [options]
```

#### Subcommands

- `create` - Generate tickets from project description
- `execute` - Execute a single ticket
- `run-all` - Execute all tickets with dependency resolution
- `auto` - Automated workflow with parallel execution

#### Examples

```bash
# Create tickets from description
hydra ticket create "Build a REST API with authentication" --output tickets.yaml

# Execute single ticket
hydra ticket execute tickets.yaml 001

# Run all tickets
hydra ticket run-all tickets.yaml --max-parallel 4

# Auto workflow
hydra ticket auto tickets.yaml --workers 4
```

### `hydra parallel`

Execute tickets in parallel with smart dependency resolution.

```bash
hydra parallel [options] <tickets_file>
```

#### Options

- `--workers <n>` - Number of parallel workers (default: 3)
- `--save-log` - Save execution log
- `--skip-preflight` - Skip preflight checks
- `--async` - Use async execution mode

#### Examples

```bash
# Execute with 4 workers
hydra ticket parallel tickets.yaml --workers 4

# Async mode with logging
hydra ticket parallel tickets.yaml --async --save-log
```

### `hydra verify`

Verify ticket completion and acceptance criteria.

```bash
hydra verify <tickets_file> <ticket_id> [options]
```

#### Options

- `--report` - Generate detailed report
- `--save` - Save verification report

### `hydra quality`

Run quality gates on ticket implementation.

```bash
hydra quality <ticket_id> [options]
```

#### Options

- `--strict` - Fail on warnings
- `--save` - Save quality report

### `hydra verify-parallel`

Verify results from parallel execution.

```bash
hydra refactor [options] <file> <instructions>
```

#### Options

- `--backup` - Create backup before refactoring
- `--dry-run` - Show changes without applying
- `--interactive` - Confirm each change
- `--preserve-style` - Maintain existing code style

#### Examples

```bash
# Refactor with default provider
hydra refactor src/main.py "Convert to async/await pattern"

# Use specific provider for refactoring
hydra refactor --provider claude --model opus \
  src/database.js "Add connection pooling"

# Dry run to preview changes
hydra refactor --dry-run src/api.py \
  "Split into smaller functions"
```

### `hydra explain`

Get explanations of code or errors.

```bash
hydra explain [options] <file-or-error>
```

#### Options

- `--detail <level>` - Detail level (brief, normal, verbose)
- `--focus <aspect>` - Focus area (logic, performance, security)
- `--examples` - Include usage examples

#### Examples

```bash
# Explain code file
hydra explain src/algorithm.py

# Explain error with Venice provider
hydra explain --provider venice "TypeError: cannot read property 'x' of undefined"

# Detailed security explanation
hydra explain --detail verbose --focus security auth.py
```

## Ticket Management

### `hydra ticket create`

Create a new ticket with provider-aware model selection.

```bash
hydra ticket create [options] <description>
```

#### Options

- `--model <name>` - Model for this ticket
- `--priority <level>` - Priority (low, medium, high)
- `--deps <ids>` - Comma-separated dependency IDs
- `--file <path>` - Ticket file (default: tickets.yaml)

#### Examples

```bash
# Create ticket with auto-selected model
hydra ticket create "Implement user authentication"

# Specify model for complex task
hydra ticket create --model smart \
  "Design and implement microservices architecture"

# Create with dependencies
hydra ticket create --deps "001,002" \
  "Integration testing for auth system"
```

### `hydra ticket execute`

Execute a specific ticket using the configured provider.

```bash
hydra ticket execute [options] <ticket-id>
```

#### Options

- `--tickets <file>` - Ticket file path
- `--cwd <path>` - Working directory
- `--verify` - Verify after execution
- `--no-commit` - Skip auto-commit

#### Examples

```bash
# Execute with default provider
hydra ticket execute 001

# Use specific provider for execution
hydra ticket execute --provider venice 002 \
  --tickets project-tickets.yaml

# Execute with verification
hydra ticket execute --verify 003
```

### `hydra ticket parallel`

Execute multiple tickets in parallel using multiple providers.

```bash
hydra ticket parallel [options]
```

#### Options

- `--tickets <file>` - Ticket file path
- `--workers <n>` - Number of parallel workers
- `--filter <status>` - Filter by status (TODO, IN_PROGRESS)
- `--provider-pool <list>` - Comma-separated provider list

#### Examples

```bash
# Parallel execution with default provider
hydra ticket parallel --workers 4

# Use multiple providers for load balancing
hydra ticket parallel --workers 3 \
  --provider-pool "claude,venice,claude"

# Execute only TODO tickets
hydra ticket parallel --filter TODO --workers 2
```

### `hydra ticket verify`

Verify ticket completion using the configured provider.

```bash
hydra ticket verify [options] <ticket-id>
```

#### Options

- `--tickets <file>` - Ticket file path
- `--criteria <type>` - Verification criteria (acceptance, code, tests)
- `--fix` - Attempt to fix issues

#### Examples

```bash
# Verify with default provider
hydra ticket verify 001

# Use specific provider for verification
hydra ticket verify --provider claude --model opus 002

# Verify and fix issues
hydra ticket verify --fix 003
```

## Provider Management

### `hydra provider list`

List all available providers and their status.

```bash
hydra provider list [options]
```

#### Options

- `--verbose` - Show detailed information
- `--check` - Check provider availability

#### Examples

```bash
# List providers
hydra provider list

# Detailed listing with availability check
hydra provider list --verbose --check
```

#### Output Example

```
Available Providers:
  claude (default)
    Status: ✓ Active
    Models: opus, sonnet, haiku
    Features: interactive, streaming, sessions
    
  venice
    Status: ✓ Configured
    Models: llama-3.1-8b, llama-3.1-70b, llama-3.1-405b
    Features: streaming, parallel
    
  mock
    Status: ✓ Available
    Models: test
    Features: testing
```

### `hydra provider test`

Test provider configuration and connectivity.

```bash
hydra provider test [options] [provider-name]
```

#### Options

- `--full` - Run comprehensive tests
- `--benchmark` - Include performance benchmarks

#### Examples

```bash
# Test default provider
hydra provider test

# Test specific provider
hydra provider test venice

# Full test with benchmarks
hydra provider test --full --benchmark claude
```

### `hydra provider config`

View or modify provider configuration.

```bash
hydra provider config [options] <action> [provider-name]
```

#### Actions

- `show` - Display configuration
- `set` - Set configuration value
- `validate` - Validate configuration

#### Examples

```bash
# Show Venice configuration
hydra provider config show venice

# Set default model
hydra provider config set venice default_model llama-3.1-405b

# Validate all configurations
hydra provider config validate
```

## Model Management

### `hydra model list`

List available models for a provider.

```bash
hydra model list [options] [provider-name]
```

#### Options

- `--category <type>` - Filter by category (fast, balanced, smart)
- `--features <list>` - Required features

#### Examples

```bash
# List models for default provider
hydra model list

# List Venice models
hydra model list venice

# Find fast models with streaming
hydra model list --category fast --features streaming
```

### `hydra model select`

Select a model for the current session.

```bash
hydra model select [options] <model-identifier>
```

#### Examples

```bash
# Select model for default provider
hydra model select opus

# Select Venice model
hydra model select --provider venice llama-3.1-70b
```

### `hydra model info`

Get detailed information about a model.

```bash
hydra model info [options] <model-identifier>
```

#### Examples

```bash
# Get model information
hydra model info opus

# Venice model details
hydra model info --provider venice llama-3.1-405b
```

## Session Management

### `hydra session list`

List active provider sessions.

```bash
hydra session list [options]
```

#### Options

- `--provider <name>` - Filter by provider
- `--all` - Include terminated sessions

#### Examples

```bash
# List all active sessions
hydra session list

# List Claude sessions only
hydra session list --provider claude
```

### `hydra session attach`

Attach to an existing provider session.

```bash
hydra session attach [options] <session-id>
```

#### Examples

```bash
# Attach to session
hydra session attach hydra_claude_abc123

# Attach with specific provider
hydra session attach --provider claude session_001
```

### `hydra session kill`

Terminate a provider session.

```bash
hydra session kill [options] <session-id>
```

#### Options

- `--force` - Force termination
- `--all` - Kill all sessions

#### Examples

```bash
# Kill specific session
hydra session kill hydra_claude_abc123

# Kill all sessions
hydra session kill --all

# Force kill
hydra session kill --force stuck_session
```

## Utility Commands

### `hydra config`

Manage Hydra configuration.

```bash
hydra config [options] <action>
```

#### Actions

- `init` - Initialize configuration
- `show` - Display current configuration
- `edit` - Open configuration in editor
- `verify` - Verify configuration validity

#### Examples

```bash
# Initialize configuration
hydra config init

# Show current configuration
hydra config show

# Verify configuration
hydra config verify
```

### `hydra health`

Check system health and provider status.

```bash
hydra health [options]
```

#### Options

- `--provider <name>` - Check specific provider
- `--all` - Check all providers
- `--verbose` - Detailed output

#### Examples

```bash
# Quick health check
hydra health

# Check all providers
hydra health --all --verbose
```

### `hydra cache`

Manage response cache.

```bash
hydra cache [options] <action>
```

#### Actions

- `clear` - Clear cache
- `stats` - Show cache statistics
- `list` - List cached items

#### Examples

```bash
# Clear all cache
hydra cache clear

# Clear provider-specific cache
hydra cache clear --provider venice

# View cache statistics
hydra cache stats
```

## Interactive Mode

### `hydra interactive`

Start an interactive session with the selected provider.

```bash
hydra interactive [options]
```

#### Options

- `--provider <name>` - Provider to use
- `--model <name>` - Model to use
- `--mode <type>` - Interaction mode (chat, code, debug)

#### Examples

```bash
# Start interactive session with default provider
hydra interactive

# Interactive Claude session with opus model
hydra interactive --provider claude --model opus

# Code-focused interactive mode
hydra interactive --mode code
```

#### Interactive Commands

Once in interactive mode:

- `/model <name>` - Switch model
- `/provider <name>` - Switch provider
- `/context <file>` - Add file to context
- `/clear` - Clear context
- `/save <file>` - Save conversation
- `/exit` - Exit interactive mode

## Environment Variables

Configure Hydra through environment variables:

```bash
# Provider selection
export LLM_PROVIDER=venice
export LLM_MODEL=llama-3.1-70b

# Provider-specific
export VENICE_API_KEY=your_key
export CLAUDE_CLI_PATH=/usr/local/bin/claude

# General settings
export HYDRA_TIMEOUT=600
export HYDRA_CACHE_DIR=~/.hydra/cache
export HYDRA_DEBUG=true

# Run with environment configuration
hydra generate "Create a web server"
```

## Configuration Files

### Project Configuration

Create `.hydra.yaml` in your project:

```yaml
# .hydra.yaml
provider: venice
model: llama-3.1-70b
context:
  - src/
  - tests/
style: documented
language: python
```

### Global Configuration

Edit `~/.hydra/config.yaml`:

```yaml
# Global Hydra configuration
default_provider: claude
providers:
  claude:
    default_model: opus
  venice:
    default_model: llama-3.1-70b
    
preferences:
  auto_commit: false
  verify_after_execute: true
  cache_responses: true
```

## Examples

### Multi-Provider Workflow

```bash
# Use Claude for complex architecture design
hydra generate --provider claude --model opus \
  "Design a scalable microservices architecture"

# Use Venice for quick code generation
hydra generate --provider venice --model llama-3.1-8b \
  "Write unit tests for user.py"

# Execute tickets with provider pool
hydra ticket parallel --provider-pool "claude,venice,claude" \
  --workers 3
```

### Provider Fallback

```bash
# Configure fallback in environment
export LLM_PROVIDER=claude
export LLM_FALLBACK_PROVIDERS=venice,mock

# Hydra will automatically fall back if Claude fails
hydra generate "Create a REST API"
```

### Batch Processing

```bash
# Process multiple files with different providers
for file in src/*.py; do
  hydra explain --provider venice "$file" > "docs/$(basename $file .py).md"
done

# Parallel ticket execution with multiple providers
hydra ticket parallel --workers 4 \
  --provider-pool "claude,claude,venice,venice"
```

## Troubleshooting

### Provider Not Found

```bash
# Check available providers
hydra provider list

# Verify provider configuration
hydra provider config validate venice
```

### Authentication Issues

```bash
# Test provider authentication
hydra provider test claude

# Check environment variables
env | grep -E "(LLM_|CLAUDE_|VENICE_)"
```

### Model Not Available

```bash
# List available models
hydra model list venice

# Use model mapping
hydra generate --model balanced "Create a function"
```

### Performance Issues

```bash
# Run provider benchmark
hydra provider test --benchmark

# Use faster model
hydra generate --model fast "Quick code generation"

# Enable caching
export HYDRA_CACHE_ENABLED=true
```

## Best Practices

1. **Set default provider**: Configure your preferred provider in `~/.hydra/config.yaml`
2. **Use model categories**: Use `fast`, `balanced`, `smart` for provider-agnostic code
3. **Configure fallbacks**: Set up fallback providers for reliability
4. **Cache responses**: Enable caching for repeated queries
5. **Use appropriate models**: Choose fast models for simple tasks, smart models for complex ones
6. **Parallel execution**: Use provider pools for parallel ticket execution
7. **Monitor usage**: Track token usage and costs with `hydra stats`

## Migration Guide

If you're migrating from old Claude-specific commands:

### Old Command → New Command

```bash
# Old
hydra claude generate "code"

# New
hydra generate --provider claude "code"
```

```bash
# Old (hardcoded model)
hydra ticket create --model opus

# New (provider-aware)
hydra ticket create --model smart
```

```bash
# Old (Claude-only parallel)
hydra ticket parallel --workers 3

# New (multi-provider parallel)
hydra ticket parallel --workers 3 --provider-pool "claude,venice,claude"
```

See the [Migration Guide](providers/migration.md) for complete details.