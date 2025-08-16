"""Hydra CLI - Backwards compatibility wrapper.

This module provides backwards compatibility by delegating to the new modular CLI structure.
All functionality has been moved to hydra.cli.main and hydra.cli.commands.
"""

import sys

from hydra.cli.main import create_parser, main

# Re-export key functions for backwards compatibility
from hydra.cli.commands.template import handle_template_command
from hydra.cli.commands.ticket import handle_ticket_command
from hydra.cli.commands.claude import handle_claude_command
from hydra.cli.commands.context import handle_context_command

# Import parallel and verify if they exist
try:
    from hydra.cli.commands.parallel import handle_parallel_commands
except ImportError:
    handle_parallel_commands = None

try:
    from hydra.cli.commands.verify import handle_verify_command
except ImportError:
    handle_verify_command = None


# Legacy exports for backwards compatibility
__all__ = [
    "create_parser",
    "main",
    "handle_template_command",
    "handle_ticket_command",
    "handle_claude_command",
    "handle_context_command",
]

if __name__ == "__main__":
    sys.exit(main())