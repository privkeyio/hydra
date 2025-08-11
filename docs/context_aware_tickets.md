# Context-Aware Ticket System

## Overview

Hydra's ticket system now includes advanced context-passing capabilities that ensure dependent tickets have full awareness of artifacts created by their dependencies. This solves the critical issue where agents working on later tickets had no knowledge of what previous tickets produced.

## Key Features

### 1. Automatic Artifact Discovery
When a ticket completes, the system automatically:
- Discovers all files created or modified
- Records file descriptions and previews
- Tracks acceptance criteria completion
- Saves context to `.hydra/ticket_context.json`

### 2. Context Injection for Dependencies
When a ticket with dependencies executes, it automatically receives:
- List of files created by dependent tickets
- Content previews for important files (reports, designs, specs)
- Acceptance criteria that were met
- Clear instructions on which files to read first

### 3. Enhanced Ticket Format
Tickets with dependencies now include:
```markdown
## Ticket 002: Design API Architecture
**Status:** TODO
**Model:** Opus 4
**Dependencies:** 001
**Description:** Design the API based on audit findings from Ticket 001

**Required Input Files:**
- audit_report.md (from Ticket 001)
- existing_api_analysis.json (from Ticket 001)

**Context Requirements:**
- FIRST: Read audit_report.md to understand current system
- Review existing_api_analysis.json for API patterns
- Build upon the recommendations in the audit

**Acceptance Criteria:**
- [ ] Create API design based on audit_report.md findings
- [ ] Address all issues identified in Ticket 001
- [ ] Document migration path from existing APIs
```

## How It Works

### During Ticket Generation
When you run `hydra ticket create`, the system now:
1. Generates tickets with dependency relationships
2. Adds "Required Input Files" sections for dependent tickets
3. Includes "Context Requirements" with specific instructions
4. References outputs from previous tickets in descriptions and criteria

### During Execution
1. **Before Starting**: Agent receives full context from dependencies
2. **During Work**: Agent can read files created by previous tickets
3. **After Completion**: System discovers and records all artifacts

### Context Storage
All context is stored in `.hydra/ticket_context.json`:
```json
{
  "001": {
    "ticket_id": "001",
    "title": "Audit Current System",
    "status": "completed",
    "artifacts": [
      {
        "file_path": "audit_report.md",
        "operation": "created",
        "description": "Audit report document",
        "content_preview": "# System Audit Report\n..."
      }
    ],
    "acceptance_criteria_met": [
      "Documented all API endpoints",
      "Identified performance bottlenecks"
    ]
  }
}
```

## CLI Commands

### View Context
```bash
# Show all ticket contexts
hydra context show

# Inspect specific ticket
hydra context inspect 001

# Show what context a ticket would receive
hydra context deps 002

# Export all contexts
hydra context export --format json > contexts.json
```

### Clear Context
```bash
# Clear specific ticket
hydra context clear 001

# Clear all contexts
hydra context clear --all
```

## Example Workflow

1. **Create Tickets**:
```bash
hydra ticket create "Build a web scraping system with data pipeline"
```

2. **Execute Tickets** (context passed automatically):
```bash
hydra ticket parallel --tickets tickets.md
```

3. **View Context**:
```bash
hydra context show
```

## Benefits

1. **Continuity**: Each ticket builds properly on previous work
2. **No Duplication**: Agents know what's already been done
3. **Clear Dependencies**: Explicit file requirements documented
4. **Better Quality**: Agents have full context for informed decisions
5. **Debugging**: Easy to inspect what each ticket produced

## Technical Details

### ArtifactTracker Class
Located in `src/hydra/context/artifact_tracker.py`:
- Discovers artifacts using git status and file system monitoring
- Generates context strings for dependent tickets
- Manages persistent storage of contexts

### Integration Points
- `ParallelExecutor`: Injects context before execution, records after
- `ClaudeTmuxProvider`: Receives enhanced prompts with context
- `CLI`: New context management commands

## Best Practices

1. **Always include context requirements** in tickets with dependencies
2. **Name output files clearly** so dependent tickets can find them
3. **Use descriptive acceptance criteria** that reference specific deliverables
4. **Check context before execution** with `hydra context deps <ticket>`
5. **Clear old contexts** when starting fresh projects

## Troubleshooting

### Missing Context
If a ticket doesn't receive expected context:
1. Check if dependency completed: `hydra context show`
2. Verify artifacts were created: `hydra context inspect <dep_ticket>`
3. Ensure tickets.md has proper dependency declarations

### Context Not Updated
If artifacts aren't being tracked:
1. Check git status - files must be created/modified
2. Ensure files aren't in .gitignore or .hydra/
3. Verify ticket completed successfully

### Clear and Rebuild
To start fresh:
```bash
hydra context clear --all
rm .hydra/ticket_context.json
```

## Future Enhancements

Planned improvements:
- Automatic artifact validation
- Cross-project context sharing  
- Context templates for common patterns
- Visual dependency graphs with artifacts
- Smart context compression for large files