import os
import subprocess
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

USE_VENICE = os.getenv("USE_VENICE", "false").lower() == "true"
USE_CLAUDE_CLI = os.getenv("USE_CLAUDE_CLI", "true").lower() == "true"
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "claude")  # Default to 'claude'
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "dummy"))

def generate_code_with_claude_cli(prompt):
    try:
        # Use CLAUDE_CLI_PATH from environment or default to 'claude'
        cmd = f'{CLAUDE_CLI_PATH} "{prompt}"'
        
        # Debug logging
        print(f"[DEBUG] Running command: {cmd}")
            
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=os.environ.copy()
        )
        if result.returncode == 0:
            return result.stdout
        else:
            raise Exception(f"Claude CLI error: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        if USE_VENICE:
            try:
                import venice
                client = venice.Client()
                return client.generate(prompt)
            except ImportError:
                pass
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text