"""Async orchestrator for parallel ticket execution using asyncio.gather."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from hydra.database.async_database import AsyncTicketDatabase
from hydra.providers.async_base import AsyncLLMProvider

logger = logging.getLogger(__name__)


class TicketStatus(Enum):
    """Ticket execution status."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass
class TicketResult:
    """Result of ticket execution."""

    ticket_number: str
    status: TicketStatus
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    tokens_used: int = 0


class AsyncTicketOrchestrator:
    """Orchestrator for parallel ticket execution using async patterns."""

    def __init__(
        self,
        provider: AsyncLLMProvider,
        database: Optional[AsyncTicketDatabase] = None,
        max_concurrent: int = 5,
        timeout_per_ticket: int = 300
    ):
        self.provider = provider
        self.database = database or AsyncTicketDatabase()
        self.max_concurrent = max_concurrent
        self.timeout_per_ticket = timeout_per_ticket
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_ticket(
        self,
        ticket: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> TicketResult:
        """Execute a single ticket asynchronously."""
        ticket_number = ticket.get("ticket_number", ticket.get("id", "unknown"))
        start_time = asyncio.get_event_loop().time()

        try:
            # Update status to IN_PROGRESS
            if self.database:
                await self.database.update_ticket_status(
                    ticket_number,
                    TicketStatus.IN_PROGRESS.value
                )

            # Build prompt from ticket
            prompt = self._build_prompt(ticket, context)

            # Execute with timeout
            result = await asyncio.wait_for(
                self.provider.generate(prompt),
                timeout=self.timeout_per_ticket
            )

            # Validate acceptance criteria if present
            if ticket.get("acceptance_criteria"):
                validation_result = await self._validate_criteria(
                    ticket,
                    result
                )
                if not validation_result["all_passed"]:
                    logger.warning(
                        f"Ticket {ticket_number} validation failed: "
                        f"{validation_result['failed_criteria']}"
                    )

            # Update status to DONE
            if self.database:
                await self.database.update_ticket_status(
                    ticket_number,
                    TicketStatus.DONE.value
                )

            execution_time = asyncio.get_event_loop().time() - start_time

            return TicketResult(
                ticket_number=ticket_number,
                status=TicketStatus.DONE,
                result=result,
                execution_time=execution_time,
                tokens_used=len(result.split())  # Rough estimate
            )

        except asyncio.TimeoutError:
            error_msg = f"Ticket {ticket_number} timed out after {self.timeout_per_ticket}s"
            logger.error(error_msg)

            if self.database:
                await self.database.update_ticket_status(
                    ticket_number,
                    TicketStatus.FAILED.value
                )

            return TicketResult(
                ticket_number=ticket_number,
                status=TicketStatus.FAILED,
                error=error_msg,
                execution_time=self.timeout_per_ticket
            )

        except Exception as e:
            error_msg = f"Ticket {ticket_number} failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            if self.database:
                await self.database.update_ticket_status(
                    ticket_number,
                    TicketStatus.FAILED.value
                )

            execution_time = asyncio.get_event_loop().time() - start_time

            return TicketResult(
                ticket_number=ticket_number,
                status=TicketStatus.FAILED,
                error=error_msg,
                execution_time=execution_time
            )

    async def execute_tickets_parallel(
        self,
        tickets: List[Dict[str, Any]],
        respect_dependencies: bool = True
    ) -> List[TicketResult]:
        """Execute multiple tickets in parallel using asyncio.gather."""
        if respect_dependencies:
            # Execute in dependency order
            return await self._execute_with_dependencies(tickets)
        else:
            # Execute all tickets in parallel
            return await self._execute_parallel_batch(tickets)

    async def _execute_parallel_batch(
        self,
        tickets: List[Dict[str, Any]]
    ) -> List[TicketResult]:
        """Execute a batch of tickets in parallel without dependencies."""

        async def execute_with_semaphore(ticket: Dict[str, Any]) -> TicketResult:
            async with self._semaphore:
                return await self.execute_ticket(ticket)

        # Use asyncio.gather for true parallel execution
        tasks = [execute_with_semaphore(ticket) for ticket in tickets]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        return results

    async def _execute_with_dependencies(
        self,
        tickets: List[Dict[str, Any]]
    ) -> List[TicketResult]:
        """Execute tickets respecting dependency order."""
        # Build dependency graph
        dependency_graph = self._build_dependency_graph(tickets)

        # Topological sort to get execution order
        execution_layers = self._topological_sort(dependency_graph)

        all_results = []
        completed_tickets = set()

        # Execute each layer in parallel
        for layer in execution_layers:
            # Filter tickets that are ready to execute
            ready_tickets = []
            for ticket_id in layer:
                ticket = next(
                    (t for t in tickets if self._get_ticket_id(t) == ticket_id),
                    None
                )
                if ticket:
                    deps = ticket.get("dependencies", [])
                    if all(dep in completed_tickets for dep in deps):
                        ready_tickets.append(ticket)

            if ready_tickets:
                # Execute current layer in parallel using asyncio.gather
                layer_results = await self._execute_parallel_batch(ready_tickets)

                # Track completed tickets
                for result in layer_results:
                    if result.status == TicketStatus.DONE:
                        completed_tickets.add(result.ticket_number)

                all_results.extend(layer_results)

        return all_results

    async def execute_project(
        self,
        project_id: int,
        filter_status: Optional[str] = "TODO"
    ) -> Dict[str, Any]:
        """Execute all tickets in a project."""
        # Fetch tickets from database
        tickets = await self.database.get_all_tickets(
            project_id=project_id,
            status=filter_status
        )

        logger.info(f"Executing {len(tickets)} tickets for project {project_id}")

        start_time = asyncio.get_event_loop().time()

        # Execute tickets in parallel
        results = await self.execute_tickets_parallel(
            tickets,
            respect_dependencies=True
        )

        total_time = asyncio.get_event_loop().time() - start_time

        # Calculate statistics
        stats = self._calculate_stats(results, total_time)

        return {
            "project_id": project_id,
            "results": results,
            "stats": stats
        }

    async def stream_execute_tickets(
        self,
        tickets: List[Dict[str, Any]],
        callback=None
    ):
        """Execute tickets with streaming updates."""

        async def execute_and_stream(ticket: Dict[str, Any]):
            ticket_number = self._get_ticket_id(ticket)

            # Stream execution updates
            if callback:
                await callback({
                    "type": "start",
                    "ticket": ticket_number,
                    "timestamp": datetime.utcnow().isoformat()
                })

            result = await self.execute_ticket(ticket)

            if callback:
                await callback({
                    "type": "complete",
                    "ticket": ticket_number,
                    "status": result.status.value,
                    "timestamp": datetime.utcnow().isoformat()
                })

            return result

        # Execute with streaming updates
        tasks = [execute_and_stream(ticket) for ticket in tickets]
        return await asyncio.gather(*tasks)

    def _build_prompt(
        self,
        ticket: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build execution prompt from ticket."""
        prompt_parts = [
            "Execute the following ticket:",
            f"Title: {ticket.get('title', 'Untitled')}",
            f"Description: {ticket.get('description', 'No description')}",
        ]

        if ticket.get("acceptance_criteria"):
            prompt_parts.append("Acceptance Criteria:")
            for criterion in ticket["acceptance_criteria"]:
                if isinstance(criterion, dict):
                    prompt_parts.append(f"- {criterion.get('criterion', criterion)}")
                else:
                    prompt_parts.append(f"- {criterion}")

        if context:
            prompt_parts.append(f"Context: {json.dumps(context)}")

        return "\n".join(prompt_parts)

    async def _validate_criteria(
        self,
        ticket: Dict[str, Any],
        result: str
    ) -> Dict[str, Any]:
        """Validate acceptance criteria."""
        criteria = ticket.get("acceptance_criteria", [])

        if not criteria:
            return {"all_passed": True, "failed_criteria": []}

        # Build validation prompt
        validation_prompt = f"""
        Validate if the following result meets the acceptance criteria.
        
        Result:
        {result}
        
        Acceptance Criteria:
        {json.dumps(criteria)}
        
        Respond with JSON: {{"passed": [criteria_numbers], "failed": [criteria_numbers]}}
        """

        try:
            validation_result = await self.provider.generate_json(validation_prompt)

            all_passed = len(validation_result.get("failed", [])) == 0

            return {
                "all_passed": all_passed,
                "passed_criteria": validation_result.get("passed", []),
                "failed_criteria": validation_result.get("failed", [])
            }
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"all_passed": False, "failed_criteria": ["Validation error"]}

    def _build_dependency_graph(
        self,
        tickets: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Build dependency graph from tickets."""
        graph = {}

        for ticket in tickets:
            ticket_id = self._get_ticket_id(ticket)
            dependencies = ticket.get("dependencies", [])
            graph[ticket_id] = dependencies

        return graph

    def _topological_sort(
        self,
        graph: Dict[str, List[str]]
    ) -> List[List[str]]:
        """Perform topological sort to get execution layers."""
        # Calculate in-degree for each node
        in_degree = {node: 0 for node in graph}

        for deps in graph.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        layers = []

        while in_degree:
            # Find nodes with no dependencies
            current_layer = [
                node for node, degree in in_degree.items()
                if degree == 0
            ]

            if not current_layer:
                # Circular dependency detected
                logger.warning("Circular dependency detected")
                current_layer = list(in_degree.keys())

            layers.append(current_layer)

            # Remove processed nodes
            for node in current_layer:
                del in_degree[node]

                # Decrease in-degree for dependent nodes
                for other_node in graph:
                    if node in graph.get(other_node, []):
                        if other_node in in_degree:
                            in_degree[other_node] -= 1

        return layers

    def _get_ticket_id(self, ticket: Dict[str, Any]) -> str:
        """Get ticket identifier."""
        return ticket.get("ticket_number", ticket.get("id", str(id(ticket))))

    def _calculate_stats(
        self,
        results: List[TicketResult],
        total_time: float
    ) -> Dict[str, Any]:
        """Calculate execution statistics."""
        successful = sum(1 for r in results if r.status == TicketStatus.DONE)
        failed = sum(1 for r in results if r.status == TicketStatus.FAILED)

        return {
            "total_tickets": len(results),
            "successful": successful,
            "failed": failed,
            "success_rate": successful / len(results) if results else 0,
            "total_time": total_time,
            "avg_time_per_ticket": total_time / len(results) if results else 0,
            "total_tokens": sum(r.tokens_used for r in results),
            "parallelism_efficiency": len(results) / (
                total_time / min(r.execution_time for r in results if r.execution_time > 0)
            ) if results and any(r.execution_time > 0 for r in results) else 0
        }
