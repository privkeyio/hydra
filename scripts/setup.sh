#!/bin/bash
# Setup script for Hydra development environment

echo "Setting up Hydra development environment..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)"; then
    echo "Error: Python 3.11 or higher is required (found $python_version)"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install package in development mode
echo "Installing Hydra in development mode..."
pip install -e ".[dev]"

# Set up pre-commit hooks
echo "Setting up pre-commit hooks..."
pre-commit install

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit .env and add your API keys"
fi

# Create logs directory if it doesn't exist
mkdir -p logs

echo ""
echo "Setup complete! To get started:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Edit .env and add your API keys"
echo "3. Run 'make test' to verify installation"
echo "4. Run 'hydra --help' to see usage"