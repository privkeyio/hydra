.PHONY: help install install-dev test test-unit test-integration lint format clean run build docs

# Default target
help:
	@echo "Hydra - Self-Replicating Coding Agent System"
	@echo ""
	@echo "Available commands:"
	@echo "  make install       Install production dependencies"
	@echo "  make install-dev   Install development dependencies"
	@echo "  make test          Run all tests"
	@echo "  make test-unit     Run unit tests only"
	@echo "  make test-int      Run integration tests only"
	@echo "  make lint          Run code linting"
	@echo "  make format        Format code with black"
	@echo "  make clean         Clean generated files"
	@echo "  make run           Run the CLI with a sample task"
	@echo "  make build         Build the package"
	@echo "  make docs          Generate documentation"

# Install production dependencies
install:
	pip install -e .

# Install development dependencies
install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Run all tests
test:
	pytest tests/ -v --cov=hydra --cov-report=html --cov-report=term

# Run unit tests only
test-unit:
	pytest tests/unit/ -v

# Run integration tests only
test-int:
	pytest tests/integration/ -v

# Run linting
lint:
	flake8 src/ tests/
	mypy src/
	ruff check src/ tests/

# Format code
format:
	black src/ tests/
	ruff format src/ tests/

# Clean generated files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	rm -rf build/ dist/

# Run the CLI with a sample task
run:
	hydra "Create a function to calculate factorial"

# Build the package
build: clean
	python -m build

# Generate documentation
docs:
	@echo "Documentation generation not yet configured"
	@echo "Consider using Sphinx or MkDocs"

# Development workflow
dev: install-dev lint test