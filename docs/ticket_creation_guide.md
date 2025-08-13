# Hydra Ticket Creation Guide

**Comprehensive guide to using Hydra's ticket-based development workflow**

## Table of Contents

1. [Quick Start](#quick-start)
2. [Ticket Structure](#ticket-structure)
3. [Dependency Management](#dependency-management)
4. [Project Templates](#project-templates)
5. [Model Selection](#model-selection)
6. [Interactive Refinement](#interactive-refinement)
7. [Parallel Execution](#parallel-execution)
8. [Quality Gates](#quality-gates)
9. [Advanced Features](#advanced-features)
10. [Troubleshooting](#troubleshooting)

## Quick Start

### Basic Workflow

```bash
# 1. Generate tickets from project description
hydra ticket create "Build a REST API with user authentication"

# 2. Execute all tickets in parallel
hydra ticket parallel --workers 4

# 3. Verify completion and fix any issues
hydra ticket verify-parallel --workers 4
```

### Your First Ticket File

When you run `hydra ticket create`, you'll get a `tickets.md` file with structured tasks:

```markdown
## Ticket 001: Setup FastAPI application
**Status:** TODO
**Model:** balanced
**Dependencies:** None
**Description:** Create the main FastAPI application with basic structure

**Acceptance Criteria:**
- [ ] Create main.py with FastAPI app instance
- [ ] Add health check endpoint at /health
- [ ] Configure CORS for frontend integration
- [ ] Add basic error handling middleware
```

## Ticket Structure

### Required Fields

Every ticket must have these fields:

```markdown
## Ticket NNN: [Clear, actionable title]
**Status:** [TODO|IN_PROGRESS|DONE|QUALITY_FAILED]
**Model:** [smart|balanced|fast|coder]
**Dependencies:** [None or comma-separated numbers: 001,002]
**Description:** [Specific task description]

**Acceptance Criteria:**
- [ ] [Specific, testable requirement]
- [ ] [Another requirement]
```

### Status Meanings

- **TODO**: Ready to start
- **IN_PROGRESS**: Currently being worked on
- **DONE**: Successfully completed with all criteria met
- **QUALITY_FAILED**: Completed but failed quality gates

### Model Selection Guide

Choose the right model for each task:

#### Smart Model
Use for complex tasks requiring deep analysis:
- Architecture decisions
- Complex algorithm implementation
- System design tasks
- Critical security implementations

```markdown
**Model:** smart
```

#### Balanced Model (Default)
Use for standard development tasks:
- Feature implementation
- API endpoints
- Database operations
- Standard testing

```markdown
**Model:** balanced
```

#### Fast Model
Use for simple, routine tasks:
- File creation
- Configuration updates
- Simple documentation
- Basic scaffolding

```markdown
**Model:** fast
```

#### Coder Model
Use for implementation-heavy tasks:
- Large code refactoring
- Complex integrations
- Performance optimizations
- Multiple file changes

```markdown
**Model:** coder
```

## Dependency Management

### Defining Dependencies

```markdown
## Ticket 001: Setup Database
**Dependencies:** None
**Description:** Create database schema

## Ticket 002: User Authentication
**Dependencies:** 001
**Description:** Implement auth using the database

## Ticket 003: API Endpoints
**Dependencies:** 001,002
**Description:** Create user management endpoints
```

### Dependency Rules

1. **Circular Dependencies**: Not allowed - validation will catch these
2. **Missing Dependencies**: Referenced tickets must exist
3. **File Flow Validation**: Output files from dependencies must match input requirements
4. **Execution Order**: Dependencies run before dependents

### File Flow Example

```markdown
## Ticket 001: Database Models
**Output Files:**
- src/models/user.py
- src/models/database.py

## Ticket 002: User Service
**Dependencies:** 001
**Required Input Files:**
- src/models/user.py (from Ticket 001)
- src/models/database.py (from Ticket 001)
**Output Files:**
- src/services/user_service.py
```

## Project Templates

Use templates to structure tickets for common project types:

### Available Templates

```bash
# Migration projects
hydra ticket create "Migrate from REST to GraphQL" --project-type migration

# New features
hydra ticket create "Add payment processing" --project-type feature

# Bug fixes
hydra ticket create "Fix memory leak in user service" --project-type bugfix

# Code refactoring
hydra ticket create "Refactor authentication system" --project-type refactor
```

### Template Structure

#### Migration Template
- Analysis → Design → Implementation → Testing → Validation

#### Feature Template
- Requirements → Design → Backend → Frontend → Integration

#### Bugfix Template
- Reproduce → Analyze → Fix → Test → Verify

#### Refactor Template
- Analysis → Plan → Refactor → Test → Cleanup

## Interactive Refinement

Launch interactive mode to improve generated tickets:

```bash
hydra ticket create "Build user dashboard" --interactive
```

### Interactive Options

1. **Adjust Model Assignments**: Change complexity levels
2. **Split Large Tickets**: Break down complex tasks
3. **Add Missing Dependencies**: Fix dependency chains
4. **Validate File Flows**: Ensure input/output consistency

### Example Refinement Session

```
🔧 Interactive Ticket Refinement

Found 5 tickets to review:

1. Ticket 001: Setup Database (smart) ✓
2. Ticket 002: User Authentication (balanced) - Consider splitting?
3. Ticket 003: Frontend Components (balanced) ✓
4. Ticket 004: API Integration (coder) ✓
5. Ticket 005: Testing Suite (balanced) ✓

Select ticket to refine (1-5) or 'q' to quit: 2

Ticket 002: User Authentication
Current criteria: 8 items
Estimated complexity: HIGH

Options:
- s) Split into smaller tickets
- m) Change model assignment
- d) Add/modify dependencies
- c) Edit criteria
- v) Validate file flows
```

## Parallel Execution

### Basic Parallel Execution

```bash
# Execute with default 3 workers
hydra ticket parallel

# Use more workers for faster execution
hydra ticket parallel --workers 6

# Enable async mode for better resource utilization
hydra ticket parallel --async
```

### Batch Processing

For related tickets, use batch processing to reduce overhead:

```bash
hydra ticket batch --max-batch-size 5 --workers 4
```

### Execution Monitoring

Access the real-time dashboard:

```bash
# Start execution (dashboard auto-starts)
hydra ticket parallel --workers 4

# Access dashboard
open http://localhost:8080
```

Dashboard shows:
- Live progress per ticket
- Model usage statistics
- Resource utilization
- Error logs and debugging info

### Execution Strategy

Hydra automatically:
1. **Analyzes dependencies** to create execution waves
2. **Groups compatible tickets** for parallel execution
3. **Prevents file conflicts** through smart scheduling
4. **Handles failures gracefully** with rollback capabilities

## Quality Gates

Every ticket goes through automatic quality validation:

### Quality Checks

1. **Linting**: Code style and syntax validation
2. **Type Checking**: Static type analysis
3. **Testing**: Automated test execution
4. **Security**: Basic security scanning

### Quality Configuration

Quality gates are configured automatically but can be customized:

```yaml
# .hydra/quality_config.yaml
linting:
  enabled: true
  tools: [ruff, flake8]
  fail_on_error: false

type_checking:
  enabled: true
  tools: [mypy]
  fail_on_error: false

testing:
  enabled: true
  command: pytest
  min_coverage: 80

security:
  enabled: true
  tools: [bandit]
```

### Quality Gate Failure

When quality gates fail:

```markdown
## Ticket 001: Setup API
**Status:** QUALITY_FAILED

**Quality Gate Results:** ❌ FAILED
- Linting: ❌ (3 style violations)
- Type checking: ✅
- Tests: ❌ (Coverage: 65%)
- Security: ✅
```

Fix issues and re-run:

```bash
hydra ticket quality 001
```

## Advanced Features

### Complexity Estimation

Tickets are automatically assigned effort and time estimates:

```markdown
## Ticket 001: Complex Algorithm
**Estimated Effort:** large
**Estimated Time:** 4hr
```

Estimation factors:
- Number of acceptance criteria
- Complexity keywords in description
- File operations required
- Dependencies count

### Pre-flight Validation

Before execution, comprehensive validation runs:

```bash
# Manual pre-flight check
hydra ticket preflight

# Skip validation (not recommended)
hydra ticket parallel --skip-preflight
```

Pre-flight checks:
- Dependency graph validation
- File flow consistency
- Resource availability
- Model configuration

### Progress Tracking

Enhanced progress tracking shows:
- **Stages**: Started → Implementation → Testing → Review → Completed
- **Real-time updates** during execution
- **Historical data** for analytics
- **Webhook integration** for external monitoring

### Analytics and Reporting

Track performance and improve estimates:

```bash
# View execution analytics
open analytics_dashboard.html

# Export metrics
hydra ticket analytics --export metrics.json
```

Analytics include:
- Actual vs estimated completion times
- Model performance by task type
- Common failure patterns
- Improvement recommendations

## Troubleshooting

### Common Issues

#### 1. Dependency Validation Errors

```
❌ Circular dependency detected: 001 → 002 → 001
```

**Solution**: Remove circular references by restructuring dependencies.

#### 2. File Flow Mismatches

```
⚠️ Required file 'src/models/user.py' from ticket 001 not found in output files
```

**Solution**: Update output files in the dependency ticket or fix the required input specification.

#### 3. Model Selection Errors

```
❌ Unknown model: 'super-smart'
```

**Solution**: Use valid model categories: `smart`, `balanced`, `fast`, `coder`.

#### 4. Quality Gate Failures

```
❌ Linting failed: 15 violations found
```

**Solution**: 
- Fix linting issues manually
- Update quality configuration to be less strict
- Use auto-fixer: `hydra ticket fix 001`

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
export HYDRA_DEBUG=true
hydra ticket parallel --workers 2
```

### Recovery Procedures

#### Resume Failed Execution

```bash
# Resume from where execution stopped
hydra ticket parallel --resume

# Force restart specific tickets
hydra ticket execute 003
```

#### Reset Ticket Status

```bash
# Reset failed tickets to TODO
hydra ticket reset 001,002,003

# Reset all tickets
hydra ticket reset --all
```

### Performance Optimization

#### Faster Execution

```bash
# Use more workers (limited by CPU cores)
hydra ticket parallel --workers 8

# Enable async mode
hydra ticket parallel --async

# Use batch processing for small tickets
hydra ticket batch --max-batch-size 10
```

#### Resource Management

```bash
# Limit memory usage per worker
export HYDRA_MAX_MEMORY=2GB

# Set timeout for stuck tickets
export HYDRA_TICKET_TIMEOUT=1800  # 30 minutes
```

## Best Practices

### 1. Ticket Design

- **Keep tickets atomic**: One clear responsibility per ticket
- **Write specific criteria**: Avoid vague requirements like "make it work"
- **Include verification steps**: How to test the implementation
- **Reference specific files**: Mention exact file paths when relevant

### 2. Dependencies

- **Minimize dependencies**: Only depend on what you actually need
- **Logical ordering**: Earlier tickets should be foundational
- **File flow clarity**: Clearly specify input/output files
- **Avoid deep chains**: Long dependency chains slow execution

### 3. Execution Strategy

- **Start small**: Begin with 2-3 workers and scale up
- **Monitor resources**: Watch CPU and memory usage
- **Use templates**: Leverage project templates for consistency
- **Quality first**: Don't skip quality gates in production

### 4. Model Selection

- **Match complexity**: Don't use smart models for simple tasks
- **Consider cost**: Balanced models are usually sufficient
- **Profile performance**: Track which models work best for your tasks
- **Mix strategically**: Use different models for different ticket types

---

## Support

- **Documentation**: Full docs at `docs/`
- **Examples**: Real-world examples in `examples/`
- **API Reference**: Complete API docs at `docs/api_reference.md`
- **Troubleshooting**: Common issues at `docs/troubleshooting/`

---

**Happy ticket creation! 🎫**