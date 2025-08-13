"""Async Parallel Execution Engine for Hydra.

Replaces ThreadPoolExecutor with asyncio for true async concurrency.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiofiles

from hydra.agents.pool import AgentPool
from hydra.orchestrator.claude_code_orchestrator import ClaudeCodeOrchestrator
from hydra.quality import QualityGateRunner
from hydra.safety.file_lock import get_file_lock_manager
from hydra.ticket_workflow import (
    mark_ticket_completed,
    mark_ticket_in_progress,
    parse_ticket,
)

logger = logging.getLogger(__name__)


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
    """Execution plan for async ticket processing."""

    ready_queue: asyncio.Queue[str]
    dependency_graph: Dict[str, List[str]]
    total_tickets: int
    max_concurrent: int


class AsyncParallelExecutor:
    """Executes tickets in parallel using asyncio for true concurrency."""

    def __init__(self, max_concurrent: int = 3, project_root: str = ".",
                 dashboard_state=None):
        self.max_concurrent = max_concurrent
        self.project_root = Path(project_root).resolve()
        self.tickets: Dict[str, TicketNode] = {}
        self.lock = asyncio.Lock()
        self.completed_tickets: Set[str] = set()
        self.failed_tickets: Set[str] = set()
        self.running_tickets: Set[str] = set()
        self.orchestrators: Dict[str, ClaudeCodeOrchestrator] = {}
        self.dashboard_state = dashboard_state
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Track pending tasks by dependency
        self.dependency_waiters: Dict[str, Set[str]] = {}
        self.ready_queue = asyncio.Queue()

        # Initialize agent pool
        self.agent_pool = AgentPool(max_agents=max_concurrent)
        self.agent_pool.start()

        # Initialize file lock manager
        self.file_lock_manager = get_file_lock_manager()
        from hydra.safety.claude_file_interceptor import SmartFileLockManager
        self.smart_lock_manager = SmartFileLockManager()

    async def load_tickets(self, tickets_path: str) -> Dict[str, TicketNode]:
        """Load all tickets from tickets.md asynchronously."""
        self.tickets_path = tickets_path
        tickets = {}

        async with aiofiles.open(tickets_path, 'r') as f:
            content = await f.read()

        # Find all ticket IDs using existing logic
        import re
        ticket_patterns = [
            r'## Ticket (\d+):',
            r'## TICKET-(\d+):',
            r'## Ticket-(\d+):',
            r'## \w+-(\d+):',
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
            if ticket_data:
                ticket_status = ticket_data.get('status', 'TODO').upper()
                if ticket_data.get('completed') or ticket_status == 'DONE':
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

                    if self.dashboard_state:
                        self.dashboard_state.add_ticket(
                            ticket_id,
                            ticket_data['title'],
                            ticket_data['model'],
                            ticket_data.get('dependencies', [])
                        )

        self.tickets = tickets
        return tickets

    def build_dynamic_execution_plan(self) -> ExecutionPlan:
        """Build execution plan with dynamic scheduling."""
        logger.info("Building dynamic execution plan without rigid waves")

        # Initialize ready queue with tickets that have no dependencies
        ready_queue = asyncio.Queue()
        dependency_graph = {}

        for ticket_id, node in self.tickets.items():
            dependency_graph[ticket_id] = node.dependencies.copy()

            # If ticket has no unresolved dependencies, add to ready queue
            unresolved_deps = [
                dep for dep in node.dependencies
                if dep not in self.completed_tickets and dep in self.tickets
            ]

            if not unresolved_deps:
                ready_queue.put_nowait(ticket_id)
                logger.debug(f"Ticket {ticket_id} added to ready queue (no deps)")
            else:
                # Track which tickets are waiting for this dependency
                for dep in unresolved_deps:
                    if dep not in self.dependency_waiters:
                        self.dependency_waiters[dep] = set()
                    self.dependency_waiters[dep].add(ticket_id)

        logger.info(f"Ready queue initialized with {ready_queue.qsize()} tickets")

        return ExecutionPlan(
            ready_queue=ready_queue,
            dependency_graph=dependency_graph,
            total_tickets=len(self.tickets),
            max_concurrent=self.max_concurrent
        )

    async def execute_ticket(self, ticket_id: str, tickets_path: str) -> bool:
        """Execute a single ticket asynchronously."""
        delay_time = 0.1 * hash(ticket_id) % 50 / 10
        start_delay = asyncio.create_task(asyncio.sleep(delay_time))
        await start_delay

        logger.info(f"Starting async execution of ticket {ticket_id}")

        # Acquire agent
        agent_id = self.agent_pool.spawn_agent(ticket_id)
        if not agent_id:
            logger.warning(f"No available agent slots for ticket {ticket_id}")
            return False

        async with self.lock:
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

            if self.dashboard_state:
                from hydra.dashboard.state import TicketStatus
                self.dashboard_state.update_ticket_status(
                    ticket_id, TicketStatus.RUNNING
                )

        logger.info(f"🎫 Starting Ticket {ticket_id}: {node.title}")
        logger.info(f"🤖 Model: {node.model}")

        # Mark ticket as IN_PROGRESS in tickets.md
        await asyncio.get_event_loop().run_in_executor(
            None, mark_ticket_in_progress, tickets_path, ticket_id
        )

        try:
            # Parse ticket for full details
            ticket_data = await asyncio.get_event_loop().run_in_executor(
                None, parse_ticket, tickets_path, ticket_id
            )

            # Create model-specific orchestrator
            ticket_model = ticket_data.get('model', 'sonnet')
            logger.info(f"🧠 Ticket {ticket_id} requires model: {ticket_model.upper()}")

            # Set model environment
            import os
            original_model = os.environ.get('CLAUDE_MODEL')

            if ticket_model.lower() == 'opus':
                os.environ['CLAUDE_MODEL'] = 'claude-opus-4-1-20250805'
            else:
                os.environ['CLAUDE_MODEL'] = 'claude-sonnet-4-20250514'

            orchestrator = ClaudeCodeOrchestrator()
            self.orchestrators[ticket_id] = orchestrator

            # Build prompt
            prompt = f"""IMPORTANT: You MUST execute ONLY Ticket {ticket_id} from
