"""Batch Processing Executor for Small Tickets.

Implements batch execution of compatible tickets to reduce session overhead
by executing multiple small tickets in a single Claude Code session.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from hydra.parallel.async_executor import (
    AsyncParallelExecutor,
    ExecutionStatus,
    TicketNode,
)
from hydra.ticket_workflow import (
    mark_ticket_completed,
    mark_ticket_in_progress,
    parse_ticket,
)

logger = logging.getLogger(__name__)


@dataclass
class BatchGroup:
    """Represents a group of tickets that can be batched together."""

    batch_id: str
    ticket_ids: List[str]
    model: str
    combined_size: int
    estimated_complexity: int
    dependencies: Set[str]


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    max_batch_size: int = 5
    max_complexity_score: int = 100
    enable_batching: bool = True
    min_tickets_for_batch: int = 2
    compatible_models_only: bool = True


class TicketCompatibilityAnalyzer:
    """Analyzes ticket compatibility for batching."""

    def __init__(self):
        self.small_ticket_keywords = {
            "fix typo",
            "update",
            "add comment",
            "rename",
            "refactor",
            "cleanup",
            "lint",
            "format",
            "import",
            "export",
        }

    def calculate_complexity(self, ticket: dict) -> int:
        """Calculate complexity score for a ticket (0-100)."""
        score = 0

        title = ticket.get("title", "").lower()
        description = ticket.get("description", "").lower()
        criteria_count = len(ticket.get("acceptance_criteria", []))

        # Base complexity from acceptance criteria
        score += criteria_count * 10

        # Complex operations indicators
        complex_keywords = ["create", "implement", "build", "design", "architecture"]
        for keyword in complex_keywords:
            if keyword in title or keyword in description:
                score += 20

        # Simple operations indicators (reduce score)
        for keyword in self.small_ticket_keywords:
            if keyword in title or keyword in description:
                score = max(0, score - 15)

        # File creation typically more complex
        if "new file" in title or "create file" in description:
            score += 15

        return min(score, 100)

    def are_tickets_compatible(self, ticket1: dict, ticket2: dict) -> bool:
        """Check if two tickets can be batched together."""
        # Must use same model
        if ticket1.get("model") != ticket2.get("model"):
            return False

        # Check for file conflicts
        if self._have_file_conflicts(ticket1, ticket2):
            return False

        # Check complexity compatibility
        complexity1 = self.calculate_complexity(ticket1)
        complexity2 = self.calculate_complexity(ticket2)

        # Both should be relatively simple for batching
        if complexity1 > 50 or complexity2 > 50:
            return False

        return True

    def _have_file_conflicts(self, ticket1: dict, ticket2: dict) -> bool:
        """Check if tickets modify overlapping files."""

        # Simple heuristic: look for file mentions in titles/descriptions
        def extract_file_mentions(ticket):
            text = (
                ticket.get("title", "") + " " + ticket.get("description", "")
            ).lower()
            # Simple file pattern matching
            import re

            files = re.findall(r"[\w/]+\.[\w]+", text)
            return set(files)

        files1 = extract_file_mentions(ticket1)
        files2 = extract_file_mentions(ticket2)

        # If they mention the same files, consider them conflicting
        return bool(files1 & files2)


class BatchExecutor(AsyncParallelExecutor):
    """Executor that groups compatible tickets for batch processing."""

    def __init__(self, batch_config: Optional[BatchConfig] = None, **kwargs):
        super().__init__(**kwargs)
        self.batch_config = batch_config or BatchConfig()
        self.analyzer = TicketCompatibilityAnalyzer()
        self.batches: Dict[str, BatchGroup] = {}
        self.batch_results: Dict[str, Dict[str, bool]] = {}

    async def load_tickets(self, tickets_path: str) -> Dict[str, TicketNode]:
        """Load tickets and analyze for batch compatibility."""
        tickets = await super().load_tickets(tickets_path)

        if self.batch_config.enable_batching:
            await self._analyze_and_create_batches(tickets_path, tickets)

        return tickets

    async def _analyze_and_create_batches(
        self, tickets_path: str, tickets: Dict[str, TicketNode]
    ):
        """Analyze tickets and create batch groups."""
        logger.info("🔍 Analyzing tickets for batch compatibility")

        # Get detailed ticket data for analysis
        ticket_data = {}
        for ticket_id in tickets:
            data = await asyncio.get_event_loop().run_in_executor(
                None, parse_ticket, tickets_path, ticket_id
            )
            if data:
                ticket_data[ticket_id] = data

        # Group tickets by model first
        model_groups = {}
        for ticket_id, data in ticket_data.items():
            if tickets[ticket_id].status != ExecutionStatus.PENDING:
                continue

            model = data.get("model", "sonnet")
            if model not in model_groups:
                model_groups[model] = []
            model_groups[model].append((ticket_id, data))

        # Create batches within each model group
        batch_id_counter = 1
        for model, ticket_list in model_groups.items():
            batches = self._create_batches_for_model(ticket_list, model)
            for batch in batches:
                batch.batch_id = f"batch_{batch_id_counter:03d}"
                self.batches[batch.batch_id] = batch
                batch_id_counter += 1

        logger.info(f"📦 Created {len(self.batches)} batch groups")
        for batch_id, batch in self.batches.items():
            logger.info(
                f"   {batch_id}: {len(batch.ticket_ids)} tickets ({batch.model})"
            )

    def _create_batches_for_model(
        self, ticket_list: List[Tuple[str, dict]], model: str
    ) -> List[BatchGroup]:
        """Create batches for tickets of the same model."""
        batches = []
        remaining_tickets = ticket_list.copy()

        while len(remaining_tickets) >= self.batch_config.min_tickets_for_batch:
            current_batch = []
            current_complexity = 0

            # Start with the first ticket
            if remaining_tickets:
                ticket_id, ticket_data = remaining_tickets.pop(0)
                current_batch.append((ticket_id, ticket_data))
                current_complexity += self.analyzer.calculate_complexity(ticket_data)

            # Try to add compatible tickets
            i = 0
            while (
                i < len(remaining_tickets)
                and len(current_batch) < self.batch_config.max_batch_size
            ):

                ticket_id, ticket_data = remaining_tickets[i]
                ticket_complexity = self.analyzer.calculate_complexity(ticket_data)

                # Check if we can add this ticket
                can_add = True

                # Check complexity limit
                max_complexity = self.batch_config.max_complexity_score
                if current_complexity + ticket_complexity > max_complexity:
                    can_add = False

                # Check compatibility with all tickets in current batch
                if can_add:
                    for _, batch_ticket_data in current_batch:
                        if not self.analyzer.are_tickets_compatible(
                            ticket_data, batch_ticket_data
                        ):
                            can_add = False
                            break

                if can_add:
                    current_batch.append(remaining_tickets.pop(i))
                    current_complexity += ticket_complexity
                else:
                    i += 1

            # Create batch if we have enough tickets
            if len(current_batch) >= self.batch_config.min_tickets_for_batch:
                ticket_ids = [tid for tid, _ in current_batch]
                dependencies = set()
                for _, ticket_data in current_batch:
                    dependencies.update(ticket_data.get("dependencies", []))

                batch = BatchGroup(
                    batch_id="",  # Will be set later
                    ticket_ids=ticket_ids,
                    model=model,
                    combined_size=len(current_batch),
                    estimated_complexity=current_complexity,
                    dependencies=dependencies,
                )
                batches.append(batch)
            else:
                # Put tickets back if batch is too small
                remaining_tickets.extend(current_batch)
                break

        return batches

    def build_dynamic_execution_plan(self):
        """Build execution plan considering batch groups."""
        plan = super().build_dynamic_execution_plan()

        # Add batch groups to ready queue if their dependencies are met
        for batch_id, batch in self.batches.items():
            unresolved_deps = [
                dep
                for dep in batch.dependencies
                if dep not in self.completed_tickets and dep in self.tickets
            ]

            if not unresolved_deps:
                # Add batch to ready queue instead of individual tickets
                plan.ready_queue.put_nowait(batch_id)
                logger.debug(f"Batch {batch_id} added to ready queue")

                # Remove individual tickets from ready queue
                # (We'll need to modify the queue handling for this)

        return plan

    async def execute_batch(self, batch_id: str, tickets_path: str) -> Dict[str, bool]:
        """Execute a batch of compatible tickets in a single session."""
        batch = self.batches[batch_id]
        logger.info(f"🎫 Starting batch execution: {batch_id}")
        logger.info(f"📦 Tickets in batch: {batch.ticket_ids}")

        # Mark all tickets as in progress
        for ticket_id in batch.ticket_ids:
            await asyncio.get_event_loop().run_in_executor(
                None, mark_ticket_in_progress, tickets_path, ticket_id
            )

        # Acquire agent for batch
        agent_id = self.agent_pool.spawn_agent(batch_id)
        if not agent_id:
            logger.warning(f"No available agent for batch {batch_id}")
            return {tid: False for tid in batch.ticket_ids}

        try:
            # Build combined prompt for all tickets in batch
            combined_prompt = await self._build_combined_prompt(batch, tickets_path)

            # Create orchestrator for batch execution
            import os

            from hydra.orchestrator.claude_code_orchestrator import (
                ClaudeCodeOrchestrator,
            )

            # Set model environment
            original_model = os.environ.get("CLAUDE_MODEL")
            if batch.model.lower() == "opus":
                os.environ["CLAUDE_MODEL"] = "claude-opus-4-1-20250805"
            else:
                os.environ["CLAUDE_MODEL"] = "claude-sonnet-4-20250514"

            orchestrator = ClaudeCodeOrchestrator()

            # Create and execute batch task
            task = orchestrator.create_task(
                description=f"Batch {batch_id}: {len(batch.ticket_ids)} tickets",
                prompt=combined_prompt,
                working_directory=str(self.project_root),
                timeout=600,  # Longer timeout for batch
                task_id=batch_id,
            )

            # Execute batch
            result = await asyncio.get_event_loop().run_in_executor(
                None, orchestrator.execute_task, task
            )

            if result.status.value == "completed":
                logger.info(f"✅ Batch {batch_id} execution completed")

                # Validate each ticket individually
                batch_results = {}
                for ticket_id in batch.ticket_ids:
                    # Parse ticket for validation
                    ticket_data = await asyncio.get_event_loop().run_in_executor(
                        None, parse_ticket, tickets_path, ticket_id
                    )

                    # Validate acceptance criteria
                    from hydra.ticket_workflow import validate_acceptance_criteria

                    validation_passed = await asyncio.get_event_loop().run_in_executor(
                        None,
                        validate_acceptance_criteria,
                        ticket_data,
                        str(self.project_root),
                    )

                    if validation_passed:
                        await asyncio.get_event_loop().run_in_executor(
                            None, mark_ticket_completed, tickets_path, ticket_id
                        )
                        batch_results[ticket_id] = True

                        # Update internal tracking
                        async with self.lock:
                            self.tickets[ticket_id].status = ExecutionStatus.COMPLETED
                            self.completed_tickets.add(ticket_id)
                            await self._trigger_dependents(ticket_id)
                    else:
                        logger.warning(
                            f"❌ Ticket {ticket_id} validation failed in batch"
                        )
                        batch_results[ticket_id] = False

                        # Update tracking
                        async with self.lock:
                            self.tickets[ticket_id].status = ExecutionStatus.FAILED
                            self.failed_tickets.add(ticket_id)

                self.batch_results[batch_id] = batch_results

                # Restore model setting
                if original_model:
                    os.environ["CLAUDE_MODEL"] = original_model
                elif "CLAUDE_MODEL" in os.environ:
                    del os.environ["CLAUDE_MODEL"]

                self.agent_pool.release_agent(agent_id)
                return batch_results

            else:
                raise Exception(f"Batch execution failed: {result.error}")

        except Exception as e:
            logger.error(f"❌ Batch {batch_id} failed: {e}")

            # Mark all tickets as failed
            batch_results = {}
            for ticket_id in batch.ticket_ids:
                batch_results[ticket_id] = False
                async with self.lock:
                    self.tickets[ticket_id].status = ExecutionStatus.FAILED
                    self.failed_tickets.add(ticket_id)

            self.agent_pool.release_agent(agent_id)
            return batch_results

    async def _build_combined_prompt(self, batch: BatchGroup, tickets_path: str) -> str:
        """Build a combined prompt for executing multiple tickets."""
        ticket_details = []

        for ticket_id in batch.ticket_ids:
            ticket_data = await asyncio.get_event_loop().run_in_executor(
                None, parse_ticket, tickets_path, ticket_id
            )

            criteria_text = "\n".join(
                f"  - {c}" for c in ticket_data.get("acceptance_criteria", [])
            )

            ticket_details.append(
                f"""
