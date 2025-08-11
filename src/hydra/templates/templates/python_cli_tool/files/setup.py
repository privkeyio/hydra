"""Setup module."""

from setuptools import find_packages, setup

setup(
    name="{{tool_name}}",
    version="{{version}}",
    author="{{author}}",
    description="A CLI tool built with Hydra templates",
    packages=find_packages(),
    install_requires=[
        "click>=8.0.0",
        {% if config_format == 'yaml' %}"pyyaml>=6.0",{% endif %}
        {% if config_format == 'toml' %}"toml>=0.10.0",{% endif %}
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "{{tool_name}}={{tool_name}}.cli:main",
        ],
    },
    python_requires=">=3.8",
)