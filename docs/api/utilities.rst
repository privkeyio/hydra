Utilities API
=============

Utility modules provide supporting functionality for configuration management,
validation, monitoring, and other system operations.

Configuration Management
------------------------

.. automodule:: hydra.config
   :members:
   :undoc-members:
   :show-inheritance:

Validation
----------

.. automodule:: hydra.validators
   :members:
   :undoc-members:
   :show-inheritance:

Monitoring and Metrics
----------------------

.. automodule:: hydra.monitoring
   :members:
   :undoc-members:
   :show-inheritance:

Dashboard
---------

.. automodule:: hydra.dashboard
   :members:
   :undoc-members:
   :show-inheritance:

Security and Safety
-------------------

Security Module
~~~~~~~~~~~~~~~

.. automodule:: hydra.security
   :members:
   :undoc-members:
   :show-inheritance:

Safety Guardrails
~~~~~~~~~~~~~~~~~

.. automodule:: hydra.safety.guardrails
   :members:
   :undoc-members:
   :show-inheritance:

Caching
-------

.. automodule:: hydra.cache
   :members:
   :undoc-members:
   :show-inheritance:

State Management
----------------

Project State
~~~~~~~~~~~~~

.. automodule:: hydra.state.project_state
   :members:
   :undoc-members:
   :show-inheritance:

Session Management
~~~~~~~~~~~~~~~~~~

.. automodule:: hydra.persistence.session_manager
   :members:
   :undoc-members:
   :show-inheritance:

Templates and Specifications
----------------------------

Task Specifications
~~~~~~~~~~~~~~~~~~~

.. automodule:: hydra.specifications.task_spec
   :members:
   :undoc-members:
   :show-inheritance:

Template Engine
~~~~~~~~~~~~~~~

.. automodule:: hydra.templates.template_engine
   :members:
   :undoc-members:
   :show-inheritance:

Quality Assurance
-----------------

.. automodule:: hydra.quality.gate_runner
   :members:
   :undoc-members:
   :show-inheritance:

CLI Interface
-------------

.. automodule:: hydra.cli
   :members:
   :undoc-members:
   :show-inheritance:

Usage Examples
--------------

Configuration Management
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.config import get_config, set_config
   
   # Load configuration
   config = get_config()
   print(f"Provider: {config.llm_provider.name}")
   
   # Update configuration
   set_config("llm_provider.temperature", 0.7)
   set_config("security.sandbox_enabled", True)

Validation
~~~~~~~~~~

.. code-block:: python

   from hydra.validators import validate_task_input, validate_code_output
   
   # Validate task input
   task = {
       "description": "Create a REST API",
       "requirements": ["FastAPI", "authentication"]
   }
   
   is_valid, errors = validate_task_input(task)
   if not is_valid:
       print(f"Validation errors: {errors}")
   
   # Validate generated code
   code = '''
   def hello():
       return "Hello, World!"
   '''
   
   is_safe, issues = validate_code_output(code)
   if not is_safe:
       print(f"Safety issues: {issues}")

Monitoring
~~~~~~~~~~

.. code-block:: python

   from hydra.monitoring import get_system_metrics, start_monitoring
   
   # Get current metrics
   metrics = get_system_metrics()
   print(f"CPU: {metrics.cpu_percent}%")
   print(f"Memory: {metrics.memory_percent}%") 
   print(f"Active agents: {metrics.active_agents}")
   
   # Start continuous monitoring
   monitor = start_monitoring(interval=30)  # 30 second intervals

Caching
~~~~~~~

.. code-block:: python

   from hydra.cache import get_cache, cache_result
   
   # Get cached result
   cache = get_cache()
   result = cache.get("task_123")
   
   if result is None:
       # Generate new result
       result = generate_code("Create hello world")
       
       # Cache for future use
       cache_result("task_123", result, ttl=3600)  # 1 hour TTL

State Management
~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.state.project_state import ProjectStateManager
   
   # Create state manager
   state_manager = ProjectStateManager("/path/to/project")
   
   # Save project state
   state = {
       "agents": ["agent_1", "agent_2"],
       "tasks": ["task_1", "task_2"],
       "progress": 0.75
   }
   state_manager.save_state(state)
   
   # Load state later
   restored_state = state_manager.load_state()

Template System
~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.templates.template_engine import TemplateEngine
   
   # Create template engine
   engine = TemplateEngine()
   
   # List available templates
   templates = engine.list_templates()
   print(f"Available: {templates}")
   
   # Generate from template
   result = engine.generate_from_template(
       "fastapi_rest_api",
       variables={
           "project_name": "my_api",
           "database": "postgresql",
           "auth_enabled": True
       }
   )

API Reference Details
--------------------

.. autoclass:: hydra.config.Config
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.monitoring.SystemMonitor
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.cache.CacheManager
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.state.project_state.ProjectStateManager
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.templates.template_engine.TemplateEngine
   :members:
   :special-members: __init__
   :exclude-members: __weakref__