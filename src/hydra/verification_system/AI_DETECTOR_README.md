# AI Pattern Detector Module

## Overview

The AI Pattern Detector is a sophisticated module designed to identify AI-generated code patterns and ensure production-quality code. It scans source files for common patterns that indicate AI generation, such as placeholder text, excessive comments, emoji usage, and generic code structures.

## Features

### Core Detection Capabilities

1. **AI Code Pattern Detection**
   - Verbose variable names (e.g., `user_input_data_processor_manager`)
   - Generic function names (e.g., `handleSomethingError`)
   - Boilerplate structures
   - Deep nesting patterns

2. **AI Comment Detection**
   - Excessive commenting
   - AI-style phrasing ("Initialize", "Setup", "Process")
   - Step-by-step comments
   - Comments without punctuation

3. **Placeholder Detection**
   - TODO, FIXME, HACK markers
   - "Replace with", "Insert code here" patterns
   - Lorem ipsum text
   - Dummy/temp/sample identifiers

4. **Emoji Detection**
   - Comprehensive Unicode emoji detection
   - Configurable allowance
   - Support for all emoji ranges

5. **Exception Handling Analysis**
   - Generic exception handlers
   - Empty except blocks
   - Broad exception catching

6. **AST-Based Analysis** (Python)
   - Deep nesting detection
   - Function complexity analysis
   - Code structure patterns

### Configuration Options

- **Sensitivity Levels**: LOW, MEDIUM, HIGH, PARANOID
- **Whitelist Support**: Exclude specific patterns or files
- **Custom Patterns**: Add domain-specific patterns
- **Performance Optimization**: Parallel processing, caching
- **Flexible Thresholds**: Customizable scoring thresholds

## Installation

The AI detector is included with the Hydra verification system. No additional installation required.

## Usage

### Basic Usage

```python
from hydra.verification_system import AIDetector, AIPatternConfig

# Create detector with default settings
detector = AIDetector()

# Detect patterns in a file
result = detector.detect_file(Path("example.py"))
print(f"AI Score: {result.ai_score}")
print(f"Passes: {result.passes}")
```

### CLI Usage

```bash
# Scan a single file
python -m hydra.verification_system.ai_detector_cli file.py

# Scan directory with high sensitivity
python -m hydra.verification_system.ai_detector_cli src/ --sensitivity high

# Use configuration file
python -m hydra.verification_system.ai_detector_cli src/ --config ai_config.yaml

# Export detailed report
python -m hydra.verification_system.ai_detector_cli src/ --export report.json
```

### Configuration

#### Using Configuration File (YAML)

```yaml
sensitivity: medium
emoji_allowed: false
max_workers: 4

whitelist_patterns:
  - "TODO: Security review"
  - "FIXME: Known issue #\\d+"

custom_patterns:
  - category: company_specific
    pattern: "INTERNAL_MARKER"
    severity: high

thresholds:
  low: 0.7
  medium: 0.5
  high: 0.3
  paranoid: 0.1
```

#### Programmatic Configuration

```python
config = AIPatternConfig(
    sensitivity=SensitivityLevel.HIGH,
    emoji_allowed=False,
    whitelist_patterns={"TODO: URGENT"},
    custom_patterns=[
        {"category": "custom", "pattern": "MY_PATTERN"}
    ]
)

detector = AIDetector(config)
```

## Integration with Verification Engine

The AI detector seamlessly integrates with Hydra's verification engine:

```python
from hydra.verification_system import VerificationEngine, AIPatternConfig

# Create engine with AI detection
ai_config = AIPatternConfig(sensitivity=SensitivityLevel.HIGH)
engine = VerificationEngine(project_root, ai_config)

# Run comprehensive verification
result = engine.run_comprehensive_verification(
    ticket_file="tickets.yaml",
    ticket_id="001",
    check_ai_patterns=True
)
```

## Sensitivity Levels

