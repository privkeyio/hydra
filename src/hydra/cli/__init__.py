"""Hydra CLI module - Command-line interface for multi-agent code generation."""

# Import main entry point
from hydra.cli.commands.claude import handle_claude_command

# Import command handlers for backwards compatibility
from hydra.cli.commands.ticket import handle_ticket_command
from hydra.cli.main import create_parser, main

__all__ = ["create_parser", "main", "handle_ticket_command", "handle_claude_command"]
