# Integration Tests

## Core Workflow Tests

### test_workflow_functions.py
Tests the core workflow functions directly (without CLI):
- `parse_ticket()` - Parse ticket from markdown
- `execute_single_ticket()` - Execute a single ticket
- `run_all_tickets()` - Execute all tickets in parallel
- `mark_ticket_*()` - Update ticket status
- `generate_tickets_md()` - Generate tickets from description
- `build_dependency_graph()` - Dependency resolution
- `get_quality_summary()` - Quality reporting

**Value**: Tests the actual workflow logic with mock provider, ensuring core functionality works.

### test_core_commands.py  
Tests the CLI commands end-to-end:
- `hydra ticket create` - Generate tickets.md from description
- `hydra ticket execute` - Execute single ticket
- `hydra ticket parallel` - Execute multiple tickets in parallel
- `hydra ticket verify` - Verify ticket completion
- `hydra ticket verify-parallel` - Verify multiple tickets

**Value**: Ensures CLI interface works correctly, commands parse arguments, and workflow completes.

## Why These Tests Matter

Unlike pure mock tests that test nothing, these tests:

1. **Validate core workflow** - Create → Execute → Verify pipeline
2. **Test with mock provider** - Ensures workflow completes even without real AI
3. **Check actual functionality** - Parsing, dependency resolution, status updates
4. **Prevent regression** - Future changes won't break core commands
5. **CI compatible** - Run in CI without API keys

## Running Tests

```bash
# Run workflow function tests
pytest tests/integration/test_workflow_functions.py -v

# Run CLI command tests  
pytest tests/integration/test_core_commands.py -v

# Run with real provider (requires API key)
VENICE_API_KEY=xxx pytest tests/integration/ -k "real_provider" -v
```

## Test Coverage

These tests ensure:
- ✅ Ticket creation from description works
- ✅ Ticket parsing extracts correct fields
- ✅ Single ticket execution completes
- ✅ Parallel execution handles multiple tickets
- ✅ Dependencies are resolved correctly
- ✅ Verification checks completion status
- ✅ Status updates (TODO → IN_PROGRESS → DONE)
- ✅ Quality gates run (even if skipped)
- ✅ Invalid inputs handled gracefully

## Mock vs Real Providers

- **Mock Provider**: Always returns success, tests workflow logic
- **Real Provider**: Actually generates code, tests full integration

Both are valuable:
- Mock tests run in CI, ensure workflow doesn't break
- Real tests run locally, ensure AI integration works