| Level | Threshold | Description |
|-------|-----------|-------------|
| LOW | 0.7 | Permissive - only obvious AI patterns |
| MEDIUM | 0.5 | Balanced - moderate AI pattern detection |
| HIGH | 0.3 | Strict - subtle AI pattern detection |
| PARANOID | 0.1 | Very strict - any suspicious patterns |

## Pattern Categories

### High Severity
- Emoji usage in code
- Placeholder text (TODO, FIXME without context)
- Generic exception handlers
- Empty except blocks

### Medium Severity
- Excessive comments
- AI-style docstrings
- Deep nesting (>3 levels)
- AI comment phrases

### Low Severity
- Verbose variable names
- Boilerplate structures
- Generic function names

## Performance Optimization

The module includes several optimizations for large codebases:

1. **Parallel Processing**: Configurable worker threads
2. **Pattern Caching**: LRU cache for pattern matching
3. **Compiled Regex**: Pre-compiled patterns for speed
4. **Batch Processing**: Efficient directory scanning
5. **File Size Limits**: Skip very large files

## Report Generation

The detector generates comprehensive reports in multiple formats:

### JSON Report
```json
{
  "summary": {
    "total_files": 100,
    "passed": 85,
    "failed": 15,
    "average_ai_score": 0.35
  },
  "pattern_distribution": {
    "emoji": 5,
    "placeholder_text": 10,
    "ai_comments": 20
  },
  "recommendations": [
    "Remove 5 emoji occurrences from code",
    "Replace 10 placeholder text occurrences"
  ]
}
```

### Markdown Report
- Summary statistics
- Pattern distribution table
- Failed files list
- Actionable recommendations

### HTML Report
- Interactive visualization
- Color-coded results
- Detailed pattern breakdown

## Best Practices

1. **Start with MEDIUM sensitivity** and adjust based on results
2. **Use whitelist** for legitimate patterns in your codebase
3. **Add custom patterns** for domain-specific requirements
4. **Review failed files** before taking action
5. **Integrate into CI/CD** for continuous quality checks

## Troubleshooting

### High False Positive Rate
- Lower sensitivity level
- Add patterns to whitelist
- Adjust thresholds in configuration

### Missing AI Patterns
- Increase sensitivity level
- Add custom patterns
- Check file extensions are included

### Performance Issues
- Reduce max_workers for system constraints
- Exclude large directories (node_modules, etc.)
- Use file extension filtering

## Examples

See `examples/ai_detector_usage.py` for comprehensive usage examples including:
- Basic detection
- Sensitivity level comparison
- Whitelist configuration
- Directory scanning
- Verification engine integration
- Custom pattern detection

## API Reference

### Classes

#### AIDetector
Main detection engine class.

**Methods:**
- `detect_file(file_path: Path) -> DetectionResult`
- `detect_directory(directory: Path, extensions: Set[str]) -> List[DetectionResult]`
- `generate_report(results: List[DetectionResult]) -> Dict`
- `check_single_file(file_path: str) -> Tuple[bool, str]`
- `update_config(**kwargs)`

#### AIPatternConfig
Configuration dataclass for the detector.

**Fields:**
- `sensitivity: SensitivityLevel`
- `whitelist_patterns: Set[str]`
- `whitelist_files: Set[str]`
- `emoji_allowed: bool`
- `max_workers: int`
- `custom_patterns: List[Dict]`
- `thresholds: Dict[str, float]`

#### DetectionResult
Result dataclass for pattern detection.

**Fields:**
- `file_path: str`
- `detected_patterns: List[Dict]`
- `ai_score: float`
- `passes: bool`
- `sensitivity_level: SensitivityLevel`

## Contributing

To add new patterns or improve detection:

1. Add patterns to `AI_PATTERNS` dictionary
2. Update severity mapping in `_get_severity()`
3. Add tests in `test_ai_detector.py`
4. Update configuration schema if needed

## License

Part of the Hydra project. See main LICENSE file.