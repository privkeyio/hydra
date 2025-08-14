"""Utility modules for Hydra system."""

from .venice import venice_call


def hello_world():
    """Return a hello world message."""
    return "Hello, World!"


__all__ = ["venice_call", "hello_world"]
