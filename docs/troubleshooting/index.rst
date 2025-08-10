Troubleshooting Guide
=====================

This guide helps you diagnose and resolve common issues with the Hydra system.

Quick Diagnostics
-----------------

Run the diagnostic command to check system health:

.. code-block:: bash

   python -m hydra.cli diagnose

Common Issues and Solutions
---------------------------

Installation Issues
~~~~~~~~~~~~~~~~~~~

**Problem: Module not found errors**

.. code-block:: text

   ModuleNotFoundError: No module named 'hydra'

**Solution:**

.. code-block:: bash

   # Ensure correct installation
   pip install -e .
   
   # Verify installation
   python -c "import hydra; print(hydra.__version__)"

**Problem: Dependency conflicts**

.. code-block:: text

   ERROR: pip's dependency resolver found conflicts

**Solution:**

.. code-block:: bash

   # Use virtual environment
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

Provider Issues
~~~~~~~~~~~~~~~

**Problem: Provider not found**

.. code-block:: text

   ValueError: Provider 'custom' not found in registry

**Solution:**

1. Check provider is installed:

   .. code-block:: bash
   
      python -c "from hydra.providers.discovery import list_providers; print(list_providers())"

2. Verify provider configuration:

   .. code-block:: bash
   
      cat config/providers/custom.yaml

3. Register provider manually:

   .. code-block:: python
   
      from hydra.providers.discovery import register_provider
      from my_provider import CustomProvider
      register_provider('custom', CustomProvider)

**Problem: Claude CLI not responding**

.. code-block:: text

   TimeoutError: Claude CLI session timed out

**Solution:**

1. Check Claude CLI is installed:

   .. code-block:: bash
   
      which claude
      # or
      ls ~/.claude/local/claude

2. Verify Claude CLI works standalone:

   .. code-block:: bash
   
      claude --version

3. Increase timeout settings:

   .. code-block:: yaml
   
      # config/providers/claude.yaml
      provider:
        timeout: 600  # Increase from default 300

**Problem: API rate limiting**

.. code-block:: text

   RateLimitError: API rate limit exceeded

**Solution:**

1. Implement exponential backoff:

   .. code-block:: python
   
      # In your configuration
      retry_config:
        max_attempts: 5
        base_delay: 1.0
        max_delay: 60.0

2. Use connection pooling:

   .. code-block:: yaml
   
      # config/providers/provider.yaml
      connection_pool:
        max_connections: 10
        max_keepalive: 300

Session Management Issues
~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem: Session not found**

.. code-block:: text

   SessionNotFoundError: Session 'abc123' does not exist

**Solution:**

1. Check session state:

   .. code-block:: python
   
      from hydra.persistence.session_manager import SessionManager
      manager = SessionManager()
      print(manager.list_sessions())

2. Recover lost session:

   .. code-block:: bash
   
      python -m hydra.cli recover-session --session-id abc123

**Problem: Session state corruption**

.. code-block:: text

   JSONDecodeError: Session state file corrupted

**Solution:**

1. Clear corrupted state:

   .. code-block:: bash
   
      rm -rf .hydra/sessions/corrupted_session_id
      
2. Restore from backup:

   .. code-block:: bash
   
      cp .hydra/sessions/archive/session_backup.json .hydra/sessions/

Memory and Performance Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem: High memory usage**

.. code-block:: text

   MemoryError: Unable to allocate memory

**Solution:**

1. Check resource limits:

   .. code-block:: python
   
      from hydra.monitoring.resource_tracker import ResourceTracker
      tracker = ResourceTracker()
      print(tracker.get_stats())

2. Configure memory limits:

   .. code-block:: yaml
   
      # config/default.yaml
      resource_limits:
        max_memory_mb: 4096
        max_sessions: 10

3. Enable garbage collection:

   .. code-block:: python
   
      import gc
      gc.collect()

**Problem: Slow execution**

**Solution:**

1. Enable performance profiling:

   .. code-block:: bash
   
      HYDRA_PROFILE=1 python -m hydra.cli execute task

2. Check for bottlenecks:

   .. code-block:: python
   
      from hydra.monitoring import get_metrics
      print(get_metrics())

3. Optimize configuration:

   .. code-block:: yaml
   
      # Enable parallel execution
      parallel:
        enabled: true
        max_workers: 4

File System Issues
~~~~~~~~~~~~~~~~~~

**Problem: Permission denied**

.. code-block:: text

   PermissionError: [Errno 13] Permission denied: '/path/to/file'

**Solution:**

1. Check file permissions:

   .. code-block:: bash
   
      ls -la /path/to/file
      chmod 644 /path/to/file

2. Verify sandbox configuration:

   .. code-block:: python
   
      from hydra.safety.security_manager import SecurityManager
      manager = SecurityManager()
      print(manager.allowed_paths)

**Problem: File lock conflicts**

.. code-block:: text

   FileLockError: Could not acquire lock on file

**Solution:**

