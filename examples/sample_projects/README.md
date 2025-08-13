# Sample Projects

**Real-world examples showcasing Hydra's integrated features**

This directory contains complete sample projects that demonstrate how to use Hydra's ticket workflow with all the advanced features from dependent tickets 001-009.

## Available Examples

### 1. E-commerce API (`ecommerce-api/`)
A complete REST API with authentication, product catalog, and order management.

**Features Demonstrated:**
- Complex dependency chains
- Multiple model assignments
- Pre-flight validation
- Parallel execution optimization
- Quality gates
- Progress tracking
- Analytics collection

### 2. React Dashboard (`react-dashboard/`)
A full-stack application with React frontend and FastAPI backend.

**Features Demonstrated:**
- Feature template usage
- Interactive refinement
- File flow validation
- Batch processing
- Complexity estimation

### 3. Data Pipeline (`data-pipeline/`)
A data processing pipeline with ETL operations and monitoring.

**Features Demonstrated:**
- Migration template
- Pre-flight checks
- Execution analytics
- Quality assurance

### 4. Microservices Platform (`microservices/`)
A microservices architecture with API Gateway, auth service, and data services.

**Features Demonstrated:**
- Large-scale project decomposition
- Parallel execution at scale
- Advanced dependency management
- Model selection strategies

## Quick Start

Each example includes:
- `README.md` - Project overview and instructions
- `tickets.md` - Generated ticket structure
- `run_example.sh` - Script to execute the example
- `expected_output/` - What the final result should look like

### Running an Example

```bash
# Navigate to example
cd examples/sample_projects/ecommerce-api

# Run the complete workflow
./run_example.sh

# Or run steps manually
hydra ticket create "$(cat project_description.txt)" --project-type feature
hydra ticket parallel --workers 4
hydra ticket verify-parallel --workers 4
```

### Learning Path

1. **Start with**: `ecommerce-api` (comprehensive example)
2. **Then try**: `react-dashboard` (frontend + backend)
3. **Advanced**: `microservices` (complex architecture)
4. **Specialized**: `data-pipeline` (data processing)

Each example builds on previous concepts while introducing new features and patterns.