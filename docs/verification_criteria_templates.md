# Verification Criteria Templates Documentation

## Overview

The verification criteria templates system provides reusable verification criteria for common project types. This system ensures consistent quality checks across different types of software projects with configurable strictness levels.

## Strictness Levels

### LENIENT
- Basic functionality checks
- Minimal file requirements
- Suitable for prototypes and early development

### BALANCED (Default)
- Comprehensive functionality checks
- Standard file structure requirements
- Error handling validation
- Suitable for most production projects

### STRICT
- All BALANCED criteria plus:
- Additional documentation requirements
- Enhanced security checks
- Performance validation
- Type safety requirements
- Suitable for mission-critical applications

## Template Types

### 1. API Endpoint Template

**Purpose**: Validates REST API implementations

**File Structure Requirements**:
- `api.py` - Main API module
- `routes.py` - Route definitions
- `models.py` - Data models
- `test_api.py` - API tests

**Criteria Checked**:
- HTTP methods implementation (GET, POST, PUT, DELETE)
- Error handling presence
- Data model definitions
- Test coverage

**STRICT Mode Additions**:
- Input validation mechanisms
- Authentication implementation
- API documentation (`api_docs.md`)

**Usage**:
```python
from hydra.verification_system.criteria_templates import APIEndpointTemplate, StrictnessLevel

template = APIEndpointTemplate(StrictnessLevel.STRICT)
criteria = template.get_template()
```

### 2. CLI Tool Template

**Purpose**: Validates command-line interface implementations

**File Structure Requirements**:
- `cli.py` - Main CLI entry point

**Criteria Checked**:
- Argument parser implementation
- Help text availability
- Exit code handling
- Executable functionality

**STRICT Mode Additions**:
- Subcommand support
- Input validation
- CLI tests (`test_cli.py`)

**Usage**:
```python
from hydra.verification_system.criteria_templates import CLIToolTemplate

template = CLIToolTemplate(StrictnessLevel.BALANCED)
criteria = template.get_template()
```

### 3. Library Template

**Purpose**: Validates Python library implementations

**File Structure Requirements**:
- `__init__.py` - Main module
- `tests/test_main.py` - Test files

**Criteria Checked**:
- Core functionality implementation
- Docstring presence
- Package structure
- Test existence

**STRICT Mode Additions**:
- Type hints usage
- Setup file (`setup.py` or `pyproject.toml`)
- Documentation (`README.md`)

**Usage**:
```python
from hydra.verification_system.criteria_templates import LibraryTemplate

template = LibraryTemplate(StrictnessLevel.LENIENT)
criteria = template.get_template()
```

### 4. Web Application Template

**Purpose**: Validates web application implementations

**File Structure Requirements**:
- `app.py` - Main application
- `templates/` - HTML templates directory
- `static/` - Static files directory
- `templates/index.html` - Main template

**Criteria Checked**:
- Route configuration
- Template structure
- Static file organization

**STRICT Mode Additions**:
- CSS stylesheets (`static/style.css`)
- JavaScript files (`static/script.js`)
- Form validation implementation

**Usage**:
```python
from hydra.verification_system.criteria_templates import WebAppTemplate

template = WebAppTemplate(StrictnessLevel.STRICT)
criteria = template.get_template()
```

## Criteria Types

### CriteriaType Enum Values

- **FILE_EXISTS**: Checks file existence
- **DIRECTORY_EXISTS**: Checks directory existence
- **CONTENT_CONTAINS**: Checks if file contains specific text
- **CONTENT_MATCHES**: Checks if file matches regex pattern
- **FUNCTION_EXISTS**: Checks if function is defined in Python file
- **CLASS_EXISTS**: Checks if class is defined in Python file
- **TEST_COVERAGE**: Validates test coverage percentage
- **DOCUMENTATION**: Checks documentation completeness
- **PERFORMANCE**: Validates performance benchmarks
- **SECURITY**: Checks security best practices
- **FUNCTIONALITY**: Tests functional requirements
- **COMMAND_RUNS**: Executes command and checks success
- **API_ENDPOINT**: Tests API endpoint availability
- **CUSTOM**: User-defined custom checks

## Custom Criteria Composition

### CriteriaComposer Class

The `CriteriaComposer` allows creation of custom verification templates:

