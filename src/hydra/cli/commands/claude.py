"""Claude Code orchestration commands for Hydra CLI."""

import os


def add_claude_parser(subparsers):
    """Add Claude Code subcommands to the parser."""
    claude_parser = subparsers.add_parser(
        "claude",
        help="Claude Code CLI orchestration - manage and execute tasks with Claude Code"
    )
    claude_subparsers = claude_parser.add_subparsers(
        dest="claude_action",
        help="Claude Code operations"
    )

    # Execute task with Claude Code
    execute_parser = claude_subparsers.add_parser(
        "execute",
        help="Execute a task with Claude Code"
    )
    execute_parser.add_argument(
        "task",
        help="Task description for Claude Code to execute"
    )
    execute_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds (default: 300)"
    )
    execute_parser.add_argument(
        "--cwd",
        help="Working directory for task execution (default: current directory)"
    )

    # Create development session
    session_parser = claude_subparsers.add_parser(
        "session",
        help="Create a Claude Code development session"
    )
    session_parser.add_argument(
        "project_path",
        help="Path to the project directory"
    )
    session_parser.add_argument(
        "--name",
        help="Session name (auto-generated if not provided)"
    )

    # List sessions
    claude_subparsers.add_parser(
        "list",
        help="List all active Claude Code sessions"
    )

    # Attach to session
    attach_parser = claude_subparsers.add_parser(
        "attach",
        help="Attach to an existing Claude Code session"
    )
    attach_parser.add_argument(
        "session_name",
        help="Name of the session to attach to"
    )

    # Kill session
    kill_parser = claude_subparsers.add_parser(
        "kill",
        help="Kill a Claude Code session"
    )
    kill_parser.add_argument(
        "session_name",
        help="Name of the session to kill"
    )

    # Save session
    save_parser = claude_subparsers.add_parser(
        "save",
        help="Save Claude Code session state"
    )
    save_parser.add_argument(
        "session_name",
        help="Name of the session to save"
    )

    # Restore session
    restore_parser = claude_subparsers.add_parser(
        "restore",
        help="Restore a Claude Code session from saved state"
    )
    restore_parser.add_argument(
        "session_name",
        help="Name of the session to restore"
    )


def _handle_claude_execute(orchestrator, args):
    """Handle claude execute command."""
    task = orchestrator.create_task(
        description=args.task[:50],
        prompt=args.task,
        working_directory=args.cwd,
        timeout=args.timeout
    )

    print("🚀 Executing task with Claude Code CLI...")
    result = orchestrator.execute_task(task)

    if result.status.value == "completed":
        print("✅ Task completed successfully")
        if result.files_changed:
            changed_files = ', '.join(result.files_changed)
            print(f"📝 Files changed: {changed_files}")
        return 0
    else:
        print(f"❌ Task failed: {result.error}")
        return 1


def _handle_claude_session_management(orchestrator, args):
    """Handle session-related commands."""
    if args.claude_action == "session":
        orchestrator.create_development_session(args.project_path, args.name)
        return 0
    elif args.claude_action == "list":
        sessions = orchestrator.list_sessions()
        if not sessions:
            print("No active Claude Code sessions")
        else:
            print("Active Claude Code sessions:")
            for session in sessions:
                session_info = f"  - {session['name']}: {session['project_path']}"
                print(session_info)
        return 0
    elif args.claude_action == "attach":
        orchestrator.attach_to_session(args.session_name)
        return 0
    elif args.claude_action == "kill":
        orchestrator.kill_session(args.session_name)
        return 0
    return None


def _handle_claude_persistence(orchestrator, args):
    """Handle save/restore commands."""
    from hydra.persistence.session_manager import SessionManager
    manager = SessionManager()

    if args.claude_action == "save":
        tasks = orchestrator.task_history
        project_path = os.getcwd()
        save_path = manager.save_session(args.session_name, project_path, tasks)
        print(f"✅ Session saved to: {save_path}")
        return 0
    elif args.claude_action == "restore":
        state = manager.restore_session(args.session_name)
        if state:
            print(f"✅ Session restored: {args.session_name}")
            print(f"📁 Project: {state.project_path}")
            print(f"📋 Tasks: {len(state.tasks)}")
            orchestrator.task_history = state.tasks
            return 0
        else:
            print(f"❌ Session not found: {args.session_name}")
            return 1
    return None


def handle_claude_command(args):
    """Handle Claude Code orchestration commands."""
    from hydra.orchestrator.claude_code_orchestrator import ClaudeCodeOrchestrator

    try:
        orchestrator = ClaudeCodeOrchestrator()
    except ValueError as e:
        print(f"Error initializing Claude Code orchestrator: {e}")
        return 1

    if args.claude_action == "execute":
        return _handle_claude_execute(orchestrator, args)

    session_result = _handle_claude_session_management(orchestrator, args)
    if session_result is not None:
        return session_result

    persistence_result = _handle_claude_persistence(orchestrator, args)
    if persistence_result is not None:
        return persistence_result

    print("Unknown Claude action")
    return 1

