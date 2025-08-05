from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="hydra-sdk",
    version="1.0.0",
    author="Hydra AI",
    author_email="contact@hydra-ai.com",
    description="Python SDK for Hydra AI agent system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hydra-ai/hydra",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.25.0",
        "aiohttp>=3.8.0",
        "pydantic>=1.8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=0.900",
        ],
    },
)
