import subprocess
import sys
import json
import pytest


def run_cli(args, input_text=None):
    cmd = [sys.executable, "-m", "hydra.cli"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_text
    )
    return result


def test_cli_help():
    result = run_cli(["--help"])
    assert result.returncode == 0
    assert "Hydra: Multi-agent code generation system" in result.stdout
    assert "Examples:" in result.stdout


def test_cli_no_task():
    result = run_cli([])
    assert result.returncode == 1


def test_cli_simple_task():
    result = run_cli(["run", "Create a hello world function"])
    assert result.returncode == 0
    assert "Executing task:" in result.stdout
    assert "Agent: boss" in result.stdout


def test_cli_multi_line_stdin():
    task = """Create two functions:
1. add(a, b) that returns sum
2. subtract(a, b) that returns difference"""

    result = run_cli(["run", "dummy"], input_text=task)
    assert result.returncode == 0
    assert "Executing task:" in result.stdout


def test_cli_json_output():
    result = run_cli(["run", "Simple task", "--json"])
    assert result.returncode == 0

    try:
        data = json.loads(result.stdout.split("-" * 60)[1].strip())
        assert "task" in data
        assert "agents" in data
    except (json.JSONDecodeError, IndexError):
        pytest.fail("Invalid JSON output")


def test_cli_custom_agent_name():
    result = run_cli(["run", "Task", "--agent-name", "manager"])
    assert result.returncode == 0
    assert "Agent: manager" in result.stdout


def test_cli_refactor_functions():
    task = "Refactor add/subtract functions"
    result = run_cli(["run", task])

    assert result.returncode == 0
    assert "Executing task:" in result.stdout
    assert "Generated Code:" in result.stdout


def test_cli_error_handling():
    result = run_cli(["run", "", "--depth", "10"])
    assert result.returncode == 1


def test_cli_interrupt_simulation():
    import signal
    import os
    import time
    import threading

    def delayed_interrupt(pid):
        time.sleep(0.1)
        os.kill(pid, signal.SIGINT)

    proc = subprocess.Popen(
        [sys.executable, "-m", "hydra.cli", "run", "Long running task"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    thread = threading.Thread(target=delayed_interrupt, args=(proc.pid,))
    thread.start()

    stdout, stderr = proc.communicate()
    thread.join()

    assert proc.returncode != 0


if __name__ == "__main__":
    test_cli_help()
    print("✓ Help test passed")

    test_cli_no_task()
    print("✓ No task test passed")

    test_cli_simple_task()
    print("✓ Simple task test passed")

    test_cli_multi_line_stdin()
    print("✓ Multi-line stdin test passed")

    test_cli_json_output()
    print("✓ JSON output test passed")

    test_cli_custom_agent_name()
    print("✓ Custom agent name test passed")

    test_cli_refactor_functions()
    print("✓ Refactor functions test passed")

    test_cli_error_handling()
    print("✓ Error handling test passed")

    print("\nAll CLI tests passed!")
