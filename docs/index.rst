Hydra Agent System Documentation
==================================

Welcome to the comprehensive documentation for the Hydra self-replicating AI agent system.
Hydra enables autonomous code generation through a hierarchical agent architecture built on
modern AI technologies.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started:

   getting-started/index
   getting-started/installation
   getting-started/quickstart

.. toctree::
   :maxdepth: 2
   :caption: User Guide:

   user-guide/index
   user-guide/configuration
   user-guide/providers
   user-guide/workflows

.. toctree::
   :maxdepth: 2
   :caption: API Reference:

   api/index
   api/agents
   api/providers
   api/workflows
   api/utilities

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide:

   developer-guide/index
   developer-guide/provider-development
   developer-guide/architecture
   developer-guide/contributing

.. toctree::
   :maxdepth: 2
   :caption: Examples:

   examples/index
   examples/basic-usage
   examples/custom-providers
   examples/advanced-workflows

.. toctree::
   :maxdepth: 2
   :caption: Troubleshooting:

   troubleshooting/index
   troubleshooting/common-issues
   troubleshooting/debugging

Key Features
============

* **Hierarchical Agent System**: Boss and employee agents with controlled spawning
* **Provider Abstraction**: Support for multiple AI providers (Claude, OpenAI, etc.)
* **Safety First**: Built-in security controls and sandboxing
* **Parallel Execution**: Concurrent task processing with intelligent scheduling
* **Persistent State**: Session management and recovery capabilities

Quick Start
===========

.. code-block:: python

   from hydra import CodeAgent, execute_workflow

   # Create a code generation agent
   agent = CodeAgent("my_agent")
   
   # Execute a simple task
   result = agent.generate_code("Create a FastAPI hello world endpoint")
   
   # Run a complex workflow
   workflow_result = execute_workflow({
       "task": "Build a REST API with authentication",
       "requirements": ["FastAPI", "SQLAlchemy", "JWT"]
   })

Architecture Overview
====================

The Hydra system consists of several key components:

* **Agent Layer**: CodeAgent, BossAgent, EmployeeAgent hierarchy
* **Provider Layer**: Abstraction for different AI services
* **Workflow Engine**: LangGraph-based orchestration
* **Safety Layer**: Security controls and validation
* **Persistence Layer**: State management and recovery

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`