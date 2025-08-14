# Hydra Safety Guards Documentation

## Overview

The Hydra safety system provides comprehensive protection against potentially dangerous operations, including unauthorized file access, malicious git commands, and destructive system operations. The system consists of five main components working together to ensure secure execution of agent tasks.

## Components

### 1. GitGuard

**Purpose**: Protects against unauthorized git configuration modifications and dangerous git operations.

**Key Features**:
- Blocks modifications to git user configuration
- Prevents dangerous operations like force push and hard reset
- Validates remote URLs to prevent local file access
- Detects suspicious patterns in git hooks
- Supports strict and permissive modes

**Usage**:
```python
from hydra.safety.git_guard import GitGuard

guard = GitGuard(strict_mode=True)
allowed, error = guard.validate_git_command("git config user.name 'New Name'")
# Returns: (False, "Git configuration modification blocked...")
```

**Blocked Operations**:
- Git config modifications (user, credential, proxy settings)
- Force pushes (`git push --force`)
- Hard resets (`git reset --hard`)
- Aggressive cleans (`git clean -xdf`)
- Filter-branch operations

### 2. FileGuard

**Purpose**: Protects sensitive files and directories from unauthorized access.

**Key Features**:
- Blocks access to environment files (.env, .env.*)
- Protects security-sensitive files (keys, certificates, passwords)
- Prevents modifications to system directories
- Validates symbolic links for safety
- Scans directories for sensitive files

**Usage**:
```python
from hydra.safety.file_guard import FileGuard

guard = FileGuard(project_root=Path("/project"))
allowed, error = guard.validate_file_access(".env", "write")
# Returns: (False, "Access to protected file denied...")
```

**Protected Patterns**:
- Environment files: `.env`, `.env.local`, `.env.production`
- Private keys: `.pem`, `.key`, `id_rsa`, `id_dsa`
- Certificates: `.crt`, `.p12`, `.pfx`
- Password databases: `.kdbx`, `.keystore`
- Version control: `.git/`, `.svn/`, `.hg/`
- Cloud credentials: `.aws/`, `.azure/`, `.kube/`

### 3. OperationValidator

**Purpose**: Provides flexible whitelist/blacklist validation for operations.

**Key Features**:
- Configurable whitelist and blacklist rules
- Priority-based rule evaluation
- Support for multiple operation types
- JSON configuration import/export
- Batch validation support

**Usage**:
```python
from hydra.safety.operation_validator import OperationValidator, OperationType

validator = OperationValidator(default_allow=False)
allowed, reason, rule = validator.validate_operation(
    OperationType.FILE_WRITE,
    "/tmp/safe_file.txt"
)
```

**Operation Types**:
- `FILE_READ`: Reading file contents
- `FILE_WRITE`: Writing or modifying files
- `FILE_DELETE`: Deleting files
- `COMMAND_EXECUTE`: Running shell commands
- `NETWORK_REQUEST`: Making network requests
- `DATABASE_QUERY`: Executing database queries
- `API_CALL`: Making API calls

### 4. RateLimiter

**Purpose**: Prevents rapid execution of destructive commands through rate limiting.

**Key Features**:
- Command categorization (safe, moderate, destructive, critical)
- Configurable rate limits per category
- Burst protection
- Cooldown periods after limit reached
- Adaptive limits based on success rates

**Usage**:
```python
from hydra.safety.rate_limiter import RateLimiter

limiter = RateLimiter()
allowed, reason, retry_after = limiter.check_rate_limit(
    identifier="user_123",
    command="rm -rf directory"
)
```

**Default Rate Limits**:

| Category | Max Operations/Min | Burst Limit | Cooldown |
|----------|-------------------|-------------|----------|
| Safe | 1000 | 100 | 0s |
| Moderate | 100 | 20 | 5s |
| Destructive | 10 | 3 | 30s |
| Critical | 3 per 5min | 1 | 60s |

### 5. FileSandbox

**Purpose**: Provides a sandboxed environment for file operations with validation and rollback.

**Key Features**:
- Automatic backup before modifications
- Transaction-style rollback on failure
- File size and extension validation
- Integration with FileGuard and OperationValidator
- Operation history tracking

**Usage**:
```python
from hydra.safety.sandbox import FileSandbox

sandbox = FileSandbox(enable_backups=True)

with sandbox.sandboxed_operation("update config"):
    sandbox.write_file(Path("config.json"), new_config)
    # Automatic rollback if exception occurs
```

