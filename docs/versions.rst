Version History
===============

This document tracks the version history and release notes for Hydra.

Current Version
---------------

**v1.0.0** - Latest Stable Release

Version Scheme
--------------

Hydra follows `Semantic Versioning <https://semver.org/>`_:

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions  
- **PATCH** version for backwards-compatible bug fixes

Release Channels
----------------

**Stable Releases**
   Production-ready versions with full testing and documentation

**Beta Releases**
   Feature-complete versions undergoing final testing

**Development Builds**
   Nightly builds from the main branch (use with caution)

Version 1.0.0 (Current)
-----------------------

**Release Date:** 2024-01-15

**Major Features:**

- Complete provider abstraction system
- Enhanced safety framework with git operation controls
- Persistent state management with .hydra directory
- Plugin architecture for AI providers
- Universal prompt detection system
- Comprehensive error recovery mechanisms
- Resource monitoring dashboard
- Hierarchical configuration management
- Provider capability negotiation
- Session pooling with warm start
- Connection pooling for providers
- Async execution pipeline
- Intelligent file conflict resolution
- Dynamic work stealing scheduler
- Batch processing for small tickets
- Distributed execution support
- Testing infrastructure enhancements
- Session backend abstraction (tmux-independent)
- Full documentation system

**Provider Support:**

- Claude CLI (Anthropic)
- OpenAI GPT models
- Venice API
- Mock provider for testing
- Custom provider framework

**Breaking Changes:**

- None (initial release)

Version 0.9.0 (Beta)
--------------------

**Release Date:** 2023-12-01

**Features:**

- Initial provider system
- Basic workflow engine
- Claude CLI integration
- File safety controls
- Simple state management

**Known Issues:**

- Hard-coded provider paths
- Limited error recovery
- No session pooling
- Single-threaded execution

Version 0.8.0 (Alpha)
---------------------

**Release Date:** 2023-10-15

**Features:**

- Proof of concept implementation
- Basic agent spawning
- Simple task execution
- Initial safety checks

**Limitations:**

- Claude-only support
- No plugin system
- Limited documentation
- Minimal testing

Upgrade Guide
-------------

Upgrading from 0.9.x to 1.0.0
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Configuration Migration:**

   .. code-block:: bash
   
      # Backup old configuration
      cp -r config/ config.backup/
      
      # Run migration script
      python -m hydra.migrate_config

2. **Provider Updates:**

   - Old provider code needs updating to new interface
   - Use ``InteractiveAIProvider`` base class
   - Update capability declarations

3. **State Directory:**

   - Migrate from ``.claude/`` to ``.hydra/``
   - Session format has changed
   - Run state migration tool

4. **API Changes:**

   - ``CodeAgent`` constructor signature changed
   - Workflow engine uses new state format
   - Provider discovery is now automatic

Deprecation Notices
-------------------

**Deprecated in 1.0.0:**

- Direct Claude CLI calls (use provider interface)
- Hardcoded provider paths (use discovery)
- Legacy state format (use JSON state)
- Synchronous execution (use async)

**Removal Timeline:**

- v1.1.0: Deprecation warnings added
- v1.2.0: Features moved to legacy module
- v2.0.0: Complete removal

Compatibility Matrix
--------------------

.. list-table:: Python Version Compatibility
   :header-rows: 1
   
   * - Hydra Version
     - Python 3.9
     - Python 3.10
     - Python 3.11
     - Python 3.12
   * - 1.0.0
     - ❌
     - ✅
     - ✅
     - ✅
   * - 0.9.0
     - ✅
     - ✅
     - ✅
     - ❌
   * - 0.8.0
     - ✅
     - ✅
     - ❌
     - ❌

.. list-table:: Provider Compatibility
   :header-rows: 1
   
   * - Hydra Version
     - Claude CLI
     - OpenAI
     - Venice
     - Custom
   * - 1.0.0
     - ✅
     - ✅
     - ✅
     - ✅
   * - 0.9.0
     - ✅
     - ❌
     - ❌
     - ❌
   * - 0.8.0
     - ✅
     - ❌
     - ❌
     - ❌

Long-term Support
-----------------

**LTS Versions:**

- v1.0.x - Supported until 2025-01-15
- v2.0.x - (Planned) Support until 2026

**Support Policy:**

- LTS versions receive security updates for 1 year
- Bug fixes for 6 months after release
- Documentation updates throughout support period

Release Process
---------------

1. **Development Phase**
   
   - Feature development in feature branches
   - Continuous integration testing
   - Code review and approval

2. **Beta Phase**
   
   - Feature freeze
   - Extensive testing
   - Documentation completion
   - Community feedback

3. **Release Candidate**
   
   - Final testing
   - Performance validation
   - Security audit
   - Documentation review

4. **Stable Release**
   
   - Version tagging
   - Package publishing
   - Documentation deployment
   - Announcement

Version Detection
-----------------

Check installed version:

.. code-block:: bash

   # Command line
   python -m hydra.cli --version
   
   # Python code
   import hydra
   print(hydra.__version__)
   
   # Package info
   pip show hydra-agents

Roadmap
-------

**Version 1.1.0 (Planned)**

- GraphQL API support
- Enhanced monitoring dashboard
- Additional provider integrations
- Performance optimizations

**Version 1.2.0 (Planned)**

- Web UI for management
- Kubernetes operator
- Multi-region support
- Advanced caching strategies

**Version 2.0.0 (Future)**

- Complete async rewrite
- Native cloud deployment
- AI model fine-tuning support
- Advanced workflow orchestration

Contributing to Releases
------------------------

See :doc:`developer-guide/contributing` for information on:

- How to contribute features
- Release branch workflow
- Version bump procedures
- Release testing requirements

Release Notes Archive
---------------------

Full release notes for all versions are available at:

- GitHub Releases page
- CHANGELOG.md in repository root
- Documentation archive for each version

Versioning Best Practices
--------------------------

For Library Users
~~~~~~~~~~~~~~~~~

- Pin to specific versions in production
- Test upgrades in staging first
- Review breaking changes before upgrading
- Keep dependencies up to date

For Contributors
~~~~~~~~~~~~~~~~

- Follow semantic versioning strictly
- Document all breaking changes
- Provide migration guides
- Maintain backwards compatibility when possible

Support Channels
----------------

- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: Community support
- **Security**: security@hydra-project.org
- **Commercial**: enterprise@hydra-project.org