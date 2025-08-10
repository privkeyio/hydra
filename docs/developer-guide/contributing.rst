Contributing to Hydra
=====================

Thank you for your interest in contributing to Hydra! This guide will help you get started.

Code of Conduct
---------------

Please be respectful and constructive in all interactions. We welcome contributors 
of all experience levels and backgrounds.

Getting Started
---------------

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a new branch for your feature or fix
4. Make your changes
5. Submit a pull request

Development Setup
-----------------

.. code-block:: bash

   # Clone repository
   git clone <your-fork-url>
   cd hydra
   
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate
   
   # Install development dependencies
   pip install -e .[dev]
   
   # Run tests to verify setup
   pytest

Code Style
----------

We use ``ruff`` for code formatting and linting:

.. code-block:: bash

   # Format code
   ruff format src/
   
   # Check linting
   ruff check src/
   
   # Fix linting issues
   ruff check --fix src/

Testing Requirements
--------------------

All contributions must include appropriate tests:

- Unit tests for new functions/classes
- Integration tests for new features
- Maintain or improve code coverage (>80%)

.. code-block:: bash

   # Run all tests
   pytest
   
   # Run with coverage
   pytest --cov=src/hydra --cov-report=term-missing
   
   # Run specific test file
   pytest tests/unit/test_specific.py

Documentation
-------------

Update documentation for any user-facing changes:

- Docstrings for all public functions/classes
- Update relevant .rst files in docs/
- Add examples if introducing new features

.. code-block:: bash

   # Build documentation
   cd docs/
   make html
   
   # View documentation
   open _build/html/index.html

Pull Request Process
--------------------

1. **Branch Naming**: Use descriptive names (e.g., ``feature/new-provider``, ``fix/session-leak``)

2. **Commit Messages**: Follow conventional commits:
   
   - ``feat:`` New feature
   - ``fix:`` Bug fix
   - ``docs:`` Documentation only
   - ``test:`` Testing only
   - ``refactor:`` Code restructuring
   - ``perf:`` Performance improvement

3. **PR Description**: Include:
   
   - Problem being solved
   - Solution approach
   - Testing performed
   - Breaking changes (if any)

4. **Review Process**:
   
   - CI must pass (tests, linting)
   - Code review by maintainer
   - Address feedback promptly

Types of Contributions
-----------------------

Bug Reports
~~~~~~~~~~~

File issues with:

- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- System information
- Error messages/logs

Feature Requests
~~~~~~~~~~~~~~~~

Propose features with:

- Use case description
- Proposed solution
- Alternative approaches considered
- Impact on existing functionality

Code Contributions
~~~~~~~~~~~~~~~~~~

We welcome:

- Bug fixes
- New features
- Performance improvements
- Test improvements
- Documentation updates

Review Criteria
---------------

PRs are evaluated on:

1. **Correctness**: Does it solve the problem?
2. **Testing**: Are there adequate tests?
3. **Documentation**: Is it well documented?
4. **Performance**: No performance regressions
5. **Security**: No security vulnerabilities
6. **Style**: Follows project conventions

Release Process
---------------

Releases follow semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backwards compatible)
- **PATCH**: Bug fixes

Release Checklist
~~~~~~~~~~~~~~~~~

1. Update version in ``setup.py``
2. Update ``CHANGELOG.md``
3. Run full test suite
4. Build and test distribution
5. Tag release in git
6. Publish to PyPI

Recognition
-----------

Contributors are recognized in:

- ``CONTRIBUTORS.md`` file
- Release notes
- Project documentation

Questions?
----------

- File an issue for questions
- Join community discussions
- Contact maintainers directly

Thank you for contributing to Hydra!