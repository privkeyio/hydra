# Prompt Versioning and Hot-Reload System

This document describes the advanced prompt versioning and hot-reload system implemented for Hydra. This system provides comprehensive version control, A/B testing, performance tracking, and optimization capabilities for prompt management.

## Features

### 1. Version Control
- **Version Creation**: Create and store prompt configurations with unique version IDs
- **Version Tracking**: Automatic timestamping and content hashing for version integrity
- **Rollback Capability**: Revert to any previous prompt version
- **Version Comparison**: Compare performance metrics between different versions

### 2. Hot-Reload Mechanism
- **File Watching**: Automatic monitoring of prompt configuration files
- **Real-time Updates**: Changes to prompt files trigger immediate reloads
- **Callback System**: Custom callbacks for handling file change events
- **Cooldown Protection**: Prevents excessive reloads with configurable cooldown periods

### 3. A/B Testing Framework
- **Variant Management**: Define multiple prompt variants for testing
- **Traffic Splitting**: Configurable traffic distribution between variants
- **Consistent Assignment**: Users get the same variant consistently across sessions
- **Performance Comparison**: Compare metrics between test variants

### 4. Performance Metrics Tracking
- **Execution Metrics**: Track execution time, success rates, and usage counts
- **Time-based Analysis**: Analyze performance over specific time windows
- **Variant Tracking**: Separate metrics for different prompt variants
- **Real-time Buffering**: Efficient metrics collection with configurable buffer sizes

### 5. Optimization Suggestions
- **Automated Analysis**: AI-powered optimization suggestions based on performance data
- **Severity Levels**: Categorized suggestions (high, medium, low severity)
- **Trend Detection**: Identify declining performance patterns
- **Actionable Recommendations**: Specific suggestions for improvement

## Architecture

### Core Components

#### PromptVersionManager
The main class responsible for version management, A/B testing, and performance tracking.

```python
from hydra.prompts.versioning import PromptVersionManager

manager = PromptVersionManager(
    db_path="/path/to/database.db",
    enable_hot_reload=True,
    watch_directories=["/path/to/prompts"]
)
```

#### Data Models

- **PromptVersionInfo**: Contains version metadata, content, and performance metrics
- **ABTestConfig**: Configuration for A/B test variants and traffic splitting
- **PromptMetrics**: Individual performance metrics for prompt executions

### Database Schema

The system uses SQLite for persistent storage with three main tables:

1. **prompt_versions**: Stores version content and performance metrics
2. **ab_tests**: Stores A/B test configurations
3. **prompt_metrics**: Stores individual execution metrics

## Usage Examples

### Basic Version Management

```python
from hydra.prompts.versioning import get_version_manager, create_prompt_version

# Create a new version
content = {
    "prompts": {
        "greeting": {
            "template": "Hello {name}, welcome to our service!",
            "variables": ["name"]
        }
    }
}

version_id = create_prompt_version(content, "v1.0")
print(f"Created version: {version_id}")

# List all versions
manager = get_version_manager()
versions = manager.list_versions()

# Rollback to a previous version
manager.rollback_to_version("v1.0")
```

### A/B Testing

```python
# Create A/B test
variants = {
    "control": "Hello {name}, welcome!",
    "friendly": "Hi {name}! 😊 Welcome!",
    "professional": "Good day {name}. Welcome to our platform."
}

manager.create_ab_test("greeting_test", variants)

# Get variant for a user
variant = manager.get_ab_test_variant("greeting_test", "user_123")
prompt_template = variants[variant]
```

### Performance Tracking

```python
from hydra.prompts.versioning import record_prompt_usage

# Record usage metrics
record_prompt_usage(
    prompt_name="greeting",
    execution_time=1.5,
    success=True,
    variant="friendly",
    metadata={"context": "homepage"}
)

# Get performance data
performance = manager.get_prompt_performance("greeting", "friendly")
print(f"Success rate: {performance['success_rate']:.1%}")
print(f"Avg execution time: {performance['avg_execution_time']:.2f}s")
```

### Hot-Reload Setup

```python
# Enable hot-reload with custom callback
def on_prompt_change(file_path):
    print(f"Prompt file changed: {file_path}")
    # Custom reload logic here

manager = PromptVersionManager(enable_hot_reload=True)
manager.add_reload_callback(on_prompt_change)
```

### Optimization Suggestions

```python
# Get optimization suggestions
suggestions = manager.get_optimization_suggestions("slow_prompt")

for suggestion in suggestions:
    print(f"[{suggestion['severity'].upper()}] {suggestion['type']}")
    print(f"  {suggestion['message']}")
    if 'metric_value' in suggestion:
        print(f"  Current value: {suggestion['metric_value']}")
```

## CLI Interface

The system includes a comprehensive CLI for management operations:

