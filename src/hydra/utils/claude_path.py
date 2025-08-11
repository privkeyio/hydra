"""Utility for finding Claude CLI path dynamically."""
import os
import shutil
from pathlib import Path


def find_claude_cli_path():
    """Find the Claude CLI executable path dynamically.
    
    Search order:
    1. CLAUDE_CLI_PATH environment variable
    2. 'claude' in PATH
    3. ~/.claude/local/claude (user home directory)
    4. ~/.local/bin/claude
    5. /usr/local/bin/claude
    
    Returns:
        str: Path to claude CLI executable, or None if not found

    """
    # 1. Check environment variable first
    env_path = os.environ.get('CLAUDE_CLI_PATH')
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. Check if 'claude' is in PATH
    claude_in_path = shutil.which('claude')
    if claude_in_path:
        return claude_in_path

    # 3. Check user's home directory locations
    home = Path.home()

    # Common user-specific locations
    user_locations = [
        home / '.claude' / 'local' / 'claude',
        home / '.local' / 'bin' / 'claude',
        home / 'bin' / 'claude',
    ]

    for path in user_locations:
        if path.exists():
            return str(path)

    # 4. Check system-wide locations
    system_locations = [
        Path('/usr/local/bin/claude'),
        Path('/usr/bin/claude'),
        Path('/opt/claude/claude'),
    ]

    for path in system_locations:
        if path.exists():
            return str(path)

    # If not found, return a sensible default
    # This will fail gracefully if the path doesn't exist
    return str(home / '.claude' / 'local' / 'claude')


def get_claude_cli_path():
    """Get the Claude CLI path with caching.
    
    Returns:
        str: Path to claude CLI executable

    """
    if not hasattr(get_claude_cli_path, '_cached_path'):
        get_claude_cli_path._cached_path = find_claude_cli_path()
    return get_claude_cli_path._cached_path
