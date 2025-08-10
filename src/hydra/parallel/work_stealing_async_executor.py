"""Work Stealing Async Executor for Hydra.

Integrates WorkStealingScheduler with AsyncParallelExecutor for optimal load balancing.
"""

import asyncio
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
from hydra.parallel.work_stealing_scheduler import (
    StealingPolicy,
    Task,
    WorkStealingScheduler,
)
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


class WorkStealingAsyncExecutor:
    """Async executor with work stealing for optimal load balancing."""

    def __init__(
        self,
        max_concurrent: int = 3,
        project_root: str = ".",
        dashboard_state=None,
        stealing_policy: StealingPolicy = StealingPolicy.BALANCED,
        rebalance_interval: float = 10.0
    ):
        self.max_concurrent = max_concurrent
        self.project_root = Path(project_root).resolve()
        self.tickets: Dict[str, TicketNode] = {}
        self.lock = asyncio.Lock()
        self.completed_tickets: Set[str] = set()
        self.failed_tickets: Set[str] = set()
        self.running_tickets: Set[str] = set()
        self.orchestrators: Dict[str, ClaudeCodeOrchestrator] = {}
        self.dashboard_state = dashboard_state

        # Initialize work stealing scheduler
        self.work_stealing_scheduler = WorkStealingScheduler(
            num_workers=max_concurrent,
            stealing_policy=stealing_policy,
            rebalance_interval=rebalance_interval
        )

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

        # Start work stealing scheduler
        self.work_stealing_scheduler.start()

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

    def build_execution_plan(self):
        """Build execution plan and submit tasks to work stealing scheduler."""
        logger.info("Building execution plan with work stealing scheduler")

        # Submit ready tickets to work stealing scheduler
        ready_count = 0
        for ticket_id, node in self.tickets.items():
            if node.status == ExecutionStatus.PENDING:
                # Check if dependencies are satisfied
                unresolved_deps = [
                    dep for dep in node.dependencies
                    if dep not in self.completed_tickets and dep in self.tickets
                ]

                if not unresolved_deps:
                    # Estimate task duration based on model and description
                    estimated_duration = self._estimate_task_duration(node)

                    task = Task(
                        task_id=ticket_id,
                        priority=self._calculate_task_priority(node),
                        estimated_duration=estimated_duration,
                        dependencies=node.dependencies
                    )

                    if self.work_stealing_scheduler.submit_task(task):
                        ready_count += 1
                        logger.debug(f"Submitted ticket {ticket_id} to work stealing scheduler")
                    else:
                        # Track as dependency waiter
                        for dep in unresolved_deps:
                            if dep not in self.dependency_waiters:
                                self.dependency_waiters[dep] = set()
                            self.dependency_waiters[dep].add(ticket_id)

        logger.info(f"Submitted {ready_count} tickets to work stealing scheduler")

    def _estimate_task_duration(self, node: TicketNode) -> float:
        """Estimate task duration based on model and complexity."""
        # Base duration by model
        base_durations = {
            'opus': 180.0,  # Opus tasks tend to be more complex
            'sonnet': 120.0  # Sonnet is faster
        }

        model_key = node.model.lower()
        base_duration = base_durations.get(model_key, 120.0)

        # Adjust based on title complexity
        complexity_keywords = ['refactor', 'implement', 'create', 'enhance', 'optimize']
        complexity_multiplier = 1.0

        title_lower = node.title.lower()
        for keyword in complexity_keywords:
            if keyword in title_lower:
                complexity_multiplier += 0.2

        return base_duration * complexity_multiplier

    def _calculate_task_priority(self, node: TicketNode) -> int:
        """Calculate task priority based on dependencies and importance."""
        # Higher priority for tasks that others depend on
        dependency_count = sum(
            1 for other_node in self.tickets.values()
            if node.ticket_id in other_node.dependencies
        )

        # Base priority + dependency bonus
        priority = 5 + (dependency_count * 2)

        # Opus tasks get slight priority boost for quality
        if node.model.lower() == 'opus':
            priority += 1

        return priority

    async def execute_ticket(self, ticket_id: str, worker_id: str, tickets_path: str) -> bool:
        """Execute a single ticket asynchronously with work stealing integration."""
        start_delay = asyncio.create_task(asyncio.sleep(0.1 * hash(ticket_id) % 50 / 10))
        await start_delay

        logger.info(f"Worker {worker_id} starting execution of ticket {ticket_id}")

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
        logger.info(f"🤖 Model: {node.model} (Worker: {worker_id})")

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
            prompt = f"""IMPORTANT: You MUST execute ONLY Ticket {ticket_id} from tickets.md - NOT any other ticket!

Find and execute specifically "## Ticket {ticket_id}:" in tickets.md

DO NOT work on any other ticket even if it appears first or seems easier. You are assigned ONLY to ticket {ticket_id}.

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

When you finish, ensure acceptance criteria is met then update tickets.md and then run lint, build, test etc before we move on.

DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS! This has to be production quality, take your time.

REMINDER: You are working on Ticket {ticket_id} ONLY. Ignore all other tickets."""

            # Create and execute task
            task = orchestrator.create_task(
                description=f"Ticket {ticket_id}: {node.title}",
                prompt=prompt,
                working_directory=str(self.project_root),
                timeout=300,
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
                    None, validate_acceptance_criteria, ticket_data, str(self.project_root)
                )

                if validation_passed:
                    logger.info("✅ Acceptance criteria validated")
                else:
                    logger.warning("❌ Acceptance criteria validation failed")
                    raise Exception("Acceptance criteria not met")

                # Run quality fixes
                logger.info(f"🔧 Running automatic quality fixes for ticket {ticket_id}")
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

                # Update work stealing scheduler metrics
                task_obj = Task(task_id=ticket_id)
                task_obj.assigned_at = node.start_time
                self.work_stealing_scheduler.complete_task(worker_id, task_obj, quality_passed)

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

            # Update work stealing scheduler metrics for failed task
            task_obj = Task(task_id=ticket_id)
            task_obj.assigned_at = node.start_time if node.start_time else time.time()
            self.work_stealing_scheduler.complete_task(worker_id, task_obj, False)

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
                    # Submit to work stealing scheduler
                    estimated_duration = self._estimate_task_duration(node)
                    task = Task(
                        task_id=waiting_ticket,
                        priority=self._calculate_task_priority(node),
                        estimated_duration=estimated_duration,
                        dependencies=node.dependencies
                    )

                    if self.work_stealing_scheduler.submit_task(task):
                        logger.debug(f"Submitted dependent ticket {waiting_ticket} to work stealing scheduler")

            # Clean up
            del self.dependency_waiters[completed_ticket_id]

    async def execute_with_work_stealing(self, tickets_path: str) -> Dict[str, Any]:
        """Execute tickets using work stealing scheduler."""
        start_time = time.time()

        # Initialize dashboard session
        if self.dashboard_state:
            session_id = str(uuid.uuid4())[:8]
            self.dashboard_state.start_session(
                session_id=session_id,
                tickets_path=tickets_path,
                total_tickets=len(self.tickets),
                total_waves=1,
                workers=self.max_concurrent
            )

        logger.info("📋 Work Stealing Execution Plan")
        logger.info(f"Total tickets: {len(self.tickets)}")
        logger.info(f"Max concurrent workers: {self.max_concurrent}")
        logger.info(f"Stealing policy: {self.work_stealing_scheduler.stealing_policy.value}")

        # Build execution plan and submit initial tasks
        self.build_execution_plan()

        # Create worker coroutines
        async def worker_coroutine(worker_id: str):
            """Worker coroutine that processes tasks using work stealing."""
            logger.info(f"Worker {worker_id} started")

            while True:
                # Get task from work stealing scheduler
                task = self.work_stealing_scheduler.get_task(worker_id)

                if task is None:
                    # No tasks available, check if we should continue
                    await asyncio.sleep(1.0)  # Brief wait before checking again

                    # Check if all work is done
                    active_tickets = len(self.running_tickets)
                    pending_tasks = sum(
                        len(queue) for queue in self.work_stealing_scheduler.worker_queues.values()
                    )

                    if active_tickets == 0 and pending_tasks == 0:
                        # No more work to do
                        break
                    continue

                # Execute the task
                success = await self.execute_ticket(task.task_id, worker_id, tickets_path)
                logger.debug(f"Worker {worker_id} completed task {task.task_id}: {success}")

            logger.info(f"Worker {worker_id} finished")

        # Start all workers
        worker_tasks = []
        for i in range(self.max_concurrent):
            worker_id = f"worker_{i}"
            worker_task = asyncio.create_task(worker_coroutine(worker_id))
            worker_tasks.append(worker_task)

        # Wait for all workers to complete
        await asyncio.gather(*worker_tasks, return_exceptions=True)

        # Generate summary
        duration = time.time() - start_time
        stealing_metrics = self.work_stealing_scheduler.get_metrics()

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
            "work_stealing_metrics": stealing_metrics,
            "efficiency_improvement": self._calculate_efficiency_improvement(duration)
        }

        return summary

    def _calculate_efficiency_improvement(self, duration: float) -> Dict[str, Any]:
        """Calculate efficiency improvement from work stealing."""
        stealing_metrics = self.work_stealing_scheduler.get_metrics()

        total_steals = sum(
            worker["tasks_stolen_to"] + worker["tasks_stolen_from"]
            for worker in stealing_metrics["worker_metrics"].values()
        )

        load_distribution = self.work_stealing_scheduler.get_load_distribution()
        load_variance = sum(
            (load - 100/len(load_distribution))**2
            for load in load_distribution.values()
        ) / len(load_distribution)

        # Estimate improvement (simplified calculation)
        estimated_improvement = min(40, total_steals * 2 + max(0, 50 - load_variance))

        return {
            "total_work_steals": total_steals,
            "load_variance": load_variance,
            "estimated_time_reduction_percent": estimated_improvement,
            "final_load_distribution": load_distribution
        }

    def generate_report(self, summary: Dict[str, Any]) -> str:
        """Generate execution report with work stealing metrics."""
        from hydra.ticket_workflow import get_quality_summary
        quality_summary = get_quality_summary(self.tickets_path) if hasattr(self, 'tickets_path') else None

        lines = [
            f"\n{'='*60}",
            "📊 Work Stealing Async Execution Report",
            f"{'='*60}",
            f"Total tickets: {summary['total_tickets']}",
            f"✅ Completed (Quality Passed): {summary['completed']}",
            f"❌ Failed/Quality Issues: {summary['failed']}",
            f"⛔ Blocked: {summary['blocked']}",
            f"📈 Success rate: {summary['success_rate']:.1f}%",
            f"⏱️ Total duration: {summary['duration']:.2f}s",
            "",
            "🔄 Work Stealing Metrics:",
            f"   Policy: {summary['work_stealing_metrics']['stealing_policy']}",
            f"   Total work steals: {summary['efficiency_improvement']['total_work_steals']}",
            f"   Estimated time reduction: {summary['efficiency_improvement']['estimated_time_reduction_percent']:.1f}%",
            f"   Load variance: {summary['efficiency_improvement']['load_variance']:.2f}",
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

        # Add worker efficiency details
        lines.extend([
            "",
            "👥 Worker Efficiency:",
        ])

        worker_metrics = summary['work_stealing_metrics']['worker_metrics']
        for worker_id, metrics in worker_metrics.items():
            efficiency = metrics['efficiency_score']
            steals_from = metrics['tasks_stolen_from']
            steals_to = metrics['tasks_stolen_to']
            lines.append(
                f"   {worker_id}: {efficiency:.2f} efficiency "
                f"(gave {steals_from}, received {steals_to})"
            )

        lines.append(f"{'='*60}")
        return "\n".join(lines)

    def shutdown(self):
        """Shutdown the executor and clean up resources."""
        if hasattr(self, 'work_stealing_scheduler'):
            self.work_stealing_scheduler.stop()

        if hasattr(self, 'agent_pool'):
            self.agent_pool.stop()
            logger.info("🛑 Work stealing async executor shutdown complete")