tickets.md - NOT any other ticket!

Find and execute specifically "## Ticket {ticket_id}:" in tickets.md

DO NOT work on any other ticket even if it appears first or seems easier.
You are assigned ONLY to ticket {ticket_id}.

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

When you finish, ensure acceptance criteria is met then update tickets.md
and then run lint, build, test etc before we move on.

DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS! This has to be
production quality, take your time.

REMINDER: You are working on Ticket {ticket_id} ONLY. Ignore all other
tickets."""

            # Create and execute task
            task = orchestrator.create_task(
                description=f"Ticket {ticket_id}: {node.title}",
                prompt=prompt,
                working_directory=str(self.project_root),
                timeout=900,
                task_id=ticket_id
            )

            # Execute in executor to avoid blocking event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None, orchestrator.execute_task, task
            )

            if result.status.value == "completed":
                # Validate acceptance criteria
                from hydra.ticket_workflow import validate_acceptance_criteria

                validation_passed = await asyncio.get_event_loop().run_in_executor(
                    None, validate_acceptance_criteria, ticket_data,
                    str(self.project_root)
                )

                if validation_passed:
                    logger.info("✅ Acceptance criteria validated")
                else:
                    logger.warning("❌ Acceptance criteria validation failed")
                    raise Exception("Acceptance criteria not met")

                # Run quality fixes
                logger.info(
                    f"🔧 Running automatic quality fixes for ticket {ticket_id}"
                )
                from hydra.quality.auto_fixer import QualityAutoFixer
                fixer = QualityAutoFixer(self.project_root)
                fixes = await asyncio.get_event_loop().run_in_executor(
                    None, fixer.fix_common_issues
                )

                if fixes:
                    logger.info("📝 Applied automatic fixes")
                    for issue, fixed, message in fixes:
                        status = "✅" if fixed else "⚠️"
                        logger.info(f"   {status} {issue}: {message}")

                # Run quality gates
                logger.info(f"🚦 Running quality gates for ticket {ticket_id}")
                gate_runner = QualityGateRunner(self.project_root)
                quality_report = await asyncio.get_event_loop().run_in_executor(
                    None, gate_runner.run_quality_gates, ticket_id
                )

                # Log quality gate results
                logger.info("📋 Quality Gate Results:")
                for check in quality_report.results:
                    status_icon = "✅" if check.status.value == "passed" else "❌" if check.status.value == "failed" else "⚠️"
                    logger.info(f"   {status_icon} {check.name}: {check.status.value}")

                allowed_statuses = ["passed", "warning"]
                quality_passed = quality_report.overall_status.value in allowed_statuses

                # Mark completion
                if validation_passed and quality_passed:
                    await asyncio.get_event_loop().run_in_executor(
                        None, mark_ticket_completed, tickets_path, ticket_id
                    )
                    logger.info("✅ Quality gates passed - ticket marked as DONE")
                else:
                    from hydra.ticket_workflow import mark_ticket_quality_failed
                    await asyncio.get_event_loop().run_in_executor(
                        None, mark_ticket_quality_failed, tickets_path, ticket_id, quality_report
                    )
                    if not quality_passed:
                        logger.warning("⚠️ Quality gates failed - ticket marked as QUALITY_FAILED")

                async with self.lock:
                    node.status = ExecutionStatus.COMPLETED if quality_passed else ExecutionStatus.FAILED
                    node.end_time = time.time()
                    node.quality_passed = quality_passed
                    if quality_passed:
                        self.completed_tickets.add(ticket_id)
                        # Trigger dependent tickets
                        await self._trigger_dependents(ticket_id)
                    else:
                        self.failed_tickets.add(ticket_id)
                    self.running_tickets.remove(ticket_id)

                    if self.dashboard_state:
                        from hydra.dashboard.state import TicketStatus
                        status = TicketStatus.COMPLETED if quality_passed else TicketStatus.FAILED
                        self.dashboard_state.update_ticket_status(ticket_id, status)

                duration = node.end_time - node.start_time
                status_msg = "✅ completed" if quality_passed else "⚠️ completed with quality issues"
                logger.info(f"{status_msg} Ticket {ticket_id} in {duration:.2f}s")

                self.agent_pool.release_agent(agent_id)
                self.file_lock_manager.release_all_locks(agent_id)
                return True
            else:
                raise Exception(f"Task failed: {result.error}")

        except Exception as e:
            async with self.lock:
                node.status = ExecutionStatus.FAILED
                node.end_time = time.time()
                node.error = str(e)
                self.failed_tickets.add(ticket_id)
                self.running_tickets.remove(ticket_id)

                if self.dashboard_state:
                    from hydra.dashboard.state import TicketStatus
                    self.dashboard_state.update_ticket_status(
                        ticket_id, TicketStatus.FAILED, str(e)
                    )

            logger.error(f"❌ Ticket {ticket_id} failed: {e}")
            self.agent_pool.release_agent(agent_id)
            self.file_lock_manager.release_all_locks(agent_id)
            return False
        finally:
            # Restore original model setting
            if 'original_model' in locals():
                if original_model:
                    os.environ['CLAUDE_MODEL'] = original_model
                elif 'CLAUDE_MODEL' in os.environ:
                    del os.environ['CLAUDE_MODEL']

    async def _trigger_dependents(self, completed_ticket_id: str):
        """Trigger tickets that were waiting for this dependency."""
        if completed_ticket_id in self.dependency_waiters:
            for waiting_ticket in self.dependency_waiters[completed_ticket_id]:
                # Check if all dependencies are now satisfied
                node = self.tickets[waiting_ticket]
                unresolved_deps = [
                    dep for dep in node.dependencies
                    if dep not in self.completed_tickets and dep in self.tickets
                ]

                if not unresolved_deps and waiting_ticket not in self.running_tickets:
                    await self.ready_queue.put(waiting_ticket)
                    logger.debug(f"Ticket {waiting_ticket} added to ready queue (deps satisfied)")

            # Clean up
            del self.dependency_waiters[completed_ticket_id]

    async def execute_tickets_dynamically(self, tickets_path: str) -> Dict[str, Any]:
        """Execute tickets with dynamic scheduling (no rigid waves)."""
        start_time = time.time()

        # Initialize dashboard session
        if self.dashboard_state:
            session_id = str(uuid.uuid4())[:8]
            self.dashboard_state.start_session(
                session_id=session_id,
                tickets_path=tickets_path,
                total_tickets=len(self.tickets),
                total_waves=1,  # Dynamic scheduling uses a single conceptual wave
                workers=self.max_concurrent
            )

        logger.info("📋 Dynamic Execution Plan")
        logger.info(f"Total tickets: {len(self.tickets)}")
        logger.info(f"Max concurrent: {self.max_concurrent}")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_ticket_with_semaphore(ticket_id: str) -> tuple[str, bool]:
            """Process a single ticket with semaphore control."""
            async with semaphore:
                result = await self.execute_ticket(ticket_id, tickets_path)
                return ticket_id, result

        # Track running tasks
        running_tasks: Set[asyncio.Task] = set()
        all_results = {}

        while True:
            # Start new tasks from ready queue
            while len(running_tasks) < self.max_concurrent:
                try:
                    # Non-blocking check for ready tickets
                    ticket_id = self.ready_queue.get_nowait()

                    # Skip if already processed
                    if (ticket_id in self.completed_tickets or
                        ticket_id in self.failed_tickets or
                        ticket_id in self.running_tickets):
                        continue

                    task = asyncio.create_task(
                        process_ticket_with_semaphore(ticket_id)
                    )
                    running_tasks.add(task)
                    logger.info(f"🚀 Started task for ticket {ticket_id} (active: {len(running_tasks)})")

                except asyncio.QueueEmpty:
                    # No more ready tickets
                    break

            # If no tasks running and queue is empty, we're done
            if not running_tasks:
                break

            # Wait for at least one task to complete
            done, running_tasks = await asyncio.wait(
                running_tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Process completed tasks
            for task in done:
                ticket_id, success = await task
                all_results[ticket_id] = success
                logger.info(f"✅ Completed ticket {ticket_id}: {success}")

        # Generate summary
        duration = time.time() - start_time

        summary = {
            "total_tickets": len(self.tickets),
            "completed": len(self.completed_tickets),
            "failed": len(self.failed_tickets),
            "blocked": sum(
                1 for n in self.tickets.values()
                if n.status == ExecutionStatus.BLOCKED
            ),
            "duration": duration,
            "success_rate": (
                len(self.completed_tickets) / len(self.tickets) * 100
                if len(self.tickets) > 0 else 0
            ),
            "results": all_results
        }

        return summary

    async def execute_plan(self, plan: ExecutionPlan, tickets_path: str) -> Dict[str, Any]:
        """Execute the full execution plan asynchronously."""
        # For backwards compatibility, delegate to dynamic execution
        return await self.execute_tickets_dynamically(tickets_path)

    def generate_report(self, summary: Dict[str, Any]) -> str:
        """Generate execution report (same as sync version)."""
        from hydra.ticket_workflow import get_quality_summary
        quality_summary = get_quality_summary(self.tickets_path) if hasattr(self, 'tickets_path') else None

        lines = [
            f"\n{'='*60}",
            "📊 Async Parallel Execution Report",
            f"{'='*60}",
            f"Total tickets: {summary['total_tickets']}",
            f"✅ Completed (Quality Passed): {summary['completed']}",
            f"❌ Failed/Quality Issues: {summary['failed']}",
            f"⛔ Blocked: {summary['blocked']}",
            f"📈 Success rate: {summary['success_rate']:.1f}%",
            f"⏱️ Total duration: {summary['duration']:.2f}s",
            "",
        ]

        if quality_summary and quality_summary['quality_failed'] > 0:
            lines.extend([
                "⚠️ QUALITY ISSUES DETECTED:",
                f"   {quality_summary['quality_failed']} ticket(s) have failing quality gates",
                "   Check tickets.md for detailed Quality Gate Results",
                "",
            ])

        lines.append("📋 Ticket Details:")

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

    async def save_completion_report(self, summary: Dict[str, Any]) -> str:
        """Save a completion report asynchronously."""
        hydra_dir = self.project_root / ".hydra"
        await asyncio.get_event_loop().run_in_executor(
            None, hydra_dir.mkdir, True
        )

        reports_dir = hydra_dir / "reports"
        await asyncio.get_event_loop().run_in_executor(
            None, reports_dir.mkdir, True
        )

        report_file = reports_dir / f"async_completion_{int(time.time())}.md"
        report_content = self.generate_report(summary)

        full_report = f"""# 🎉 Async Project Completion Report

