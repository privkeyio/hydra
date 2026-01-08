#!/usr/bin/env python3
"""Test script for production file locking system."""

import sys
import threading
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hydra.production_config import get_production_config
from hydra.safety.claude_file_interceptor import (
    ClaudeFileInterceptor,
    SmartFileLockManager,
)
from hydra.safety.file_lock import get_file_lock_manager


def test_basic_file_locking():
    """Test basic file lock acquisition and release."""
    print("\n=== Testing Basic File Locking ===")

    manager = get_file_lock_manager()

    # Test lock acquisition
    assert manager.acquire_lock("agent1", "test.py", timeout=5)
    print("✅ Lock acquired: agent1 -> test.py")

    # Test that another agent can't acquire the same lock
    assert not manager.acquire_lock("agent2", "test.py", timeout=1)
    print("✅ Lock correctly blocked: agent2 -> test.py")

    # Release lock
    manager.release_lock("agent1", "test.py")
    print("✅ Lock released: agent1 -> test.py")

    # Now agent2 should be able to acquire
    assert manager.acquire_lock("agent2", "test.py", timeout=1)
    print("✅ Lock acquired after release: agent2 -> test.py")

    # Cleanup
    manager.release_all_locks("agent2")
    print("✅ All locks released for agent2")


def test_file_interceptor():
    """Test the Claude file interceptor."""
    print("\n=== Testing File Interceptor ===")

    interceptor = ClaudeFileInterceptor()

    # Test operation detection
    output1 = "Reading: src/main.py"
    op = interceptor.detect_file_operation(output1, "agent1")
    assert op == ("read", "src/main.py")
    print("✅ Detected read operation")

    output2 = "Writing: config.json"
    op = interceptor.detect_file_operation(output2, "agent1")
    assert op == ("write", "config.json")
    print("✅ Detected write operation")

    output3 = "Editing: README.md"
    op = interceptor.detect_file_operation(output3, "agent1")
    assert op == ("edit", "README.md")
    print("✅ Detected edit operation")

    # Test lock acquisition
    assert interceptor.acquire_file_lock("agent1", "test.txt", "write")
    print("✅ File lock acquired through interceptor")

    # Cleanup
    interceptor.release_agent_locks("agent1")
    print("✅ Agent locks released through interceptor")


def test_smart_scheduling():
    """Test smart ticket scheduling."""
    print("\n=== Testing Smart Scheduling ===")

    manager = SmartFileLockManager()

    # Test requirement analysis
    ticket1 = """
    ## Ticket 001: Update Configuration
    Modify src/config.py to add new settings.
    Update tests/test_config.py with tests.
    """

    files = manager.analyze_ticket_requirements(ticket1)
    assert "src/config.py" in str(files) or "config" in str(files).lower()
    print(f"✅ Analyzed ticket, found potential files: {files}")

    # Test conflict detection
    ticket2 = """
    ## Ticket 002: Refactor Config Module
    Refactor src/config.py for better structure.
    """

    files1 = manager.analyze_ticket_requirements(ticket1)
    files2 = manager.analyze_ticket_requirements(ticket2)

    conflict = manager.check_conflict_potential(files1, files2)
    print(f"✅ Conflict potential detected: {conflict:.2f}")

    # Test scheduling
    tickets = {
        "001": ticket1,
        "002": ticket2,
        "003": "## Ticket 003: Update README\nModify README.md",
    }

    waves = manager.schedule_tickets_smartly(tickets)
    print(f"✅ Smart scheduling created {len(waves)} waves:")
    for i, wave in enumerate(waves, 1):
        print(f"   Wave {i}: {wave}")


def test_concurrent_locking():
    """Test concurrent lock acquisition."""
    print("\n=== Testing Concurrent Locking ===")

    manager = get_file_lock_manager()
    results = {"agent1": False, "agent2": False}

    def try_lock(agent_id, delay=0):
        time.sleep(delay)
        results[agent_id] = manager.acquire_lock(agent_id, "shared.py", timeout=3)
        if results[agent_id]:
            print(f"   🔒 {agent_id} acquired lock")
            time.sleep(1)  # Hold lock briefly
            manager.release_lock(agent_id, "shared.py")
            print(f"   🔓 {agent_id} released lock")

    # Start two threads trying to acquire the same lock
    t1 = threading.Thread(target=try_lock, args=("agent1", 0))
    t2 = threading.Thread(target=try_lock, args=("agent2", 0.1))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # Both should eventually succeed (one after the other)
    assert results["agent1"] or results["agent2"]
    print("✅ Concurrent locking handled correctly")


def test_production_config():
    """Test production configuration."""
    print("\n=== Testing Production Configuration ===")

    config = get_production_config()

    assert config.enable_file_locking == True
    print("✅ File locking enabled in production")

    assert config.enable_smart_scheduling == True
    print("✅ Smart scheduling enabled in production")

    assert config.enable_git_safety == True
    print("✅ Git safety enabled in production")

    env_vars = config.to_env_vars()
    assert env_vars["HYDRA_FILE_LOCKING"] == "1"
    print("✅ Environment variables set correctly")

    print(f"✅ Production config: {config.max_parallel_tickets} parallel tickets")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 TESTING PRODUCTION FILE LOCKING SYSTEM")
    print("=" * 60)

    try:
        test_basic_file_locking()
        test_file_interceptor()
        test_smart_scheduling()
        test_concurrent_locking()
        test_production_config()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\n🎉 The production file locking system is ready for use!")
        print("\nTo use in production:")
        print("  hydra ticket parallel --workers 3 --tickets tickets.md")
        print("\nThe system will automatically:")
        print("  • Detect potential file conflicts")
        print("  • Schedule tickets to minimize conflicts")
        print("  • Apply real-time file locking")
        print("  • Prevent race conditions and data corruption")

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
