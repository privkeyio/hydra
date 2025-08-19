"""Acceptance Criteria Parser Module

Extracts and validates requirements from ticket acceptance criteria.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml


class CriterionStatus(Enum):
    """Status of an acceptance criterion."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass
class AcceptanceCriterion:
    """Represents a single acceptance criterion."""

    id: str
    text: str
    status: CriterionStatus
    completed: bool
    verified: bool
    requirements: List[str]
    validation_rules: List[str]
    verification_method: Optional[str] = None


@dataclass
class ParsedCriteria:
    """Container for parsed acceptance criteria."""

    ticket_id: str
    criteria: List[AcceptanceCriterion]
    total_count: int
    completed_count: int
    verified_count: int


class CriteriaParser:
    """Parser for extracting and validating acceptance criteria from tickets.
    """

    def __init__(self):
        """Initialize the criteria parser."""
        self.requirement_patterns = [
            r"create\s+(.+)",
            r"implement\s+(.+)",
            r"add\s+(.+)",
            r"build\s+(.+)",
            r"ensure\s+(.+)",
            r"validate\s+(.+)",
            r"configure\s+(.+)",
            r"setup\s+(.+)"
        ]

        self.file_patterns = [
            r"([a-zA-Z_][a-zA-Z0-9_/]*\.py)",
            r"([a-zA-Z_][a-zA-Z0-9_/]*\.json)",
            r"([a-zA-Z_][a-zA-Z0-9_/]*\.yaml)",
            r"([a-zA-Z_][a-zA-Z0-9_/]*\.yml)",
            r"([a-zA-Z_][a-zA-Z0-9_/]*\.md)",
            r"([a-zA-Z_][a-zA-Z0-9_/]*\.txt)"
        ]

        self.validation_keywords = [
            "test", "verify", "check", "validate", "ensure",
            "confirm", "assert", "coverage", "quality"
        ]

    def extract_requirements_from_text(self, criterion_text: str) -> List[str]:
        """Extract specific requirements from criterion text."""
        requirements = []
        text_lower = criterion_text.lower()

        # Extract using requirement patterns
        for pattern in self.requirement_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            requirements.extend(matches)

        # Extract file references
        for pattern in self.file_patterns:
            matches = re.findall(pattern, criterion_text)
            for match in matches:
                requirements.append(f"file: {match}")

        # Extract directory references
        dir_matches = re.findall(r'(\w+/\w*)', criterion_text)
        for match in dir_matches:
            if not any(ext in match for ext in ['.py', '.json', '.yaml', '.yml', '.md', '.txt']):
                requirements.append(f"directory: {match}")

        return list(set(requirements))  # Remove duplicates

    def extract_validation_rules(self, criterion_text: str) -> List[str]:
        """Extract validation rules from criterion text."""
        validation_rules = []
        text_lower = criterion_text.lower()

        # Check for validation keywords
        for keyword in self.validation_keywords:
            if keyword in text_lower:
                validation_rules.append(f"requires_{keyword}")

        # Extract specific validation patterns
        if "test" in text_lower:
            validation_rules.append("requires_unit_tests")

        if "coverage" in text_lower:
            validation_rules.append("requires_test_coverage")

        if "integration" in text_lower:
            validation_rules.append("requires_integration_tests")

        if "format" in text_lower or "json" in text_lower or "html" in text_lower:
            validation_rules.append("requires_output_format")

        if "command" in text_lower or "cli" in text_lower:
            validation_rules.append("requires_cli_interface")

        if "config" in text_lower or "setting" in text_lower:
            validation_rules.append("requires_configuration")

        return list(set(validation_rules))

    def determine_verification_method(self, criterion_text: str, requirements: List[str]) -> str:
        """Determine the appropriate verification method for a criterion."""
        text_lower = criterion_text.lower()

        # File existence verification
        if any("file:" in req for req in requirements):
            return "file_existence"

        # Directory structure verification
        if any("directory:" in req for req in requirements):
            return "directory_structure"

        # Functionality verification
        if any(keyword in text_lower for keyword in ["implement", "functionality", "working"]):
            return "functionality_test"

        # Integration verification
        if "integration" in text_lower:
            return "integration_test"

        # Configuration verification
        if any(keyword in text_lower for keyword in ["config", "setting", "customize"]):
            return "configuration_test"

        # CLI verification
        if any(keyword in text_lower for keyword in ["cli", "command", "line"]):
            return "cli_test"

        # Default to manual verification
        return "manual_verification"

    def parse_criterion(self, criterion_data: Union[str, Dict[str, Any]], index: int) -> AcceptanceCriterion:
        """Parse a single acceptance criterion."""
        # Handle different input formats
        if isinstance(criterion_data, str):
            criterion_text = criterion_data
            completed = False
            verified = False
        elif isinstance(criterion_data, dict):
            criterion_text = criterion_data.get("criterion", criterion_data.get("text", ""))
            completed = criterion_data.get("completed", False)
            verified = criterion_data.get("verified", False)
        else:
            raise ValueError(f"Invalid criterion format: {type(criterion_data)}")

        # Generate criterion ID
        criterion_id = f"criterion_{index:03d}"

        # Extract requirements and validation rules
        requirements = self.extract_requirements_from_text(criterion_text)
        validation_rules = self.extract_validation_rules(criterion_text)
        verification_method = self.determine_verification_method(criterion_text, requirements)

        # Determine status
        if verified:
            status = CriterionStatus.VERIFIED
        elif completed:
            status = CriterionStatus.COMPLETED
        else:
            status = CriterionStatus.NOT_STARTED

        return AcceptanceCriterion(
            id=criterion_id,
            text=criterion_text,
            status=status,
            completed=completed,
            verified=verified,
            requirements=requirements,
            validation_rules=validation_rules,
            verification_method=verification_method
        )

    def parse_ticket_criteria(self, ticket_data: Dict[str, Any]) -> ParsedCriteria:
        """Parse all acceptance criteria from a ticket."""
        ticket_id = ticket_data.get("id", "unknown")
        criteria_data = ticket_data.get("acceptance_criteria", [])

        criteria = []
        for i, criterion_data in enumerate(criteria_data):
            try:
                criterion = self.parse_criterion(criterion_data, i + 1)
                criteria.append(criterion)
            except Exception:
                # Create a failed criterion for parsing errors
                criteria.append(AcceptanceCriterion(
                    id=f"criterion_{i+1:03d}",
                    text=str(criterion_data),
                    status=CriterionStatus.FAILED,
                    completed=False,
                    verified=False,
                    requirements=[],
                    validation_rules=[],
                    verification_method="manual_verification"
                ))

        completed_count = sum(1 for c in criteria if c.completed)
        verified_count = sum(1 for c in criteria if c.verified)

        return ParsedCriteria(
            ticket_id=ticket_id,
            criteria=criteria,
            total_count=len(criteria),
            completed_count=completed_count,
            verified_count=verified_count
        )

    def load_and_parse_ticket(self, ticket_file: str, ticket_id: str) -> Optional[ParsedCriteria]:
        """Load a ticket file and parse its acceptance criteria."""
        ticket_path = Path(ticket_file)

        if not ticket_path.exists():
            raise FileNotFoundError(f"Ticket file not found: {ticket_file}")

        # Load ticket data
        with open(ticket_path, 'r') as f:
            if ticket_file.endswith('.yaml') or ticket_file.endswith('.yml'):
                data = yaml.safe_load(f)
            elif ticket_file.endswith('.json'):
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {ticket_file}")

        # Find the specific ticket
        tickets = data.get("tickets", [])
        ticket_data = None

        for ticket in tickets:
            if ticket.get("id") == ticket_id:
                ticket_data = ticket
                break

        if not ticket_data:
            return None

        return self.parse_ticket_criteria(ticket_data)

    def generate_verification_plan(self, parsed_criteria: ParsedCriteria) -> Dict[str, Any]:
        """Generate a verification plan based on parsed criteria."""
        verification_methods = {}
        required_files = []
        required_directories = []
        validation_requirements = set()

        for criterion in parsed_criteria.criteria:
            method = criterion.verification_method
            if method not in verification_methods:
                verification_methods[method] = []
            verification_methods[method].append(criterion.id)

            # Collect file and directory requirements
            for req in criterion.requirements:
                if req.startswith("file:"):
                    required_files.append(req[5:].strip())
                elif req.startswith("directory:"):
                    required_directories.append(req[10:].strip())

            # Collect validation requirements
            validation_requirements.update(criterion.validation_rules)

        return {
            "ticket_id": parsed_criteria.ticket_id,
            "total_criteria": parsed_criteria.total_count,
            "verification_methods": verification_methods,
            "required_files": list(set(required_files)),
            "required_directories": list(set(required_directories)),
            "validation_requirements": list(validation_requirements),
            "criteria_summary": {
                "not_started": len([c for c in parsed_criteria.criteria if c.status == CriterionStatus.NOT_STARTED]),
                "in_progress": len([c for c in parsed_criteria.criteria if c.status == CriterionStatus.IN_PROGRESS]),
                "completed": len([c for c in parsed_criteria.criteria if c.status == CriterionStatus.COMPLETED]),
                "verified": len([c for c in parsed_criteria.criteria if c.status == CriterionStatus.VERIFIED]),
                "failed": len([c for c in parsed_criteria.criteria if c.status == CriterionStatus.FAILED])
            },
            "generated_at": datetime.now().isoformat()
        }

    def export_criteria_analysis(self, parsed_criteria: ParsedCriteria, output_file: str) -> bool:
        """Export criteria analysis to a file."""
        try:
            analysis_data = {
                "ticket_id": parsed_criteria.ticket_id,
                "total_criteria": parsed_criteria.total_count,
                "completed_criteria": parsed_criteria.completed_count,
                "verified_criteria": parsed_criteria.verified_count,
                "criteria": [
                    {
                        "id": c.id,
                        "text": c.text,
                        "status": c.status.value,
                        "completed": c.completed,
                        "verified": c.verified,
                        "requirements": c.requirements,
                        "validation_rules": c.validation_rules,
                        "verification_method": c.verification_method
                    }
                    for c in parsed_criteria.criteria
                ],
                "verification_plan": self.generate_verification_plan(parsed_criteria),
                "exported_at": datetime.now().isoformat()
            }

            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                if output_file.endswith('.json'):
                    json.dump(analysis_data, f, indent=2)
                elif output_file.endswith('.yaml') or output_file.endswith('.yml'):
                    yaml.dump(analysis_data, f, default_flow_style=False)
                else:
                    json.dump(analysis_data, f, indent=2)

            return True

        except Exception as e:
            print(f"Error exporting criteria analysis: {e}")
            return False
