"""Verification Engine Module

Scans directories and validates file existence against ticket requirements.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class VerificationResult:
    """Represents the result of a verification check."""

    passed: bool
    message: str
    details: Dict[str, Any]
    timestamp: datetime


@dataclass
class FileArtifact:
    """Represents a file artifact that should be created."""

    type: str
    path: str
    created: bool = False
    exists: bool = False
    size: Optional[int] = None
    last_modified: Optional[datetime] = None


class VerificationEngine:
    """Main verification engine that scans directories and validates file existence.
    """

    def __init__(self, project_root: str):
        """Initialize the verification engine."""
        self.project_root = Path(project_root)
        self.results: List[VerificationResult] = []

    def scan_directory(self, directory: str) -> Dict[str, Any]:
        """Scan a directory and return file structure information."""
        dir_path = self.project_root / directory
        if not dir_path.exists():
            return {
                "exists": False,
                "files": [],
                "subdirectories": [],
                "total_files": 0
            }

        files = []
        subdirs = []

        for item in dir_path.iterdir():
            if item.is_file():
                files.append({
                    "name": item.name,
                    "path": str(item.relative_to(self.project_root)),
                    "size": item.stat().st_size,
                    "last_modified": datetime.fromtimestamp(item.stat().st_mtime)
                })
            elif item.is_dir():
                subdirs.append({
                    "name": item.name,
                    "path": str(item.relative_to(self.project_root))
                })

        return {
            "exists": True,
            "files": files,
            "subdirectories": subdirs,
            "total_files": len(files)
        }

    def validate_file_existence(self, artifacts: List[Dict[str, Any]]) -> List[VerificationResult]:
        """Validate that required files and directories exist."""
        results = []

        for artifact in artifacts:
            artifact_path = self.project_root / artifact["path"]
            artifact_type = artifact.get("type", "file")

            if artifact_type == "directory":
                exists = artifact_path.is_dir()
                if exists:
                    scan_result = self.scan_directory(artifact["path"])
                    details = {
                        "type": "directory",
                        "path": artifact["path"],
                        "scan_result": scan_result
                    }
                else:
                    details = {
                        "type": "directory",
                        "path": artifact["path"],
                        "scan_result": {"exists": False}
                    }
            else:
                exists = artifact_path.is_file()
                if exists:
                    stat = artifact_path.stat()
                    details = {
                        "type": "file",
                        "path": artifact["path"],
                        "size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(stat.st_mtime)
                    }
                else:
                    details = {
                        "type": "file",
                        "path": artifact["path"],
                        "size": None,
                        "last_modified": None
                    }

            result = VerificationResult(
                passed=exists,
                message=f"{'Found' if exists else 'Missing'} {artifact_type}: {artifact['path']}",
                details=details,
                timestamp=datetime.now()
            )
            results.append(result)

        return results

    def verify_ticket_artifacts(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify all artifacts defined in a ticket."""
        artifacts = ticket_data.get("artifacts", [])
        verification_results = self.validate_file_existence(artifacts)

        passed_count = sum(1 for r in verification_results if r.passed)
        total_count = len(verification_results)

        return {
            "ticket_id": ticket_data.get("id"),
            "title": ticket_data.get("title"),
            "total_artifacts": total_count,
            "passed_artifacts": passed_count,
            "success_rate": (passed_count / total_count) if total_count > 0 else 0,
            "results": [asdict(r) for r in verification_results],
            "overall_status": "PASS" if passed_count == total_count else "FAIL"
        }

    def load_ticket_file(self, ticket_file: str) -> Dict[str, Any]:
        """Load ticket data from YAML file."""
        ticket_path = Path(ticket_file)
        if not ticket_path.exists():
            raise FileNotFoundError(f"Ticket file not found: {ticket_file}")

        with open(ticket_path, 'r') as f:
            if ticket_file.endswith('.yaml') or ticket_file.endswith('.yml'):
                return yaml.safe_load(f)
            elif ticket_file.endswith('.json'):
                return json.load(f)
            else:
                raise ValueError(f"Unsupported ticket file format: {ticket_file}")

    def find_ticket_by_id(self, ticket_file: str, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Find a specific ticket by ID in the ticket file."""
        data = self.load_ticket_file(ticket_file)
        tickets = data.get("tickets", [])

        for ticket in tickets:
            if ticket.get("id") == ticket_id:
                return ticket

        return None

    def run_verification(self, ticket_file: str, ticket_id: str) -> Dict[str, Any]:
        """Run complete verification for a specific ticket."""
        try:
            ticket = self.find_ticket_by_id(ticket_file, ticket_id)
            if not ticket:
                return {
                    "success": False,
                    "error": f"Ticket {ticket_id} not found in {ticket_file}",
                    "timestamp": datetime.now().isoformat()
                }

            verification_result = self.verify_ticket_artifacts(ticket)
            verification_result["success"] = True
            verification_result["timestamp"] = datetime.now().isoformat()

            return verification_result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