## Configuration

### Environment Variables

```bash
# Enable/disable safety features
HYDRA_SAFETY_ENABLED=true
HYDRA_SAFETY_STRICT_MODE=true

# Rate limiting
HYDRA_RATE_LIMIT_ENABLED=true
HYDRA_RATE_LIMIT_LOG_VIOLATIONS=true

# File operations
HYDRA_MAX_FILE_SIZE=104857600  # 100MB
HYDRA_SANDBOX_ROOT=/tmp/hydra_sandbox
```

### JSON Configuration

Create a `safety_config.json` file:

```json
{
  "default_allow": false,
  "whitelist": [
    {
      "pattern": "^/project/.*\\.py$",
      "operation_types": ["file_read", "file_write"],
      "description": "Allow Python files in project",
      "priority": 10
    }
  ],
  "blacklist": [
    {
      "pattern": ".*\\.exe$",
      "operation_types": ["file_write", "command_execute"],
      "description": "Block executable files",
      "priority": 20
    }
  ]
}
```

## Integration

### With Hydra Agents

```python
from hydra.safety import FileGuard, GitGuard, RateLimiter

class SafeAgent:
    def __init__(self):
        self.file_guard = FileGuard()
        self.git_guard = GitGuard(strict_mode=True)
        self.rate_limiter = RateLimiter()
    
    def execute_command(self, command: str) -> bool:
        # Check rate limits
        allowed, reason, _ = self.rate_limiter.check_rate_limit(
            self.agent_id, command=command
        )
        if not allowed:
            raise Exception(f"Rate limited: {reason}")
        
        # Validate git commands
        if command.startswith("git "):
            allowed, error = self.git_guard.validate_git_command(command)
            if not allowed:
                raise Exception(f"Git command blocked: {error}")
        
        # Execute command...
        return True
```

### With File Operations

```python
from hydra.safety import FileSandbox

def update_project_files(files_to_update):
    sandbox = FileSandbox(enable_backups=True)
    
    try:
        with sandbox.sandboxed_operation("batch update"):
            for file_path, content in files_to_update.items():
                success, error = sandbox.write_file(
                    Path(file_path), content
                )
                if not success:
                    raise Exception(f"Failed to update {file_path}: {error}")
            
            # All updates successful
            return True
    except Exception as e:
        # Automatic rollback occurred
        logger.error(f"Update failed: {e}")
        return False
```

## Security Best Practices

### 1. Defense in Depth

Use multiple layers of protection:
- FileGuard for path validation
- OperationValidator for operation filtering
- RateLimiter for frequency control
- FileSandbox for execution isolation

### 2. Principle of Least Privilege

- Start with `default_allow=False` in OperationValidator
- Use strict mode in GitGuard
- Explicitly whitelist required operations

### 3. Audit and Monitoring

```python
# Enable detailed logging
limiter = RateLimiter(enable_logging=True)

# Track operation statistics
stats = validator.get_statistics()
logger.info(f"Operations blocked: {stats['blocked_count']}")

# Export rules for review
validator.export_rules(Path("current_rules.json"))
```

### 4. Regular Updates

- Review and update protection patterns regularly
- Monitor for new attack vectors
- Adjust rate limits based on usage patterns

## Troubleshooting

### Common Issues

**Issue**: Legitimate operations being blocked
**Solution**: Review logs, adjust whitelist rules or priorities

**Issue**: Rate limiting too restrictive
**Solution**: Customize rate limit configurations per category

**Issue**: Backup storage growing large
**Solution**: Implement periodic cleanup of old backups

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger("hydra.safety").setLevel(logging.DEBUG)
```

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/test_safety_guards.py -v
```

Key test areas:
- Git command validation
- File access control
- Rate limiting behavior
- Sandbox rollback functionality
- Operation validation rules

## Performance Considerations

- **Regex Compilation**: Patterns are pre-compiled for efficiency
- **Caching**: Validation results can be cached for repeated operations
- **Batch Operations**: Use batch validation for multiple operations
- **Cleanup**: Regularly clean up backup files and operation history

## Future Enhancements

Planned improvements:
- Machine learning-based anomaly detection
- Network request validation
- Database query sanitization
- Container/VM-based isolation
- Real-time threat intelligence integration