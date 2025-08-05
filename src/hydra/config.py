import os
import subprocess
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

USE_VENICE = os.getenv("USE_VENICE", "false").lower() == "true"
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "dummy"))

def generate_code_with_claude_cli(prompt):
    try:
        result = subprocess.run(
            ["claude", "code", prompt],
            capture_output=True,
            text=True,
            timeout=30
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