# E-commerce API Example

**Complete REST API demonstrating all Hydra features**

This example builds a production-ready e-commerce API showcasing:
- Complex dependency management
- Multiple model assignments based on task complexity
- Pre-flight validation
- Parallel execution optimization
- Quality gates and verification
- Progress tracking and analytics

## Project Overview

The API includes:
- **User Management**: Registration, authentication, profiles
- **Product Catalog**: Products, categories, search, inventory
- **Shopping Cart**: Cart operations, session management
- **Order Processing**: Checkout, payment integration, order tracking
- **Admin Panel**: Admin operations, analytics, reporting

## Architecture

```
├── src/
│   ├── models/          # Database models (Ticket 001-003)
│   ├── auth/            # Authentication system (Ticket 004-005)
│   ├── api/             # API endpoints (Ticket 006-010)
│   ├── services/        # Business logic (Ticket 011-013)
│   └── utils/           # Utilities (Ticket 014)
├── tests/               # Test suite (Ticket 015-017)
├── docs/                # API documentation (Ticket 018)
└── deployment/          # Deployment configs (Ticket 019-020)
```

## Features Demonstrated

### 1. Dependency Validation (Ticket 001)
Complex dependency chains where later tickets depend on foundational components:
- Database models → Auth system → API endpoints → Services

### 2. Model Selection Intelligence (Ticket 003)
Strategic model assignments:
- **Smart**: Architecture decisions, security implementations
- **Balanced**: Standard API endpoints, business logic
- **Fast**: Configuration files, simple utilities
- **Coder**: Large implementations, complex integrations

### 3. Project Templates (Ticket 002)
Uses the "feature" template structure optimized for new API development.

### 4. Interactive Refinement (Ticket 004)
Example shows how to use interactive mode to:
- Split large tickets into manageable pieces
- Optimize dependency relationships
- Adjust model assignments

### 5. Complexity Estimation (Ticket 005)
Demonstrates automatic effort estimation:
- Small tasks: 1-2 hours
- Medium tasks: 4-6 hours
- Large tasks: 8+ hours

### 6. Pre-flight Validation (Ticket 006)
Comprehensive pre-execution checks:
- Dependency graph validation
- File flow consistency
- Resource availability

### 7. Parallel Execution (Ticket 007)
Optimized execution groups:
- Wave 1: Foundation (models, database)
- Wave 2: Core services (auth, catalog)
- Wave 3: API endpoints
- Wave 4: Integration and testing

### 8. Progress Tracking (Ticket 008)
Real-time monitoring of:
- Individual ticket progress
- Overall project completion
- Resource utilization
- Performance metrics

### 9. Analytics (Ticket 009)
Comprehensive analytics including:
- Execution time analysis
- Model performance comparison
- Bottleneck identification
- Success rate tracking

## Running the Example

### Quick Start

```bash
# Generate tickets with feature template
hydra ticket create "$(cat project_description.txt)" --project-type feature --interactive

# Execute with optimized parallel processing
hydra ticket parallel --workers 4 --save-log

# Verify all acceptance criteria are met
hydra ticket verify-parallel --workers 4 --save-report verification.json

# View analytics dashboard
open analytics_dashboard.html
```

### Step-by-Step Execution

```bash
# 1. Generate tickets
hydra ticket create "Build a complete e-commerce API with user authentication, product catalog, shopping cart, and order processing" --project-type feature

# 2. Review generated tickets
cat tickets.md

# 3. Optional: Interactive refinement
hydra ticket create "$(cat project_description.txt)" --interactive

# 4. Run pre-flight validation
hydra ticket preflight

# 5. Execute with monitoring
hydra ticket parallel --workers 4 --save-log

# 6. Monitor progress (in another terminal)
open http://localhost:8080

# 7. Verify completion
hydra ticket verify-parallel --workers 4

# 8. Review quality gates
hydra ticket quality 001
hydra ticket quality 002
# ... for each ticket

# 9. View final analytics
open analytics_dashboard.html
```

## Expected Execution Flow

### Wave 1: Foundation (Parallel)
- **Ticket 001**: Database setup and configuration
- **Ticket 002**: Core data models (User, Product, Order)
- **Ticket 003**: Database migrations and seeding

### Wave 2: Core Services (Parallel, depends on Wave 1)
- **Ticket 004**: Authentication system (JWT, password hashing)
- **Ticket 005**: User management service
- **Ticket 006**: Product catalog service

### Wave 3: Business Logic (Parallel, depends on Wave 2)
- **Ticket 007**: Shopping cart implementation
- **Ticket 008**: Order processing service
- **Ticket 009**: Payment integration
- **Ticket 010**: Inventory management

### Wave 4: API Layer (Parallel, depends on Wave 3)
- **Ticket 011**: User API endpoints
- **Ticket 012**: Product API endpoints
- **Ticket 013**: Cart API endpoints
- **Ticket 014**: Order API endpoints

### Wave 5: Quality & Deployment (Sequential, depends on Wave 4)
- **Ticket 015**: Comprehensive test suite
- **Ticket 016**: API documentation
- **Ticket 017**: Deployment configuration
- **Ticket 018**: Performance optimization
- **Ticket 019**: Security audit
- **Ticket 020**: Production monitoring

## Key Learning Points

### 1. Dependency Design
Notice how tickets are structured to minimize dependencies while maintaining logical order:
```markdown
## Ticket 004: Authentication System
**Dependencies:** 001,002  # Needs database and User model
**Model:** smart          # Complex security requirements

## Ticket 011: User API Endpoints  
**Dependencies:** 004,005  # Needs auth system and user service
**Model:** balanced       # Standard API implementation
```

### 2. Model Selection Strategy
- **Smart models** for critical security and architecture decisions
- **Balanced models** for standard business logic
- **Fast models** for configuration and simple utilities
- **Coder models** for complex implementations with many files

### 3. File Flow Validation
Each ticket specifies:
- **Required Input Files**: Dependencies must produce these
- **Output Files**: What this ticket will create
- **Modified Files**: Existing files that will be updated

### 4. Quality Gate Integration
Every ticket includes specific quality criteria:
- Code coverage requirements
- Security scan passing
- Performance benchmarks
- Documentation completeness

## Troubleshooting

### Common Issues

1. **Dependency Validation Errors**
   ```bash
   # Check dependency graph
   hydra context deps 008
   ```

2. **Quality Gate Failures**
   ```bash
   # Auto-fix common issues
   hydra ticket fix 001
   
   # Manual quality check
   hydra ticket quality 001 --save
   ```

3. **Parallel Execution Conflicts**
   ```bash
   # Check file lock status
   hydra context show
   
   # Resume failed execution
   hydra ticket parallel --resume
   ```

## Performance Expectations

With 4 workers on a modern development machine:
- **Total Execution Time**: 45-60 minutes
- **Parallel Efficiency**: 70-80% (vs sequential)
- **Success Rate**: 95%+ with quality gates
- **Code Coverage**: 85%+ across all modules

## Next Steps

After completing this example:
1. Review the generated code structure
2. Examine the analytics report
3. Try modifying the project description
4. Experiment with different worker counts
5. Test the interactive refinement features

## Files in This Example

- `project_description.txt` - Input project description
- `run_example.sh` - Automated execution script  
- `expected_output/` - Example of completed project structure
- `analytics_config.yaml` - Custom analytics configuration
- `quality_gates.yaml` - Quality gate definitions