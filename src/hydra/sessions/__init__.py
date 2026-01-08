"""Session management system for Hydra.

Provides provider-agnostic session backends for terminal multiplexers,
direct process management, and containerized execution.
"""

from .manager import (
    DirectProcessBackend,
    DockerBackend,
    SessionBackend,
    SessionBackendType,
    SessionConfig,
    SessionInfo,
    SessionManager,
    TmuxBackend,
)

__all__ = [
    "SessionBackend",
    "SessionBackendType",
    "SessionConfig",
    "SessionInfo",
    "SessionManager",
    "TmuxBackend",
    "DirectProcessBackend",
    "DockerBackend",
]