```python
from hydra.verification_system.criteria_templates import (
    CriteriaComposer, 
    VerificationCriteria, 
    CriteriaType
)

composer = CriteriaComposer()

# Create custom criteria
custom_criteria = VerificationCriteria(
    name="Config file exists",
    type=CriteriaType.FILE_EXISTS,
    description="Configuration file must exist",
    check_function=composer.file_exists_check,
    args={"file_path": "config.json"}
)

# Create custom template
template = composer.compose_custom_template(
    name="Custom Project Template",
    description="Custom verification template",
    criteria=[custom_criteria]
)
```

### Merging Templates

Combine multiple templates for complex projects:

```python
api_template = composer.create_template("api_endpoint")
cli_template = composer.create_template("cli_tool")

merged = composer.merge_templates(
    [api_template, cli_template],
    name="API with CLI",
    description="API service with CLI interface"
)
```

## Boss Agent Integration

### BossAgentIntegration Class

Integrates with the boss agent verification system:

```python
from hydra.verification_system.criteria_templates import BossAgentIntegration

integration = BossAgentIntegration(composer)

# Evaluate project against template
result = integration.evaluate_criteria_template(template, "/path/to/project")

# Generate feedback for failures
if result["overall_status"] == "FAIL":
    feedback = integration.generate_failure_feedback(result)
    print(feedback)
```

### Evaluation Result Structure

```python
{
    "template_name": "API Endpoint Template",
    "template_description": "Verification template for REST API endpoints",
    "project_type": "api_endpoint",
    "total_criteria": 6,
    "passed_criteria": 4,
    "success_rate": 0.67,
    "overall_status": "FAIL",
    "criteria_results": [
        {
            "name": "API module exists",
            "type": "file_exists",
            "description": "Main API module file exists",
            "passed": True,
            "required": True,
            "strictness_level": "balanced"
        }
        # ... more criteria results
    ]
}
```

## Convenience Functions

### Quick Template Creation

```python
from hydra.verification_system.criteria_templates import create_template_for_project_type

template = create_template_for_project_type("web_app", StrictnessLevel.STRICT)
```

### Quick Project Evaluation

```python
from hydra.verification_system.criteria_templates import evaluate_project_against_template

result = evaluate_project_against_template("/path/to/project", template)
```

## Integration with Verification Engine

The criteria templates integrate seamlessly with the existing verification engine:

```python
from hydra.verification_system.engine import VerificationEngine
from hydra.verification_system.criteria_templates import create_template_for_project_type

engine = VerificationEngine("/path/to/project")
template = create_template_for_project_type("api_endpoint")

# The boss agent can use templates for enhanced verification
result = evaluate_project_against_template("/path/to/project", template)
```

## Best Practices

1. **Choose Appropriate Strictness**: Use LENIENT for early development, BALANCED for most cases, STRICT for production-critical systems

2. **Compose Custom Templates**: For unique project requirements, create custom criteria rather than modifying existing templates

3. **Use Boss Agent Integration**: Leverage the integration layer for consistent evaluation and feedback generation

4. **Validate Template Effectiveness**: Test templates against known good and bad project examples

5. **Document Custom Criteria**: When creating custom verification criteria, document the purpose and expected behavior

## Examples

### API Project Verification

```python
# Verify an API project with strict requirements
template = create_template_for_project_type("api_endpoint", StrictnessLevel.STRICT)
result = evaluate_project_against_template("/path/to/api/project", template)

if result["overall_status"] == "FAIL":
    print(f"Verification failed: {result['passed_criteria']}/{result['total_criteria']} criteria passed")
    for criteria in result["criteria_results"]:
        if not criteria["passed"]:
            print(f"- Failed: {criteria['name']}")
```

### Library with Custom Requirements

```python
composer = CriteriaComposer()
library_template = composer.create_template("library", StrictnessLevel.BALANCED)

# Add custom criteria for version file
version_criteria = VerificationCriteria(
    name="Version file exists",
    type=CriteriaType.FILE_EXISTS,
    description="Version file must exist",
    check_function=lambda file_path: Path(file_path).exists(),
    args={"file_path": "VERSION"}
)

library_template.criteria.append(version_criteria)
result = evaluate_project_against_template("/path/to/library", library_template)
```

This documentation provides comprehensive guidance for using the verification criteria templates system effectively.