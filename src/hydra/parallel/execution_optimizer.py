"""Parallel execution optimizer for ticket workflows.

This module analyzes ticket dependencies to identify optimal parallel execution
groups, minimizing total execution time while respecting dependency constraints.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..estimation.complexity_estimator import ComplexityEstimator
from ..preflight.preflight_checker import PreflightChecker
from ..validation.dependency_validator import (
    DependencyValidationResult,
    DependencyValidator,
)
from .group_analyzer import GroupAnalyzer, ParallelGroup


@dataclass
class ExecutionPlan:
    """Represents an optimized execution plan for tickets."""

    groups: List[ParallelGroup]
    total_phases: int
    parallel_speedup: float
    estimated_duration: float
    critical_path: List[str]
    optimization_report: str


@dataclass
class TicketExecutionMetrics:
    """Metrics for a single ticket's execution."""

    ticket_id: str
    estimated_duration: float
    complexity_score: float
    dependencies: List[str]
    earliest_start: float
    latest_start: float
    slack_time: float


class ExecutionOptimizer:
    """Optimizes ticket execution for parallel processing."""

    def __init__(self):
        """Initialize the execution optimizer."""
        self.dependency_validator = DependencyValidator()
        self.preflight_checker = PreflightChecker()
        self.group_analyzer = GroupAnalyzer()
        self.complexity_estimator = ComplexityEstimator()
        self.metrics: Dict[str, TicketExecutionMetrics] = {}

    def optimize_execution(
        self, tickets_path: str, max_parallel: int = 4
    ) -> ExecutionPlan:
        """Create an optimized execution plan for tickets.

        Args:
            tickets_path: Path to the tickets file
            max_parallel: Maximum number of tickets to execute in parallel

        Returns:
            ExecutionPlan with optimized groups and metrics

        """
        # Validate dependencies first
        validation_result = self.dependency_validator.validate_ticket_dependencies(
            tickets_path
        )

        if not validation_result.valid:
            return self._create_fallback_plan(validation_result)

        # Analyze dependencies and create groups
        analysis_result = self.group_analyzer.analyze_dependencies(
            validation_result.dependency_graph,
            validation_result.file_flows,
            validation_result.topological_order,
        )

        # Optimize groups based on complexity and constraints
        optimized_groups = self._optimize_groups(
            analysis_result.groups,
            self._get_ticket_complexities(tickets_path),
            max_parallel,
        )

        # Calculate metrics
        self._calculate_execution_metrics(
            optimized_groups, validation_result.dependency_graph
        )

        # Find critical path
        critical_path = self._find_critical_path(
            validation_result.dependency_graph, validation_result.topological_order
        )

        # Calculate speedup and duration
        speedup = self._calculate_speedup(optimized_groups)
        total_duration = self._estimate_total_duration(optimized_groups)

        # Generate optimization report
        report = self._generate_optimization_report(
            optimized_groups, critical_path, speedup
        )

        return ExecutionPlan(
            groups=optimized_groups,
            total_phases=len(optimized_groups),
            parallel_speedup=speedup,
            estimated_duration=total_duration,
            critical_path=critical_path,
            optimization_report=report,
        )

    def _create_fallback_plan(
        self, validation_result: DependencyValidationResult
    ) -> ExecutionPlan:
        """Create a fallback plan when validation fails."""
        error_msg = "Cannot optimize execution due to validation errors:\n"
        for issue in validation_result.issues:
            error_msg += f"  - {issue.description}\n"

        return ExecutionPlan(
            groups=[],
            total_phases=0,
            parallel_speedup=0.0,
            estimated_duration=0.0,
            critical_path=[],
            optimization_report=error_msg,
        )

    def _get_ticket_complexities(self, tickets_path: str) -> Dict[str, float]:
        """Get complexity scores for all tickets.

        Args:
            tickets_path: Path to tickets file

        Returns:
            Dictionary mapping ticket IDs to complexity scores

        """
        tickets = self.preflight_checker._parse_tickets(tickets_path)
        complexities = {}

        for ticket_id, ticket_data in tickets.items():
            estimation = self.complexity_estimator.estimate_ticket(ticket_data)
            complexities[ticket_id] = estimation.total_complexity_score

        return complexities

    def _optimize_groups(
        self,
        initial_groups: List[ParallelGroup],
        complexities: Dict[str, float],
        max_parallel: int,
    ) -> List[ParallelGroup]:
        """Optimize groups for balanced execution.

        Args:
            initial_groups: Initial grouping from dependency analysis
            complexities: Ticket complexity scores
            max_parallel: Maximum parallel execution limit

        Returns:
            Optimized list of ParallelGroup objects

        """
        optimized_groups = []

        for group in initial_groups:
            if group.can_parallel and len(group.tickets) > max_parallel:
                # Split large parallel groups
                subgroups = self._split_group_by_complexity(
                    group.tickets, complexities, max_parallel
                )
                for subgroup in subgroups:
                    optimized_groups.append(
                        ParallelGroup(
                            phase=len(optimized_groups) + 1,
                            tickets=subgroup,
                            can_parallel=True,
                            estimated_duration=self._estimate_group_duration(
                                subgroup, complexities
                            ),
                            dependencies_resolved=group.dependencies_resolved.copy(),
                        )
                    )
            else:
                # Keep group as is but update phase and duration
                group.phase = len(optimized_groups) + 1
                group.estimated_duration = self._estimate_group_duration(
                    group.tickets, complexities
                )
                optimized_groups.append(group)

        return optimized_groups

    def _split_group_by_complexity(
        self, tickets: List[str], complexities: Dict[str, float], max_size: int
    ) -> List[List[str]]:
        """Split a large group into balanced subgroups.

        Args:
            tickets: List of ticket IDs
            complexities: Ticket complexity scores
            max_size: Maximum subgroup size

        Returns:
            List of subgroups

        """
        # Sort tickets by complexity (highest first)
        sorted_tickets = sorted(
            tickets, key=lambda t: complexities.get(t, 0), reverse=True
        )

        # Use bin packing algorithm
        subgroups: List[List[str]] = []
        subgroup_loads: List[float] = []

        for ticket in sorted_tickets:
            complexity = complexities.get(ticket, 1.0)

            # Find subgroup with lowest load that has space
            best_idx = -1
            min_load = float("inf")

            for i, load in enumerate(subgroup_loads):
                if len(subgroups[i]) < max_size and load < min_load:
                    best_idx = i
                    min_load = load

            if best_idx == -1:
                # Create new subgroup
                subgroups.append([ticket])
                subgroup_loads.append(complexity)
            else:
                # Add to existing subgroup
                subgroups[best_idx].append(ticket)
                subgroup_loads[best_idx] += complexity

        return subgroups

    def _estimate_group_duration(
        self, tickets: List[str], complexities: Dict[str, float]
    ) -> float:
        """Estimate execution duration for a group.

        Args:
            tickets: List of ticket IDs in the group
            complexities: Ticket complexity scores

        Returns:
            Estimated duration in hours

        """
        if not tickets:
            return 0.0

        # For parallel groups, duration is the max complexity
        # For sequential groups, duration is the sum
        max_complexity = max(complexities.get(t, 1.0) for t in tickets)

        # Convert complexity to hours (rough heuristic)
        # Complexity 1-3: 0.5h, 4-6: 1h, 7-9: 2h, 10+: 4h
        if max_complexity <= 3:
            return 0.5
        elif max_complexity <= 6:
            return 1.0
        elif max_complexity <= 9:
            return 2.0
        else:
            return 4.0

    def _calculate_execution_metrics(
        self, groups: List[ParallelGroup], dependency_graph: Dict[str, List[str]]
    ) -> None:
        """Calculate execution metrics for all tickets.

        Args:
            groups: Optimized execution groups
            dependency_graph: Ticket dependency graph

        """
        # Build ticket to phase mapping
        ticket_phase: Dict[str, int] = {}
        for group in groups:
            for ticket in group.tickets:
                ticket_phase[ticket] = group.phase

        # Calculate metrics for each ticket
        for group in groups:
            for ticket in group.tickets:
                dependencies = dependency_graph.get(ticket, [])

                # Calculate earliest start (after all dependencies complete)
                earliest_start = 0.0
                for dep in dependencies:
                    if dep in ticket_phase:
                        dep_phase = ticket_phase[dep]
                        dep_duration = next(
                            g.estimated_duration
                            for g in groups
                            if g.phase == dep_phase
                        )
                        earliest_start = max(earliest_start, dep_duration * dep_phase)

                # Calculate latest start (without delaying successors)
                # This is simplified - a full CPM implementation would be more complex
                latest_start = earliest_start + group.estimated_duration

                self.metrics[ticket] = TicketExecutionMetrics(
                    ticket_id=ticket,
                    estimated_duration=group.estimated_duration,
                    complexity_score=0.0,  # Will be filled if needed
                    dependencies=dependencies,
                    earliest_start=earliest_start,
                    latest_start=latest_start,
                    slack_time=latest_start - earliest_start,
                )

    def _find_critical_path(
        self, dependency_graph: Dict[str, List[str]], topological_order: List[str]
    ) -> List[str]:
        """Find the critical path through the dependency graph.

        Args:
            dependency_graph: Ticket dependencies
            topological_order: Topological sort of tickets

        Returns:
            List of ticket IDs forming the critical path

        """
        if not topological_order:
            return []

        # Build reverse dependency graph (who depends on this ticket)
        reverse_deps: Dict[str, List[str]] = {t: [] for t in topological_order}
        for ticket, deps in dependency_graph.items():
            for dep in deps:
                if dep in reverse_deps:
                    reverse_deps[dep].append(ticket)

        # Find longest path using dynamic programming
        distances: Dict[str, float] = {t: 0.0 for t in topological_order}
        predecessors: Dict[str, Optional[str]] = {t: None for t in topological_order}

        for ticket in topological_order:
            # Get this ticket's duration from metrics
            duration = (
                self.metrics[ticket].estimated_duration
                if ticket in self.metrics
                else 1.0
            )

            # Update distances to all successors
            for successor in reverse_deps[ticket]:
                new_distance = distances[ticket] + duration
                if new_distance > distances[successor]:
                    distances[successor] = new_distance
                    predecessors[successor] = ticket

        # Find the ticket with maximum distance
        end_ticket = max(distances.keys(), key=lambda k: distances[k])

        # Reconstruct path
        path = []
        current = end_ticket
        while current is not None:
            path.append(current)
            current = predecessors[current]

        return list(reversed(path))

    def _calculate_speedup(self, groups: List[ParallelGroup]) -> float:
        """Calculate the speedup from parallel execution.

        Args:
            groups: Optimized execution groups

        Returns:
            Speedup factor (sequential_time / parallel_time)

        """
        if not groups:
            return 1.0

        # Calculate sequential time (sum of all ticket durations)
        sequential_time = sum(
            len(g.tickets) * g.estimated_duration for g in groups
        )

        # Calculate parallel time (sum of group durations)
        parallel_time = sum(g.estimated_duration for g in groups)

        if parallel_time == 0:
            return 1.0

        return sequential_time / parallel_time

    def _estimate_total_duration(self, groups: List[ParallelGroup]) -> float:
        """Estimate total execution duration.

        Args:
            groups: Optimized execution groups

        Returns:
            Total estimated duration in hours

        """
        return sum(g.estimated_duration for g in groups)

    def _generate_optimization_report(
        self,
        groups: List[ParallelGroup],
        critical_path: List[str],
        speedup: float,
    ) -> str:
        """Generate a detailed optimization report.

        Args:
            groups: Optimized execution groups
            critical_path: Critical path tickets
            speedup: Calculated speedup factor

        Returns:
            Human-readable optimization report

        """
        lines = [
            "Execution Optimization Report",
            "=" * 50,
            f"Total Phases: {len(groups)}",
            f"Parallel Speedup: {speedup:.2f}x",
            f"Critical Path Length: {len(critical_path)} tickets",
            "",
        ]

        # Phase details
        lines.append("Execution Phases:")
        for group in groups:
            phase_type = "parallel" if group.can_parallel else "sequential"
            tickets_str = ", ".join(group.tickets)
            lines.append(
                f"  Phase {group.phase} ({phase_type}, "
                f"{group.estimated_duration:.1f}h): {tickets_str}"
            )

        # Critical path
        if critical_path:
            lines.extend(
                [
                    "",
                    "Critical Path:",
                    f"  {' → '.join(critical_path)}",
                ]
            )

        # Parallelization opportunities
        parallel_groups = [g for g in groups if g.can_parallel and len(g.tickets) > 1]
        if parallel_groups:
            total_parallel_tickets = sum(len(g.tickets) for g in parallel_groups)
            lines.extend(
                [
                    "",
                    "Parallelization Summary:",
                    f"  Parallel phases: {len(parallel_groups)}",
                    f"  Total parallel tickets: {total_parallel_tickets}",
                ]
            )

        # Optimization recommendations
        lines.extend(
            [
                "",
                "Optimization Recommendations:",
            ]
        )

        # Check for bottlenecks
        bottleneck_groups = [
            g for g in groups if not g.can_parallel and len(g.tickets) > 2
        ]
        if bottleneck_groups:
            lines.append(
                f"  - {len(bottleneck_groups)} sequential bottlenecks detected"
            )
            lines.append(
                "    Consider breaking dependencies to enable parallelization"
            )

        # Check for imbalanced groups
        if parallel_groups:
            max_group_size = max(len(g.tickets) for g in parallel_groups)
            min_group_size = min(len(g.tickets) for g in parallel_groups)
            if max_group_size > min_group_size * 2:
                lines.append("  - Imbalanced parallel groups detected")
                lines.append("    Consider redistributing tickets for better balance")

        if not bottleneck_groups and parallel_groups:
            lines.append("  - Execution is well-optimized for parallelization")

        return "\n".join(lines)

    def identify_bottlenecks(
        self, execution_plan: ExecutionPlan
    ) -> List[Tuple[str, str]]:
        """Identify execution bottlenecks.

        Args:
            execution_plan: The execution plan to analyze

        Returns:
            List of (ticket_id, bottleneck_reason) tuples

        """
        bottlenecks = []

        # Check for tickets on critical path with high slack
        for ticket_id in execution_plan.critical_path:
            if ticket_id in self.metrics:
                metric = self.metrics[ticket_id]
                if metric.slack_time == 0:
                    bottlenecks.append(
                        (ticket_id, "Critical path ticket - no slack")
                    )

        # Check for sequential phases with multiple tickets
        for group in execution_plan.groups:
            if not group.can_parallel and len(group.tickets) > 2:
                for ticket in group.tickets:
                    bottlenecks.append(
                        (ticket, f"Sequential phase - {len(group.tickets)} tickets")
                    )

        return bottlenecks

    def suggest_optimizations(
        self, execution_plan: ExecutionPlan
    ) -> List[str]:
        """Suggest potential optimizations for the execution plan.

        Args:
            execution_plan: The execution plan to optimize

        Returns:
            List of optimization suggestions

        """
        suggestions = []

        # Check speedup
        if execution_plan.parallel_speedup < 1.5:
            suggestions.append(
                "Low parallel speedup detected. Consider:"
                "\n  - Breaking large tickets into smaller subtasks"
                "\n  - Reviewing and potentially removing unnecessary dependencies"
                "\n  - Identifying independent work that can be parallelized"
            )

        # Check phase count
        if execution_plan.total_phases > 10:
            suggestions.append(
                f"High number of phases ({execution_plan.total_phases}). Consider:"
                "\n  - Combining related tickets"
                "\n  - Reducing dependency depth"
                "\n  - Batching similar operations"
            )

        # Check critical path
        if len(execution_plan.critical_path) > execution_plan.total_phases * 0.7:
            suggestions.append(
                "Long critical path detected. Consider:"
                "\n  - Identifying tickets that can be started earlier"
                "\n  - Breaking critical path tickets into parallel subtasks"
                "\n  - Prioritizing critical path work"
            )

        # Check for bottlenecks
        bottlenecks = self.identify_bottlenecks(execution_plan)
        if len(bottlenecks) > 3:
            suggestions.append(
                f"Multiple bottlenecks found ({len(bottlenecks)} tickets). Consider:"
                "\n  - Reviewing bottleneck tickets for parallelization opportunities"
                "\n  - Allocating more resources to bottleneck tickets"
                "\n  - Restructuring dependencies around bottlenecks"
            )

        if not suggestions:
            suggestions.append(
                "Execution plan is well-optimized. No major improvements suggested."
            )

        return suggestions

