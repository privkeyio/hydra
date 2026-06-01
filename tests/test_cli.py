"""Tests for Hydra CLI."""

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest

from hydra.cli import create_parser, main
from hydra.cli.commands.claude import handle_claude_command
from hydra.cli.commands.context import handle_context_command
from hydra.cli.commands.template import handle_template_command
from hydra.cli.commands.ticket import handle_ticket_command


class TestCLIParser:
    """Test CLI parser creation and configuration."""

    def test_create_parser(self):
        """Test that parser is created correctly."""
        parser = create_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.description
        assert "Hydra" in parser.description

    def test_parser_has_subparsers(self):
        """Test that parser has all expected subcommands."""
        parser = create_parser()
        # Parse empty args to check subparsers
        args = parser.parse_args([])
        assert hasattr(args, 'command')

    def test_template_command_parser(self):
        """Test template command parser."""
        parser = create_parser()
        
        # Test template list
        args = parser.parse_args(['template', 'list'])
        assert args.command == 'template'
        assert args.template_action == 'list'

        # Test template create
        args = parser.parse_args(['template', 'create', 'flask_app', './output'])
        assert args.command == 'template'
        assert args.template_action == 'create'
        assert args.template_name == 'flask_app'
        assert args.output_dir == './output'

    def test_ticket_command_parser(self):
        """Test ticket command parser."""
        parser = create_parser()
        
        # Test ticket create
        args = parser.parse_args(['ticket', 'create', 'Build a web app'])
        assert args.command == 'ticket'
        assert args.ticket_action == 'create'
        assert args.description == 'Build a web app'

        # Test ticket execute
        args = parser.parse_args(['ticket', 'execute', '001'])
        assert args.command == 'ticket'
        assert args.ticket_action == 'execute'
        assert args.identifier == '001'

    def test_claude_command_parser(self):
        """Test Claude command parser."""
        parser = create_parser()
        
        # Test claude execute
        args = parser.parse_args(['claude', 'execute', 'Run a task'])
        assert args.command == 'claude'
        assert args.claude_action == 'execute'
        assert args.task == 'Run a task'

    def test_context_command_parser(self):
        """Test context command parser."""
        parser = create_parser()
        
        # Test context show
        args = parser.parse_args(['context', 'show'])
        assert args.command == 'context'
        assert args.context_action == 'show'

        # Test context inspect
        args = parser.parse_args(['context', 'inspect', '001'])
        assert args.command == 'context'
        assert args.context_action == 'inspect'
        assert args.ticket_id == '001'

    def test_global_flags(self):
        """Test global flags."""
        parser = create_parser()
        
        # Test provider flag
        args = parser.parse_args(['--provider', 'venice', 'template', 'list'])
        assert args.provider == 'venice'

        args = parser.parse_args(['--provider', 'nearai', 'template', 'list'])
        assert args.provider == 'nearai'
        
        # Test model flag
        args = parser.parse_args(['--model', 'gpt-4', 'template', 'list'])
        assert args.model == 'gpt-4'
        
        # Test no-cache flag
        args = parser.parse_args(['--no-cache', 'template', 'list'])
        assert args.no_cache is True


class TestCommandHandlers:
    """Test command handler functions."""

    @patch('hydra.cli.commands.template.TemplateEngine')
    def test_handle_template_command_list(self, mock_engine_class):
        """Test handle_template_command with list action."""
        mock_engine = MagicMock()
        mock_engine.list_templates.return_value = ['flask_app', 'django_app']
        mock_engine_class.return_value = mock_engine
        
        args = MagicMock()
        args.template_action = 'list'
        
        result = handle_template_command(args)
        assert result == 0
        mock_engine.list_templates.assert_called_once()

    @patch('hydra.cli.commands.ticket.generate_tickets_md')
    def test_handle_ticket_command_create(self, mock_generate):
        """Test handle_ticket_command with create action."""
        mock_generate.return_value = True
        
        args = MagicMock()
        args.ticket_action = 'create'
        args.description = 'Build a web app'
        args.output = 'tickets.md'
        args.project_type = None
        args.interactive = False
        
        result = handle_ticket_command(args)
        assert result == 0
        mock_generate.assert_called_once_with('Build a web app', 'tickets.md', None)

    @patch('hydra.cli.commands.context.ArtifactTracker')
    def test_handle_context_command_show(self, mock_tracker_class):
        """Test handle_context_command with show action."""
        mock_tracker = MagicMock()
        mock_tracker.ticket_contexts = {}
        mock_tracker_class.return_value = mock_tracker
        
        args = MagicMock()
        args.context_action = 'show'
        args.dir = '.'
        
        result = handle_context_command(args)
        assert result == 0


class TestCLIIntegration:
    """Test CLI integration."""

    @patch('hydra.cli.main.StartupChecker')
    def test_main_with_no_args(self, mock_checker_class):
        """Test main function with no arguments."""
        mock_checker = MagicMock()
        mock_checker.run_startup_checks.return_value = {}
        mock_checker_class.return_value = mock_checker
        
        with patch.object(sys, 'argv', ['hydra']):
            parser = create_parser()
            args = parser.parse_args([])
            # Should show help when no command given
            assert args.command is None

    @patch('hydra.cli.main.StartupChecker')
    @patch('hydra.cli.commands.template.TemplateEngine')
    def test_main_with_template_list(self, mock_engine_class, mock_checker_class):
        """Test main function with template list command."""
        mock_checker = MagicMock()
        mock_checker.run_startup_checks.return_value = {}
        mock_checker_class.return_value = mock_checker
        
        mock_engine = MagicMock()
        mock_engine.list_templates.return_value = []
        mock_engine_class.return_value = mock_engine
        
        with patch.object(sys, 'argv', ['hydra', 'template', 'list']):
            result = main()
            assert result == 0


class TestBackwardsCompatibility:
    """Test backwards compatibility of cli.py wrapper."""

    def test_cli_wrapper_imports(self):
        """Test that cli.py wrapper provides expected imports."""
        from hydra import cli
        
        assert hasattr(cli, 'create_parser')
        assert hasattr(cli, 'main')
        assert hasattr(cli, 'handle_template_command')
        assert hasattr(cli, 'handle_ticket_command')
        assert hasattr(cli, 'handle_claude_command')
        assert hasattr(cli, 'handle_context_command')

    def test_cli_wrapper_create_parser(self):
        """Test that cli.py wrapper's create_parser works."""
        from hydra.cli import create_parser as wrapper_create_parser
        from hydra.cli.main import create_parser as main_create_parser
        
        # Both should return the same type of object
        wrapper_parser = wrapper_create_parser()
        main_parser = main_create_parser()
        
        assert type(wrapper_parser) == type(main_parser)
        assert isinstance(wrapper_parser, argparse.ArgumentParser)
