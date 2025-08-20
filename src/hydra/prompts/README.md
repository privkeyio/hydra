# Hydra Prompt Configuration System

The Hydra prompt configuration system provides a robust, centralized way to manage and customize prompts used throughout the system. It supports YAML-based configuration, environment variable overrides, provider-specific customization, versioning, hot-reload capability, and comprehensive validation.

## Configuration Files

### Primary Configuration
- **File**: `src/hydra/prompts/prompts.yaml`
- **Purpose**: Main YAML configuration file containing all prompt definitions
- **Format**: YAML with structured sections for prompts, provider overrides, and settings

### Python Interface
- **File**: `src/hydra/prompts/config.py`
- **Purpose**: Programmatic interface for prompt configuration management
- **Classes**: `PromptConfigManager`, `PromptConfig`, `PromptValidator`

## Prompt Variables Documentation

All prompts support variable substitution using Python's `str.format()` syntax with curly braces: `{variable_name}`.

### Core Prompt Variables

#### Ticket Generation Prompts
- **`description`** (string): Project description to generate tickets from
  - Example: "Build a web calculator with React and TypeScript"
  - Required: Yes
  - Used in: `ticket_generation` prompt

#### Ticket Execution Prompts
- **`ticket_id`** (string): Unique identifier for the ticket
  - Example: "001", "T-1234"
  - Required: Yes
  - Used in: `ticket_execution` prompt

- **`title`** (string): Human-readable title of the ticket
  - Example: "Implement user authentication system"
  - Required: Yes
  - Used in: `ticket_execution` prompt

- **`description`** (string): Detailed description of what needs to be implemented
  - Example: "Create login/logout functionality with JWT tokens"
  - Required: Yes
  - Used in: `ticket_execution` prompt

- **`criteria`** (string): Acceptance criteria for the ticket
  - Example: "[ ] Login form validates credentials\n[ ] JWT tokens are generated\n[ ] Logout clears session"
  - Required: Yes
  - Used in: `ticket_execution` prompt

#### Verification Prompts
- **`criteria`** (string): Acceptance criteria to verify against
  - Example: List of checkboxes that need to be validated
  - Required: Yes
  - Used in: `verification` prompt

- **`files`** (string): List of files created or modified
  - Example: "src/auth.py, tests/test_auth.py, docs/auth.md"
  - Required: Yes
  - Used in: `verification` prompt

- **`test_results`** (string): Results from running tests
  - Example: "All 15 tests passed, 95% coverage"
  - Required: Yes
  - Used in: `verification` prompt

#### Code Review Prompts
- **`code`** (string): Code content to review
  - Example: Multi-line string containing source code
  - Required: Yes
  - Used in: `code_review` prompt

- **`file_path`** (string): Path to the file being reviewed
  - Example: "src/components/Calculator.tsx"
  - Required: Yes
  - Used in: `code_review` prompt

#### Analysis Prompts
- **`description`** (string): Description to analyze for complexity
  - Example: "Implement real-time chat with WebSockets"
  - Required: Yes
  - Used in: `estimate_complexity` prompt

- **`dependencies`** (string): List of dependencies
  - Example: "Redis for session storage, Socket.io for WebSocket handling"
  - Required: Yes
  - Used in: `estimate_complexity` prompt

#### Production Quality Assessment
- **`code`** (string): Code to assess for production readiness
  - Example: Complete source code content
  - Required: Yes
  - Used in: `assess_production_quality` prompt

- **`test_coverage`** (string): Test coverage information
  - Example: "85% line coverage, 92% branch coverage"
  - Required: Yes
  - Used in: `assess_production_quality` prompt

### Provider-Specific Variables

Provider overrides can use any of the core variables but may have additional provider-specific variables:

#### Claude TMUX Provider
- All core variables supported
- Additional context about tmux session management

#### Venice Provider
- All core variables supported
- Additional context about Venice-specific execution patterns

#### Anthropic Provider
- All core variables supported
- Standard Anthropic API execution context

