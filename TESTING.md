# Hydra Testing Documentation

## End-to-End Testing

### Core Workflow Tests

The test suite includes comprehensive end-to-end tests for the core Hydra workflow:

#### 1. Ticket Workflow Tests (`tests/integration/test_ticket_workflow_e2e.py`)

Tests the complete ticket lifecycle:
- **Create**: Generate ticket files in proper format
- **Execute**: Run ticket execution with mock provider
- **Verify**: Validate ticket completion and criteria

Key test scenarios:
- Single ticket execution
- Parallel ticket execution
- Ticket dependencies handling
- Acceptance criteria verification
- Error handling
- State persistence

#### 2. CLI Command Tests (`tests/integration/test_cli_commands_e2e.py`)

Tests all CLI commands:
- `hydra ticket execute` - Execute single ticket
- `hydra ticket parallel` - Execute multiple tickets in parallel
- `hydra ticket verify` - Verify ticket completion
- `hydra ticket verify-parallel` - Verify multiple tickets
- `hydra ticket generate` - Generate tickets.md file

### Running Tests

#### Local Development
```bash
# Run all E2E tests
pytest tests/integration/test_ticket_workflow_e2e.py tests/integration/test_cli_commands_e2e.py -v

# Run specific test
pytest tests/integration/test_ticket_workflow_e2e.py::TestTicketWorkflowE2E::test_create_execute_verify_workflow -v
```

#### CI Environment
Tests run automatically in CI with mock provider:
```bash
export LLM_PROVIDER=mock
pytest tests/integration/ -v --tb=short --timeout=60
```

### Test Structure

Tests use temporary workspaces and create tickets.md files with proper format:

```markdown
# Project Tickets

## Ticket 001: Task Name

**Priority**: 1

**Description**: Task description

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2

**Dependencies**: None

**Status**: TODO
```

### CI Integration

Tests are integrated into GitHub Actions workflow:
- Run on every push to main/develop
- Run on pull requests
- Use mock provider to avoid API calls
- Timeout after 5 minutes
- Run in parallel where possible

### Test Coverage

The E2E tests ensure:
1. **Ticket Creation**: Proper format and structure
2. **Ticket Execution**: Mock provider integration
3. **Ticket Verification**: Criteria validation
4. **Parallel Processing**: Multi-ticket handling
5. **Dependency Resolution**: Correct execution order
6. **Error Handling**: Graceful failure modes
7. **State Management**: Persistence across runs

### Future Improvements

- Add performance benchmarks
- Test with real providers in staging
- Add integration with monitoring systems
- Test rollback scenarios
- Add load testing for parallel execution