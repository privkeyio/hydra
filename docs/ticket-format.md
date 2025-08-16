# Ticket Format Guide

Hydra uses YAML format for tickets, providing structure and reliability.

## Basic Structure

```yaml
version: '1.0'
project:
  name: Project Name
  description: Brief description
  created_at: '2024-01-01T00:00:00Z'
  
tickets:
  - id: "001"
    title: Concise title
    status: TODO
    priority: 1
    model: balanced
    description: |
      Detailed description of what needs to be done.
      Can be multiple lines.
    acceptance_criteria:
      - Specific measurable requirement
      - Another testable requirement
    dependencies: []
```

## Field Reference

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (e.g., "001", "002") |
| `title` | string | Short descriptive title |
| `status` | string | TODO, IN_PROGRESS, DONE, BLOCKED |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `priority` | integer | 5 | 1-10, lower = higher priority |
| `model` | string | balanced | fast, balanced, smart, coder |
| `description` | string | "" | Detailed description |
| `acceptance_criteria` | list | [] | Testable requirements |
| `dependencies` | list | [] | IDs of prerequisite tickets |
| `complexity` | string | medium | low, medium, high |

## Model Selection

Choose models based on task complexity:

- **fast**: Simple tasks, boilerplate, configurations
- **balanced**: Standard features, moderate complexity
- **smart**: Complex logic, architecture decisions
- **coder**: Heavy coding tasks, optimizations

## Acceptance Criteria

Good criteria are:
- **Specific**: Clear what needs to be done
- **Measurable**: Can verify completion
- **Achievable**: Realistic for single ticket
- **Testable**: Can write tests to verify

### Examples

✅ Good:
```yaml
acceptance_criteria:
  - API endpoint returns 200 for valid requests
  - Invalid input returns 400 with error message
  - All functions have docstrings
  - Unit tests achieve 80% coverage
```

❌ Bad:
```yaml
acceptance_criteria:
  - Make it work
  - Code should be good
  - Add some tests
```

## Dependencies

Define execution order:

```yaml
tickets:
  - id: "001"
    title: Setup database
    dependencies: []
    
  - id: "002"
    title: Create models
    dependencies: ["001"]  # Needs database first
    
  - id: "003"
    title: Add API endpoints
    dependencies: ["002"]  # Needs models first
    
  - id: "004"
    title: Write tests
    dependencies: ["002", "003"]  # Needs both models and API
```

## Complete Example

```yaml
version: '1.0'
project:
  name: Task Manager API
  description: REST API for task management
  
tickets:
  - id: "001"
    title: Setup project structure
    status: TODO
    priority: 1
    model: fast
    description: Initialize Python project with standard structure
    acceptance_criteria:
      - Create src/ directory structure
      - Add requirements.txt with FastAPI, SQLAlchemy
      - Create main.py with basic FastAPI app
      - Add .gitignore for Python
    dependencies: []
    
  - id: "002"
    title: Design database schema
    status: TODO
    priority: 2
    model: balanced
    description: Create SQLAlchemy models for tasks
    acceptance_criteria:
      - Task model with id, title, description, status, created_at
      - Database migrations setup with Alembic
      - Models have proper relationships
    dependencies: ["001"]
    
  - id: "003"
    title: Implement CRUD endpoints
    status: TODO
    priority: 3
    model: balanced
    description: Create REST endpoints for task operations
    acceptance_criteria:
      - POST /tasks creates new task
      - GET /tasks lists all tasks with pagination
      - GET /tasks/{id} returns single task
      - PUT /tasks/{id} updates task
      - DELETE /tasks/{id} removes task
      - All endpoints have proper error handling
    dependencies: ["002"]
    
  - id: "004"
    title: Add authentication
    status: TODO
    priority: 4
    model: smart
    description: Implement JWT authentication
    acceptance_criteria:
      - POST /auth/register creates user
      - POST /auth/login returns JWT token
      - Protected endpoints require valid token
      - Token refresh mechanism works
    dependencies: ["003"]
    
  - id: "005"
    title: Write comprehensive tests
    status: TODO
    priority: 5
    model: balanced
    description: Add unit and integration tests
    acceptance_criteria:
      - Test coverage > 80%
      - All endpoints have integration tests
      - Models have unit tests
      - Authentication flows tested
    dependencies: ["004"]
```

## Migration from Markdown

Hydra automatically detects format. To convert:

```bash
# Manual conversion
hydra ticket convert tickets.md tickets.yaml

# Auto-detection works with both
hydra ticket execute tickets.md 001   # Still works
hydra ticket execute tickets.yaml 001  # Preferred
```

## Tips

1. **Keep tickets focused**: One feature per ticket
2. **Clear dependencies**: Prevents execution conflicts
3. **Specific criteria**: Easier to verify completion
4. **Appropriate models**: Match complexity to save costs
5. **Incremental approach**: Build foundation first