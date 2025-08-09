"""Parallel Execution Engine for Hydra.

Runs multiple Claude Code agents concurrently on independent tickets.
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from hydra.agents.pool import AgentPool
from hydra.orchestrator.claude_code_orchestrator import (
    ClaudeCodeOrchestrator,
)
from hydra.quality import QualityGateRunner
from hydra.safety.file_lock import get_file_lock_manager
from hydra.ticket_workflow import mark_ticket_completed, parse_ticket


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
        self.running_tickets: Set[str] = set()
        self.orchestrators: Dict[str, ClaudeCodeOrchestrator] = {}
        self.dashboard_state = dashboard_state
        
        # Initialize agent pool for managing Claude Code terminals
        self.agent_pool = AgentPool(max_agents=max_workers)
        self.agent_pool.start()
        
        # Initialize file lock manager
        self.file_lock_manager = get_file_lock_manager()

    def load_tickets(self, tickets_path: str) -> Dict[str, TicketNode]:
        """Load all tickets from tickets.md."""
        tickets = {}

        with open(tickets_path, 'r') as f:
            content = f.read()

        # Find all ticket IDs
        import re
        ticket_patterns = [
            r'## Ticket (\d+):',  # Match "## Ticket 001:"
            r'## TICKET-(\d+):',
            r'## Ticket-(\d+):',
            r'## \w+-(\d+):',     # Match any prefix like CALC-001
            r'### TICKET-(\d+):',
            r'## #(\d+):',
            r'## (\d+):'
        ]

        ticket_ids = []
        for pattern in ticket_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                ticket_ids = matches
                break

        # Parse each ticket
        for ticket_id in ticket_ids:
            ticket_data = parse_ticket(tickets_path, ticket_id)
            if ticket_data and not ticket_data.get('completed'):
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

    def build_execution_plan(self) -> ExecutionPlan:
        """Build an execution plan based on dependencies."""
        # Build dependency graph
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

        try:
            # Parse ticket for full details
            ticket_data = parse_ticket(tickets_path, ticket_id)

            # Create model-specific orchestrator for this ticket
            ticket_model = ticket_data.get('model', 'sonnet')  # Default to sonnet
            print(f"🧠 Ticket {ticket_id} requires model: {ticket_model.upper()}")

            # Set the model environment for this agent
            import os
            original_model = os.environ.get('CLAUDE_MODEL')

            if ticket_model.lower() == 'opus':
                os.environ['CLAUDE_MODEL'] = 'claude-opus-4-1-20250805'
            else:
                os.environ['CLAUDE_MODEL'] = 'claude-sonnet-4-20250514'

            orchestrator = ClaudeCodeOrchestrator()
            self.orchestrators[ticket_id] = orchestrator

            # Build prompt with comprehensive instructions
            prompt = f"""Execute ticket {ticket_id} in tickets.md

Task: {ticket_data['title']}
Description: {ticket_data['description']}

Acceptance Criteria:
{chr(10).join(f'- {criteria}' for criteria in ticket_data['acceptance_criteria'])}

Working Directory: {self.project_root}

CRITICAL INSTRUCTIONS:
Be minimalistic, surgical and future proof! 

QUALITY REQUIREMENTS:
- Avoid using any code or comments that may be construed as AI generated
- Make sure you do a good job because other LLMs said your code sucked!
- DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS! 
- This has to be production quality, take your time
- Write code that looks like it was written by a senior developer
- Use proper error handling and edge case management
- Follow established patterns in the existing codebase

COMPLETION PROCESS:
1. Implement ALL requirements from the ticket
2. Ensure every acceptance criteria is fully met
3. Update tickets.md to mark your criteria as complete: [x]
4. Run lint, build, test commands to validate your work
5. Only finish when everything passes and is production-ready

Take your time and deliver excellence!"""

            # Create task with the actual ticket_id for unique session naming
            task = orchestrator.create_task(
                description=f"Ticket {ticket_id}: {node.title}",
                prompt=prompt,
                working_directory=str(self.project_root),
                timeout=300,
                task_id=ticket_id  # Pass ticket ID for unique tmux session
            )

            # Execute task
            result = orchestrator.execute_task(task)

            if result.status.value == "completed":
                # Validate acceptance criteria before marking complete
                from hydra.ticket_workflow import validate_acceptance_criteria

                validation_passed = validate_acceptance_criteria(ticket_data, str(self.project_root))

                if validation_passed:
                    # Mark ticket as completed only if validation passes
                    mark_ticket_completed(tickets_path, ticket_id)
                    print("✅ Acceptance criteria validated and ticket marked complete")
                else:
                    print("❌ Acceptance criteria validation failed - ticket remains incomplete")
                    # Treat as failure if validation fails
                    raise Exception("Acceptance criteria not met")

                # Run quality gates
                print(f"\n🚦 Running quality gates for ticket {ticket_id}...")
                gate_runner = QualityGateRunner(self.project_root)
                quality_report = gate_runner.run_quality_gates(ticket_id)

                allowed_statuses = ["passed", "warning"]
                quality_passed = quality_report.overall_status.value in allowed_statuses

                with self.lock:
                    node.status = ExecutionStatus.COMPLETED
                    node.end_time = time.time()
                    node.quality_passed = quality_passed
                    self.completed_tickets.add(ticket_id)
                    self.running_tickets.remove(ticket_id)

                    # Update dashboard
                    if self.dashboard_state:
                        from hydra.dashboard.state import TicketStatus
                        self.dashboard_state.update_ticket_status(
                            ticket_id, TicketStatus.COMPLETED
                        )

                duration = node.end_time - node.start_time
                print(f"\n✅ Ticket {ticket_id} completed in {duration:.2f}s")

                if not quality_passed:
                    print(f"⚠️  Quality gates failed for ticket {ticket_id}")

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

        # Update dashboard wave
        if self.dashboard_state:
            for ticket_id in wave:
                not_completed = ticket_id not in self.completed_tickets
                not_failed = ticket_id not in self.failed_tickets
                if not_completed and not_failed:
                    # Mark as pending if not already processed
                    pass

        max_workers = min(len(wave), self.max_workers)
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
                deps_failed = any(
                    dep in self.failed_tickets for dep in node.dependencies
                )

                if deps_failed:
                    blocked_tickets.append(ticket_id)
                    with self.lock:
                        node.status = ExecutionStatus.BLOCKED
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
            "completed": len(self.completed_tickets),
            "failed": len(self.failed_tickets),
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
        lines = [
            f"\n{'='*60}",
            "📊 Parallel Execution Report",
            f"{'='*60}",
            f"Total tickets: {summary['total_tickets']}",
            f"✅ Completed: {summary['completed']}",
            f"❌ Failed: {summary['failed']}",
            f"⛔ Blocked: {summary['blocked']}",
            f"📈 Success rate: {summary['success_rate']:.1f}%",
            f"⏱️  Total duration: {summary['duration']:.2f}s",
            "",
            "📋 Ticket Details:",
        ]

        for ticket_id, node in sorted(self.tickets.items()):
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
    
    def shutdown(self):
        """Shutdown the executor and clean up resources."""
        # Stop the agent pool
        if hasattr(self, 'agent_pool'):
            self.agent_pool.stop()
            print("🛑 Agent pool shutdown complete")
