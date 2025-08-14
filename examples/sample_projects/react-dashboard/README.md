# React Dashboard Example

**Full-stack application demonstrating file flow validation and batch processing**

This example builds a React dashboard with FastAPI backend, showcasing:
- File flow validation between frontend and backend tickets
- Batch processing for related tickets
- Interactive refinement for UI components
- Complexity estimation for different technology stacks

## Project Overview

A modern dashboard application with:
- **React Frontend**: Dashboard UI, charts, data tables
- **FastAPI Backend**: REST API, data processing
- **Shared Components**: TypeScript types, API schemas
- **Testing**: Unit tests for both frontend and backend

## Features Demonstrated

### 1. File Flow Validation
Demonstrates how Hydra validates that output files from backend tickets match the required input files for frontend tickets:

```markdown
## Ticket 003: API Endpoints
**Output Files:**
- src/api/schemas.py (Pydantic models)
- src/api/endpoints.py (FastAPI routes)

## Ticket 005: TypeScript Types  
**Required Input Files:**
- src/api/schemas.py (from Ticket 003)
**Output Files:**
- frontend/src/types/api.ts (Generated from schemas)
```

### 2. Batch Processing
Related tickets are grouped into batches for efficient execution:
- **Batch 1**: Frontend components (React components, styles)
- **Batch 2**: Backend services (API, database)
- **Batch 3**: Integration (API client, data fetching)

### 3. Interactive Refinement
Example shows refinement of UI tickets:
- Split large dashboard into smaller components
- Optimize dependency relationships
- Adjust complexity estimates

## Architecture

```
react-dashboard/
├── backend/
│   ├── src/
│   │   ├── api/          # FastAPI endpoints (Ticket 003-004)
│   │   ├── models/       # Data models (Ticket 002)
│   │   └── services/     # Business logic (Ticket 006)
│   └── tests/            # Backend tests (Ticket 008)
├── frontend/
│   ├── src/
│   │   ├── components/   # React components (Ticket 005)
│   │   ├── types/        # TypeScript types (Ticket 005)
│   │   ├── services/     # API client (Ticket 007)
│   │   └── styles/       # CSS modules (Ticket 005)
│   └── tests/            # Frontend tests (Ticket 009)
└── shared/
    ├── types/            # Shared TypeScript definitions
    └── schemas/          # API schema definitions
```

## Running the Example

### Quick Start

```bash
# Generate tickets with interactive refinement
hydra ticket create "$(cat project_description.txt)" --project-type feature --interactive

# Execute using batch processing
hydra ticket batch --max-batch-size 3 --workers 3

# Verify with emphasis on file flows
hydra ticket verify-parallel --workers 2
```

### Detailed Steps

```bash
# 1. Generate tickets
hydra ticket create "Build a React dashboard with FastAPI backend for data visualization" --project-type feature

# 2. Review and refine (optional)
hydra ticket create "$(cat project_description.txt)" --interactive

# 3. Execute with batch optimization
hydra ticket batch --max-batch-size 3 --max-complexity 80 --workers 3

# 4. Monitor progress
open http://localhost:8080

# 5. Verify file flows
hydra ticket verify-parallel --workers 2

# 6. Check quality
hydra ticket quality 005  # React components
hydra ticket quality 003  # API endpoints
```

## Expected Execution

### Batch 1: Backend Foundation
- **Ticket 001**: Database setup (fast model)
- **Ticket 002**: Data models (balanced model) 
- **Ticket 003**: API endpoints (balanced model)

### Batch 2: Frontend Foundation  
- **Ticket 004**: React setup (fast model)
- **Ticket 005**: Core components (coder model)
- **Ticket 006**: Styling system (fast model)

### Batch 3: Integration
- **Ticket 007**: API client (balanced model)
- **Ticket 008**: Data fetching (balanced model)
- **Ticket 009**: Error handling (balanced model)

### Individual: Testing & Quality
- **Ticket 010**: Backend tests (balanced model)
- **Ticket 011**: Frontend tests (balanced model)
- **Ticket 012**: Integration tests (smart model)

## File Flow Examples

This example demonstrates sophisticated file flow validation:

### Backend → Frontend Type Generation
```markdown
## Backend Schema (Ticket 003)
Output: src/api/schemas.py
```python
from pydantic import BaseModel

class UserData(BaseModel):
    id: int
    name: str
    email: str
```

## Frontend Types (Ticket 005)
Required Input: src/api/schemas.py
Output: frontend/src/types/api.ts
```typescript
// Generated from backend schemas
export interface UserData {
  id: number;
  name: string; 
  email: string;
}
```

### API Routes → Client Generation
Backend routes automatically inform frontend API client structure.

## Batch Processing Benefits

This example shows ~40% efficiency improvement with batching:
- **Without batching**: 12 tickets × 15 min = 180 min
- **With batching**: 3 batches × 35 min = 105 min 
- **Efficiency gain**: 42% faster execution

## Learning Points

### 1. File Flow Design
- Backend outputs inform frontend inputs
- Shared type definitions reduce duplication
- Schema-first development ensures consistency

### 2. Batch Optimization
- Group related tickets by technology/domain
- Balance batch size vs parallelism
- Consider model requirements in batching

### 3. Interactive Refinement Value
- UI tickets benefit from decomposition
- Component hierarchies affect dependencies
- User experience considerations influence ticket structure

## Files in This Example

- `project_description.txt` - Project requirements
- `run_example.sh` - Automated execution
- `expected_output/` - Final project structure
- `batch_config.yaml` - Batch processing configuration