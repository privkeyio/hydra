"""Hydra CLI commands module."""

from hydra.cli.commands.claude import handle_claude_command
from hydra.cli.commands.context import handle_context_command
from hydra.cli.commands.parallel import handle_parallel_commands
from hydra.cli.commands.template import handle_template_command
from hydra.cli.commands.ticket import handle_ticket_command
from hydra.cli.commands.verify import handle_verify_command

__all__ = [
    "handle_claude_command",
    "handle_context_command",
    "handle_parallel_commands",
    "handle_template_command",
    "handle_ticket_command",
    "handle_verify_command",
]
