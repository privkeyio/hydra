Developer Guide
===============

This guide provides comprehensive information for developers who want to understand,
extend, or contribute to the Hydra agent system.

.. toctree::
   :maxdepth: 2

   architecture
   provider-development
   contributing

Overview
--------

Hydra is designed with extensibility in mind. The modular architecture allows
developers to:

- Create custom AI provider integrations
- Extend workflow capabilities
- Add new safety controls
- Implement custom templates
- Integrate monitoring systems

Getting Started with Development
--------------------------------

Prerequisites
~~~~~~~~~~~~~

- Python 3.11 or higher
- Git for version control
- Basic understanding of async/await patterns
- Familiarity with AI/LLM concepts

Development Setup
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Clone the repository
   git clone <repository-url>
   cd hydra
   
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -e .[dev]
   
   # Run tests
   pytest
   
   # Run linting
   ruff check src/
   
   # Start development server
   python -m hydra.cli --help

Code Organization
-----------------

The codebase follows a modular structure:

.. code-block:: text

   src/hydra/
   ├── agents/              # Agent implementations
   ├── providers/           # AI provider integrations
   ├── workflows/           # Workflow engine
   ├── safety/              # Security and validation
   ├── templates/           # Code generation templates
   ├── monitoring/          # Metrics and observability
   ├── state/               # State management
   └── cli.py               # Command-line interface

Key Design Principles
---------------------

1. **Modularity**: Components are loosely coupled and easily replaceable
2. **Safety First**: All operations are validated and sandboxed
3. **Provider Agnostic**: Core logic works with any AI provider
4. **Async by Default**: Non-blocking operations for better performance
5. **Observable**: Comprehensive logging and metrics
6. **Testable**: Extensive test coverage with mocks

Development Workflow
--------------------

1. **Feature Planning**: Discuss new features in issues
2. **Implementation**: Create feature branches
3. **Testing**: Write tests before implementation (TDD)
4. **Review**: Submit pull requests for code review
5. **Documentation**: Update docs with new features
6. **Release**: Follow semantic versioning

Core Concepts for Developers
-----------------------------

Agent Lifecycle
~~~~~~~~~~~~~~~

Understanding the agent lifecycle is crucial for development:

.. code-block:: python

   # Agent states
   IDLE → THINKING → CODING → SPAWNING → COMPLETED
                  ↓           ↓         ↓
                ERROR ←── ERROR ←── ERROR

Provider Interface
~~~~~~~~~~~~~~~~~~

All providers must implement the base interface:

.. code-block:: python

   class BaseProvider:
       def start_session(self) -> str: ...
       def execute_task(self, session_id: str, task: str) -> str: ...
       def handle_prompt(self, session_id: str, prompt: str) -> str: ...
       def get_session_state(self, session_id: str) -> dict: ...
       def cleanup_session(self, session_id: str) -> None: ...

Workflow States
~~~~~~~~~~~~~~~

Workflows progress through defined states:

.. code-block:: python

   # Workflow execution states
   PENDING → PLANNING → EXECUTING → AGGREGATING → COMPLETED
           ↓          ↓          ↓             ↓
         ERROR ←── ERROR ←── ERROR ←── ERROR

Common Development Tasks
------------------------

Adding a New Provider
~~~~~~~~~~~~~~~~~~~~~

1. Create provider class inheriting from BaseProvider
2. Implement required methods
3. Add provider configuration schema
4. Write comprehensive tests
5. Update documentation

Adding Workflow Steps
~~~~~~~~~~~~~~~~~~~~~

1. Define new graph nodes in workflow engine
2. Implement step logic with error handling
3. Add state transitions
4. Test with various scenarios
5. Document new capabilities

Extending Safety Controls
~~~~~~~~~~~~~~~~~~~~~~~~~

1. Identify new security requirements
2. Implement validation logic
3. Add to safety pipeline
4. Test with malicious inputs
5. Document security implications

Testing Strategy
----------------

The project uses a comprehensive testing approach:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete workflows
- **Performance Tests**: Validate scalability
- **Security Tests**: Verify safety controls

Debugging Tips
--------------

1. **Enable Debug Logging**: Set `HYDRA_LOG_LEVEL=DEBUG`
2. **Use Mock Providers**: Test without real AI calls
3. **Inspect State**: Check agent and workflow states
4. **Monitor Resources**: Watch CPU/memory usage
5. **Review Logs**: Check structured logs for issues

Performance Considerations
--------------------------

When developing new features, consider:

- **Async Operations**: Use async/await for I/O operations
- **Connection Pooling**: Reuse expensive connections
- **Caching**: Cache frequently accessed data
- **Resource Limits**: Implement proper timeouts
- **Memory Management**: Avoid memory leaks

Security Guidelines
-------------------

All code must follow security best practices:

- **Input Validation**: Validate all external inputs
- **Output Sanitization**: Clean all outputs
- **Privilege Separation**: Use least privilege principle
- **Secure Defaults**: Safe defaults for all configurations
- **Audit Trails**: Log security-relevant events

Contributing Guidelines
-----------------------

Please see :doc:`contributing` for detailed contribution guidelines including:

- Code style requirements
- Testing standards
- Documentation expectations
- Review process
- Release procedures