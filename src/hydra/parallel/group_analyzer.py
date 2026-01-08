"""Group analyzer for parallel execution optimization.

This module analyzes ticket dependencies to identify groups of tickets that can
be executed in parallel, respecting dependency and resource constraints.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from ..validation.dependency_validator import FileFlow


@dataclass
class ParallelGroup:
    """Represents a group of tickets that can potentially run in parallel."""

    phase: int
    tickets: List[str]
    can_parallel: bool
    estimated_duration: float = 0.0
    dependencies_resolved: Set[str] = field(default_factory=set)
    file_conflicts: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class DependencyAnalysis:
    """Results of dependency graph analysis."""

    groups: List[ParallelGroup]
    dependency_levels: Dict[str, int]
    parallel_opportunities: List[List[str]]
    total_levels: int
    max_parallelism: int


class GroupAnalyzer:
    """Analyzes dependencies to create optimal execution groups."""

    def __init__(self):
        """Initialize the group analyzer."""
        self.dependency_graph: Dict[str, List[str]] = {}
        self.reverse_graph: Dict[str, List[str]] = {}
        self.file_flows: List[FileFlow] = []
        self.topological_order: List[str] = []

    def analyze_dependencies(
        self,
        dependency_graph: Dict[str, List[str]],
        file_flows: List[FileFlow],
        topological_order: List[str],
    ) -> DependencyAnalysis:
        """Analyze dependencies to identify parallel execution groups.

        Args:
            dependency_graph: Ticket dependency graph
            file_flows: File flow dependencies
            topological_order: Topological sort of tickets

        Returns:
            DependencyAnalysis with grouped tickets

        """
        self.dependency_graph = dependency_graph
        self.file_flows = file_flows
        self.topological_order = topological_order

        # Build reverse dependency graph
        self._build_reverse_graph()

        # Calculate dependency levels
        dependency_levels = self._calculate_dependency_levels()

        # Create initial groups based on levels
        level_groups = self._create_level_groups(dependency_levels)

        # Refine groups considering file conflicts
        refined_groups = self._refine_groups_for_conflicts(level_groups)

        # Identify parallel opportunities
        parallel_opportunities = self._identify_parallel_opportunities(refined_groups)

        # Calculate metrics
        parallel_groups_with_tickets = [
            g for g in refined_groups if g.can_parallel and g.tickets
        ]
        max_parallelism = (
            max(len(g.tickets) for g in parallel_groups_with_tickets)
            if parallel_groups_with_tickets
            else 0
        )

        return DependencyAnalysis(
            groups=refined_groups,
            dependency_levels=dependency_levels,
            parallel_opportunities=parallel_opportunities,
            total_levels=len(level_groups),
            max_parallelism=max_parallelism,
        )

    def _build_reverse_graph(self) -> None:
        """Build reverse dependency graph (successors for each ticket)."""
        self.reverse_graph = defaultdict(list)

        for ticket, dependencies in self.dependency_graph.items():
            for dep in dependencies:
                self.reverse_graph[dep].append(ticket)

    def _calculate_dependency_levels(self) -> Dict[str, int]:
        """Calculate dependency levels for each ticket.

        Returns:
            Dictionary mapping ticket IDs to their dependency level

        """
        levels: Dict[str, int] = {}
        visited: Set[str] = set()

        def calculate_level(ticket: str) -> int:
            if ticket in levels:
                return levels[ticket]

            if ticket in visited and ticket not in levels:
                # Circular dependency, assign level 0
                levels[ticket] = 0
                return 0

            visited.add(ticket)

            # Calculate maximum level of dependencies
            max_dep_level = -1
            for dep in self.dependency_graph.get(ticket, []):
                if dep in self.dependency_graph:  # Valid dependency
                    dep_level = calculate_level(dep)
                    max_dep_level = max(max_dep_level, dep_level)

            levels[ticket] = max_dep_level + 1
            return levels[ticket]

        # Calculate levels for all tickets
        for ticket in self.topological_order:
            calculate_level(ticket)

        return levels

    def _create_level_groups(
        self, dependency_levels: Dict[str, int]
    ) -> Dict[int, List[str]]:
        """Group tickets by their dependency level.

        Args:
            dependency_levels: Ticket dependency levels

        Returns:
            Dictionary mapping levels to lists of tickets

        """
        level_groups: Dict[int, List[str]] = defaultdict(list)

        for ticket, level in dependency_levels.items():
            level_groups[level].append(ticket)

        return dict(level_groups)

    def _refine_groups_for_conflicts(
        self, level_groups: Dict[int, List[str]]
    ) -> List[ParallelGroup]:
        """Refine groups to handle file conflicts and other constraints.

        Args:
            level_groups: Initial grouping by dependency level

        Returns:
            List of refined ParallelGroup objects

        """
        refined_groups: List[ParallelGroup] = []
        phase_counter = 1

        for level in sorted(level_groups.keys()):
            tickets = level_groups[level]

            if len(tickets) == 1:
                # Single ticket, no parallelization needed
                group = ParallelGroup(
                    phase=phase_counter,
                    tickets=tickets,
                    can_parallel=False,
                    dependencies_resolved=self._get_resolved_dependencies(
                        tickets[0], level
                    ),
                )
                refined_groups.append(group)
                phase_counter += 1
            else:
                # Multiple tickets at same level, check for conflicts
                conflict_groups = self._split_by_conflicts(tickets)

                for conflict_group in conflict_groups:
                    can_parallel = not self._has_internal_conflicts(conflict_group)

                    group = ParallelGroup(
                        phase=phase_counter,
                        tickets=conflict_group,
                        can_parallel=can_parallel,
                        dependencies_resolved=self._get_resolved_dependencies_for_group(
                            conflict_group, level
                        ),
                    )

                    # Add file conflicts if any
                    if not can_parallel:
                        group.file_conflicts = self._find_file_conflicts(conflict_group)

                    refined_groups.append(group)
                    phase_counter += 1

        return refined_groups

    def _split_by_conflicts(self, tickets: List[str]) -> List[List[str]]:
        """Split tickets into groups without file conflicts.

        Args:
            tickets: List of tickets to split

        Returns:
            List of ticket groups without internal conflicts

        """
        # Build conflict graph
        conflicts: Dict[str, Set[str]] = defaultdict(set)

        for i, ticket1 in enumerate(tickets):
            for ticket2 in tickets[i + 1 :]:
                if self._have_file_conflict(ticket1, ticket2):
                    conflicts[ticket1].add(ticket2)
                    conflicts[ticket2].add(ticket1)

        # Use graph coloring to split into non-conflicting groups
        groups: List[List[str]] = []
        assigned: Dict[str, int] = {}

        for ticket in tickets:
            if ticket in assigned:
                continue

            # Find first available group
            for group_idx, group in enumerate(groups):
                # Check if ticket conflicts with any in this group
                has_conflict = any(other in conflicts[ticket] for other in group)
                if not has_conflict:
                    group.append(ticket)
                    assigned[ticket] = group_idx
                    break
            else:
                # Need new group
                groups.append([ticket])
                assigned[ticket] = len(groups) - 1

        return groups

    def _have_file_conflict(self, ticket1: str, ticket2: str) -> bool:
        """Check if two tickets have file write conflicts.

        Args:
            ticket1: First ticket ID
            ticket2: Second ticket ID

        Returns:
            True if tickets have conflicting file operations

        """
        # Check direct file flow dependencies
        for flow in self.file_flows:
            if (flow.source_ticket == ticket1 and flow.target_ticket == ticket2) or (
                flow.source_ticket == ticket2 and flow.target_ticket == ticket1
            ):
                return True

        # In a real implementation, would also check output file conflicts
        # This would require parsing ticket data for output files
        return False

    def _has_internal_conflicts(self, tickets: List[str]) -> bool:
        """Check if a group of tickets has internal conflicts.

        Args:
            tickets: List of ticket IDs

        Returns:
            True if there are conflicts within the group

        """
        for i, ticket1 in enumerate(tickets):
            for ticket2 in tickets[i + 1 :]:
                if self._have_file_conflict(ticket1, ticket2):
                    return True
        return False

    def _find_file_conflicts(self, tickets: List[str]) -> List[Tuple[str, str]]:
        """Find all file conflicts within a group.

        Args:
            tickets: List of ticket IDs

        Returns:
            List of (ticket1, ticket2) pairs with conflicts

        """
        conflicts = []
        for i, ticket1 in enumerate(tickets):
            for ticket2 in tickets[i + 1 :]:
                if self._have_file_conflict(ticket1, ticket2):
                    conflicts.append((ticket1, ticket2))
        return conflicts

    def _get_resolved_dependencies(self, ticket: str, level: int) -> Set[str]:
        """Get all resolved dependencies for a ticket.

        Args:
            ticket: Ticket ID
            level: Dependency level of the ticket

        Returns:
            Set of resolved dependency ticket IDs

        """
        resolved = set()
        for dep in self.dependency_graph.get(ticket, []):
            resolved.add(dep)
            # Recursively add transitive dependencies
            resolved.update(self._get_resolved_dependencies(dep, level - 1))
        return resolved

    def _get_resolved_dependencies_for_group(
        self, tickets: List[str], level: int
    ) -> Set[str]:
        """Get all resolved dependencies for a group.

        Args:
            tickets: List of ticket IDs
            level: Dependency level of the group

        Returns:
            Set of resolved dependency ticket IDs

        """
        resolved = set()
        for ticket in tickets:
            resolved.update(self._get_resolved_dependencies(ticket, level))
        return resolved

    def _identify_parallel_opportunities(
        self, groups: List[ParallelGroup]
    ) -> List[List[str]]:
        """Identify tickets that can be executed in parallel.

        Args:
            groups: Refined execution groups

        Returns:
            List of ticket sets that can run in parallel

        """
        opportunities = []

        for group in groups:
            if group.can_parallel and len(group.tickets) > 1:
                opportunities.append(group.tickets)

        return opportunities

    def find_dependency_chains(self) -> List[List[str]]:
        """Find all dependency chains in the graph.

        Returns:
            List of dependency chains (paths through the graph)

        """
        chains = []
        visited_global = set()

        def find_chains_from(ticket: str, current_chain: List[str]) -> None:
            current_chain.append(ticket)

            successors = self.reverse_graph.get(ticket, [])
            if not successors:
                # End of chain
                if len(current_chain) > 1:
                    chains.append(current_chain.copy())
            else:
                for successor in successors:
                    if successor not in current_chain:  # Avoid cycles
                        find_chains_from(successor, current_chain.copy())

        # Start from tickets with no dependencies
        for ticket in self.topological_order:
            if not self.dependency_graph.get(ticket, []):
                if ticket not in visited_global:
                    find_chains_from(ticket, [])
                    visited_global.add(ticket)

        return chains

    def calculate_parallelism_metrics(
        self, analysis: DependencyAnalysis
    ) -> Dict[str, float]:
        """Calculate metrics about parallelization potential.

        Args:
            analysis: Dependency analysis results

        Returns:
            Dictionary of parallelism metrics

        """
        metrics = {
            "total_tickets": len(self.topological_order),
            "total_phases": analysis.total_levels,
            "max_parallelism": analysis.max_parallelism,
            "parallel_phases": 0,
            "sequential_phases": 0,
            "average_phase_size": 0.0,
            "parallelization_ratio": 0.0,
        }

        if not analysis.groups:
            return metrics

        parallel_phases = sum(1 for g in analysis.groups if g.can_parallel)
        sequential_phases = len(analysis.groups) - parallel_phases

        metrics["parallel_phases"] = parallel_phases
        metrics["sequential_phases"] = sequential_phases
        metrics["average_phase_size"] = sum(
            len(g.tickets) for g in analysis.groups
        ) / len(analysis.groups)

        # Calculate parallelization ratio
        total_parallel_tickets = sum(
            len(g.tickets) for g in analysis.groups if g.can_parallel
        )
        metrics["parallelization_ratio"] = (
            total_parallel_tickets / metrics["total_tickets"]
            if metrics["total_tickets"] > 0
            else 0.0
        )

        return metrics

    def visualize_groups(self, analysis: DependencyAnalysis) -> str:
        """Generate a text visualization of execution groups.

        Args:
            analysis: Dependency analysis results

        Returns:
            Text visualization of the execution plan

        """
        lines = [
            "Execution Group Visualization",
            "=" * 50,
        ]

        if not analysis.groups:
            lines.append("No groups to visualize")
            return "\n".join(lines)

        # Find maximum tickets in any phase for alignment (commented out for now)
        # Could be used for better visualization alignment in the future

        for group in analysis.groups:
            phase_type = "||" if group.can_parallel else "--"
            tickets_str = ", ".join(group.tickets)

            # Create visual representation
            if group.can_parallel and len(group.tickets) > 1:
                lines.append(f"Phase {group.phase} {phase_type} [{tickets_str}]")
                lines.append(f"         {' ' * len(phase_type)} (parallel execution)")
            else:
                lines.append(f"Phase {group.phase} {phase_type} {tickets_str}")
                if len(group.tickets) > 1:
                    lines.append(
                        f"         {' ' * len(phase_type)} "
                        "(sequential due to conflicts)"
                    )

            # Show dependencies resolved
            if group.dependencies_resolved:
                deps_str = ", ".join(sorted(group.dependencies_resolved)[:3])
                if len(group.dependencies_resolved) > 3:
                    deps_str += f" +{len(group.dependencies_resolved) - 3} more"
                lines.append(f"         {' ' * len(phase_type)} Deps: {deps_str}")

            lines.append("")  # Empty line between phases

        # Add summary
        lines.extend(
            [
                "Summary:",
                f"  Total phases: {analysis.total_levels}",
                f"  Maximum parallelism: {analysis.max_parallelism} tickets",
                f"  Parallel opportunities: {len(analysis.parallel_opportunities)}",
            ]
        )

        return "\n".join(lines)

    def recommend_dependency_changes(self, analysis: DependencyAnalysis) -> List[str]:
        """Recommend dependency changes to improve parallelization.

        Args:
            analysis: Dependency analysis results

        Returns:
            List of recommendations

        """
        recommendations = []

        # Check for long sequential chains
        chains = self.find_dependency_chains()
        long_chains = [c for c in chains if len(c) > 3]

        if long_chains:
            recommendations.append(
                f"Found {len(long_chains)} long dependency chains (>3 tickets):"
            )
            for chain in long_chains[:2]:  # Show first 2
                recommendations.append(f"  - {' → '.join(chain)}")
            recommendations.append(
                "  Consider breaking these chains to enable parallelization"
            )

        # Check for phases with single tickets that could be merged
        single_ticket_phases = [g for g in analysis.groups if len(g.tickets) == 1]
        if len(single_ticket_phases) > analysis.total_levels * 0.5:
            recommendations.append(
                f"High number of single-ticket phases ({len(single_ticket_phases)}):"
            )
            recommendations.append("  - Review dependencies to combine related work")
            recommendations.append("  - Consider batching small tickets together")

        # Check parallelization ratio
        metrics = self.calculate_parallelism_metrics(analysis)
        if metrics["parallelization_ratio"] < 0.3:
            recommendations.append(
                f"Low parallelization ratio ({metrics['parallelization_ratio']:.1%}):"
            )
            recommendations.append("  - Identify independent work streams")
            recommendations.append("  - Reduce unnecessary dependencies")
            recommendations.append("  - Split large tickets into parallel subtasks")

        if not recommendations:
            recommendations.append(
                "Dependency structure is well-optimized for parallel execution"
            )

        return recommendations