1. Clear stale locks:

   .. code-block:: bash
   
      rm .hydra/locks/*.lock

2. Use lock timeout:

   .. code-block:: python
   
      from hydra.safety.file_lock import FileLock
      with FileLock(path, timeout=30):
          # operations

Workflow Execution Issues
~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem: Workflow stuck**

.. code-block:: text

   WorkflowTimeoutError: Workflow exceeded maximum execution time

**Solution:**

1. Check workflow state:

   .. code-block:: python
   
      from hydra.workflows.engine import get_workflow_state
      state = get_workflow_state(workflow_id)
      print(state)

2. Increase timeout:

   .. code-block:: yaml
   
      workflow:
        timeout: 3600  # 1 hour

3. Enable debug logging:

   .. code-block:: bash
   
      HYDRA_LOG_LEVEL=DEBUG python -m hydra.cli execute

**Problem: Circular dependencies**

.. code-block:: text

   CircularDependencyError: Task A → B → C → A

**Solution:**

1. Visualize dependencies:

   .. code-block:: python
   
      from hydra.orchestrator import visualize_dependencies
      visualize_dependencies(project_spec)

2. Break circular reference:

   .. code-block:: yaml
   
      tasks:
        - name: task_a
          depends_on: []  # Remove circular dependency

Database Issues
~~~~~~~~~~~~~~~

**Problem: Database connection failed**

.. code-block:: text

   DatabaseError: Could not connect to database

**Solution:**

1. Check database URL:

   .. code-block:: bash
   
      echo $DATABASE_URL
      # Should be: sqlite:///hydra.db or postgresql://...

2. Initialize database:

   .. code-block:: bash
   
      alembic upgrade head

3. Test connection:

   .. code-block:: python
   
      from hydra.models.db import test_connection
      test_connection()

Redis/Cache Issues
~~~~~~~~~~~~~~~~~~

**Problem: Redis connection refused**

.. code-block:: text

   RedisConnectionError: Connection refused

**Solution:**

1. Start Redis:

   .. code-block:: bash
   
      redis-server
      # or
      docker run -d -p 6379:6379 redis

2. Verify connection:

   .. code-block:: bash
   
      redis-cli ping
      # Should return: PONG

3. Configure Redis URL:

   .. code-block:: bash
   
      export REDIS_URL=redis://localhost:6379/0

Testing Issues
~~~~~~~~~~~~~~

**Problem: Tests failing with mock provider**

.. code-block:: text

   AssertionError: Mock provider not returning expected response

**Solution:**

1. Set test environment:

   .. code-block:: bash
   
      export LLM_PROVIDER=mock
      export TESTING=1

2. Clear test cache:

   .. code-block:: bash
   
      rm -rf .pytest_cache/
      rm -rf htmlcov/

3. Run specific test:

   .. code-block:: bash
   
      pytest tests/unit/test_specific.py -xvs

Debugging Techniques
--------------------

Enable Debug Logging
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Set environment variable
   export HYDRA_LOG_LEVEL=DEBUG
   
   # Or in Python
   import logging
   logging.basicConfig(level=logging.DEBUG)

Use Interactive Debugger
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Add breakpoint in code
   import pdb; pdb.set_trace()
   
   # Or use IPython
   from IPython import embed; embed()

Monitor System Resources
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Watch resource usage
   watch -n 1 'ps aux | grep hydra'
   
   # Monitor logs
   tail -f logs/hydra.log

Check Configuration
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.config import get_config
   config = get_config()
   print(config.to_dict())

Environment Variables
---------------------

Key environment variables for troubleshooting:

.. code-block:: bash

   # Logging
   HYDRA_LOG_LEVEL=DEBUG
   HYDRA_LOG_FILE=/path/to/log
   
   # Providers
   LLM_PROVIDER=mock
   CLAUDE_CLI_PATH=/path/to/claude
   
   # Database
   DATABASE_URL=sqlite:///hydra.db
   REDIS_URL=redis://localhost:6379/0
   
   # Testing
   TESTING=1
   PYTEST_CURRENT_TEST=test_name
   
   # Performance
   HYDRA_PROFILE=1
   HYDRA_TRACE=1

Log File Locations
------------------

Default log locations:

.. code-block:: text

   logs/
   ├── hydra.log           # Main application log
   ├── agent_activity.log  # Agent operations
   ├── error.log           # Error messages
   └── performance.log     # Performance metrics
   
   .hydra/
   ├── logs/               # Session-specific logs
   └── debug/              # Debug information

Getting Help
------------

If you cannot resolve an issue:

1. **Search existing issues**: Check GitHub issues for similar problems
2. **Gather information**: Collect logs, configuration, and error messages
3. **Create minimal reproduction**: Isolate the problem
4. **File an issue**: Include all relevant details

Issue Template
~~~~~~~~~~~~~~

When reporting issues, include:

.. code-block:: markdown

   **Environment:**
   - OS: [e.g., Ubuntu 22.04]
   - Python version: [e.g., 3.11.0]
   - Hydra version: [e.g., 1.0.0]
   
   **Description:**
   Clear description of the problem
   
   **Steps to Reproduce:**
   1. Step one
   2. Step two
   3. ...
   
   **Expected Behavior:**
   What should happen
   
   **Actual Behavior:**
   What actually happens
   
   **Logs:**
   ```
   Relevant error messages
   ```
   
   **Configuration:**
   ```yaml
   Relevant config settings
   ```

Performance Optimization Tips
-----------------------------

1. **Use connection pooling** for API calls
2. **Enable caching** for frequently accessed data
3. **Batch operations** when possible
4. **Limit concurrent sessions** to prevent resource exhaustion
5. **Monitor and adjust timeouts** based on workload
6. **Use async operations** for I/O-bound tasks
7. **Profile code** to identify bottlenecks

Security Considerations
------------------------

When troubleshooting:

- **Never share API keys** in logs or issues
- **Sanitize sensitive data** before sharing
- **Use mock providers** for reproduction
- **Check file permissions** for security
- **Review audit logs** for security events