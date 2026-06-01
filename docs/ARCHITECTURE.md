# Hydra Architecture Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Components](#core-components)
3. [Data Flow](#data-flow)
4. [Agent Hierarchy](#agent-hierarchy)
5. [Technical Design](#technical-design)
6. [Security Architecture](#security-architecture)
7. [Deployment Architecture](#deployment-architecture)

## System Overview

Hydra is a hierarchical multi-agent system designed for autonomous code generation and task delegation. The architecture follows a tree-based hierarchy where agents can spawn child agents to handle subtasks.

```
┌─────────────────────────────────────────────────────────────┐
│                        Hydra System                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐    ┌──────────────┐    ┌─────────────────┐  │
│  │   CLI   │───▶│   Workflow   │───▶│     Agents      │  │
│  │ (Entry) │    │   Engine     │    │   (Hierarchy)   │  │
│  └─────────┘    └──────────────┘    └─────────────────┘  │
│       │                │                      │            │
│       └────────────────┴──────────────────────┘           │
│                          │                                 │
│                    ┌─────▼─────┐                          │
│                    │    LLM    │                          │
│                    │ Provider  │                          │
│                    └───────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. CLI Layer (`src/hydra/cli.py`)
- **Purpose**: User interface for task input
- **Responsibilities**:
  - Parse command-line arguments
  - Handle multi-line input
  - Format output (text/JSON)
  - Exit code management

### 2. Workflow Engine (`src/hydra/workflows/engine.py`)
- **Purpose**: Orchestrate agent execution flow
- **Built on**: LangGraph state machine
- **Key Nodes**:
  ```
  Plan Node ──▶ Spawn Node ──▶ Aggregate Node
       ▲              │              │
       └──────────────┴──────────────┘
  ```

### 3. Agent System (`src/hydra/agents/base.py`)
- **Core Class**: `CodeAgent`
- **Key Methods**:
  - `reason()`: Task decomposition
  - `generate_code()`: Code creation
  - `execute_code()`: Sandboxed execution
  - `create_employee()`: Spawn child agents

### 4. LLM Provider System (`src/hydra/providers/`)
- **Base Provider**: Abstract interface for all LLM providers
- **Provider Factory**: Dynamic provider instantiation
- **Implementations**: Venice, Anthropic, OpenAI, Claude CLI
- **Auto-registration**: Automatic provider discovery

### 5. Configuration System (`src/hydra/config.py`)
- **Provider Selection**: Runtime provider switching
- **Environment Override**: ENV vars override YAML config
- **API Key Management**: Provider-specific credentials
- **Parameter Configuration**: Temperature, tokens, timeouts

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Workflow
    participant Boss
    participant Employee
    participant LLM
    participant Sandbox

    User->>CLI: Input task
    CLI->>Workflow: Execute workflow
    Workflow->>Boss: Create boss agent
    Boss->>LLM: Reason about task
    LLM->>Boss: Return plan + subtasks
    
    alt Has subtasks
        Boss->>Employee: Spawn employees
        Employee->>LLM: Generate code
        LLM->>Employee: Return code
        Employee->>Sandbox: Execute code
        Sandbox->>Employee: Return results
        Employee->>Boss: Return to parent
    end
    
    Boss->>Workflow: Aggregate results
    Workflow->>CLI: Final output
    CLI->>User: Display results
```

## Agent Hierarchy

### Depth Limits
```
Level 0: Boss Agent
├── Level 1: Employee Agents
│   ├── Level 2: Sub-Employee Agents (MAX DEPTH)
│   └── Level 2: Sub-Employee Agents (MAX DEPTH)
└── Level 1: Employee Agents
```

### Parent-Child Relationships
- Each agent maintains reference to parent
- Parent tracks all spawned employees
- Bidirectional result passing
- Hierarchical logging with full ancestry

### State Management
```python
WorkflowState = {
    'task': str,           # Current task
    'depth': int,          # Current depth level
    'results': dict,       # Aggregated results
    'agents': list,        # Agent names
    'current_agent': str,  # Active agent
    'subtasks': list,      # Decomposed tasks
    'plan': str           # Execution plan
}
```

## LLM Provider Architecture

### Provider Class Hierarchy
```
LLMProvider (Abstract Base)
├── Properties
│   ├── config: LLMConfig
│   ├── name: str (abstract)
│   └── model: str
├── Abstract Methods
│   ├── validate_config()
│   ├── generate(prompt) -> str
│   ├── generate_json(prompt) -> Dict
│   └── list_models() -> List[str]
└── Implementations
    ├── NearAIProvider
    ├── VeniceProvider
    ├── AnthropicProvider
    ├── OpenAIProvider
    └── ClaudeCLIProvider
```

### Provider Factory Pattern
```python
# Auto-registration on import
providers/
├── __init__.py      # Imports all providers
├── base.py          # Abstract base class
├── factory.py       # Factory with registry
├── nearai.py        # NEAR AI Cloud implementation
├── venice.py        # Venice implementation
├── anthropic.py     # Anthropic implementation
├── openai.py        # OpenAI implementation
└── claude_cli.py    # Claude CLI wrapper
```

### Provider Configuration Flow
```
1. Environment Variables
   └── Override config values
2. YAML Configuration
   └── Default provider settings
3. Provider Factory
   └── Create provider instance
4. Validation
   └── Check API keys, settings
5. Agent Integration
   └── Use provider for generation
```

## Technical Design

### Class Hierarchy
```
CodeAgent
├── Properties
│   ├── name: str
│   ├── parent: Optional[CodeAgent]
│   ├── depth: int
│   ├── agent_id: str
│   └── employees: List[CodeAgent]
├── Methods
│   ├── reason(task) -> Dict
│   ├── generate_code(prompt) -> str
│   ├── execute_code(code) -> Dict
│   └── create_employee(subtask) -> Dict
└── Class Methods
    └── _setup_logger() -> Logger
```

### Workflow Graph Structure
```
StateGraph
├── Nodes
│   ├── plan_node: Task decomposition
│   ├── spawn_node: Employee creation
│   └── aggregate_node: Result collection
├── Edges
│   ├── plan → spawn (conditional)
│   ├── plan → aggregate (conditional)
│   ├── spawn → aggregate
│   └── aggregate → END
└── Entry Point: plan_node
```

### Execution Pipeline
1. **Task Input** → CLI parsing
2. **Workflow Init** → State creation
3. **Planning Phase** → LLM reasoning
4. **Spawning Phase** → Employee generation
5. **Execution Phase** → Code sandbox
6. **Aggregation Phase** → Result synthesis
7. **Output Phase** → Formatted display

## Security Architecture

### Sandboxing Strategy
```python
subprocess.run(
    ["python", "-c", code_str],
    capture_output=True,
    text=True,
    timeout=30,  # Hard timeout
    check=False  # Don't raise on error
)
```

### Safety Mechanisms
1. **Recursion Guards**
   - Hard limit at depth 2
   - Exception on depth violation
   - Tracked in agent state

2. **Code Validation**
   - AST parsing before execution
   - Syntax validation
   - Import restrictions

3. **Execution Limits**
   - 30-second timeout
   - Subprocess isolation
   - No file system access

4. **Error Handling**
   - Retry logic (2 attempts)
   - Graceful degradation
   - Comprehensive logging

### API Key Management
```
.env (git-ignored)
├── LLM_PROVIDER (nearai|venice|anthropic|openai|claude_cli)
├── NEARAI_API_KEY
├── VENICE_API_KEY
├── ANTHROPIC_API_KEY
├── OPENAI_API_KEY
└── CLAUDE_CLI_PATH
```

## Deployment Architecture

### Local Development
```
Developer Machine
├── Python 3.11+ environment
├── Virtual environment (venv)
├── Local API keys (.env)
└── File-based logging
```

### Internal Deployment
```
Internal Server
├── GitLab CI/CD pipeline
├── Container runtime (future)
├── Centralized logging
└── Monitoring (future)
```

### Configuration Hierarchy
1. Environment variables (highest priority)
2. Local config files
3. Default configuration
4. Hardcoded fallbacks

### Logging Architecture
```
logs/
└── agent_activity.log
    ├── Timestamp
    ├── Agent hierarchy
    ├── Task details
    ├── Execution results
    └── Error traces
```

## Extension Points

### Adding New LLM Providers
1. Create new provider class inheriting from `LLMProvider`
2. Implement required methods: `validate_config()`, `generate()`, `generate_json()`, `list_models()`, `name`
3. Place in `src/hydra/providers/` directory
4. Auto-registration will detect it automatically
5. Add provider-specific config handling in `HydraConfig._create_llm_provider()`
6. Update `.env.example` with new provider settings

### Custom Workflow Nodes
1. Define node function
2. Add to StateGraph
3. Update edges/conditions
4. Test state transitions

### Agent Capabilities
1. Subclass CodeAgent
2. Override key methods
3. Maintain interface contract
4. Add to agent registry

## Performance Considerations

### Bottlenecks
- LLM API calls (network latency)
- Sequential spawning (not parallel)
- Subprocess overhead

### Optimization Opportunities
- Async LLM calls
- Parallel employee execution
- Result caching
- Connection pooling

## Future Architecture Considerations

### Scalability Path
```
Current: Single Process
    ↓
Phase 1: Multi-threading
    ↓
Phase 2: Multi-processing
    ↓
Phase 3: Distributed (Celery/RQ)
    ↓
Phase 4: Kubernetes Jobs
```

### Monitoring Integration
- OpenTelemetry instrumentation
- Metrics collection
- Distributed tracing
- Performance profiling

### Storage Backend
- Current: In-memory + logs
- Future: PostgreSQL for state
- Redis for caching
- S3 for artifacts
