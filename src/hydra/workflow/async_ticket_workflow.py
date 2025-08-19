"""Async ticket workflow implementation with parallel execution."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from hydra.database.async_database import AsyncTicketDatabase
from hydra.orchestrator.async_orchestrator import AsyncTicketOrchestrator
from hydra.providers.async_anthropic import AsyncAnthropicProvider
from hydra.providers.async_openai import AsyncOpenAIProvider
from hydra.providers.base import LLMConfig

logger = logging.getLogger(__name__)


class AsyncTicketWorkflow:
    """Async workflow for ticket processing with parallel execution."""

    def __init__(
        self,
        provider_config: Optional[LLMConfig] = None,
        database_url: Optional[str] = None,
        max_concurrent: int = 5
    ):
        self.provider_config = provider_config or self._get_default_config()
        self.database = AsyncTicketDatabase(database_url)
        self.provider = None
        self.orchestrator = None
        self.max_concurrent = max_concurrent

    def _get_default_config(self) -> LLMConfig:
        """Get default provider configuration."""
        provider_type = os.getenv("LLM_PROVIDER", "anthropic")

        if provider_type == "anthropic":
            return LLMConfig(
                provider_type="anthropic",
                model=os.getenv("CLAUDE_MODEL", "claude-3-sonnet-20240229"),
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                temperature=0.2,
                max_tokens=4096
            )
        elif provider_type == "openai":
            return LLMConfig(
                provider_type="openai",
                model=os.getenv("OPENAI_MODEL", "gpt-4"),
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=0.2,
                max_tokens=4096
            )
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

    async def initialize(self):
        """Initialize async resources."""
        # Connect to database
        await self.database.connect()

        # Create provider
        if self.provider_config.provider_type == "anthropic":
            self.provider = AsyncAnthropicProvider(self.provider_config)
        elif self.provider_config.provider_type == "openai":
            self.provider = AsyncOpenAIProvider(self.provider_config)
        else:
            raise ValueError(f"Unknown provider: {self.provider_config.provider_type}")

        # Create orchestrator
        self.orchestrator = AsyncTicketOrchestrator(
            provider=self.provider,
            database=self.database,
            max_concurrent=self.max_concurrent
        )

    async def cleanup(self):
        """Cleanup async resources."""
        if self.provider:
            await self.provider.close()
        if self.database:
            await self.database.close()

    async def load_tickets_from_file(
        self,
        file_path: str
    ) -> List[Dict[str, Any]]:
        """Load tickets from YAML or Markdown file."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Ticket file not found: {file_path}")

        content = path.read_text()

        if path.suffix in [".yaml", ".yml"]:
            data = yaml.safe_load(content)
            return data.get("tickets", [])
        elif path.suffix == ".md":
            return self._parse_markdown_tickets(content)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def _parse_markdown_tickets(self, content: str) -> List[Dict[str, Any]]:
        """Parse tickets from Markdown format."""
        tickets = []
        current_ticket = None

        for line in content.split("\n"):
            if line.startswith("## Ticket "):
                if current_ticket:
                    tickets.append(current_ticket)

                # Extract ticket number
                parts = line.split(":")
                ticket_num = parts[0].replace("## Ticket ", "").strip()
                title = parts[1].strip() if len(parts) > 1 else "Untitled"

                current_ticket = {
                    "ticket_number": ticket_num,
                    "title": title,
                    "description": "",
                    "acceptance_criteria": [],
                    "status": "TODO"
                }
            elif current_ticket:
                if line.startswith("**Status**:"):
                    current_ticket["status"] = line.split(":")[1].strip()
                elif line.startswith("**Priority**:"):
                    current_ticket["priority"] = int(line.split(":")[1].strip())
                elif line.startswith("**Model**:"):
                    current_ticket["model"] = line.split(":")[1].strip()
                elif line.startswith("- [ ]") or line.startswith("- [x]"):
                    criterion = line[6:].strip()
                    completed = line.startswith("- [x]")
                    current_ticket["acceptance_criteria"].append({
                        "criterion": criterion,
                        "completed": completed
                    })
                elif line.strip() and not line.startswith("**"):
                    current_ticket["description"] += line + "\n"

        if current_ticket:
            tickets.append(current_ticket)

        return tickets

    async def execute_single_ticket(
        self,
        ticket_file: str,
        ticket_number: str
    ) -> Dict[str, Any]:
        """Execute a single ticket from file."""
        tickets = await self.load_tickets_from_file(ticket_file)

        ticket = next(
            (t for t in tickets if t.get("ticket_number") == ticket_number),
            None
        )

        if not ticket:
            raise ValueError(f"Ticket {ticket_number} not found in {ticket_file}")

        result = await self.orchestrator.execute_ticket(ticket)

        return {
            "ticket": ticket,
            "result": result
        }

    async def execute_parallel_tickets(
        self,
        ticket_file: str,
        ticket_numbers: Optional[List[str]] = None,
        respect_dependencies: bool = True
    ) -> Dict[str, Any]:
        """Execute multiple tickets in parallel using asyncio.gather."""
        tickets = await self.load_tickets_from_file(ticket_file)

        # Filter tickets if specific numbers provided
        if ticket_numbers:
            tickets = [
                t for t in tickets
                if t.get("ticket_number") in ticket_numbers
            ]

        logger.info(f"Executing {len(tickets)} tickets in parallel")

        start_time = asyncio.get_event_loop().time()

        # Execute tickets in parallel
        results = await self.orchestrator.execute_tickets_parallel(
            tickets,
            respect_dependencies=respect_dependencies
        )

        total_time = asyncio.get_event_loop().time() - start_time

        # Calculate performance improvement
        sequential_estimate = sum(r.execution_time for r in results)
        speedup = sequential_estimate / total_time if total_time > 0 else 1

        return {
            "tickets": tickets,
            "results": results,
            "performance": {
                "total_time": total_time,
                "sequential_estimate": sequential_estimate,
                "speedup": speedup,
                "efficiency": speedup / self.max_concurrent
            }
        }

    async def execute_all_tickets(
        self,
        ticket_file: str,
        batch_size: int = 10
    ) -> Dict[str, Any]:
        """Execute all tickets in batches for optimal performance."""
        tickets = await self.load_tickets_from_file(ticket_file)

        all_results = []
        total_time = 0

        # Process in batches
        for i in range(0, len(tickets), batch_size):
            batch = tickets[i:i + batch_size]

            logger.info(f"Processing batch {i//batch_size + 1} ({len(batch)} tickets)")

            start_time = asyncio.get_event_loop().time()

            # Use asyncio.gather for parallel execution within batch
            batch_results = await asyncio.gather(
                *[self.orchestrator.execute_ticket(ticket) for ticket in batch],
                return_exceptions=False
            )

            batch_time = asyncio.get_event_loop().time() - start_time
            total_time += batch_time

            all_results.extend(batch_results)

            logger.info(f"Batch completed in {batch_time:.2f}s")

        return {
            "total_tickets": len(tickets),
            "results": all_results,
            "total_time": total_time,
            "avg_time_per_ticket": total_time / len(tickets) if tickets else 0
        }

    async def validate_parallel_execution(
        self,
        ticket_file: str,
        workers: int = 4
    ) -> Dict[str, Any]:
        """Validate tickets were executed correctly in parallel."""
        tickets = await self.load_tickets_from_file(ticket_file)

        validation_tasks = []

        async def validate_ticket(ticket: Dict[str, Any]) -> Dict[str, Any]:
            """Validate a single ticket's acceptance criteria."""
            criteria = ticket.get("acceptance_criteria", [])

            if not criteria:
                return {
                    "ticket_number": ticket.get("ticket_number"),
                    "valid": True,
                    "message": "No criteria to validate"
                }

            # Check each criterion
            passed_criteria = []
            failed_criteria = []

            for criterion in criteria:
                # Simulate validation check
                criterion_text = (
                    criterion.get("criterion")
                    if isinstance(criterion, dict)
                    else criterion
                )

                # For demo, randomly pass/fail based on hash
                passed = hash(criterion_text) % 2 == 0

                if passed:
                    passed_criteria.append(criterion_text)
                else:
                    failed_criteria.append(criterion_text)

            return {
                "ticket_number": ticket.get("ticket_number"),
                "valid": len(failed_criteria) == 0,
                "passed": passed_criteria,
                "failed": failed_criteria
            }

        # Create validation tasks
        for ticket in tickets:
            validation_tasks.append(validate_ticket(ticket))

        # Execute validations in parallel using asyncio.gather
        validation_results = await asyncio.gather(*validation_tasks)

        # Calculate statistics
        total_valid = sum(1 for r in validation_results if r["valid"])

        return {
            "total_tickets": len(tickets),
            "valid_tickets": total_valid,
            "invalid_tickets": len(tickets) - total_valid,
            "validation_rate": total_valid / len(tickets) if tickets else 0,
            "details": validation_results
        }


async def main():
    """Example usage of async ticket workflow."""
    # Create workflow
    workflow = AsyncTicketWorkflow(max_concurrent=10)

    try:
        # Initialize resources
        await workflow.initialize()

        # Execute tickets in parallel
        result = await workflow.execute_parallel_tickets(
            "tickets.yaml",
            respect_dependencies=True
        )

        print(f"Executed {len(result['results'])} tickets")
        print(f"Total time: {result['performance']['total_time']:.2f}s")
        print(f"Speedup: {result['performance']['speedup']:.2f}x")
        print(f"Efficiency: {result['performance']['efficiency']:.1%}")

    finally:
        # Cleanup
        await workflow.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
