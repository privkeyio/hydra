Workflows API
=============

The workflow system orchestrates complex multi-step tasks using LangGraph,
providing automatic task decomposition and parallel execution.

Workflow Engine
---------------

.. automodule:: hydra.workflows.engine
   :members:
   :undoc-members:
   :show-inheritance:

Parallel Execution Engine  
-------------------------

.. automodule:: hydra.workflows.parallel_engine
   :members:
   :undoc-members:
   :show-inheritance:

Usage Examples
--------------

Basic Workflow Execution
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra import execute_workflow
   
   # Define workflow configuration
   workflow_config = {
       "task": "Build a web application",
       "requirements": [
           "Frontend with React",
           "Backend with FastAPI", 
           "Database with PostgreSQL",
           "Docker deployment"
       ],
       "output_format": "structured_project"
   }
   
   # Execute workflow
   result = execute_workflow(workflow_config)
   print(f"Generated {len(result.files)} files")

Advanced Workflow Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.workflows.engine import WorkflowEngine
   
   # Create workflow engine with custom settings
   engine = WorkflowEngine(
       max_depth=2,
       parallel_limit=3,
       timeout=300,
       safety_checks=True
   )
   
   # Define complex workflow
   workflow = {
       "task": "Create microservice architecture",
       "components": {
           "api_gateway": {
               "technology": "FastAPI",
               "features": ["authentication", "rate_limiting"]
           },
           "user_service": {
               "technology": "FastAPI + SQLAlchemy",
               "database": "PostgreSQL"
           },
           "notification_service": {
               "technology": "FastAPI + Celery",
               "queue": "Redis"
           }
       },
       "infrastructure": {
           "containerization": "Docker",
           "orchestration": "Docker Compose",
           "monitoring": "Prometheus + Grafana"
       }
   }
   
   # Execute with custom engine
   result = engine.execute(workflow)

Parallel Task Execution
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.workflows.parallel_engine import ParallelExecutionEngine
   
   # Create parallel engine
   engine = ParallelExecutionEngine(
       max_workers=4,
       max_agents=8
   )
   
   # Submit multiple tasks
   tasks = [
       "Create user authentication module",
       "Implement data models", 
       "Set up API routing",
       "Add error handling"
   ]
   
   # Execute tasks in parallel
   task_ids = []
   for task in tasks:
       task_id = engine.submit_task("parallel_task", task)
       task_ids.append(task_id)
   
   # Wait for completion
   engine.wait_for_completion(timeout=120)
   
   # Get results
   results = [engine.get_task_result(task_id) for task_id in task_ids]

Workflow States and Monitoring
------------------------------

Workflow Execution States
~~~~~~~~~~~~~~~~~~~~~~~~~~

Workflows progress through these states:

- **PENDING**: Workflow queued for execution
- **PLANNING**: Task decomposition in progress
- **EXECUTING**: Tasks being executed
- **SPAWNING**: Creating sub-workflows/agents
- **AGGREGATING**: Combining results
- **COMPLETED**: Workflow finished successfully
- **FAILED**: Workflow encountered errors

Monitoring Progress
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.workflows.engine import WorkflowEngine
   
   engine = WorkflowEngine()
   
   # Start workflow execution
   workflow_id = engine.start_workflow(config)
   
   # Monitor progress
   while True:
       status = engine.get_workflow_status(workflow_id)
       print(f"Status: {status.state}, Progress: {status.progress}%")
       
       if status.state in ["COMPLETED", "FAILED"]:
           break
       
       time.sleep(2)
   
   # Get final results
   result = engine.get_workflow_result(workflow_id)

Workflow Safety Controls
------------------------

The workflow system includes comprehensive safety mechanisms:

Depth Control
~~~~~~~~~~~~~

- Maximum workflow nesting depth (default: 2 levels)
- Prevents infinite recursion
- Configurable per workflow

Resource Limits
~~~~~~~~~~~~~~~

- CPU usage monitoring
- Memory consumption tracking  
- Execution timeout enforcement
- Concurrent task limits

Task Validation
~~~~~~~~~~~~~~~

- Input validation before execution
- Output format verification
- Code safety checks
- Dependency validation

Error Recovery
~~~~~~~~~~~~~~

- Automatic retry with exponential backoff
- Partial result preservation
- Graceful degradation
- Rollback capabilities

API Reference Details
--------------------

.. autoclass:: hydra.workflows.engine.WorkflowEngine
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.workflows.parallel_engine.ParallelExecutionEngine
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autofunction:: hydra.workflows.engine.execute_workflow

Workflow Configuration Schema
-----------------------------

.. code-block:: json

   {
       "task": "string - Main task description",
       "requirements": ["array of specific requirements"],
       "output_format": "string - desired output format", 
       "constraints": {
           "max_depth": "integer - maximum nesting depth",
           "timeout": "integer - execution timeout in seconds",
           "parallel_limit": "integer - max parallel tasks"
       },
       "context": {
           "project_type": "string - type of project",
           "technologies": ["array of preferred technologies"],
           "environment": "string - target environment"
       }
   }