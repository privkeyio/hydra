#!/usr/bin/env python
"""Setup configuration for Hydra package."""

from setuptools import setup, find_packages
import os

# Read the README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

# Development requirements
dev_requirements = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "flake8>=6.0.0",
    "black>=23.0.0",
    "mypy>=1.0.0",
    "pre-commit>=3.0.0",
]

setup(
    name="hydra-agents",
    version="1.0.0",
    author="Hydra Team",
    author_email="team@hydra.internal",
    description="Self-replicating AI agent system for autonomous code generation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/internal/hydra",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Code Generators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "dev": dev_requirements,
    },
    entry_points={
        "console_scripts": [
            "hydra=hydra.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "hydra": ["config/*.yaml", "config/*.json"],
    },
)