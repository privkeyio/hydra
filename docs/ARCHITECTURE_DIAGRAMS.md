# Hydra Architecture Diagrams

## Component Interaction Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              HYDRA SYSTEM                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────┐         ┌─────────────────┐         ┌───────────────┐  │
│  │            │         │                 │         │               │  │
│  │  CLI Entry │────────▶│ Workflow Engine │────────▶│ Agent System  │  │
│  │   (cli.py) │         │  (LangGraph)    │         │  (CodeAgent)  │  │
│  │            │         │                 │         │               │  │
│  └────────────┘         └─────────────────┘         └───────────────┘  │
│         │                       │                           │            │
│         │                       ▼                           ▼            │
│         │               ┌───────────────┐          ┌───────────────┐    │
│         │               │    State      │          │   Subprocess  │    │
│         │               │  Management   │          │   Execution   │    │
│         └──────────────▶│  (Dict/JSON)  │          │   (Sandbox)   │    │
│                         └───────────────┘          └───────────────┘    │
│                                 │                           │            │
│                                 ▼                           ▼            │
│                         ┌───────────────────────────────────────┐       │
│                         │          LLM Integration              │       │
│                         ├───────────────────────────────────────┤       │
│                         │  Primary: Anthropic Claude API        │       │
│                         │  Fallback: Venice API                 │       │
│                         └───────────────────────────────────────┘       │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Agent Hierarchy Tree

```
                              Boss Agent (Depth 0)
                             /                    \
                            /                      \
                   Employee 1 (Depth 1)      Employee 2 (Depth 1)
                   /            \                    |
                  /              \                   |
      Sub-Employee 1.1    Sub-Employee 1.2   Sub-Employee 2.1
         (Depth 2)           (Depth 2)          (Depth 2)
            ⚠️                   ⚠️                 ⚠️
        [MAX DEPTH]         [MAX DEPTH]        [MAX DEPTH]
```

## Workflow State Machine

```
        ┌─────────────┐
        │    START    │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  PLAN NODE  │──────────┐
        └──────┬──────┘          │
               │                 │
        Has Subtasks?            │ No Subtasks
               │                 │
              Yes                │
               │                 │
               ▼                 │
        ┌─────────────┐          │
        │ SPAWN NODE  │          │
        └──────┬──────┘          │
               │                 │
               ▼                 ▼
        ┌───────────────────────────┐
        │    AGGREGATE NODE         │
        └────────────┬──────────────┘
                     │
                     ▼
               ┌─────────────┐
               │     END     │
               └─────────────┘
```

## Data Flow Sequence

```
User Input ──▶ CLI Parser ──▶ Workflow Engine
                                    │
                                    ▼
                              Create Boss Agent
                                    │
                                    ▼
                              LLM Reasoning
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
              Has Subtasks                    No Subtasks
                    │                               │
                    ▼                               │
              Spawn Employees                       │
                    │                               │
                    ▼                               │
              Execute Tasks                         │
                    │                               │
                    ▼                               ▼
              Collect Results ◀─────────────────────┘
                    │
                    ▼
              Format Output
                    │
                    ▼
              Display to User
```

## Code Execution Sandbox

```
┌─────────────────────────────────────────────┐
│          Agent Process (Parent)             │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │     Generated Code String           │   │
│  └──────────────┬──────────────────────┘   │
│                 │                           │
│                 ▼                           │
│  ┌─────────────────────────────────────┐   │
│  │        AST Validation               │   │
│  └──────────────┬──────────────────────┘   │
│                 │                           │
│                 ▼                           │
│  ╔═════════════════════════════════════╗   │
│  ║    Subprocess (Isolated)            ║   │
│  ║  ┌─────────────────────────────┐   ║   │
│  ║  │   Python Interpreter        │   ║   │
│  ║  │   - No file access         │   ║   │
│  ║  │   - 30s timeout            │   ║   │
│  ║  │   - Limited imports        │   ║   │
│  ║  └─────────────────────────────┘   ║   │
│  ╚═════════════════════════════════════╝   │
│                 │                           │
│                 ▼                           │
│  ┌─────────────────────────────────────┐   │
│  │     Capture stdout/stderr           │   │
│  └──────────────┬──────────────────────┘   │
│                 │                           │
│                 ▼                           │
│  ┌─────────────────────────────────────┐   │
│  │      Return Execution Result        │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Logging Hierarchy

```
logs/agent_activity.log
│
├─ [TIMESTAMP] Boss_12345 - Task: "Create calculator"
│  ├─ [TIMESTAMP] Boss_12345 - Plan: "Break into components"
│  │
│  ├─ [TIMESTAMP] Employee_1_67890 - Task: "Create add function"
│  │  ├─ [TIMESTAMP] Employee_1_67890 - Code generated
│  │  └─ [TIMESTAMP] Employee_1_67890 - Execution success
│  │
│  └─ [TIMESTAMP] Employee_2_11121 - Task: "Create subtract function"
│     ├─ [TIMESTAMP] Employee_2_11121 - Code generated
│     ├─ [TIMESTAMP] SubEmployee_2_1_31415 - Task: "Add validation"
│     │  └─ [TIMESTAMP] SubEmployee_2_1_31415 - Execution success
│     └─ [TIMESTAMP] Employee_2_11121 - Results aggregated
│
└─ [TIMESTAMP] Boss_12345 - Final results compiled
```

## Configuration Layers

```
┌─────────────────────────────────┐
│     Environment Variables       │ ◀── Highest Priority
│        (.env file)             │
├─────────────────────────────────┤
│      Config Files              │
│   (config/default.yaml)        │
├─────────────────────────────────┤
│    Default Configuration       │
│     (in source code)           │
├─────────────────────────────────┤
│     Hardcoded Values           │ ◀── Lowest Priority
│    (fallback constants)        │
└─────────────────────────────────┘
```

## Error Handling Flow

```
                    Task Execution
                         │
                         ▼
                 ┌───────────────┐
                 │  Try Execute  │
                 └───────┬───────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
        Success                    Error
            │                         │
            │                         ▼
            │                  ┌──────────────┐
            │                  │ Retry Logic  │
            │                  │ (Attempt 2)  │
            │                  └──────┬───────┘
            │                         │
            │              ┌──────────┴──────────┐
            │              ▼                     ▼
            │          Success               Failed
            │              │                     │
            ▼              ▼                     ▼
      ┌─────────────────────────────┐   ┌──────────────┐
      │    Return Results           │   │  Log Error   │
      └─────────────────────────────┘   │ Return Error │
                                        └──────────────┘
```