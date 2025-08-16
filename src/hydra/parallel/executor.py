"""Parallel Execution Engine for Hydra.

Runs multiple Claude Code agents concurrently on independent tickets.
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from hydra.agents.pool import AgentPool
from hydra.context import ArtifactTracker, TicketUpdater
from hydra.orchestrator.claude_code_orchestrator import ClaudeCodeOrchestrator
from hydra.quality import QualityGateRunner
from hydra.safety.file_lock import get_file_lock_manager
from hydra.shutdown_manager import get_shutdown_manager
from hydra.ticket_workflow import (
    mark_ticket_completed,
    mark_ticket_in_progress,
)


class ExecutionStatus(Enum):
    """Status of ticket execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class TicketNode:
    """Represents a ticket in the dependency graph."""

    ticket_id: str
    title: str
    model: str
    dependencies: List[str]
    status: ExecutionStatus
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    quality_passed: Optional[bool] = None


@dataclass
class ExecutionPlan:
    """Execution plan for parallel ticket processing."""

    waves: List[List[str]]  # Tickets grouped by dependency level
    dependency_graph: Dict[str, List[str]]
    total_tickets: int
    max_parallel: int


class ParallelExecutor:
    """Executes tickets in parallel respecting dependencies."""

    def __init__(self, max_workers: int = 3, project_root: str = ".",
                 dashboard_state=None):
        self.max_workers = max_workers
        self.project_root = Path(project_root).resolve()
        self.tickets: Dict[str, TicketNode] = {}
        self.lock = threading.Lock()
        self.completed_tickets: Set[str] = set()
        self.failed_tickets: Set[str] = set()
        self.quality_failed_tickets: Set[str] = set()  # Track quality failures separately
        self.running_tickets: Set[str] = set()
        self.orchestrators: Dict[str, ClaudeCodeOrchestrator] = {}
        self.dashboard_state = dashboard_state

        # Initialize agent pool for managing Claude Code terminals
        self.agent_pool = AgentPool(max_agents=max_workers)
        self.agent_pool.start()

        # Initialize file lock manager and smart interceptor
        self.file_lock_manager = get_file_lock_manager()
        from hydra.safety.claude_file_interceptor import SmartFileLockManager
        self.smart_lock_manager = SmartFileLockManager()
        # Start deadlock monitoring for production use
        if not os.environ.get('TESTING'):
            self.smart_lock_manager.start_deadlock_monitoring()

        # Initialize artifact tracker for context passing
        self.artifact_tracker = ArtifactTracker(project_root)
        self.ticket_updater = TicketUpdater(project_root)

        # Register with shutdown manager for graceful shutdown
        self.shutdown_manager = get_shutdown_manager()
        self.shutdown_manager.register_shutdown_handler(self._cleanup_resources)

        # Register background threads
        if hasattr(self.agent_pool, '_cleanup_thread') and self.agent_pool._cleanup_thread:
            self.shutdown_manager.register_background_thread(self.agent_pool._cleanup_thread)
        if hasattr(self.smart_lock_manager, '_deadlock_monitor_thread'):
            deadlock_thread = getattr(self.smart_lock_manager, '_deadlock_monitor_thread', None)
            if deadlock_thread:
                self.shutdown_manager.register_background_thread(deadlock_thread)

        # Register state saving
        if hasattr(self, 'dashboard_state') and self.dashboard_state:
            self.shutdown_manager.register_state_saver(
                lambda: getattr(self.dashboard_state, 'save_state', lambda: None)()
            )

    def load_tickets(self, tickets_path: str) -> Dict[str, TicketNode]:
        """Load all tickets from YAML or MD file."""
        self.tickets_path = tickets_path  # Store for smart scheduling
        tickets = {}
        
        # Use the unified TicketFormatHandler
        from hydra.tickets.compatibility import TicketFormatHandler
        handler = TicketFormatHandler()
        
        # Get all ticket IDs from the file
        ticket_ids = handler.get_ticket_ids(tickets_path)
        
        # Parse each ticket
        for ticket_id in ticket_ids:
            ticket_data = handler.parse_ticket(tickets_path, ticket_id)
            if ticket_data:
                # Check status field
                ticket_status = ticket_data.get('status', 'TODO').upper()
                if ticket_data.get('completed') or ticket_status == 'DONE':
                    # Track completed tickets but mark them as already done
                    node = TicketNode(
                        ticket_id=ticket_id,
                        title=ticket_data['title'],
                        model=ticket_data['model'],
                        dependencies=ticket_data.get('dependencies', []),
                        status=ExecutionStatus.COMPLETED
                    )
                    tickets[ticket_id] = node
                    self.completed_tickets.add(ticket_id)
                else:
                    node = TicketNode(
                        ticket_id=ticket_id,
                        title=ticket_data['title'],
                        model=ticket_data['model'],
                        dependencies=ticket_data.get('dependencies', []),
                        status=ExecutionStatus.PENDING
                    )
                    tickets[ticket_id] = node

                    # Add to dashboard if available
                    if self.dashboard_state:
                        self.dashboard_state.add_ticket(
                            ticket_id,
                            ticket_data['title'],
                            ticket_data['model'],
                            ticket_data.get('dependencies', [])
                        )

        self.tickets = tickets
        return tickets

    def _build_smart_execution_plan(self) -> ExecutionPlan:
        """Build execution plan using smart conflict detection AND dependency resolution."""
        print("🧠 Using smart scheduling to minimize file conflicts while respecting dependencies...")

        # First, build dependency-aware waves using standard logic
        dependency_graph = {}
        reverse_deps = {}  # Track which tickets depend on each ticket

        for ticket_id, node in self.tickets.items():
            dependency_graph[ticket_id] = node.dependencies

            for dep in node.dependencies:
                if dep not in reverse_deps:
                    reverse_deps[dep] = []
                reverse_deps[dep].append(ticket_id)

        # Topological sort to find execution waves
        dependency_waves = []
        processed = set()

        while len(processed) < len(self.tickets):
            wave = []

            for ticket_id, node in self.tickets.items():
                if ticket_id in processed:
                    continue

                # Check if all dependencies are processed
                deps_satisfied = all(
                    dep in processed or dep not in self.tickets
                    for dep in node.dependencies
                )

                if deps_satisfied:
                    wave.append(ticket_id)

            if not wave:
                # Circular dependency or missing dependency
                remaining = set(self.tickets.keys()) - processed
                dep_warning = (
                    f"⚠️  Warning: Circular or missing dependencies detected for: "
                    f"{remaining}"
                )
                print(dep_warning)
                wave = list(remaining)  # Force execution of remaining tickets

            dependency_waves.append(wave)
            processed.update(wave)

        # Now apply smart conflict detection within each dependency wave
        # Read ticket contents for analysis
        tickets_content = {}
        with open(self.tickets_path, 'r') as f:
            content = f.read()
            for ticket_id in self.tickets:
                # Extract ticket content
                import re
                pattern = rf'## Ticket {ticket_id}:.*?(?=## Ticket \d+:|$)'
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    tickets_content[ticket_id] = match.group(0)

        # Optimize each dependency wave for file conflicts
        final_waves = []
        for dep_wave in dependency_waves:
            if len(dep_wave) <= 1:
                # Single ticket, no conflict to resolve
                final_waves.append(dep_wave)
            else:
                # Use smart scheduler to split wave if there are conflicts
                wave_content = {tid: tickets_content.get(tid, '') for tid in dep_wave}
                conflict_free_subwaves = self.smart_lock_manager.schedule_tickets_smartly(wave_content)

                # Merge subwaves back if they're small
                if len(conflict_free_subwaves) == 1:
                    final_waves.append(conflict_free_subwaves[0])
                else:
                    # Multiple subwaves means conflicts were detected
                    print(f"   ⚠️  Detected file conflicts in dependency wave {dep_wave}, splitting into {len(conflict_free_subwaves)} subwaves")
                    final_waves.extend(conflict_free_subwaves)

        print(f"📊 Smart scheduling created {len(final_waves)} execution waves (respecting both dependencies and file conflicts)")
        for i, wave in enumerate(final_waves, 1):
            print(f"   Wave {i}: {', '.join(wave)}")

        return ExecutionPlan(
            waves=final_waves,
            dependency_graph=dependency_graph,
            total_tickets=len(self.tickets),
            max_parallel=self.max_workers
        )

    def build_execution_plan(self) -> ExecutionPlan:
        """Build an execution plan based on dependencies."""
        import os

        # Check if smart scheduling is enabled
        use_smart_scheduling = os.environ.get('HYDRA_SMART_SCHEDULING', '0') == '1'

        if use_smart_scheduling and hasattr(self, 'smart_lock_manager'):
            # Use smart scheduling to minimize conflicts
            return self._build_smart_execution_plan()

        # Build dependency graph (standard approach)
        dependency_graph = {}
        reverse_deps = {}  # Track which tickets depend on each ticket

        for ticket_id, node in self.tickets.items():
            dependency_graph[ticket_id] = node.dependencies

            for dep in node.dependencies:
                if dep not in reverse_deps:
                    reverse_deps[dep] = []
                reverse_deps[dep].append(ticket_id)

        # Topological sort to find execution waves
        waves = []
        processed = set()

        while len(processed) < len(self.tickets):
            wave = []

            for ticket_id, node in self.tickets.items():
                if ticket_id in processed:
                    continue

                # Check if all dependencies are processed
                deps_satisfied = all(
                    dep in processed or dep not in self.tickets
                    for dep in node.dependencies
                )

                if deps_satisfied:
                    wave.append(ticket_id)

            if not wave:
                # Circular dependency or missing dependency
                remaining = set(self.tickets.keys()) - processed
                dep_warning = (
                    f"⚠️  Warning: Circular or missing dependencies detected for: "
                    f"{remaining}"
                )
                print(dep_warning)
                wave = list(remaining)  # Force execution of remaining tickets

            waves.append(wave)
            processed.update(wave)

        return ExecutionPlan(
            waves=waves,
            dependency_graph=dependency_graph,
            total_tickets=len(self.tickets),
            max_parallel=self.max_workers
        )

    def execute_ticket(self, ticket_id: str, tickets_path: str) -> bool:
        """Execute a single ticket."""
        # Get thread info for debugging
        thread_id = threading.current_thread().name
        print(f"🧵 Thread {thread_id} assigned to Ticket {ticket_id}")

        # Add staggered start to prevent Claude Code session collisions
        import random
        start_delay = random.uniform(0.5, 5.0)  # Random delay between 0.5-5 seconds
        print(f"⏱️  Ticket {ticket_id} starting in {start_delay:.1f}s to prevent session collision...")
        time.sleep(start_delay)

        # Spawn an agent for this ticket
        agent_id = self.agent_pool.spawn_agent(ticket_id)
        if not agent_id:
            print(f"⚠️  No available agent slots for ticket {ticket_id}")
            return False

        with self.lock:
            if ticket_id in self.completed_tickets:
                self.agent_pool.release_agent(agent_id)
                return True
            if ticket_id in self.failed_tickets:
                self.agent_pool.release_agent(agent_id)
                return False

            self.running_tickets.add(ticket_id)
            node = self.tickets[ticket_id]
            node.status = ExecutionStatus.RUNNING
            node.start_time = time.time()

            # Register task with shutdown manager
            self.shutdown_manager.register_task(ticket_id)

            # Update dashboard
            if self.dashboard_state:
                from hydra.dashboard.state import TicketStatus
                self.dashboard_state.update_ticket_status(
                    ticket_id, TicketStatus.RUNNING
                )

        print(f"\n{'='*60}")
        print(f"🎫 Starting Ticket {ticket_id}: {node.title}")
        print(f"🤖 Model: {node.model}")
        print(f"⏰ Started at: {time.strftime('%H:%M:%S')}")
        print('='*60)

        # Mark ticket as IN_PROGRESS in tickets.md
        mark_ticket_in_progress(tickets_path, ticket_id)

        try:
            # Parse ticket for full details
            from hydra.tickets.compatibility import TicketFormatHandler
            handler = TicketFormatHandler()
            ticket_data = handler.parse_ticket(tickets_path, ticket_id)

            # Create model-specific orchestrator for this ticket
            ticket_model = ticket_data.get('model', 'balanced').lower()  # Default to balanced
            print(f"🧠 Ticket {ticket_id} requires model: {ticket_model.upper()}")

            # Set the model environment for this agent
            import os
            original_model = os.environ.get('CLAUDE_MODEL')

            # Set the model category for Claude to use
            # The claude_tmux provider will map these to actual Claude models
            os.environ['CLAUDE_MODEL'] = ticket_model

            orchestrator = ClaudeCodeOrchestrator()
            self.orchestrators[ticket_id] = orchestrator

            # Get file snapshot before execution (for artifact tracking)
            before_snapshot = self.artifact_tracker.get_file_snapshot()

            # Get context from dependent tickets
            dependencies = ticket_data.get('dependencies', [])
            dependency_context = ""
            if dependencies:
                print(f"📚 Loading context from dependencies: {', '.join(dependencies)}")
                dependency_context = self.artifact_tracker.get_dependency_context(
                    ticket_id, dependencies
                )

            # Build prompt - production quality implementation
            prompt = f"""Execute ticket {ticket_id} from tickets.yaml in the current directory.

CRITICAL REQUIREMENTS:
- Be minimalistic, surgical, and future-proof in your implementation
- Avoid ANY code or comments that could be construed as AI-generated  
- This MUST be production quality - NO shortcuts, workarounds, or mocks
- Take your time to ensure excellence - other LLMs said your code quality was poor, prove them wrong!
- Create ACTUAL files (HTML, CSS, JS, etc.) as required by the ticket - DO NOT modify Hydra system files

{dependency_context}

EXECUTION STEPS:
1. Use 'cat tickets.yaml' or Read tool to understand ticket {ticket_id} requirements
2. Create the ACTUAL files needed (e.g., index.html for a web calculator, NOT hydra system files)
3. Ensure ALL acceptance criteria are fully met with production-quality code
4. Update tickets.yaml to change ticket {ticket_id} status from "TODO" to "DONE"
5. Run quality checks if available (lint, prettier, etc.)

IMPORTANT: You are implementing the actual project described in the ticket (e.g., a calculator), 
NOT modifying the Hydra ticket system itself. Create NEW files as needed for the project.

PYTHON CODE QUALITY REQUIREMENTS:
- Add module docstrings to all Python files
- Include __init__.py in all new package directories
- Use proper type hints for all functions
- Follow PEP 8 style guidelines
- Avoid unused imports
- Add error handling where appropriate

Be minimalistic, surgical and future proof!
Avoid using any code or comments that may be construed as AI generated.
Make sure you do a good job because other LLMs said your code sucked!

CRITICAL: Before marking the ticket as complete, you MUST:
1. Run all applicable linting/formatting tools (e.g., `ruff check --fix`, `black`, `prettier`, etc.)
2. Fix ALL linting issues - do not leave any warnings or errors
3. Run type checking if applicable (e.g., `mypy`, `tsc`)
4. Run tests if they exist (e.g., `pytest`, `npm test`)
5. Update the acceptance criteria checkboxes in tickets.md to mark completed items

If any quality checks fail, FIX THEM before considering the ticket done. Keep iterating until all checks pass.

DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS! This has to be production quality, take your time.

REMINDER: You are working on Ticket {ticket_id} ONLY. Ignore all other tickets."""

            # Create task with the actual ticket_id for unique session naming
            task = orchestrator.create_task(
                description=f"Ticket {ticket_id}: {node.title}",
                prompt=prompt,
                working_directory=str(self.project_root),
                timeout=900,
                task_id=ticket_id  # Pass ticket ID for unique tmux session
            )

            # Execute task
            result = orchestrator.execute_task(task)

            if result.status.value == "completed":
                # Validate acceptance criteria before marking complete
                from hydra.ticket_workflow import validate_acceptance_criteria

                validation_passed = validate_acceptance_criteria(ticket_data, str(self.project_root))

                if validation_passed:
                    print("✅ Acceptance criteria validated")
                else:
                    print("❌ Acceptance criteria validation failed - ticket remains incomplete")
                    # Treat as failure if validation fails
                    raise Exception("Acceptance criteria not met")

                # Try to auto-fix common issues before running quality gates
                print(f"\n🔧 Running automatic quality fixes for ticket {ticket_id}...")
                from hydra.quality.auto_fixer import QualityAutoFixer
                fixer = QualityAutoFixer(self.project_root)
                fixes = fixer.fix_common_issues()

                if fixes:
                    print("📝 Applied automatic fixes:")
                    for issue, fixed, message in fixes:
                        if fixed:
                            print(f"   ✅ {issue}: {message}")
                        else:
                            print(f"   ⚠️  {issue}: {message}")

                # Run quality gates
                print(f"\n🚦 Running quality gates for ticket {ticket_id}...")
                gate_runner = QualityGateRunner(self.project_root)
                quality_report = gate_runner.run_quality_gates(ticket_id)

                # Print quality gate details for debugging
                print("📋 Quality Gate Results:")
                for check in quality_report.results:
                    status_icon = "✅" if check.status.value == "passed" else "❌" if check.status.value == "failed" else "⚠️"
                    print(f"   {status_icon} {check.name}: {check.status.value}")
                    if check.status.value == "failed" and check.error:
                        # Show first few lines of error
                        error_lines = check.error.split('\n')[:3]
                        for line in error_lines:
                            if line.strip():
                                print(f"      → {line[:100]}")

                allowed_statuses = ["passed", "warning"]
                quality_passed = quality_report.overall_status.value in allowed_statuses

                # Mark ticket as completed if acceptance criteria are met
                # Quality issues are informational only - they don't block completion
                if validation_passed:
                    mark_ticket_completed(tickets_path, ticket_id)
                    if quality_passed:
                        print("✅ Ticket completed with all quality gates passed")
                    else:
                        print("⚠️  Ticket completed but has quality issues (agent should have fixed these)")
                        # Log quality issues for information (without failing)
                        # Note: Quality issues don't block completion

                    # Discover and record artifacts created by this ticket
                    print(f"📦 Discovering artifacts created by ticket {ticket_id}...")
                    artifacts = self.artifact_tracker.discover_artifacts(ticket_id, before_snapshot)

                    if artifacts:
                        print(f"   Found {len(artifacts)} artifact(s):")
                        for artifact in artifacts[:5]:  # Show first 5
                            op_symbol = {
                                'created': '➕',
                                'modified': '✏️',
                                'deleted': '➖'
                            }.get(artifact.operation, '📄')
                            print(f"     {op_symbol} {artifact.file_path}")
                        if len(artifacts) > 5:
                            print(f"     ... and {len(artifacts) - 5} more")

                    # Extract acceptance criteria met
                    criteria_met = []
                    if 'acceptance_criteria' in ticket_data:
                        for criterion in ticket_data['acceptance_criteria']:
                            # Handle both string and dict formats
                            if isinstance(criterion, str):
                                # String format - check if it starts with ✅
                                if criterion.startswith('✅'):
                                    criteria_met.append(criterion.replace('✅', '').strip())
                            elif isinstance(criterion, dict):
                                # Dict format - check completed flag
                                if criterion.get('completed', False):
                                    criteria_met.append(criterion.get('description', ''))

                    # Record ticket completion and artifacts
                    self.artifact_tracker.record_ticket_completion(
                        ticket_id=ticket_id,
                        title=node.title,
                        artifacts=artifacts,
                        acceptance_criteria_met=criteria_met
                    )

                    # Update future tickets with actual file references
                    if artifacts:
                        print("🔄 Updating future tickets with specific file references...")
                        updates_made = self.ticket_updater.update_future_tickets(
                            ticket_id, artifacts
                        )
                        if updates_made > 0:
                            print(f"   ✏️ Updated {updates_made} future ticket(s) with actual filenames")

                with self.lock:
                    # Ticket is completed regardless of quality status
                    node.status = ExecutionStatus.COMPLETED
                    node.end_time = time.time()
                    node.quality_passed = quality_passed
                    self.completed_tickets.add(ticket_id)
                    if not quality_passed:
                        self.quality_failed_tickets.add(ticket_id)  # Track for reporting
                    self.running_tickets.remove(ticket_id)

                    # Unregister task from shutdown manager
                    self.shutdown_manager.unregister_task(ticket_id)

                    # Update dashboard
                    if self.dashboard_state:
                        from hydra.dashboard.state import TicketStatus
                        status = TicketStatus.COMPLETED if quality_passed else TicketStatus.FAILED
                        self.dashboard_state.update_ticket_status(ticket_id, status)

                duration = node.end_time - node.start_time
                if quality_passed:
                    status_msg = "✅ Completed"
                else:
                    status_msg = "✅ Functionally complete ⚠️  (has quality issues - review output)"
                print(f"\n{status_msg} Ticket {ticket_id} in {duration:.2f}s")

                # Release the agent back to the pool and file locks
                self.agent_pool.release_agent(agent_id)
                self.file_lock_manager.release_all_locks(agent_id)
                return True
            else:
                raise Exception(f"Task failed: {result.error}")

        except Exception as e:
            with self.lock:
                node.status = ExecutionStatus.FAILED
                node.end_time = time.time()
                node.error = str(e)
                self.failed_tickets.add(ticket_id)
                self.running_tickets.remove(ticket_id)

                # Unregister task from shutdown manager
                self.shutdown_manager.unregister_task(ticket_id)

                # Update dashboard
                if self.dashboard_state:
                    from hydra.dashboard.state import TicketStatus
                    self.dashboard_state.update_ticket_status(
                        ticket_id, TicketStatus.FAILED, str(e)
                    )

            print(f"\n❌ Ticket {ticket_id} failed: {e}")
            # Release the agent and locks even on failure
            self.agent_pool.release_agent(agent_id)
            self.file_lock_manager.release_all_locks(agent_id)
            return False
        finally:
            # Restore original model setting for other agents
            if 'original_model' in locals():
                if original_model:
                    os.environ['CLAUDE_MODEL'] = original_model
                elif 'CLAUDE_MODEL' in os.environ:
                    del os.environ['CLAUDE_MODEL']

    def execute_wave(self, wave: List[str], tickets_path: str) -> Dict[str, bool]:
        """Execute a wave of tickets in parallel."""
        results = {}

        print(f"\n🌊 Executing wave with {len(wave)} tickets: {', '.join(wave)}")
        print(f"🔧 Using {min(len(wave), self.max_workers)} parallel workers")

        # Update dashboard wave
        if self.dashboard_state:
            for ticket_id in wave:
                not_completed = ticket_id not in self.completed_tickets
                not_failed = ticket_id not in self.failed_tickets
                if not_completed and not_failed:
                    # Mark as pending if not already processed
                    pass

        max_workers = min(len(wave), self.max_workers)
        print(f"🚀 Submitting {len(wave)} tickets to ThreadPoolExecutor with {max_workers} workers")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.execute_ticket, ticket_id, tickets_path): ticket_id
                for ticket_id in wave
            }

            for future in as_completed(futures):
                ticket_id = futures[future]
                try:
                    success = future.result()
                    results[ticket_id] = success
                except Exception as e:
                    print(f"❌ Error executing ticket {ticket_id}: {e}")
                    results[ticket_id] = False

        return results

    def execute_plan(self, plan: ExecutionPlan, tickets_path: str) -> Dict[str, Any]:
        """Execute the full execution plan."""
        start_time = time.time()

        # Store tickets_path for use in reports
        self.tickets_path = tickets_path

        # Initialize dashboard session
        if self.dashboard_state:
            import uuid
            session_id = str(uuid.uuid4())[:8]
            self.dashboard_state.start_session(
                session_id=session_id,
                tickets_path=tickets_path,
                total_tickets=plan.total_tickets,
                total_waves=len(plan.waves),
                workers=self.max_workers
            )

        print("\n📋 Execution Plan")
        print(f"{'='*60}")
        print(f"Total tickets: {plan.total_tickets}")
        print(f"Execution waves: {len(plan.waves)}")
        print(f"Max parallel workers: {plan.max_parallel}")

        for i, wave in enumerate(plan.waves):
            print(f"  Wave {i+1}: {', '.join(wave)}")

        print(f"{'='*60}")

        all_results = {}

        for wave_num, wave in enumerate(plan.waves, 1):
            print(f"\n🚀 Starting Wave {wave_num}/{len(plan.waves)}")

            # Update dashboard wave
            if self.dashboard_state:
                self.dashboard_state.update_wave(wave_num)

            # Filter out already completed tickets
            wave_to_execute = [
                t for t in wave
                if t not in self.completed_tickets and t not in self.failed_tickets
            ]

            if not wave_to_execute:
                print(f"⏭️  All tickets in wave {wave_num} already processed")
                continue

            # Check dependencies
            blocked_tickets = []
            ready_tickets = []

            for ticket_id in wave_to_execute:
                node = self.tickets[ticket_id]
                # Check if any dependencies failed or were blocked (transitive failure)
                deps_failed = any(
                    dep in self.failed_tickets for dep in node.dependencies
                )

                # Also check if dependencies were blocked (transitive failure from earlier deps)
                deps_blocked = any(
                    self.tickets.get(dep) and self.tickets[dep].status == ExecutionStatus.BLOCKED
                    for dep in node.dependencies
                )

                # Check if dependencies are missing (not completed when they should be)
                deps_missing = any(
                    dep not in self.completed_tickets and
                    dep not in self.quality_failed_tickets
                    for dep in node.dependencies
                )

                if deps_failed or deps_blocked or deps_missing:
                    blocked_tickets.append(ticket_id)
                    with self.lock:
                        node.status = ExecutionStatus.BLOCKED
                        if deps_failed:
                            node.error = f"Dependency failed: {[d for d in node.dependencies if d in self.failed_tickets]}"
                        elif deps_blocked:
                            node.error = f"Dependency blocked: {[d for d in node.dependencies if self.tickets.get(d) and self.tickets[d].status == ExecutionStatus.BLOCKED]}"
                        else:
                            node.error = f"Dependency not completed: {[d for d in node.dependencies if d not in self.completed_tickets and d not in self.quality_failed_tickets]}"
                else:
                    ready_tickets.append(ticket_id)

            if blocked_tickets:
                blocked_list = ', '.join(blocked_tickets)
                print(f"⛔ Blocked tickets due to failed dependencies: {blocked_list}")

            if ready_tickets:
                wave_results = self.execute_wave(ready_tickets, tickets_path)
                all_results.update(wave_results)

        # Generate summary
        duration = time.time() - start_time

        summary = {
            "total_tickets": plan.total_tickets,
            "functionally_completed": len(self.completed_tickets),  # All tickets that ran to completion
            "quality_passed": len(self.completed_tickets) - len(self.quality_failed_tickets),  # Tickets that passed quality gates
            "completed": len(self.completed_tickets) - len(self.quality_failed_tickets),  # For backwards compatibility
            "failed": len(self.failed_tickets),  # Tickets that failed to execute
            "quality_failed": len(self.quality_failed_tickets),  # Tickets that completed but failed quality
            "blocked": sum(
                1 for n in self.tickets.values()
                if n.status == ExecutionStatus.BLOCKED
            ),
            "duration": duration,
            "success_rate": (
                len(self.completed_tickets) / plan.total_tickets * 100
                if plan.total_tickets > 0 else 0
            ),
            "results": all_results
        }

        return summary

    def generate_report(self, summary: Dict[str, Any]) -> str:
        """Generate execution report."""
        # Get quality summary from tickets.md
        from hydra.ticket_workflow import get_quality_summary
        quality_summary = get_quality_summary(self.tickets_path) if hasattr(self, 'tickets_path') else None

        lines = [
            f"\n{'='*60}",
            "📊 Parallel Execution Report",
            f"{'='*60}",
            f"Total tickets: {summary['total_tickets']}",
            f"✅ Functionally Complete: {summary.get('functionally_completed', summary['completed'])} (executed successfully)",
            f"   ✅ Quality Passed: {summary.get('quality_passed', summary['completed'])}",
            f"   ⚠️  Quality Failed: {summary.get('quality_failed', 0)}",
            f"❌ Execution Failed: {summary['failed']} (couldn't complete)",
            f"⛔ Blocked: {summary['blocked']} (dependencies failed)",
            f"📈 Completion rate: {summary['success_rate']:.1f}%",
            f"⏱️  Total duration: {summary['duration']:.2f}s",
            "",
        ]

        if quality_summary and quality_summary['quality_failed'] > 0:
            lines.extend([
                "⚠️  QUALITY ISSUES DETECTED:",
                f"   {quality_summary['quality_failed']} ticket(s) have failing quality gates",
                "   Check tickets.md for detailed Quality Gate Results",
                "",
            ])

        lines.append("📋 Ticket Details:")

        for ticket_id, node in sorted(self.tickets.items()):
            # Show special icon for quality failures
            if ticket_id in self.quality_failed_tickets:
                status_icon = "⚠️"  # Quality failed but completed
            else:
                status_icon = {
                    ExecutionStatus.COMPLETED: "✅",
                    ExecutionStatus.FAILED: "❌",
                    ExecutionStatus.BLOCKED: "⛔",
                    ExecutionStatus.PENDING: "⏳",
                    ExecutionStatus.RUNNING: "🔄"
                }.get(node.status, "❓")

            line = f"  {status_icon} {ticket_id}: {node.title}"

            if node.start_time and node.end_time:
                duration = node.end_time - node.start_time
                line += f" ({duration:.2f}s)"

            if node.quality_passed is not None:
                line += " [QA: " + ("✅" if node.quality_passed else "⚠️") + "]"

            lines.append(line)

            if node.error:
                lines.append(f"     Error: {node.error[:100]}")

        lines.append(f"{'='*60}")

        return "\n".join(lines)

    def save_completion_report(self, summary: Dict[str, Any]) -> str:
        """Save a completion report and dashboard snapshot."""
        # Create .hydra directory structure
        hydra_dir = self.project_root / ".hydra"
        hydra_dir.mkdir(exist_ok=True)

        reports_dir = hydra_dir / "reports"
        reports_dir.mkdir(exist_ok=True)

        # Save completion report
        report_file = reports_dir / f"completion_{int(time.time())}.md"
        report_content = self.generate_report(summary)

        # Add extra information for the saved report
        full_report = f"""# 🎉 Project Completion Report

**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Project:** {self.project_root}
**Success Rate:** {summary['success_rate']:.1f}%

{report_content}

## 📊 Dashboard
View the live dashboard at: http://localhost:8080
Or check the saved dashboard snapshot in `.hydra/dashboard/`

## 📁 Generated Files
Check your project directory for all the generated calculator files.

## ✅ All Tickets Completed!
"""

        with open(report_file, 'w') as f:
            f.write(full_report)

        # Save dashboard HTML snapshot if available
        if self.dashboard_state:
            dashboard_dir = hydra_dir / "dashboard"
            dashboard_dir.mkdir(exist_ok=True)

            snapshot_file = dashboard_dir / f"snapshot_{int(time.time())}.html"
            # Create a static HTML snapshot
            self._save_dashboard_snapshot(snapshot_file, summary)

        return str(report_file)

    def _save_dashboard_snapshot(self, snapshot_file: Path, summary: Dict[str, Any]):
        """Save a static HTML dashboard snapshot."""
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Hydra Completion Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e27;
            color: #e4e4e7;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            color: #60a5fa;
            text-align: center;
        }}
        .success-banner {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin: 20px 0;
            font-size: 24px;
            font-weight: bold;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .stat-card {{
            background: #1e293b;
            border-radius: 8px;
            padding: 20px;
            border: 1px solid #334155;
        }}
        .stat-label {{
            font-size: 12px;
            color: #94a3b8;
            text-transform: uppercase;
            margin-bottom: 8px;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: 600;
            color: #f1f5f9;
        }}
        .tickets-list {{
            background: #1e293b;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }}
        .ticket-item {{
            padding: 10px;
            border-bottom: 1px solid #334155;
        }}
        .ticket-item:last-child {{
            border-bottom: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Hydra Project Completion</h1>

        <div class="success-banner">
            🎉 All {summary['total_tickets']} Tickets Completed Successfully!
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">Total Tickets</div>
                <div class="stat-value">{summary['total_tickets']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Completed</div>
                <div class="stat-value">{summary['completed']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Success Rate</div>
                <div class="stat-value">{summary['success_rate']:.0f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Time</div>
                <div class="stat-value">{summary['duration']:.0f}s</div>
            </div>
        </div>

        <div class="tickets-list">
            <h2>📋 Completed Tickets</h2>
"""
        for ticket_id, node in sorted(self.tickets.items()):
            if node.status == ExecutionStatus.COMPLETED:
                duration = ""
                if node.start_time and node.end_time:
                    duration = f" - {node.end_time - node.start_time:.1f}s"
                html_content += f"""            <div class="ticket-item">✅ {ticket_id}: {node.title}{duration}</div>
"""

        html_content += """        </div>
    </div>
</body>
</html>"""

        with open(snapshot_file, 'w') as f:
            f.write(html_content)

    def save_execution_log(
        self, summary: Dict[str, Any], log_dir: Optional[str] = None
    ):
        """Save execution log."""
        if not log_dir:
            log_dir = self.project_root / ".hydra" / "logs"
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"parallel_execution_{int(time.time())}.json"

        log_data = {
            "timestamp": time.time(),
            "summary": summary,
            "tickets": {
                ticket_id: {
                    "title": node.title,
                    "model": node.model,
                    "dependencies": node.dependencies,
                    "status": node.status.value,
                    "start_time": node.start_time,
                    "end_time": node.end_time,
                    "error": node.error,
                    "quality_passed": node.quality_passed
                }
                for ticket_id, node in self.tickets.items()
            }
        }

        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)

        return str(log_file)

    def _cleanup_resources(self):
        """Clean up resources when called by shutdown manager."""
        # Stop the agent pool
        if hasattr(self, 'agent_pool'):
            self.agent_pool.stop()

        # Stop smart lock manager deadlock monitoring
        if hasattr(self, 'smart_lock_manager'):
            try:
                if hasattr(self.smart_lock_manager, 'stop_deadlock_monitoring'):
                    self.smart_lock_manager.stop_deadlock_monitoring()
            except Exception as e:
                print(f"⚠️  Warning: Error stopping deadlock monitoring: {e}")

        # Close any open file handles
        if hasattr(self, 'file_lock_manager'):
            try:
                # Release any remaining locks
                for agent_id in list(self.running_tickets):
                    self.file_lock_manager.release_all_locks(agent_id)
            except Exception as e:
                print(f"⚠️  Warning: Error releasing file locks: {e}")

    def shutdown(self):
        """Shutdown the executor and clean up resources."""
        # Use the shutdown manager for coordinated shutdown
        if hasattr(self, 'shutdown_manager'):
            self.shutdown_manager.shutdown()
        else:
            # Fallback to direct cleanup
            self._cleanup_resources()
