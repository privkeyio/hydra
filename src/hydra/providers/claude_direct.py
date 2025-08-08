"""Direct Claude CLI invocation with proper terminal allocation."""
import os
import pty
import select
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path
from typing import Any, Dict

from .base import LLMProvider


class ClaudeDirectProvider(LLMProvider):
    """Run Claude CLI directly with PTY for full interactive capabilities."""

    def validate_config(self):
        """Validate Claude CLI configuration."""
        self.claude_path = self.config.extra_params.get(
            'claude_path',
            os.environ.get('CLAUDE_CLI_PATH', '/home/kyle/.claude/local/claude')
        )
        
        if not Path(self.claude_path).exists():
            raise ValueError(f"Claude CLI not found at: {self.claude_path}")

    @property
    def name(self) -> str:
        return "claude_direct"

    def generate(self, prompt: str, **kwargs) -> str:
        """Execute Claude with full terminal capabilities."""
        
        project_dir = kwargs.get('cwd', os.getcwd())
        
        # Save current directory
        original_dir = os.getcwd()
        
        try:
            # Change to project directory
            os.chdir(project_dir)
            
            print(f"🚀 Starting Claude Code in {project_dir}")
            print("📝 Sending task to Claude...")
            
            # Create master and slave pseudo-terminals
            master, slave = pty.openpty()
            
            # Start Claude process with PTY
            process = subprocess.Popen(
                [self.claude_path],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                preexec_fn=os.setsid,
                cwd=project_dir
            )
            
            # Close slave in parent
            os.close(slave)
            
            # Send the prompt to Claude
            time.sleep(2)  # Wait for Claude to initialize
            
            # Send prompt line by line
            for line in prompt.split('\n'):
                os.write(master, (line + '\n').encode())
                time.sleep(0.1)
            
            # Add completion instruction
            os.write(master, b"\nWhen you're done with all file operations, please type 'exit'\n")
            
            # Monitor output
            output_lines = []
            start_time = time.time()
            
            while time.time() - start_time < self.config.timeout:
                # Check if process is still running
                if process.poll() is not None:
                    break
                
                # Check for output
                ready, _, _ = select.select([master], [], [], 1)
                if ready:
                    try:
                        data = os.read(master, 1024)
                        if data:
                            decoded = data.decode('utf-8', errors='ignore')
                            output_lines.append(decoded)
                            print(decoded, end='', flush=True)
                            
                            # Check if Claude is done
                            if 'exit' in decoded.lower() or 'goodbye' in decoded.lower():
                                break
                    except OSError:
                        break
                
                # Check for file changes periodically
                if int(time.time() - start_time) % 10 == 0:
                    git_status = subprocess.run(
                        ["git", "status", "--short"],
                        capture_output=True,
                        text=True,
                        cwd=project_dir
                    )
                    if git_status.stdout:
                        print(f"\n📝 Files changed so far: {len(git_status.stdout.strip().split(chr(10)))} files")
            
            # Terminate Claude if still running
            if process.poll() is None:
                os.write(master, b"\nexit\n")
                time.sleep(1)
                process.terminate()
                process.wait(timeout=5)
            
            # Close master
            os.close(master)
            
            # Check final results
            git_status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                cwd=project_dir
            )
            
            if git_status.stdout:
                print("\n✅ Files successfully modified by Claude Code:")
                for line in git_status.stdout.strip().split('\n'):
                    print(f"   {line}")
                return "Files have been successfully edited"
            else:
                return ''.join(output_lines) or "Claude session completed"
                
        except Exception as e:
            raise Exception(f"Claude direct execution error: {str(e)}")
        finally:
            # Restore original directory
            os.chdir(original_dir)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Not used for direct mode."""
        result = self.generate(prompt, **kwargs)
        return {"result": result}

    def stream_generate(self, prompt: str, **kwargs):
        """Not used for direct mode."""
        yield self.generate(prompt, **kwargs)
    
    def list_models(self):
        """Return available models."""
        return ["claude-3-opus", "claude-3-sonnet"]