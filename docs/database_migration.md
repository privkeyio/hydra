# Ticket Database Migration Guide

## Overview

This guide describes the migration from markdown-based ticket storage to database-backed ticket management in Hydra. The new system provides better performance, scalability, and query capabilities while maintaining full backward compatibility.

## Architecture

### New Components

1. **Enhanced Database Models** (`src/hydra/dashboard/database.py`)
   - `Ticket`: Core ticket model with performance indexes
   - `TicketDependency`: Explicit dependency tracking
   - `TicketArtifact`: Artifact storage and metadata

2. **Ticket Service Layer** (`src/hydra/database/ticket_service.py`)
   - `TicketDatabaseService`: Main service for database operations
   - Import/export functionality
   - Dependency graph management

3. **Compatibility Layer** (`src/hydra/database/ticket_compatibility.py`)
   - Transparent fallback between database and markdown
   - Drop-in replacements for existing functions
   - Sync utilities

4. **Database Migrations** (`alembic/`)
   - Alembic configuration for schema versioning
   - Initial migration for new tables

## Migration Steps

### 1. Initial Setup

```bash
# Install required dependencies
pip install alembic sqlalchemy

# Set database URL (optional, defaults to SQLite)
export DATABASE_URL="sqlite:///.hydra/dashboard/hydra.db"

# Run database migrations
alembic upgrade head
```

### 2. Import Existing Tickets

```python
from hydra.database.ticket_service import TicketDatabaseService

# Create service instance
service = TicketDatabaseService()

# Import tickets from markdown
count = service.import_from_markdown("tickets.md", "my_project")
print(f"Imported {count} tickets")
```

### 3. Configure Usage Mode

Control whether to use database or markdown via environment variable:

```bash
# Always use database
export HYDRA_USE_DATABASE=true

# Always use markdown (legacy mode)
export HYDRA_USE_DATABASE=false

# Auto-detect (default) - uses database if available
export HYDRA_USE_DATABASE=auto
```

### 4. Using Compatibility Functions

Replace existing function calls with compatibility versions:

```python
# Old code
from hydra.ticket_workflow import parse_ticket, parse_all_tickets

# New code (with backward compatibility)
from hydra.database import parse_ticket_compat, parse_all_tickets_compat

# Usage remains the same
ticket = parse_ticket_compat("tickets.md", "001")
all_tickets = parse_all_tickets_compat("tickets.md")
```

## Key Features

### Performance Optimizations

1. **Indexed Queries**
   - Status filtering: `idx_ticket_status`
   - Priority sorting: `idx_ticket_priority`
   - Project+Status combo: `idx_ticket_project_status`
   - Dependency lookups: `idx_parent_depends`

2. **Eager Loading**
   - Relationships loaded in single query
   - Reduced N+1 query problems

3. **Batch Operations**
   - Bulk imports with transaction management
   - Efficient dependency resolution

### Data Integrity

1. **Unique Constraints**
   - Project + Ticket Number uniqueness
   - No duplicate dependencies

2. **Foreign Key Constraints**
   - Cascading deletes for related data
   - Referential integrity

3. **Transaction Support**
   - Atomic operations
   - Rollback on errors

## API Reference

### TicketDatabaseService

```python
# Import/Export
service.import_from_markdown(markdown_path, project_name)
service.export_to_markdown(project_name, output_path)

# CRUD Operations
service.get_ticket(project_name, ticket_number)
service.get_all_tickets(project_name)
service.update_ticket_status(project_name, ticket_number, status)

# Artifacts
service.add_ticket_artifact(project_name, ticket_number, 
                          name, type, path, content, metadata)

# Dependencies
deps, reverse_deps = service.get_dependency_graph(project_name)
```

### Compatibility Functions

```python
# Direct replacements for existing functions
parse_ticket_compat(tickets_path, ticket_id)
parse_all_tickets_compat(tickets_path)
mark_ticket_completed_compat(tickets_path, ticket_id)
mark_ticket_in_progress_compat(tickets_path, ticket_id)
mark_ticket_quality_failed_compat(tickets_path, ticket_id)

# New sync utilities
sync_markdown_to_database(tickets_path, force=False)
sync_database_to_markdown(project_name, output_path)
```

## Testing

Run the comprehensive test suite:

```bash
# Run all database tests
pytest tests/test_ticket_database.py -v

# Test performance with large datasets
pytest tests/test_ticket_database.py::TestTicketDatabaseService::test_performance_large_dataset -v

# Test backward compatibility
pytest tests/test_ticket_database.py::TestTicketCompatibility -v
```

## Performance Benchmarks

Based on test results with 100 tickets:

- **Import Time**: < 5 seconds
- **Query All Tickets**: < 1 second  
- **Build Dependency Graph**: < 1 second
- **Single Ticket Lookup**: < 10ms

## Migration Checklist

- [ ] Install dependencies (alembic, sqlalchemy)
- [ ] Configure DATABASE_URL if needed
- [ ] Run database migrations
- [ ] Import existing tickets to database
- [ ] Update code to use compatibility functions
- [ ] Test ticket operations
- [ ] Configure HYDRA_USE_DATABASE mode
- [ ] Monitor performance improvements

## Rollback Procedure

If issues arise, you can rollback to markdown-only mode:

1. Set `export HYDRA_USE_DATABASE=false`
2. Export current database state: `sync_database_to_markdown()`
3. Use exported markdown file as source of truth

## Troubleshooting

### Common Issues

1. **Database locked error (SQLite)**
   - Ensure only one process accesses database
   - Consider upgrading to PostgreSQL for concurrent access

2. **Import fails with duplicate key**
   - Database already contains tickets
   - Use `force=True` flag or clear existing data

3. **Performance degradation**
   - Check if indexes are created
   - Run `ANALYZE` on database
   - Consider database vacuum/optimize

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

- [ ] PostgreSQL support for production
- [ ] Redis caching layer
- [ ] GraphQL API
- [ ] Real-time updates via WebSocket
- [ ] Full-text search with PostgreSQL
- [ ] Audit trail for all changes