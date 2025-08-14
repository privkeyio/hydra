# Hydra API Reference

**Complete reference for Hydra's Python API and CLI commands**

## Table of Contents

1. [CLI Commands](#cli-commands)
2. [Ticket Workflow API](#ticket-workflow-api)
3. [Agent System](#agent-system)
4. [Provider System](#provider-system)
5. [Configuration](#configuration)
6. [Analytics & Tracking](#analytics--tracking)
7. [Validation & Quality](#validation--quality)
8. [Type Definitions](#type-definitions)
9. [Error Handling](#error-handling)

## CLI Commands

### Core Commands

#### `hydra run <task>`

Execute a single task with the agent system.

```bash
# Basic task execution
hydra run "Create a REST API endpoint"

# With custom agent and depth
hydra run "Complex analysis" --agent-name analyst --depth 1

# JSON output
hydra run "Generate report" --json
```

**Options:**
- `--agent-name`: Root agent name (default: `boss`)
- `--depth`: Starting depth (default: `0`)
- `--json`: Output in JSON format
- `--provider`: Override LLM provider (`venice`, `claude_tmux`, `anthropic`, `openai`, `mock`)
- `--model`: Override model (e.g., `qwen-2.5-coder-32b`, `gpt-4`)

### Ticket Workflow Commands

#### `hydra ticket create <description>`

Generate tickets from project description.

```bash
# Basic ticket creation
hydra ticket create "Build a REST API with authentication"

# With project type template
hydra ticket create "Migrate to microservices" --project-type migration

# Interactive refinement
hydra ticket create "User dashboard" --interactive

# Custom output file
hydra ticket create "Admin panel" --output admin_tickets.md
```

**Options:**
- `--output`: Output file (default: `tickets.md`)
- `--project-type`: Project template (`migration`, `feature`, `bugfix`, `refactor`)
- `--interactive`: Launch interactive refinement after creation

#### `hydra ticket execute <identifier>`

Execute a specific ticket.

```bash
# Execute by number
hydra ticket execute 001

# Execute with custom tickets file
hydra ticket execute TICKET-123 --tickets ./project/tickets.md
```

**Options:**
- `--tickets`: Tickets file path (default: `tickets.md`)

#### `hydra ticket parallel`

Execute tickets in parallel with dependency resolution.

```bash
# Default parallel execution
hydra ticket parallel

# More workers
hydra ticket parallel --workers 6

# Async mode (experimental)
hydra ticket parallel --async

# Save execution log
hydra ticket parallel --save-log
```

**Options:**
- `--tickets`: Tickets file (default: `tickets.md`)
- `--workers`: Maximum parallel workers (default: `3`)
- `--save-log`: Save execution log to file
- `--async`: Use async execution engine

#### `hydra ticket batch`

Execute tickets in optimized batches.

```bash
# Basic batch execution
hydra ticket batch

# Custom batch configuration
hydra ticket batch --max-batch-size 10 --max-complexity 150

# Disable batching
hydra ticket batch --disable-batching
```

**Options:**
- `--workers`: Maximum parallel workers (default: `3`)
- `--max-batch-size`: Maximum tickets per batch (default: `5`)
- `--max-complexity`: Maximum complexity score per batch (default: `100`)
- `--min-batch-tickets`: Minimum tickets to create batch (default: `2`)
- `--disable-batching`: Run individual tickets instead

#### `hydra ticket verify-parallel`

Verify and fix unmet acceptance criteria in parallel.

```bash
# Verify all tickets
hydra ticket verify-parallel

# Save detailed report
hydra ticket verify-parallel --save-report verification_report.json

# Static analysis only
hydra ticket verify-parallel --static-only
```

**Options:**
- `--workers`: Maximum parallel workers (default: `4`)
- `--save-report`: Save verification report to file
- `--static-only`: Skip model-based verification

#### `hydra ticket verify <identifier>`

Verify specific ticket acceptance criteria.

```bash
hydra ticket verify 001
hydra ticket verify TICKET-123 --tickets ./project/tickets.md
```

#### `hydra ticket quality <identifier>`

Run quality gates for a ticket.

```bash
# Run quality checks
hydra ticket quality 001

# Save quality report
hydra ticket quality 001 --save
```

**Options:**
- `--save`: Save quality report to file

### Template Commands

#### `hydra template list`

List available project templates.

```bash
hydra template list
```

#### `hydra template create <template> <output_dir>`

Create project from template.

```bash
# Basic template usage
hydra template create flask_web_app ./my-app

# With parameters
hydra template create python_cli_tool ./cli-tool --param name=mytool --param author="John Doe"
```

**Options:**
- `--param`: Template parameter (`key=value` format)

#### `hydra template validate`

Validate template structure.

```bash
# Validate all templates
hydra template validate

# Validate specific template
hydra template validate --template flask_web_app
```

### Claude Code Orchestration

#### `hydra claude execute <task>`

Execute task with Claude Code CLI.

```bash
# Basic execution
hydra claude execute "Create FastAPI service"

# With timeout and working directory
hydra claude execute "Refactor auth module" --timeout 600 --cwd ./backend
```

**Options:**
- `--timeout`: Timeout in seconds (default: `300`)
- `--cwd`: Working directory (default: current directory)

#### `hydra claude session <project_path>`

Create Claude Code development session.

```bash
# Create named session
hydra claude session ./project --name dev-session

# Auto-generated name
hydra claude session ./project
```

**Options:**
- `--name`: Session name (auto-generated if not provided)

#### Session Management

```bash
# List active sessions
hydra claude list

# Attach to session
hydra claude attach session-name

# Kill session
hydra claude kill session-name

# Save session state
hydra claude save session-name

# Restore session
hydra claude restore session-name
```

### Context Management

#### `hydra context show`

Show all tracked ticket contexts.

```bash
hydra context show
```

#### `hydra context inspect <ticket_id>`

Inspect specific ticket context.

```bash
hydra context inspect 001
```

#### `hydra context clear`

Clear ticket contexts.

```bash
# Clear specific ticket
hydra context clear 001

# Clear all contexts
hydra context clear --all
```

#### `hydra context deps <ticket_id>`

Show dependency context for ticket.

```bash
hydra context deps 003
```

#### `hydra context export`

Export all contexts.

```bash
# Text format
hydra context export

# JSON format
hydra context export --format json
```

## Ticket Workflow API

### Core Functions

#### `generate_tickets_md(description: str, output_file: str, project_type: Optional[str]) -> bool`

Generate tickets.md from project description.

```python
from hydra.ticket_workflow import generate_tickets_md

success = generate_tickets_md(
    description="Build user authentication system",
    output_file="auth_tickets.md",
    project_type="feature"
)
```

#### `execute_single_ticket(tickets_file: str, identifier: str) -> bool`

Execute a specific ticket.

```python
from hydra.ticket_workflow import execute_single_ticket

success = execute_single_ticket("tickets.md", "001")
```

#### `run_all_tickets(tickets_file: str, max_parallel: int = 3) -> bool`

Execute all tickets with optional parallel execution.

```python
from hydra.ticket_workflow import run_all_tickets

success = run_all_tickets("tickets.md", max_parallel=4)
```

#### `parse_ticket(tickets_file: str, identifier: str) -> Optional[Dict[str, Any]]`

Parse specific ticket from file.

```python
from hydra.ticket_workflow import parse_ticket

ticket_data = parse_ticket("tickets.md", "001")
if ticket_data:
    print(f"Title: {ticket_data['title']}")
    print(f"Status: {ticket_data['status']}")
    print(f"Dependencies: {ticket_data['dependencies']}")
```

#### `parse_all_tickets(tickets_file: str) -> Dict[str, Dict[str, Any]]`

Parse all tickets from file.

```python
from hydra.ticket_workflow import parse_all_tickets

all_tickets = parse_all_tickets("tickets.md")
for ticket_id, ticket_data in all_tickets.items():
    print(f"Ticket {ticket_id}: {ticket_data['title']}")
```

### Validation API

#### `DependencyValidator`

Validate ticket dependencies and file flows.

```python
from hydra.validation.dependency_validator import DependencyValidator

validator = DependencyValidator()

# Validate dependencies
is_valid, errors = validator.validate_dependencies(tickets_data)

# Validate file flows
flow_valid, flow_errors = validator.validate_file_flows(tickets_data)

# Get validation report
report = validator.generate_validation_report(tickets_data)
```

#### `AcceptanceValidator`

Validate acceptance criteria completion.

```python
from hydra.validation.acceptance_validator import AcceptanceValidator

validator = AcceptanceValidator("/project/path")

# Validate ticket completion
completion_status = validator.validate_ticket_completion("001", ticket_data)

# Check criteria
criteria_status = validator.check_acceptance_criteria(
    criteria_list, 
    project_files
)
```

### Complexity Estimation

#### `ComplexityEstimator`

Estimate ticket complexity and effort.

```python
from hydra.estimation.complexity_estimator import ComplexityEstimator

estimator = ComplexityEstimator()

# Estimate single ticket
estimate = estimator.estimate_ticket_complexity(ticket_data)
print(f"Effort: {estimate.effort_level}")
print(f"Time: {estimate.estimated_hours}h")

# Estimate all tickets
estimates = estimator.estimate_project_complexity(all_tickets)
```

### Parallel Execution

#### `ParallelExecutor`

Execute tickets in parallel with dependency resolution.

```python
from hydra.parallel.executor import ParallelExecutor

executor = ParallelExecutor(
    max_workers=4,
    project_root="/project/path"
)

# Load tickets
tickets = executor.load_tickets("tickets.md")

# Build execution plan
plan = executor.build_execution_plan()

# Execute plan
summary = executor.execute_plan(plan, "tickets.md")

# Generate report
report = executor.generate_report(summary)
```

#### `ExecutionOptimizer`

Optimize parallel execution strategy.

```python
from hydra.parallel.execution_optimizer import ExecutionOptimizer

optimizer = ExecutionOptimizer()

# Analyze dependencies
dependency_graph = optimizer.analyze_dependencies(tickets_data)

# Create execution groups
groups = optimizer.create_execution_groups(dependency_graph)

# Optimize scheduling
optimized_plan = optimizer.optimize_execution_plan(groups)
```

### Interactive Refinement

#### `TicketRefiner`

Interactive ticket refinement system.

```python
from hydra.interactive.ticket_refiner import TicketRefiner

refiner = TicketRefiner("tickets.md")

# Start interactive refinement
refined_tickets = refiner.refine_tickets_interactive()

# Auto-refine based on rules
auto_refined = refiner.auto_refine_tickets(
    split_large_tickets=True,
    optimize_dependencies=True
)
```

#### `RefinementCLI`

Command-line interface for refinement.

```python
from hydra.interactive.refinement_cli import run_interactive_refinement

# Launch interactive CLI
result = run_interactive_refinement("tickets.md")
```

### Progress Tracking

#### `ProgressTracker`

Track execution progress with detailed metrics.

```python
from hydra.tracking.progress_tracker import ProgressTracker

tracker = ProgressTracker()

# Start tracking session
session_id = tracker.start_session("project-name", total_tickets=10)

# Update progress
tracker.update_ticket_progress("001", "STARTED", progress=0.1)
tracker.update_ticket_progress("001", "COMPLETED", progress=1.0)

# Get session summary
summary = tracker.get_session_summary(session_id)
```

### Analytics

#### `ExecutionAnalytics`

Collect and analyze execution metrics.

```python
from hydra.analytics.execution_analytics import ExecutionAnalytics

analytics = ExecutionAnalytics()

# Record execution
analytics.record_ticket_execution(
    ticket_id="001",
    start_time=start_time,
    end_time=end_time,
    success=True,
    model_used="balanced"
)

# Generate insights
insights = analytics.generate_insights()

# Export metrics
analytics.export_metrics("metrics.json")
```

## Agent System

### Core Agent Classes

#### `CodeAgent`

Primary agent implementation.

```python
from hydra.agents.base import CodeAgent

# Create agent
agent = CodeAgent("developer", depth=0)

# Reason about task
reasoning = agent.reason("Implement user authentication")

# Generate code
code = agent.generate_code("Create login function")

# Execute code
result = agent.execute_code(code)

# Create employee for subtask
employee_result = agent.create_employee("Validate input data")
```

#### `ClaudeCodeAgent`

Claude Code specific agent.

```python
from hydra.agents.claude_code_agent import ClaudeCodeAgent

agent = ClaudeCodeAgent(
    name="claude-dev",
    session_manager=session_manager
)

# Execute with Claude Code
result = agent.execute_task("Refactor authentication module")
```

### Agent Pool Management

#### `AgentPool`

Manage multiple agent instances.

```python
from hydra.agents.pool import AgentPool

pool = AgentPool(max_agents=5)

# Get agent from pool
agent = pool.get_agent("task-executor")

# Return agent to pool
pool.return_agent(agent)

# Shutdown pool
pool.shutdown()
```

## Provider System

### Base Provider Interface

#### `LLMProvider`

Abstract base for all providers.

```python
from hydra.providers.base import LLMProvider

class CustomProvider(LLMProvider):
    def validate_config(self):
        # Validate configuration
        pass
    
    def generate(self, prompt: str, **kwargs) -> str:
        # Generate text response
        pass
    
    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        # Generate JSON response
        pass
    
    def list_models(self) -> List[str]:
        # List available models
        pass
```

### Provider Factory

#### `create_provider_from_environment()`

Create provider from environment configuration.

```python
from hydra.providers.provider_factory import create_provider_from_environment

# Create provider based on environment variables
provider = create_provider_from_environment()

# Generate response
response = provider.generate("Write a hello world function")
```

### Available Providers

#### Venice Provider

```python
from hydra.providers.venice import VeniceProvider
from hydra.providers.provider_config import LLMConfig

config = LLMConfig(
    provider_type="venice",
    model="qwen-2.5-coder-32b",
    api_key="your-venice-key"
)

provider = VeniceProvider(config)
response = provider.generate("Create a sorting algorithm")
```

#### Anthropic Provider

```python
from hydra.providers.anthropic import AnthropicProvider

config = LLMConfig(
    provider_type="anthropic",
    model="claude-3-5-sonnet-20241022",
    api_key="your-anthropic-key"
)

provider = AnthropicProvider(config)
```

#### Claude CLI Provider

```python
from hydra.providers.claude_tmux import ClaudeTmuxProvider

config = LLMConfig(
    provider_type="claude_tmux",
    extra_params={
        "claude_path": "/usr/local/bin/claude",
        "session_name": "dev-session"
    }
)

provider = ClaudeTmuxProvider(config)
```

### Model Mapping

#### `ModelMapper`

Map abstract model categories to provider-specific models.

```python
from hydra.providers.model_mapper import get_model_mapper

mapper = get_model_mapper()

# Map model category to provider-specific model
provider_model = mapper.map_model("balanced", "venice")
# Returns: "qwen-2.5-coder-32b"

# Get all mappings for provider
mappings = mapper.get_provider_mappings("anthropic")
```

## Configuration

### Data Classes

#### `LLMConfig`

Provider configuration.

```python
from hydra.providers.provider_config import LLMConfig

config = LLMConfig(
    provider_type="venice",
    model="qwen-2.5-coder-32b",
    api_key="key",
    temperature=0.2,
    max_tokens=2048,
    timeout=30,
    extra_params={"custom_param": "value"}
)
```

#### `ProductionConfig`

Production environment configuration.

```python
from hydra.production_config import get_production_config

config = get_production_config()

# Configuration properties
print(f"Max parallel tickets: {config.max_parallel_tickets}")
print(f"Enable file locking: {config.enable_file_locking}")
print(f"Dashboard enabled: {config.enable_dashboard}")

# Convert to environment variables
env_vars = config.to_env_vars()
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | Provider type | `venice` |
| `LLM_MODEL` | Model name | Provider default |
| `VENICE_API_KEY` | Venice API key | None |
| `ANTHROPIC_API_KEY` | Anthropic API key | None |
| `OPENAI_API_KEY` | OpenAI API key | None |
| `CLAUDE_CLI_PATH` | Claude CLI path | `/usr/local/bin/claude` |
| `HYDRA_MAX_WORKERS` | Max parallel workers | `3` |
| `HYDRA_ENABLE_DASHBOARD` | Enable dashboard | `true` |
| `HYDRA_DEBUG` | Enable debug logging | `false` |

## Analytics & Tracking

### Progress Tracking

#### `ProgressTracker`

Real-time progress tracking with stages.

```python
from hydra.tracking.progress_tracker import ProgressTracker, TicketStage

tracker = ProgressTracker()

# Update ticket stage
tracker.update_ticket_stage("001", TicketStage.IMPLEMENTATION)

# Set progress percentage
tracker.set_ticket_progress("001", 0.7)

# Add execution logs
tracker.add_execution_log("001", "Generated user model")

# Get real-time status
status = tracker.get_ticket_status("001")
```

#### `ProgressUI`

Terminal UI for progress visualization.

```python
from hydra.tracking.progress_ui import ProgressUI

ui = ProgressUI()

# Start UI with tickets
ui.start_tracking(ticket_list)

# Update progress (called by tracker)
ui.update_display(ticket_statuses)

# Stop UI
ui.stop_tracking()
```

### Analytics

#### `ExecutionAnalytics`

Comprehensive execution analytics.

```python
from hydra.analytics.execution_analytics import ExecutionAnalytics

analytics = ExecutionAnalytics()

# Record metrics
analytics.record_execution_start("session-123")
analytics.record_ticket_completion("001", duration=300, success=True)

# Generate reports
performance_report = analytics.generate_performance_report()
model_analysis = analytics.analyze_model_performance()

# Export data
analytics.export_metrics("analytics.json")
```

#### `PerformanceReport`

Generate detailed performance reports.

```python
from hydra.analytics.performance_report import PerformanceReportGenerator

generator = PerformanceReportGenerator()

# Generate HTML report
html_report = generator.generate_html_report(analytics_data)

# Generate dashboard data
dashboard_data = generator.generate_dashboard_data(analytics_data)

# Save reports
generator.save_report(html_report, "performance_report.html")
```

## Validation & Quality

### Pre-flight Validation

#### `PreflightChecker`

Comprehensive pre-execution validation.

```python
from hydra.preflight.preflight_checker import PreflightChecker

checker = PreflightChecker("/project/path")

# Run all checks
validation_result = checker.run_preflight_checks("tickets.md")

# Check specific aspects
dependency_result = checker.validate_dependencies(tickets_data)
file_flow_result = checker.validate_file_flows(tickets_data)
resource_result = checker.check_resource_availability()

# Generate report
report = checker.generate_validation_report(validation_result)
```

#### `ValidationReport`

Structured validation reporting.

```python
from hydra.preflight.validation_report import ValidationReport, ValidationStatus

report = ValidationReport()

# Add validation results
report.add_check("Dependencies", ValidationStatus.PASSED, "All dependencies valid")
report.add_check("File Flows", ValidationStatus.WARNING, "2 missing input files")

# Generate summary
summary = report.generate_summary()

# Export report
report.export_to_file("validation_report.json")
```

### Quality Gates

#### `QualityGateRunner`

Execute quality checks on completed tickets.

```python
from hydra.quality.gate_runner import QualityGateRunner

runner = QualityGateRunner("/project/path")

# Run quality gates
report = runner.run_quality_gates("001")

# Check specific gates
lint_result = runner.run_linting_check("001")
test_result = runner.run_test_check("001")
security_result = runner.run_security_check("001")

# Generate consolidated report
quality_report = runner.generate_report(report)
```

#### `AutoFixer`

Automatically fix common quality issues.

```python
from hydra.quality.auto_fixer import AutoFixer

fixer = AutoFixer("/project/path")

# Fix linting issues
lint_fixes = fixer.fix_linting_issues("001")

# Fix import issues
import_fixes = fixer.fix_import_issues("001")

# Apply all fixes
all_fixes = fixer.apply_all_fixes("001")
```

### Ticket Verification

#### `TicketVerifier`

Verify acceptance criteria completion.

```python
from hydra.verification.ticket_verifier import TicketVerifier

verifier = TicketVerifier("/project/path")

# Verify specific ticket
verification_report = verifier.verify_ticket("tickets.md", "001")

# Check acceptance criteria
criteria_results = verifier.check_acceptance_criteria(
    ticket_data["acceptance_criteria"],
    project_files
)

# Generate verification report
report = verifier.generate_report(verification_report)
```

## Type Definitions

### Core Types

```python
from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum

class TicketStatus(Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    QUALITY_FAILED = "QUALITY_FAILED"

class TicketStage(Enum):
    QUEUED = "queued"
    STARTED = "started"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"

class ValidationStatus(Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"

class TicketData(TypedDict):
    number: str
    title: str
    status: str
    model: str
    dependencies: List[str]
    description: str
    acceptance_criteria: List[str]
    estimated_effort: Optional[str]
    estimated_time: Optional[str]
    output_files: Optional[List[str]]
    required_input_files: Optional[List[str]]

class ExecutionSummary(TypedDict):
    total_tickets: int
    completed: int
    failed: int
    blocked: int
    execution_time: float
    success_rate: float
    
class WorkflowState(TypedDict):
    task: str
    depth: int
    results: Dict[str, Any]
    agents: List[str]
    current_agent: str
    subtasks: List[str]
    plan: str
```

### Validation Types

```python
class ValidationResult(TypedDict):
    is_valid: bool
    errors: List[str]
    warnings: List[str]

class QualityGateResult(TypedDict):
    gate_name: str
    status: str
    details: Dict[str, Any]
    suggestions: List[str]

class ComplexityEstimate(TypedDict):
    effort_level: str  # "small", "medium", "large", "x-large"
    estimated_hours: float
    confidence: float
    factors: List[str]
```

## Error Handling

### Exception Types

```python
from hydra.exceptions import (
    HydraError,
    ValidationError,
    ExecutionError,
    ConfigurationError,
    ProviderError
)

# Base exception
class HydraError(Exception):
    """Base exception for all Hydra errors"""
    pass

# Specific exceptions
class ValidationError(HydraError):
    """Validation failed"""
    pass

class ExecutionError(HydraError):
    """Execution failed"""
    pass

class ConfigurationError(HydraError):
    """Configuration invalid"""
    pass

class ProviderError(HydraError):
    """Provider operation failed"""
    pass
```

### Error Response Format

```python
{
    "success": False,
    "error": "Error message",
    "error_type": "ValidationError",
    "details": {
        "ticket_id": "001",
        "validation_failures": ["Missing dependency", "Invalid model"]
    },
    "suggestions": [
        "Check ticket dependencies",
        "Use valid model name"
    ]
}
```

### Best Practices

1. **Always check return values** for success/failure status
2. **Use proper exception handling** around provider calls
3. **Validate inputs** before processing
4. **Log errors appropriately** with context
5. **Provide helpful error messages** to users

## Examples

### Complete Workflow Example

```python
import os
from hydra.ticket_workflow import generate_tickets_md, run_all_tickets
from hydra.providers.provider_factory import create_provider_from_environment
from hydra.tracking.progress_tracker import ProgressTracker

# Setup environment
os.environ['LLM_PROVIDER'] = 'venice'
os.environ['VENICE_API_KEY'] = 'your-key'

# Generate tickets
success = generate_tickets_md(
    description="Build a todo app with React and FastAPI",
    output_file="todo_tickets.md",
    project_type="feature"
)

if success:
    # Track progress
    tracker = ProgressTracker()
    session_id = tracker.start_session("todo-app")
    
    # Execute tickets
    execution_success = run_all_tickets("todo_tickets.md", max_parallel=4)
    
    # Get summary
    summary = tracker.get_session_summary(session_id)
    print(f"Completed: {summary['completed_tickets']}/{summary['total_tickets']}")
```

### Custom Provider Example

```python
from hydra.providers.base import LLMProvider
from hydra.providers.provider_config import LLMConfig

class CustomProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.validate_config()
    
    def validate_config(self):
        if not self.config.api_key:
            raise ValueError("API key required")
    
    def generate(self, prompt: str, **kwargs) -> str:
        # Custom implementation
        return "Generated response"
    
    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        # Custom JSON generation
        return {"response": "json response"}
    
    def list_models(self) -> List[str]:
        return ["custom-model-1", "custom-model-2"]

# Register custom provider
from hydra.providers.provider_factory import provider_factory
provider_factory.register("custom", CustomProvider)
```

---

## Support

- **Full Documentation**: Complete guides at `docs/`
- **Examples**: Real-world examples in `examples/`
- **Troubleshooting**: Common issues at `docs/troubleshooting/`
- **Source Code**: Browse implementation for detailed usage

---

*This API reference covers Hydra v2.0+ with all advanced features integrated.*