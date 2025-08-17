"""Dependency validation system for ticket workflows."""

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ValidationStatus(Enum):
    """Status of dependency validation."""

    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


@dataclass
class ValidationIssue:
    """Represents a validation issue found during dependency checking."""

    ticket_id: str
    issue_type: str
    severity: ValidationStatus
    description: str
    suggested_fix: Optional[str] = None


@dataclass
class FileFlow:
    """Represents a file flow from one ticket to another."""

    source_ticket: str
    target_ticket: str
    file_path: str
    required: bool = True


@dataclass
class DependencyValidationResult:
    """Result of dependency validation."""

    valid: bool
    issues: List[ValidationIssue]
    file_flows: List[FileFlow]
    dependency_graph: Dict[str, List[str]]
    topological_order: List[str]


class DependencyValidator:
    """Validates ticket dependencies and file flows."""

    def __init__(self):
        self.tickets = {}
        self.dependency_graph = {}
        self.file_flows = []

    def validate_ticket_dependencies(
        self, tickets_path: str
    ) -> DependencyValidationResult:
        """Validate all ticket dependencies in the given file."""
        if not os.path.exists(tickets_path):
            return DependencyValidationResult(
                valid=False,
                issues=[
                    ValidationIssue(
                        ticket_id="N/A",
                        issue_type="file_not_found",
                        severity=ValidationStatus.INVALID,
                        description=f"Tickets file not found: {tickets_path}",
                    )
                ],
                file_flows=[],
                dependency_graph={},
                topological_order=[],
            )

        # Parse all tickets
        self._parse_tickets(tickets_path)

        # Validate dependencies
        issues = []
        issues.extend(self._check_circular_dependencies())
        issues.extend(self._validate_file_flows())
        issues.extend(self._check_missing_dependencies())
        issues.extend(self._validate_dependency_order())

        # Generate topological order
        try:
            topo_order = self._topological_sort()
        except ValueError as e:
            issues.append(
                ValidationIssue(
                    ticket_id="N/A",
                    issue_type="topological_sort_failed",
                    severity=ValidationStatus.INVALID,
                    description=str(e),
                )
            )
            topo_order = []

        return DependencyValidationResult(
            valid=not any(
                issue.severity == ValidationStatus.INVALID for issue in issues
            ),
            issues=issues,
            file_flows=self.file_flows,
            dependency_graph=self.dependency_graph,
            topological_order=topo_order,
        )

    def _parse_tickets(self, tickets_path: str) -> None:
        """Parse all tickets from the file and build dependency graph."""
        with open(tickets_path, "r") as f:
            content = f.read()

        # Find all ticket headers
        ticket_patterns = [
            r"## Ticket (\d+):(.*?)(?=## Ticket|\Z)",
            r"## TICKET-(\d+):(.*?)(?=## TICKET-|\Z)",
            r"## (\d+):(.*?)(?=## \d+:|\Z)",
        ]

        for pattern in ticket_patterns:
            matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                ticket_id = match.group(1).strip()
                ticket_content = match.group(2).strip()

                # Parse the ticket details
                ticket_data = self._parse_single_ticket(ticket_id, ticket_content)
                self.tickets[ticket_id] = ticket_data

                # Build dependency graph
                self.dependency_graph[ticket_id] = ticket_data.get("dependencies", [])

                # Extract file flows
                self._extract_file_flows(ticket_id, ticket_data)

    def _parse_single_ticket(self, ticket_id: str, content: str) -> Dict:
        """Parse a single ticket's content."""
        lines = content.split("\n")
        ticket_data = {
            "id": ticket_id,
            "title": lines[0].strip() if lines else "",
            "dependencies": [],
            "required_input_files": [],
            "output_files": [],
            "acceptance_criteria": [],
        }

        current_section = None

        for line in lines:
            line = line.strip()

            # Parse dependencies
            if line.startswith("**Dependencies:**"):
                deps_text = line.replace("**Dependencies:**", "").strip()
                if deps_text and deps_text.lower() != "none":
                    # Split by comma and clean
                    deps = [d.strip() for d in deps_text.split(",")]
                    ticket_data["dependencies"] = [d for d in deps if d]
                current_section = None

            # Parse required input files
            elif line.startswith("**Required Input Files:**"):
                current_section = "required_input_files"
            elif line.startswith("**Output Files:**"):
                current_section = "output_files"
            elif line.startswith("**Acceptance Criteria:**"):
                current_section = "acceptance_criteria"
            elif line.startswith("**"):
                current_section = None  # New section, reset

            # Parse list items based on current section
            elif line.startswith("- "):
                item = line[2:].strip()
                if not item or item.lower() == "none":
                    continue

                if current_section == "required_input_files":
                    ticket_data["required_input_files"].append(item)
                elif current_section == "output_files":
                    ticket_data["output_files"].append(item)
                elif current_section == "acceptance_criteria":
                    # Handle checkboxes
                    if (
                        item.startswith("[ ]")
                        or item.startswith("[x]")
                        or item.startswith("[X]")
                    ):
                        criteria = item[3:].strip()  # Remove checkbox part
                        if criteria:
                            ticket_data["acceptance_criteria"].append(criteria)
                    else:
                        ticket_data["acceptance_criteria"].append(item)

            # Handle standalone checkboxes
            elif (
                line.startswith("- [ ]")
                or line.startswith("- [x]")
                or line.startswith("- [X]")
            ):
                criteria = line[5:].strip()  # Remove "- [x] " part
                if criteria:
                    ticket_data["acceptance_criteria"].append(criteria)

        return ticket_data

    def _extract_file_flows(self, ticket_id: str, ticket_data: Dict) -> None:
        """Extract file flows from ticket data."""
        # Map required input files to their source tickets
        for input_file_ref in ticket_data.get("required_input_files", []):
            # Parse "(from Ticket XXX)" pattern
            source_match = re.search(r"\(from Ticket (\d+)\)", input_file_ref)
            if source_match:
                source_ticket = source_match.group(1)
                # Extract file path (everything before the parentheses)
                file_path = re.sub(
                    r"\s*\(from Ticket \d+\)", "", input_file_ref
                ).strip()

                self.file_flows.append(
                    FileFlow(
                        source_ticket=source_ticket,
                        target_ticket=ticket_id,
                        file_path=file_path,
                        required=True,
                    )
                )

    def _check_circular_dependencies(self) -> List[ValidationIssue]:
        """Check for circular dependencies using DFS."""
        issues = []
        visited = set()
        rec_stack = set()

        def has_cycle(ticket_id: str, path: List[str]) -> Optional[List[str]]:
            if ticket_id in rec_stack:
                # Found cycle, return the cycle path
                cycle_start = path.index(ticket_id)
                return path[cycle_start:] + [ticket_id]

            if ticket_id in visited:
                return None

            visited.add(ticket_id)
            rec_stack.add(ticket_id)
            path.append(ticket_id)

            for dep in self.dependency_graph.get(ticket_id, []):
                if dep in self.dependency_graph:  # Only check if dependency exists
                    cycle = has_cycle(dep, path[:])
                    if cycle:
                        return cycle

            rec_stack.remove(ticket_id)
            path.pop()
            return None

        for ticket_id in self.dependency_graph:
            if ticket_id not in visited:
                cycle = has_cycle(ticket_id, [])
                if cycle:
                    cycle_str = " → ".join(cycle)
                    issues.append(
                        ValidationIssue(
                            ticket_id=ticket_id,
                            issue_type="circular_dependency",
                            severity=ValidationStatus.INVALID,
                            description=f"Circular dependency detected: {cycle_str}",
                            suggested_fix="Remove one of the dependencies to break the cycle",
                        )
                    )

        return issues

    def _validate_file_flows(self) -> List[ValidationIssue]:
        """Validate that output files from dependencies match required input files."""
        issues = []

        for flow in self.file_flows:
            source_ticket = self.tickets.get(flow.source_ticket)
            if not source_ticket:
                issues.append(
                    ValidationIssue(
                        ticket_id=flow.target_ticket,
                        issue_type="missing_dependency",
                        severity=ValidationStatus.INVALID,
                        description=f"Dependency ticket {flow.source_ticket} not found",
                        suggested_fix=f"Create ticket {flow.source_ticket} or remove dependency",
                    )
                )
                continue

            # Check if the source ticket outputs the required file
            output_files = source_ticket.get("output_files", [])
            file_found = any(
                flow.file_path in output_file or output_file in flow.file_path
                for output_file in output_files
            )

            if not file_found:
                issues.append(
                    ValidationIssue(
                        ticket_id=flow.target_ticket,
                        issue_type="file_flow_mismatch",
                        severity=ValidationStatus.WARNING,
                        description=(
                            f"Required file '{flow.file_path}' from ticket {flow.source_ticket} "
                            f"not found in output files: {output_files}"
                        ),
                        suggested_fix=(
                            f"Add '{flow.file_path}' to output files of ticket {flow.source_ticket} "
                            f"or update the required input file specification"
                        ),
                    )
                )

        return issues

    def _check_missing_dependencies(self) -> List[ValidationIssue]:
        """Check for missing dependency tickets."""
        issues = []

        for ticket_id, dependencies in self.dependency_graph.items():
            for dep in dependencies:
                if dep not in self.tickets:
                    issues.append(
                        ValidationIssue(
                            ticket_id=ticket_id,
                            issue_type="missing_dependency",
                            severity=ValidationStatus.INVALID,
                            description=f"Dependency ticket {dep} does not exist",
                            suggested_fix=f"Create ticket {dep} or remove from dependencies",
                        )
                    )

        return issues

    def _validate_dependency_order(self) -> List[ValidationIssue]:
        """Validate that dependencies follow logical order."""
        issues = []

        for ticket_id, dependencies in self.dependency_graph.items():
            # Check if ticket depends on later tickets (by ID)
            try:
                ticket_num = int(ticket_id)
                for dep in dependencies:
                    try:
                        dep_num = int(dep)
                        if dep_num > ticket_num:
                            issues.append(
                                ValidationIssue(
                                    ticket_id=ticket_id,
                                    issue_type="dependency_order",
                                    severity=ValidationStatus.WARNING,
                                    description=(
                                        f"Ticket {ticket_id} depends on later ticket {dep}. "
                                        f"This may indicate logical ordering issues."
                                    ),
                                    suggested_fix="Consider reordering tickets or reviewing dependencies",
                                )
                            )
                    except ValueError:
                        pass  # Non-numeric ticket IDs
            except ValueError:
                pass  # Non-numeric ticket IDs

        return issues

    def _topological_sort(self) -> List[str]:
        """Perform topological sort to find execution order."""
        # Kahn's algorithm for topological sorting
        in_degree = {ticket: 0 for ticket in self.dependency_graph}

        # Calculate in-degrees (count how many dependencies each ticket has)
        for ticket in self.dependency_graph:
            in_degree[ticket] = len(self.dependency_graph[ticket])

        # Find tickets with no dependencies (in-degree 0)
        queue = [ticket for ticket, degree in in_degree.items() if degree == 0]
        topo_order = []

        while queue:
            current = queue.pop(0)
            topo_order.append(current)

            # For each ticket that depends on current, decrement its in-degree
            for ticket in self.dependency_graph:
                if current in self.dependency_graph[ticket]:
                    in_degree[ticket] -= 1
                    if in_degree[ticket] == 0:
                        queue.append(ticket)

        # Check if all tickets are included (no cycles)
        if len(topo_order) != len(self.dependency_graph):
            remaining = set(self.dependency_graph.keys()) - set(topo_order)
            raise ValueError(
                f"Topological sort failed - circular dependencies involving: {remaining}"
            )

        return topo_order

    def get_parallel_execution_groups(
        self, result: DependencyValidationResult
    ) -> List[List[str]]:
        """Identify tickets that can be executed in parallel."""
        if not result.valid or not result.topological_order:
            return []

        groups = []

        # Build level-based grouping: tickets at the same dependency level
        # can run in parallel
        levels = {}
        for ticket in result.topological_order:
            # Calculate the maximum dependency depth
            max_depth = 0
            for dep in result.dependency_graph.get(ticket, []):
                if dep in levels:
                    max_depth = max(max_depth, levels[dep] + 1)
            levels[ticket] = max_depth

        # Group tickets by level
        level_groups = {}
        for ticket, level in levels.items():
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(ticket)

        # Convert to list of groups in execution order
        for level in sorted(level_groups.keys()):
            level_tickets = level_groups[level]

            # Further split within level if there are file flow conflicts
            while level_tickets:
                current_group = [level_tickets.pop(0)]
                i = 0
                while i < len(level_tickets):
                    ticket = level_tickets[i]
                    # Check if this ticket can run with any in current group
                    can_parallel = all(
                        not self._has_file_flow_conflict(
                            ticket, group_ticket, result.file_flows
                        )
                        for group_ticket in current_group
                    )
                    if can_parallel:
                        current_group.append(level_tickets.pop(i))
                    else:
                        i += 1

                groups.append(current_group)

        return groups

    def _has_file_flow_conflict(
        self, ticket1: str, ticket2: str, file_flows: List[FileFlow]
    ) -> bool:
        """Check if two tickets have conflicting file flows."""
        # Check if either ticket depends on the other through file flows
        for flow in file_flows:
            if (flow.source_ticket == ticket1 and flow.target_ticket == ticket2) or (
                flow.source_ticket == ticket2 and flow.target_ticket == ticket1
            ):
                return True
        return False

    def generate_dependency_report(self, result: DependencyValidationResult) -> str:
        """Generate a human-readable dependency validation report."""
        lines = [
            "🔍 Dependency Validation Report",
            "=" * 50,
            f"Overall Status: {'✅ VALID' if result.valid else '❌ INVALID'}",
            f"Total Issues: {len(result.issues)}",
            "",
        ]

        if result.issues:
            lines.append("📋 Issues Found:")
            for issue in result.issues:
                status_icon = {
                    ValidationStatus.VALID: "✅",
                    ValidationStatus.WARNING: "⚠️",
                    ValidationStatus.INVALID: "❌",
                }.get(issue.severity, "❓")

                lines.append(
                    f"  {status_icon} Ticket {issue.ticket_id}: {issue.description}"
                )
                if issue.suggested_fix:
                    lines.append(f"     💡 Fix: {issue.suggested_fix}")
            lines.append("")

        if result.topological_order:
            lines.extend(
                ["📊 Execution Order:", f"  {' → '.join(result.topological_order)}", ""]
            )

        if result.file_flows:
            lines.extend(
                [
                    "📁 File Flows:",
                ]
            )
            for flow in result.file_flows:
                lines.append(
                    f"  {flow.source_ticket} → {flow.target_ticket}: {flow.file_path}"
                )

        # Parallel execution groups
        groups = self.get_parallel_execution_groups(result)
        if groups:
            lines.extend(
                [
                    "",
                    "⚡ Parallel Execution Opportunities:",
                ]
            )
            for i, group in enumerate(groups, 1):
                if len(group) > 1:
                    lines.append(
                        f"  Group {i}: {', '.join(group)} (can run in parallel)"
                    )
                else:
                    lines.append(f"  Group {i}: {group[0]} (sequential)")

        return "\n".join(lines)