```bash
# Show system status
python -m hydra.prompts.cli status

# List versions
python -m hydra.prompts.cli list-versions --limit 10

# Create new version from file
python -m hydra.prompts.cli create-version --file prompts.json --version-id v2.0

# Show version details
python -m hydra.prompts.cli show-version v2.0

# Create A/B test
python -m hydra.prompts.cli create-ab-test test_001 \
  --variants '{"control": "Hello {name}", "test": "Hi {name}!"}' \
  --split '{"control": 0.6, "test": 0.4}'

# Get performance metrics
python -m hydra.prompts.cli performance greeting --variant control --days 7

# Get optimization suggestions
python -m hydra.prompts.cli suggestions slow_prompt

# Start file watcher
python -m hydra.prompts.cli watch --enable --directories /path/to/prompts
```

## Integration with Existing Systems

### Configuration Integration

The versioning system integrates with the existing `PromptConfigManager`:

```python
from hydra.prompts import get_config_manager
from hydra.prompts.versioning import get_version_manager

# Use both systems together
config_manager = get_config_manager()
version_manager = get_version_manager()

# Create version from current config
current_config = config_manager._config
version_id = version_manager.create_version(current_config)
```

### Provider Integration

Integrate with prompt providers to track usage automatically:

```python
class EnhancedProvider:
    def __init__(self):
        self.version_manager = get_version_manager()
    
    def execute_prompt(self, prompt_name, variant="default", **kwargs):
        start_time = time.time()
        try:
            result = self._execute(prompt_name, **kwargs)
            success = True
        except Exception:
            result = None
            success = False
        finally:
            execution_time = time.time() - start_time
            record_prompt_usage(
                prompt_name=prompt_name,
                execution_time=execution_time,
                success=success,
                variant=variant
            )
        
        return result
```

## Configuration

### Environment Variables

- `HYDRA_PROMPT_DB_PATH`: Custom database path
- `HYDRA_ENABLE_HOT_RELOAD`: Enable/disable hot-reload (default: true)
- `HYDRA_WATCH_DIRECTORIES`: Comma-separated list of directories to watch

### Configuration File

```yaml
versioning:
  database_path: "/custom/path/versions.db"
  hot_reload:
    enabled: true
    directories:
      - "/app/prompts"
      - "/app/templates"
    cooldown_seconds: 1.0
  metrics:
    buffer_size: 1000
    retention_days: 30
  ab_testing:
    default_traffic_split: "equal"
    max_variants: 5
```

## Performance Considerations

### Database Optimization

- Indexes on frequently queried columns (content_hash, timestamp, prompt_name)
- Configurable metrics buffer to reduce database writes
- Automatic cleanup of old metrics based on retention policy

### Memory Management

- Thread-safe operations with proper locking
- Efficient metrics buffering to minimize memory usage
- Cleanup methods to release resources properly

### Hot-Reload Efficiency

- Cooldown periods to prevent excessive reloads
- Selective file watching (only relevant file types)
- Asynchronous file event handling

## Security Considerations

### Data Protection

- Content hashing for integrity verification
- Safe handling of sensitive prompt data
- Configurable access controls for version management

### File System Security

- Restricted file watching to authorized directories
- Validation of file paths to prevent directory traversal
- Safe handling of file change events

## Testing

### Unit Tests

Comprehensive unit tests cover all functionality:

```bash
python -m pytest tests/unit/test_prompt_versioning.py -v
```

### Integration Tests

End-to-end tests verify system integration:

```bash
python -m pytest tests/integration/test_prompt_versioning_integration.py -v
```

### Example Usage

Run the example to see the system in action:

```bash
python examples/prompt_versioning_example.py
```

## Troubleshooting

### Common Issues

1. **Hot-reload not working**: Check if watchdog is installed and directories exist
2. **Performance issues**: Increase buffer size or reduce metrics retention
3. **Database errors**: Verify write permissions and disk space
4. **Inconsistent A/B tests**: Clear cache or restart application

### Debug Mode

Enable debug logging for troubleshooting:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

manager = PromptVersionManager(enable_hot_reload=True)
```

### Health Checks

Monitor system health:

```python
# Check system status
manager = get_version_manager()
print(f"Database path: {manager.db_path}")
print(f"Hot reload: {manager.enable_hot_reload}")
print(f"Metrics buffer: {len(manager._metrics_buffer)}")

# Verify database connectivity
versions = manager.list_versions(limit=1)
print(f"Database accessible: {len(versions) >= 0}")
```

## Future Enhancements

### Planned Features

1. **Distributed A/B Testing**: Multi-instance coordination
2. **Advanced Analytics**: Machine learning-based optimization
3. **Visual Dashboard**: Web interface for version management
4. **Export/Import**: Backup and restore functionality
5. **Integration APIs**: REST API for external systems

### Extensibility

The system is designed for extensibility:

- Plugin architecture for custom metrics
- Configurable optimization algorithms
- Custom database backends
- Integration hooks for external systems

## Contributing

When contributing to the versioning system:

1. Add comprehensive tests for new features
2. Update this documentation
3. Follow the existing code style and patterns
4. Consider performance implications
5. Test with various load scenarios

## License

This prompt versioning system is part of the Hydra project and follows the same licensing terms.