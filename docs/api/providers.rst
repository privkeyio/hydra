Providers API
=============

The provider system abstracts different AI services, enabling Hydra to work with
multiple AI backends while maintaining a consistent interface.

Provider Base Classes
---------------------

.. automodule:: hydra.providers.base
   :members:
   :undoc-members:
   :show-inheritance:

Interactive Base Provider
-------------------------

.. automodule:: hydra.providers.interactive_base
   :members:
   :undoc-members:
   :show-inheritance:

Claude Providers
----------------

Claude CLI Provider
~~~~~~~~~~~~~~~~~~~

.. automodule:: hydra.providers.claude_cli
   :members:
   :undoc-members:
   :show-inheritance:

Enhanced Claude CLI Provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: hydra.providers.claude_cli_enhanced
   :members:
   :undoc-members:
   :show-inheritance:

Claude Tmux Provider
~~~~~~~~~~~~~~~~~~~~

.. automodule:: hydra.providers.claude_tmux
   :members:
   :undoc-members:
   :show-inheritance:

Other Providers
---------------

Anthropic Direct Provider
~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: hydra.providers.anthropic
   :members:
   :undoc-members:
   :show-inheritance:

OpenAI Provider
~~~~~~~~~~~~~~~

.. automodule:: hydra.providers.openai_provider
   :members:
   :undoc-members:
   :show-inheritance:

Venice Provider
~~~~~~~~~~~~~~~

.. automodule:: hydra.providers.venice
   :members:
   :undoc-members:
   :show-inheritance:

Mock Provider
~~~~~~~~~~~~~

.. automodule:: hydra.providers.mock_provider
   :members:
   :undoc-members:
   :show-inheritance:

Provider Factory
----------------

.. automodule:: hydra.providers.factory
   :members:
   :undoc-members:
   :show-inheritance:

Usage Examples
--------------

Basic Provider Usage
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.providers.factory import ProviderFactory
   
   # Create a Claude provider
   provider = ProviderFactory.create_provider("claude_cli")
   
   # Start session
   session_id = provider.start_session()
   
   # Execute task
   result = provider.execute_task(
       session_id, 
       "Write a Python function to sort a list"
   )
   
   print(result)

Custom Provider Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.providers.claude_cli import ClaudeCLIProvider
   
   # Configure provider with custom settings
   provider = ClaudeCLIProvider(config={
       "model": "claude-3-opus",
       "temperature": 0.3,
       "max_tokens": 4000,
       "timeout": 60
   })
   
   # Use configured provider
   session_id = provider.start_session()
   result = provider.execute_task(session_id, "Create a REST API")

Provider Switching
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from hydra.providers.factory import ProviderFactory
   
   # Try multiple providers with fallback
   providers = ["claude_cli", "anthropic", "openai"]
   
   for provider_name in providers:
       try:
           provider = ProviderFactory.create_provider(provider_name)
           session_id = provider.start_session()
           result = provider.execute_task(session_id, "Generate code")
           break
       except Exception as e:
           print(f"Provider {provider_name} failed: {e}")
           continue

Provider Interface
------------------

All providers must implement the base provider interface:

Essential Methods
~~~~~~~~~~~~~~~~~

- ``start_session()``: Initialize a new session
- ``execute_task()``: Execute a task in a session  
- ``handle_prompt()``: Handle interactive prompts
- ``get_session_state()``: Retrieve session state
- ``cleanup_session()``: Clean up session resources

Optional Methods
~~~~~~~~~~~~~~~~

- ``stream_response()``: Stream responses for long tasks
- ``validate_config()``: Validate provider configuration
- ``health_check()``: Check provider health status

Capabilities System
-------------------

Providers declare their capabilities through metadata:

.. code-block:: python

   {
       "capabilities": {
           "code_generation": True,
           "interactive_mode": True,
           "streaming": False,
           "file_operations": True,
           "session_persistence": True
       },
       "models": ["claude-3-opus", "claude-3-sonnet"],
       "max_tokens": 8192,
       "timeout": 120
   }

API Reference Details
--------------------

.. autoclass:: hydra.providers.base.BaseProvider
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.providers.interactive_base.InteractiveAIProvider
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.providers.claude_cli.ClaudeCLIProvider
   :members:
   :special-members: __init__
   :exclude-members: __weakref__

.. autoclass:: hydra.providers.factory.ProviderFactory
   :members:
   :special-members: __init__
   :exclude-members: __weakref__