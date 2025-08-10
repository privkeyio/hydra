Agents API
==========

The agent system forms the core of Hydra, providing hierarchical task delegation
and autonomous code generation capabilities.

Base Agent Classes
------------------

.. automodule:: hydra.agents.base
   :members:
   :undoc-members:
   :show-inheritance:

Claude Code Agent
-----------------

.. automodule:: hydra.agents.claude_code_agent
   :members:
   :undoc-members:
   :show-inheritance:

Agent Pool Management
---------------------

.. automodule:: hydra.agents.pool
   :members:
   :undoc-members:
   :show-inheritance:

Usage Examples
--------------

Basic Agent Creation
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.agents.base import CodeAgent
   
   # Create a new agent
   agent = CodeAgent("my_agent")
   
   # Generate code
   result = agent.generate_code("Create a Python function to calculate fibonacci")
   print(result)

Agent with Custom Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.agents.base import CodeAgent
   
   # Create agent with specific provider
   agent = CodeAgent(
       name="custom_agent",
       provider_type="claude_cli",
       config={
           "model": "claude-3-opus",
           "temperature": 0.7
       }
   )
   
   # Execute reasoning task
   reasoning = agent.reason("How should I approach building a REST API?")
   print(reasoning)

Hierarchical Agent System
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.agents.base import CodeAgent
   
   # Boss agent spawns employees
   boss = CodeAgent("boss")
   
   # Complex task that will spawn sub-agents
   result = boss.generate_code('''
       Create a microservice with:
       1. FastAPI backend
       2. SQLAlchemy models  
       3. Authentication middleware
       4. Docker configuration
   ''')

Agent States and Lifecycle
---------------------------

Agents in Hydra have several states:

- **IDLE**: Agent is created but not executing tasks
- **THINKING**: Agent is processing a reasoning task
- **CODING**: Agent is generating code
- **SPAWNING**: Agent is creating sub-agents
- **COMPLETED**: Task execution finished
- **ERROR**: Agent encountered an error

Safety Controls
---------------

The agent system includes several safety mechanisms:

- **Depth Limiting**: Maximum 2 levels of agent hierarchy
- **Timeout Protection**: 30-second execution limits
- **Resource Monitoring**: CPU and memory usage tracking
- **Code Validation**: Generated code is syntax-checked

API Reference Details
--------------------

.. autoclass:: hydra.agents.base.CodeAgent
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.agents.claude_code_agent.ClaudeCodeAgent
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.agents.pool.AgentPool
   :members:
   :special-members: __init__
   :exclude-members: __weakref__