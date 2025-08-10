Provider Development Guide
==========================

This guide explains how to create custom AI provider integrations for Hydra.

Understanding Provider Architecture
------------------------------------

The provider system in Hydra is designed to be completely provider-agnostic,
allowing integration with any AI tool or service.

Base Provider Interface
~~~~~~~~~~~~~~~~~~~~~~~~

All providers must inherit from the ``InteractiveAIProvider`` base class:

.. code-block:: python

   from hydra.providers.interactive_base import InteractiveAIProvider
   
   class CustomProvider(InteractiveAIProvider):
       def start_session(self) -> str:
           """Initialize a new AI session."""
           pass
       
       def execute_task(self, session_id: str, task: str) -> str:
           """Execute a specific task in the session."""
           pass
       
       def handle_prompt(self, session_id: str, prompt: str) -> str:
           """Handle prompts from the AI tool."""
           pass
       
       def get_session_state(self, session_id: str) -> dict:
           """Get current session state."""
           pass
       
       def cleanup_session(self, session_id: str) -> None:
           """Clean up resources when session ends."""
           pass

Creating a Custom Provider
--------------------------

Step 1: Provider Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create your provider class in ``src/hydra/providers/``:

.. code-block:: python

   # src/hydra/providers/custom_provider.py
   import asyncio
   from typing import Optional, Dict, Any
   from hydra.providers.interactive_base import InteractiveAIProvider
   
   class CustomProvider(InteractiveAIProvider):
       def __init__(self, config: Dict[str, Any]):
           self.config = config
           self.sessions = {}
           
       def start_session(self) -> str:
           session_id = self._generate_session_id()
           self.sessions[session_id] = {
               'state': 'active',
               'history': [],
               'context': {}
           }
           return session_id
       
       def execute_task(self, session_id: str, task: str) -> str:
           if session_id not in self.sessions:
               raise ValueError(f"Session {session_id} not found")
           
           # Implement your AI interaction logic here
           response = self._call_ai_service(task)
           
           # Update session history
           self.sessions[session_id]['history'].append({
               'task': task,
               'response': response
           })
           
           return response
       
       def handle_prompt(self, session_id: str, prompt: str) -> str:
           # Handle interactive prompts
           return self._process_prompt(prompt)
       
       def get_session_state(self, session_id: str) -> dict:
           return self.sessions.get(session_id, {})
       
       def cleanup_session(self, session_id: str) -> None:
           if session_id in self.sessions:
               del self.sessions[session_id]

Step 2: Capability Declaration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Define provider capabilities in ``capability_manager.py``:

.. code-block:: python

   # Add to src/hydra/providers/capability_manager.py
   PROVIDER_CAPABILITIES = {
       'custom_provider': {
           'code_generation': True,
           'file_operations': True,
           'web_search': False,
           'image_generation': False,
           'max_context_length': 100000,
           'supports_streaming': True,
           'supports_tools': True
       }
   }

Step 3: Provider Discovery
~~~~~~~~~~~~~~~~~~~~~~~~~~

Register your provider for automatic discovery:

.. code-block:: python

   # Add to src/hydra/providers/discovery.py
   from hydra.providers.custom_provider import CustomProvider
   
   PROVIDER_REGISTRY = {
       'custom': CustomProvider,
       # ... other providers
   }

Step 4: Configuration Schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Define configuration requirements:

.. code-block:: yaml

   # config/providers/custom.yaml
   provider:
     name: custom
     type: interactive
     settings:
       api_key: ${CUSTOM_API_KEY}
       base_url: https://api.custom-ai.com
       timeout: 300
       max_retries: 3
       rate_limit:
         requests_per_minute: 60
         tokens_per_minute: 100000

Plugin-Based Providers
----------------------

For better isolation, create providers as plugins:

Directory Structure
~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   src/hydra/plugins/custom_provider/
   ├── __init__.py
   ├── plugin.yaml
   └── providers/
       ├── __init__.py
       └── custom_provider.py

Plugin Manifest
~~~~~~~~~~~~~~~

Create ``plugin.yaml`` to declare plugin capabilities:

.. code-block:: yaml

   # src/hydra/plugins/custom_provider/plugin.yaml
   name: custom-provider
   version: 1.0.0
   description: Custom AI Provider Integration
   
   capabilities:
     - code_generation
     - file_operations
     - session_management
   
   requirements:
     - custom-ai-sdk>=2.0.0
   
   configuration:
     api_key:
       type: string
       required: true
       env: CUSTOM_API_KEY
     base_url:
       type: string
       default: https://api.custom-ai.com
   
   entry_point: providers.custom_provider:CustomProvider

Testing Your Provider
---------------------

Unit Tests
~~~~~~~~~~

Create comprehensive tests for your provider:

.. code-block:: python

   # tests/unit/test_custom_provider.py
   import pytest
   from hydra.providers.custom_provider import CustomProvider
   
   class TestCustomProvider:
       @pytest.fixture
       def provider(self):
           config = {'api_key': 'test-key'}
           return CustomProvider(config)
       
       def test_start_session(self, provider):
           session_id = provider.start_session()
           assert session_id is not None
           assert session_id in provider.sessions
       
       def test_execute_task(self, provider):
           session_id = provider.start_session()
           response = provider.execute_task(session_id, "test task")
           assert response is not None
       
       def test_cleanup_session(self, provider):
           session_id = provider.start_session()
           provider.cleanup_session(session_id)
           assert session_id not in provider.sessions

Integration Tests
~~~~~~~~~~~~~~~~~

Test provider integration with the system:

.. code-block:: python

   # tests/integration/test_custom_provider_integration.py
   import pytest
   from hydra.orchestrator.project_orchestrator import ProjectOrchestrator
   
   def test_custom_provider_workflow():
       orchestrator = ProjectOrchestrator(provider='custom')
       result = orchestrator.execute_project({
           'name': 'test-project',
           'tasks': ['generate code', 'write tests']
       })
       assert result['status'] == 'success'

Mock Provider for Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a mock version for testing without API calls:

.. code-block:: python

   # tests/mocks/mock_custom_provider.py
   class MockCustomProvider:
       def execute_task(self, session_id: str, task: str) -> str:
           return f"Mock response for: {task}"

Advanced Features
-----------------

Streaming Responses
~~~~~~~~~~~~~~~~~~~

Implement streaming for real-time responses:

.. code-block:: python

   async def stream_execute(self, session_id: str, task: str):
       async for chunk in self._stream_ai_response(task):
           yield chunk

Connection Pooling
~~~~~~~~~~~~~~~~~~

Optimize performance with connection pools:

.. code-block:: python

   from hydra.providers.claude_connection_pool import ConnectionPool
   
   class CustomProvider(InteractiveAIProvider):
       def __init__(self, config):
           self.pool = ConnectionPool(max_connections=10)

Error Handling
~~~~~~~~~~~~~~

Implement robust error handling:

.. code-block:: python

   from hydra.recovery.error_handler import ErrorRecoveryManager
   
   def execute_task(self, session_id: str, task: str) -> str:
       try:
           return self._execute_internal(session_id, task)
       except Exception as e:
           self.error_manager.handle_error(e)
           return self._fallback_response(task)

Best Practices
--------------

1. **Session Management**
   
   - Always clean up sessions properly
   - Implement session timeouts
   - Store minimal session state

2. **Resource Management**
   
   - Use connection pooling for API calls
   - Implement rate limiting
   - Monitor resource usage

3. **Error Handling**
   
   - Gracefully handle API failures
   - Provide meaningful error messages
   - Implement retry logic with backoff

4. **Security**
   
   - Never log sensitive information
   - Validate all inputs
   - Use secure credential storage

5. **Performance**
   
   - Cache frequently used data
   - Use async operations where possible
   - Implement request batching

6. **Testing**
   
   - Write comprehensive unit tests
   - Create integration tests
   - Use mock providers for testing

Provider Examples
-----------------

The repository includes several provider implementations:

- **Claude CLI Provider**: Integration with Anthropic's Claude
- **Mock Provider**: For testing without API calls
- **OpenAI Provider**: Integration with OpenAI's GPT models
- **Venice Provider**: Integration with Venice API

Study these implementations for reference when creating your own provider.

Debugging Provider Issues
-------------------------

Common Issues and Solutions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Session Not Found**
   
   - Ensure session is created before use
   - Check session timeout settings
   - Verify session cleanup logic

2. **API Rate Limiting**
   
   - Implement exponential backoff
   - Use connection pooling
   - Add request queuing

3. **Memory Leaks**
   
   - Clean up sessions properly
   - Clear large objects from memory
   - Use weak references where appropriate

4. **Timeout Issues**
   
   - Adjust timeout settings
   - Implement heartbeat mechanism
   - Add progress indicators

Logging and Monitoring
~~~~~~~~~~~~~~~~~~~~~~

Enable detailed logging for debugging:

.. code-block:: python

   import logging
   
   logger = logging.getLogger(__name__)
   
   class CustomProvider(InteractiveAIProvider):
       def execute_task(self, session_id: str, task: str) -> str:
           logger.debug(f"Executing task in session {session_id}: {task}")
           # ... implementation
           logger.info(f"Task completed successfully")

Contributing Your Provider
--------------------------

To contribute your provider to the project:

1. Ensure comprehensive test coverage (>80%)
2. Add complete documentation
3. Follow code style guidelines
4. Submit a pull request with:
   
   - Provider implementation
   - Tests
   - Documentation
   - Example usage

Provider Certification
----------------------

Providers can be certified by meeting these criteria:

- ✅ Implements all required interface methods
- ✅ Passes integration test suite
- ✅ Handles errors gracefully
- ✅ Includes comprehensive documentation
- ✅ Demonstrates performance benchmarks
- ✅ Follows security best practices

Support and Resources
----------------------

- **Documentation**: Full API reference in ``docs/api/providers.rst``
- **Examples**: See ``examples/`` directory for usage examples
- **Community**: Join discussions in project issues
- **Support**: File issues for bugs or feature requests