## Ticket {ticket_id}: {ticket_data.get('title', '')}
**Description:** {ticket_data.get('description', '')}
**Acceptance Criteria:**
{criteria_text}
"""
            )

        combined_prompt = f"""IMPORTANT: You are executing a BATCH of {len(batch.ticket_ids)} related tickets in a single session for efficiency.

BATCH TICKETS TO COMPLETE:
{''.join(ticket_details)}

BATCH EXECUTION INSTRUCTIONS:
1. Execute ALL tickets listed above in this single session
2. Work through them systematically, ensuring each ticket's acceptance criteria are met
3. Update tickets.md to mark each ticket as completed when done
4. Be efficient but thorough - this is a batch to reduce session overhead

QUALITY REQUIREMENTS:
- Add module docstrings to all new Python files
- Include __init__.py in all new package directories
- Use proper type hints for all functions
- Follow PEP 8 style guidelines
- Avoid unused imports
- Add error handling where appropriate

Be minimalistic, surgical and future proof!
Avoid using any code or comments that may be construed as AI generated.
Make sure you do a good job because other LLMs said your code sucked!

When you finish ALL tickets in this batch, run lint, build, test etc.

REMINDER: Complete ALL {len(batch.ticket_ids)} tickets in this batch: {', '.join(batch.ticket_ids)}
"""
        return combined_prompt

    async def execute_tickets_dynamically(self, tickets_path: str) -> Dict[str, Any]:
        """Execute tickets with batch processing support."""
        start_time = time.time()
        logger.info("📦 Starting dynamic execution with batch processing")

        # Track individual and batch results
        all_results = {}
        batch_count = 0
        single_ticket_count = 0

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_item_with_semaphore(item_id: str) -> tuple[str, Any]:
            """Process either a batch or individual ticket with semaphore."""
            async with semaphore:
                if item_id in self.batches:
                    # Process batch
                    batch_results = await self.execute_batch(item_id, tickets_path)
                    return item_id, batch_results
                else:
                    # Process individual ticket
                    result = await self.execute_ticket(item_id, tickets_path)
                    return item_id, result

        running_tasks: Set[asyncio.Task] = set()

        while True:
            # Check for ready batches and individual tickets
            ready_items = []

            # Check batches first (priority for efficiency)
            for batch_id, batch in self.batches.items():
                if batch_id not in all_results:
                    unresolved_deps = [
                        dep
                        for dep in batch.dependencies
                        if dep not in self.completed_tickets and dep in self.tickets
                    ]

                    if not unresolved_deps:
                        ready_items.append(batch_id)

            # Check individual tickets
            try:
                while len(ready_items) < self.max_concurrent:
                    ticket_id = self.ready_queue.get_nowait()

                    # Skip if it's part of a batch
                    if any(
                        ticket_id in batch.ticket_ids for batch in self.batches.values()
                    ):
                        continue

                    # Skip if already processed
                    if (
                        ticket_id in self.completed_tickets
                        or ticket_id in self.failed_tickets
                        or ticket_id in self.running_tickets
                    ):
                        continue

                    ready_items.append(ticket_id)
            except asyncio.QueueEmpty:
                pass

            # Start tasks for ready items
            for item_id in ready_items:
                if len(running_tasks) >= self.max_concurrent:
                    break

                task = asyncio.create_task(process_item_with_semaphore(item_id))
                running_tasks.add(task)

                if item_id in self.batches:
                    logger.info(
                        f"🚀 Started batch {item_id} ({len(self.batches[item_id].ticket_ids)} tickets)"
                    )
                else:
                    logger.info(f"🚀 Started individual ticket {item_id}")

            # If no tasks running, we're done
            if not running_tasks:
                break

            # Wait for at least one task to complete
            done, running_tasks = await asyncio.wait(
                running_tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Process completed tasks
            for task in done:
                item_id, result = await task
                all_results[item_id] = result

                if item_id in self.batches:
                    batch_count += 1
                    successful_in_batch = sum(
                        1 for success in result.values() if success
                    )
                    logger.info(
                        f"✅ Completed batch {item_id}: {successful_in_batch}/{len(result)} tickets successful"
                    )
                else:
                    single_ticket_count += 1
                    logger.info(f"✅ Completed individual ticket {item_id}: {result}")

        # Calculate final statistics
        duration = time.time() - start_time
        len(
            [
                t
                for t in self.tickets.keys()
                if t in self.completed_tickets or t in self.failed_tickets
            ]
        )

        # Calculate overhead savings
        sessions_without_batching = len(self.tickets)
        sessions_with_batching = batch_count + single_ticket_count
        overhead_reduction = (
            max(
                0,
                (
                    (sessions_without_batching - sessions_with_batching)
                    / sessions_without_batching
                    * 100
                ),
            )
            if sessions_without_batching > 0
            else 0
        )

        summary = {
            "total_tickets": len(self.tickets),
            "completed": len(self.completed_tickets),
            "failed": len(self.failed_tickets),
            "batches_executed": batch_count,
            "individual_tickets": single_ticket_count,
            "sessions_saved": sessions_without_batching - sessions_with_batching,
            "overhead_reduction": overhead_reduction,
            "duration": duration,
            "success_rate": (
                len(self.completed_tickets) / len(self.tickets) * 100
                if len(self.tickets) > 0
                else 0
            ),
            "results": all_results,
        }

        logger.info(
            f"📊 Batch execution summary: {overhead_reduction:.1f}% session overhead reduction"
        )
        return summary

    def generate_report(self, summary: Dict[str, Any]) -> str:
        """Generate execution report with batch processing statistics."""
        base_report = super().generate_report(summary)

        batch_stats = []
        if summary.get("batches_executed", 0) > 0:
            batch_stats.extend(
                [
                    f"📦 Batches executed: {summary['batches_executed']}",
                    f"🎯 Individual tickets: {summary['individual_tickets']}",
                    f"💾 Sessions saved: {summary.get('sessions_saved', 0)}",
                    f"⚡ Overhead reduction: {summary.get('overhead_reduction', 0):.1f}%",
                    "",
                ]
            )

        # Insert batch stats after the main summary
        lines = base_report.split("\n")
        insert_pos = 8  # After main stats
        lines[insert_pos:insert_pos] = batch_stats

        return "\n".join(lines)