**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Project:** {self.project_root}
**Success Rate:** {summary['success_rate']:.1f}%
**Execution Mode:** Async (Dynamic Scheduling)

{report_content}

## 📊 Dashboard
View the live dashboard at: http://localhost:8080

## ✅ Async Execution Complete!
"""

        async with aiofiles.open(report_file, 'w') as f:
            await f.write(full_report)

        return str(report_file)

    async def save_execution_log(self, summary: Dict[str, Any], log_dir: Optional[str] = None):
        """Save execution log asynchronously."""
        if not log_dir:
            log_dir = self.project_root / ".hydra" / "logs"
        else:
            log_dir = Path(log_dir)

        await asyncio.get_event_loop().run_in_executor(
            None, log_dir.mkdir, True, True
        )

        log_file = log_dir / f"async_parallel_execution_{int(time.time())}.json"

        log_data = {
            "timestamp": time.time(),
            "execution_mode": "async",
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

        async with aiofiles.open(log_file, 'w') as f:
            await f.write(json.dumps(log_data, indent=2))

        return str(log_file)

    def shutdown(self):
        """Shutdown the executor and clean up resources."""
        if hasattr(self, 'agent_pool'):
            self.agent_pool.stop()
            logger.info("🛑 Async agent pool shutdown complete")
