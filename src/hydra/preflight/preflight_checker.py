"""Pre-flight validation checker for ticket execution.

This module performs comprehensive pre-execution validation to catch issues
before ticket execution starts, preventing wasted resources and failed runs.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from ..estimation.complexity_estimator import ComplexityEstimator
from ..validation.dependency_validator import (
    DependencyValidator,
    ValidationStatus,
)
from .validation_report import (
    ValidationCheck,
    ValidationLevel,
    ValidationReport,
)


class PreflightChecker:
    """Comprehensive pre-execution validation system."""

    # Required model configurations
    AVAILABLE_MODELS = {
        "smart": ["opus-4", "claude-3-opus"],
        "coder": ["opus-4", "claude-3-opus"],
        "balanced": ["sonnet-4", "claude-3-sonnet"],
    }

    def __init__(self, project_root: Optional[str] = None):
        """Initialize the preflight checker.

        Args:
            project_root: Root directory of the project, defaults to current directory

        """
        self.project_root = Path(project_root or os.getcwd())
        self.dependency_validator = DependencyValidator()
        self.complexity_estimator = ComplexityEstimator()
        self.validation_report = ValidationReport()

    def run_preflight_checks(
        self, tickets_path: str, skip_checks: Optional[List[str]] = None
    ) -> ValidationReport:
        """Run all preflight validation checks.

        Args:
            tickets_path: Path to the tickets file
            skip_checks: List of check names to skip

        Returns:
            ValidationReport with all validation results

        """
        skip_checks = skip_checks or []

        # Check 1: Validate ticket file exists
        if "file_exists" not in skip_checks:
            self._check_ticket_file_exists(tickets_path)

        # Check 2: Validate dependencies
        if "dependencies" not in skip_checks:
            self._check_dependencies(tickets_path)

        # Check 3: Check input files exist
        if "input_files" not in skip_checks:
            self._check_input_files(tickets_path)

        # Check 4: Verify required models
        if "models" not in skip_checks:
            self._check_model_configuration(tickets_path)

        # Check 5: Check for file write conflicts
        if "conflicts" not in skip_checks:
            self._check_file_conflicts(tickets_path)

        # Check 6: Validate execution order
        if "execution_order" not in skip_checks:
            self._check_execution_order(tickets_path)

        # Check 7: Check resource availability
        if "resources" not in skip_checks:
            self._check_resource_availability(tickets_path)

        # Check 8: Validate ticket structure
        if "structure" not in skip_checks:
            self._check_ticket_structure(tickets_path)

        # Generate final report
        self.validation_report.finalize()
        return self.validation_report

    def _check_ticket_file_exists(self, tickets_path: str) -> None:
        """Check if the tickets file exists and is readable.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="ticket_file_exists",
            description="Verify tickets file exists and is readable",
            level=ValidationLevel.CRITICAL,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = f"Tickets file not found: {tickets_path}"
            check.details.append(f"Searched path: {os.path.abspath(tickets_path)}")
            self.validation_report.add_check(check)
            return

        if not os.path.isfile(tickets_path):
            check.passed = False
            check.message = f"Path is not a file: {tickets_path}"
            self.validation_report.add_check(check)
            return

        if not os.access(tickets_path, os.R_OK):
            check.passed = False
            check.message = f"Cannot read tickets file: {tickets_path}"
            check.details.append("Check file permissions")
            self.validation_report.add_check(check)
            return

        check.passed = True
        check.message = "Tickets file exists and is readable"
        self.validation_report.add_check(check)

    def _check_dependencies(self, tickets_path: str) -> None:
        """Validate all ticket dependencies.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="dependency_validation",
            description="Validate ticket dependencies and file flows",
            level=ValidationLevel.CRITICAL,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = "Cannot validate dependencies - tickets file not found"
            self.validation_report.add_check(check)
            return

        result = self.dependency_validator.validate_ticket_dependencies(tickets_path)

        if not result.valid:
            check.passed = False
            check.message = "Dependency validation failed"

            for issue in result.issues:
                if issue.severity == ValidationStatus.INVALID:
                    check.details.append(
                        f"[CRITICAL] Ticket {issue.ticket_id}: {issue.description}"
                    )
                    if issue.suggested_fix:
                        check.details.append(f"  Fix: {issue.suggested_fix}")
                elif issue.severity == ValidationStatus.WARNING:
                    check.details.append(
                        f"[WARNING] Ticket {issue.ticket_id}: {issue.description}"
                    )

            # Check for circular dependencies specifically
            circular_issues = [
                issue
                for issue in result.issues
                if issue.issue_type == "circular_dependency"
            ]
            if circular_issues:
                check.level = ValidationLevel.CRITICAL
                check.message = "Circular dependencies detected - execution impossible"

        else:
            check.passed = True
            check.message = "All dependencies are valid"
            if result.topological_order:
                check.details.append(
                    f"Execution order: {' → '.join(result.topological_order)}"
                )

        self.validation_report.add_check(check)

    def _check_input_files(self, tickets_path: str) -> None:
        """Check that all required input files exist.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="input_files_exist",
            description="Verify all required input files are accessible",
            level=ValidationLevel.ERROR,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = "Cannot check input files - tickets file not found"
            self.validation_report.add_check(check)
            return

        tickets = self._parse_tickets(tickets_path)
        missing_files = []
        checked_files = set()

        for ticket_id, ticket_data in tickets.items():
            input_files = ticket_data.get("required_input_files", [])

            for input_file_ref in input_files:
                # Extract actual file path (remove "from Ticket X" annotations)
                file_path = re.sub(
                    r"\s*\(from Ticket \d+\)", "", input_file_ref
                ).strip()

                if not file_path or file_path.lower() == "none":
                    continue

                # Skip if already checked
                if file_path in checked_files:
                    continue

                checked_files.add(file_path)

                # Check if file exists (resolve relative to project root)
                full_path = self.project_root / file_path
                if not full_path.exists():
                    missing_files.append((ticket_id, file_path))
                    check.details.append(
                        f"Ticket {ticket_id}: Missing file '{file_path}'"
                    )

        if missing_files:
            check.passed = False
            check.message = f"Found {len(missing_files)} missing input files"
            check.details.append("These files must exist before execution can begin")
        else:
            check.passed = True
            check.message = f"All {len(checked_files)} required input files exist"

        self.validation_report.add_check(check)

    def _check_model_configuration(self, tickets_path: str) -> None:
        """Verify that required models are configured and available.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="model_configuration",
            description="Verify required AI models are configured",
            level=ValidationLevel.ERROR,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = "Cannot check models - tickets file not found"
            self.validation_report.add_check(check)
            return

        tickets = self._parse_tickets(tickets_path)
        required_models = set()
        model_usage = {}

        for ticket_id, ticket_data in tickets.items():
            model = ticket_data.get("model", "").lower()
            if model and model != "none":
                required_models.add(model)
                if model not in model_usage:
                    model_usage[model] = []
                model_usage[model].append(ticket_id)

        # Check if models are valid
        invalid_models = []
        for model in required_models:
            if model not in self.AVAILABLE_MODELS:
                invalid_models.append(model)
                tickets_str = ", ".join(model_usage[model])
                check.details.append(
                    f"Unknown model '{model}' used by tickets: {tickets_str}"
                )

        if invalid_models:
            check.passed = False
            check.message = f"Found {len(invalid_models)} invalid model configurations"
            check.details.append(
                f"Valid models are: {', '.join(self.AVAILABLE_MODELS.keys())}"
            )
        else:
            check.passed = True
            check.message = f"All {len(required_models)} required models are valid"
            for model, tickets in model_usage.items():
                check.details.append(f"Model '{model}': {len(tickets)} tickets")

        self.validation_report.add_check(check)

    def _check_file_conflicts(self, tickets_path: str) -> None:
        """Check for file write conflicts between tickets.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="file_conflicts",
            description="Check for output file conflicts between tickets",
            level=ValidationLevel.WARNING,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = "Cannot check conflicts - tickets file not found"
            self.validation_report.add_check(check)
            return

        tickets = self._parse_tickets(tickets_path)

        # Check parallel execution conflicts
        conflicts = self._find_parallel_conflicts(tickets_path, tickets, check)

        # Check general file sharing
        file_writers = self._find_file_writers(tickets)
        shared_files = [
            (path, writers)
            for path, writers in file_writers.items()
            if len(writers) > 1
        ]

        # Report results
        self._report_conflict_results(check, conflicts, shared_files)
        self.validation_report.add_check(check)

    def _find_parallel_conflicts(
        self, tickets_path: str, tickets: Dict, check: ValidationCheck
    ) -> List:
        """Find file conflicts within parallel execution groups."""
        conflicts = []
        dep_result = self.dependency_validator.validate_ticket_dependencies(
            tickets_path
        )

        if not dep_result.valid:
            return conflicts

        parallel_groups = self.dependency_validator.get_parallel_execution_groups(
            dep_result
        )

        for group in parallel_groups:
            group_files: Dict[str, List[str]] = {}
            for ticket_id in group:
                if ticket_id in tickets:
                    output_files = tickets[ticket_id].get("output_files", [])
                    for file_path in output_files:
                        if file_path and file_path.lower() != "none":
                            if file_path not in group_files:
                                group_files[file_path] = []
                            group_files[file_path].append(ticket_id)

            # Check for conflicts in this parallel group
            for file_path, writers in group_files.items():
                if len(writers) > 1:
                    conflicts.append((file_path, writers))
                    writers_str = ", ".join(writers)
                    msg = f"Conflict: '{file_path}' written by parallel tickets: "
                    check.details.append(f"{msg}{writers_str}")

        return conflicts

    def _find_file_writers(self, tickets: Dict) -> Dict[str, List[str]]:
        """Find all files and their writers."""
        file_writers: Dict[str, List[str]] = {}

        for ticket_id, ticket_data in tickets.items():
            output_files = ticket_data.get("output_files", [])
            for file_path in output_files:
                if file_path and file_path.lower() != "none":
                    if file_path not in file_writers:
                        file_writers[file_path] = []
                    file_writers[file_path].append(ticket_id)

        return file_writers

    def _report_conflict_results(
        self, check: ValidationCheck, conflicts: List, shared_files: List
    ) -> None:
        """Report the results of conflict checking."""
        if conflicts:
            check.passed = False
            check.level = ValidationLevel.ERROR
            check.message = (
                f"Found {len(conflicts)} file conflicts in parallel execution"
            )
            check.details.append(
                "These tickets cannot run in parallel due to file conflicts"
            )
        elif shared_files:
            check.passed = True  # Warning only
            check.message = (
                f"Found {len(shared_files)} shared output files "
                "(sequential execution OK)"
            )
            for file_path, writers in shared_files[:5]:  # Show first 5
                check.details.append(
                    f"File '{file_path}' modified by: {', '.join(writers)}"
                )
            if len(shared_files) > 5:
                check.details.append(f"... and {len(shared_files) - 5} more")
        else:
            check.passed = True
            check.message = "No file conflicts detected"

    def _check_execution_order(self, tickets_path: str) -> None:
        """Validate that execution order is feasible.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="execution_order",
            description="Validate ticket execution order feasibility",
            level=ValidationLevel.ERROR,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = "Cannot check order - tickets file not found"
            self.validation_report.add_check(check)
            return

        result = self.dependency_validator.validate_ticket_dependencies(tickets_path)

        if not result.topological_order:
            # Check if there are any actual dependency issues
            if result.issues and any(
                issue.severity.value == "invalid" for issue in result.issues
            ):
                check.passed = False
                check.message = "Cannot determine execution order"
                check.details.append("Fix dependency issues first before execution")
            else:
                # No critical issues, just no dependencies to order
                check.passed = True
                check.message = (
                    "No dependencies to validate - tickets can execute independently"
                )
        else:
            check.passed = True
            check.message = "Valid execution order determined"

            # Get parallel execution groups
            parallel_groups = self.dependency_validator.get_parallel_execution_groups(
                result
            )

            if parallel_groups:
                check.details.append(
                    f"Execution will run in {len(parallel_groups)} phases:"
                )
                for i, group in enumerate(parallel_groups, 1):
                    if len(group) > 1:
                        check.details.append(
                            f"  Phase {i}: {', '.join(group)} (parallel)"
                        )
                    else:
                        check.details.append(f"  Phase {i}: {group[0]} (sequential)")

                # Estimate time savings from parallelization
                parallel_ticket_count = sum(
                    len(g) - 1 for g in parallel_groups if len(g) > 1
                )
                if parallel_ticket_count > 0:
                    check.details.append(
                        f"Parallel execution can process {parallel_ticket_count} "
                        f"additional tickets simultaneously"
                    )

        self.validation_report.add_check(check)

    def _check_resource_availability(self, tickets_path: str) -> None:
        """Check system resource availability for execution.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="resource_availability",
            description="Check system resources for ticket execution",
            level=ValidationLevel.WARNING,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = "Cannot check resources - tickets file not found"
            self.validation_report.add_check(check)
            return

        tickets = self._parse_tickets(tickets_path)

        # Estimate total complexity and resource needs
        total_complexity = 0.0
        large_tickets = []
        total_files = set()

        for ticket_id, ticket_data in tickets.items():
            estimation = self.complexity_estimator.estimate_ticket(ticket_data)
            total_complexity += estimation.total_complexity_score

            if estimation.effort_category.value == "large":
                large_tickets.append(ticket_id)

            # Count unique files
            for file_path in ticket_data.get("output_files", []):
                if file_path and file_path.lower() != "none":
                    total_files.add(file_path)

        # Check disk space for output files
        try:
            import shutil

            free_space = shutil.disk_usage(self.project_root).free
            free_space_gb = free_space / (1024**3)

            # Estimate space needs (rough heuristic: 10KB per file average)
            estimated_space_mb = (len(total_files) * 10) / 1024

            if free_space_gb < 1:  # Less than 1GB free
                check.level = ValidationLevel.ERROR
                check.passed = False
                check.message = f"Low disk space: {free_space_gb:.2f}GB available"
                check.details.append(
                    f"Estimated space needed: {estimated_space_mb:.2f}MB"
                )
            else:
                check.passed = True
                check.message = "Sufficient resources available"
                check.details.append(f"Free disk space: {free_space_gb:.2f}GB")

        except Exception:
            check.passed = True  # Don't fail on resource check errors
            check.message = "Resource check completed (unable to verify disk space)"

        # Add complexity summary
        check.details.append(f"Total execution complexity: {total_complexity:.1f}")
        if large_tickets:
            check.details.append(
                f"Large complexity tickets: {', '.join(large_tickets[:5])}"
            )
            if len(large_tickets) > 5:
                check.details.append(f"... and {len(large_tickets) - 5} more")

        check.details.append(f"Total output files: {len(total_files)}")

        self.validation_report.add_check(check)

    def _check_ticket_structure(self, tickets_path: str) -> None:
        """Validate ticket structure and required fields.

        Args:
            tickets_path: Path to the tickets file

        """
        check = ValidationCheck(
            name="ticket_structure",
            description="Validate ticket format and required fields",
            level=ValidationLevel.WARNING,
        )

        if not os.path.exists(tickets_path):
            check.passed = False
            check.message = "Cannot check structure - tickets file not found"
            self.validation_report.add_check(check)
            return

        tickets = self._parse_tickets(tickets_path)
        structure_issues = []

        required_fields = [
            "description",
            "model",
            "dependencies",
            "output_files",
            "acceptance_criteria",
        ]

        for ticket_id, ticket_data in tickets.items():
            missing_fields = []

            for field in required_fields:
                if field not in ticket_data or not ticket_data[field]:
                    if field == "dependencies":
                        # Dependencies can be empty
                        continue
                    missing_fields.append(field)

            if missing_fields:
                structure_issues.append(ticket_id)
                check.details.append(
                    f"Ticket {ticket_id}: Missing fields: {', '.join(missing_fields)}"
                )

            # Check for minimal acceptance criteria
            criteria = ticket_data.get("acceptance_criteria", [])
            if len(criteria) < 1:
                structure_issues.append(ticket_id)
                check.details.append(
                    f"Ticket {ticket_id}: No acceptance criteria defined"
                )

        if structure_issues:
            check.passed = False
            check.message = (
                f"Found structure issues in {len(set(structure_issues))} tickets"
            )
            check.details.append("Consider adding missing fields for better execution")
        else:
            check.passed = True
            check.message = f"All {len(tickets)} tickets have valid structure"

        self.validation_report.add_check(check)

    def _parse_tickets(self, tickets_path: str) -> Dict[str, Dict]:
        """Parse all tickets from the file.

        Args:
            tickets_path: Path to the tickets file

        Returns:
            Dictionary mapping ticket IDs to ticket data

        """
        tickets = {}

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
                tickets[ticket_id] = ticket_data

        return tickets

    def _parse_single_ticket(self, ticket_id: str, content: str) -> Dict:
        """Parse a single ticket's content.

        Args:
            ticket_id: ID of the ticket
            content: Raw content of the ticket

        Returns:
            Dictionary with parsed ticket data

        """
        lines = content.split("\n")
        ticket_data = self._init_ticket_data(ticket_id, lines)
        current_section = None

        for line in lines:
            line_stripped = line.strip()

            # Check for section headers
            section = self._parse_section_header(line_stripped, ticket_data)
            if section is not None:
                current_section = section
                continue

            # Parse list items
            if line_stripped.startswith("- "):
                self._parse_list_item(
                    line_stripped[2:].strip(), current_section, ticket_data
                )

            # Handle continuation of description
            elif current_section == "description" and line_stripped:
                ticket_data["description"] += " " + line_stripped

        return ticket_data

    def _init_ticket_data(self, ticket_id: str, lines: List[str]) -> Dict:
        """Initialize ticket data structure."""
        return {
            "id": ticket_id,
            "title": lines[0].strip() if lines else "",
            "description": "",
            "model": "",
            "dependencies": [],
            "required_input_files": [],
            "output_files": [],
            "acceptance_criteria": [],
            "status": "",
        }

    def _parse_section_header(self, line: str, ticket_data: Dict) -> Optional[str]:
        """Parse section headers and return the current section."""
        if not line.startswith("**"):
            return None

        if line.startswith("**Status:**"):
            ticket_data["status"] = line.replace("**Status:**", "").strip()
            return None
        elif line.startswith("**Model:**"):
            ticket_data["model"] = line.replace("**Model:**", "").strip()
            return None
        elif line.startswith("**Dependencies:**"):
            deps_text = line.replace("**Dependencies:**", "").strip()
            if deps_text and deps_text.lower() != "none":
                deps = [d.strip() for d in deps_text.split(",")]
                ticket_data["dependencies"] = [d for d in deps if d]
            return None
        elif line.startswith("**Description:**"):
            ticket_data["description"] = line.replace("**Description:**", "").strip()
            return "description"
        elif line.startswith("**Required Input Files:**"):
            return "required_input_files"
        elif line.startswith("**Output Files:**"):
            return "output_files"
        elif line.startswith("**Acceptance Criteria:**"):
            return "acceptance_criteria"
        else:
            return None

    def _parse_list_item(
        self, item: str, current_section: Optional[str], ticket_data: Dict
    ) -> None:
        """Parse a list item based on the current section."""
        if not item or item.lower() == "none":
            return

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
                criteria = item[3:].strip()
                if criteria:
                    ticket_data["acceptance_criteria"].append(criteria)
            else:
                ticket_data["acceptance_criteria"].append(item)

    def can_proceed(self) -> bool:
        """Check if execution can proceed based on validation results.

        Returns:
            True if no critical issues found, False otherwise

        """
        return not self.validation_report.has_critical_issues()

    def should_warn(self) -> bool:
        """Check if there are warnings that should be shown.

        Returns:
            True if there are warnings or errors

        """
        return (
            self.validation_report.has_warnings() or self.validation_report.has_errors()
        )

    def get_summary(self) -> str:
        """Get a summary of the validation results.

        Returns:
            Human-readable summary string

        """
        return self.validation_report.get_summary()

    def get_failed_checks(self) -> List[ValidationCheck]:
        """Get list of failed validation checks.

        Returns:
            List of failed ValidationCheck objects

        """
        return self.validation_report.get_failed_checks()

    def get_critical_issues(self) -> List[ValidationCheck]:
        """Get list of critical issues that block execution.

        Returns:
            List of critical ValidationCheck objects

        """
        return self.validation_report.get_critical_issues()