#### Mock Provider
- All core variables supported
- Testing-specific context and mock responses

## Configuration Structure

### YAML Configuration Format

```yaml
version: '1.0.0'
metadata:
  description: 'Configuration description'
  created: '2025-08-19T00:00:00'
  author: 'System'

prompts:
  prompt_name:
    template: 'Prompt template with {variables}'
    variables: ['list', 'of', 'required', 'variables']
    category: 'prompt_category'
    description: 'What this prompt does'
    version: '1.0.0'

provider_overrides:
  provider_name:
    prompt_name: 'Override template for specific provider'

settings:
  hot_reload: false
  validation_strict: true
  version_retention: 10
```

### Environment Variable Overrides

Environment variables can override prompt templates using the format:
`HYDRA_PROMPT_[PROMPT_NAME]`

Examples:
- `HYDRA_PROMPT_TICKET_EXECUTION`: Override ticket execution prompt
- `HYDRA_PROMPT_VERIFICATION`: Override verification prompt
- `HYDRA_PROMPT_CODE_REVIEW`: Override code review prompt

## Usage Examples

### Basic Prompt Retrieval
```python
from hydra.prompts.config import get_prompt

# Get a prompt with variables
prompt = get_prompt('ticket_execution', 
                   ticket_id='001',
                   title='Implement login',
                   description='Create user login system',
                   criteria='[ ] Login form works\n[ ] Session management')
```

### Provider-Specific Prompts
```python
# Get provider-specific override
prompt = get_prompt('ticket_execution', 
                   provider='claude_tmux',
                   ticket_id='001',
                   title='Implement login')
```

### Configuration Management
```python
from hydra.prompts.config import get_config_manager

config = get_config_manager()

# Add new prompt
config.add_prompt('custom_prompt',
                 'Custom template with {variable}',
                 variables=['variable'],
                 category='custom')

# Update existing prompt
config.update_prompt('ticket_execution',
                    template='New template')

# List available prompts
prompts = config.list_prompts()
```

### Validation
```python
# Validate variables before using prompt
missing = config.validate_prompt_variables('ticket_execution',
                                          ticket_id='001',
                                          title='Test')
if missing:
    print(f"Missing variables: {missing}")
```

## Hot-Reload Configuration

Enable hot-reload for development:

```python
config = get_config_manager(enable_hot_reload=True)

# Add callback for reload events
def on_reload(old_config, new_config):
    print("Configuration reloaded!")

config.add_reload_callback(on_reload)
```

## Versioning and Rollback

```python
# Get version history
versions = config.get_versions()

# Rollback to previous version
config.rollback_to_version('1.0.0')
```

## Validation Rules

The system validates:
1. **Required variables**: All variables listed in `variables` array must be present in template
2. **Undefined variables**: Template cannot contain variables not listed in `variables` array
3. **Template syntax**: Templates must use valid Python `str.format()` syntax
4. **Configuration structure**: YAML must contain required sections (`prompts`)
5. **Provider overrides**: Override templates must be valid

## Best Practices

1. **Variable Naming**: Use clear, descriptive variable names
2. **Documentation**: Include description for each prompt explaining its purpose
3. **Categorization**: Use appropriate categories to organize prompts
4. **Testing**: Test prompts with various input scenarios
5. **Versioning**: Update version numbers when making significant changes
6. **Provider Specificity**: Only override when provider needs different behavior

## Error Handling

The system provides detailed error messages for:
- Missing configuration files
- Invalid YAML syntax
- Template validation failures
- Missing required variables
- Provider override issues

## Security Considerations

- Template variables are not executed as code
- Environment variable overrides are sanitized
- File system access is controlled
- Configuration validation prevents injection attacks

## Integration Points

The prompt configuration system integrates with:
- **Ticket Workflow**: Provides execution and verification prompts
- **Provider System**: Supplies provider-specific prompt overrides
- **Verification Engine**: Delivers validation and review prompts
- **CLI Commands**: Supports command-line prompt customization