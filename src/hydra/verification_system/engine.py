"""Verification Engine Module

Scans directories and validates file existence against ticket requirements.
Integrates with AI pattern detection for code quality verification.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from hydra.verification_system.ai_detector import (
    AIDetector,
    AIPatternConfig,
)
from hydra.verification_system.metrics_integration import (
    MetricsIntegration,
    MetricsVerifier,
)


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
    Includes AI pattern detection for code quality verification.
    """

    def __init__(self, project_root: str, ai_detector_config: Optional[AIPatternConfig] = None, strict_mode: bool = False):
        """Initialize the verification engine."""
        self.project_root = Path(project_root)
        self.results: List[VerificationResult] = []
        self.ai_detector = AIDetector(ai_detector_config or AIPatternConfig())
        self.ai_detection_results = []
        self.metrics_verifier = MetricsVerifier(strict_mode=strict_mode)
        self.strict_mode = strict_mode

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

    def run_ai_detection(self, directory: Optional[str] = None,
                        extensions: Optional[set] = None) -> Dict[str, Any]:
        """Run AI pattern detection on project files."""
        scan_path = self.project_root
        if directory:
            scan_path = self.project_root / directory

        if extensions is None:
            extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs'}

        # Run detection
        detection_results = self.ai_detector.detect_directory(scan_path, extensions)
        self.ai_detection_results = detection_results

        # Generate report
        report = self.ai_detector.generate_report(detection_results)

        return {
            "success": True,
            "ai_detection_report": report,
            "timestamp": datetime.now().isoformat()
        }

    def run_ai_detection_on_file(self, file_path: str) -> Tuple[bool, str]:
        """Run AI pattern detection on a single file."""
        full_path = self.project_root / file_path
        if not full_path.exists():
            return False, f"File not found: {file_path}"

        result = self.ai_detector.detect_file(full_path)
        self.ai_detection_results.append(result)

        return result.passes, result.summary

    def verify_code_quality(self, artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verify code quality using AI pattern detection."""
        quality_results = []

        for artifact in artifacts:
            if artifact.get("type") == "file":
                file_path = artifact["path"]
                if Path(file_path).suffix in {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs'}:
                    passes, summary = self.run_ai_detection_on_file(file_path)
                    quality_results.append({
                        "file": file_path,
                        "passes_ai_check": passes,
                        "summary": summary
                    })

        failed_count = sum(1 for r in quality_results if not r["passes_ai_check"])

        return {
            "total_files_checked": len(quality_results),
            "passed": len(quality_results) - failed_count,
            "failed": failed_count,
            "details": quality_results,
            "overall_quality": "PASS" if failed_count == 0 else "FAIL"
        }

    def run_comprehensive_verification(self, ticket_file: str, ticket_id: str,
                                      check_ai_patterns: bool = True) -> Dict[str, Any]:
        """Run comprehensive verification including existence and AI pattern checks."""
        result = self.run_verification(ticket_file, ticket_id)

        if not result["success"]:
            return result

        if check_ai_patterns and "artifacts" in result:
            # Extract artifacts from the verification result
            artifacts = []
            for r in result.get("results", []):
                artifacts.append({
                    "type": r["details"]["type"],
                    "path": r["details"]["path"]
                })

            # Run AI quality checks
            quality_result = self.verify_code_quality(artifacts)
            result["code_quality"] = quality_result

            # Update overall status
            if quality_result["overall_quality"] == "FAIL":
                result["overall_status"] = "FAIL"
                result["failure_reason"] = "AI patterns detected in code"

        return result

    def add_check_result(self, check_name: str, passed: bool, details: Optional[Dict] = None):
        """Add a check result (for integration with other verification systems)."""
        result = VerificationResult(
            passed=passed,
            message=f"Check '{check_name}' {'passed' if passed else 'failed'}",
            details=details or {},
            timestamp=datetime.now()
        )
        self.results.append(result)

    def get_all_results(self) -> List[Dict[str, Any]]:
        """Get all verification results."""
        return [asdict(r) for r in self.results]

    def update_ai_config(self, **kwargs):
        """Update AI detector configuration."""
        self.ai_detector.update_config(**kwargs)

    def run_quality_metrics_verification(self) -> Dict[str, Any]:
        """Run quality metrics verification on the project."""
        result = self.metrics_verifier.verify_project(str(self.project_root))

        return {
            "success": result.passed,
            "score": result.score,
            "failures": result.failures,
            "warnings": result.warnings,
            "recommendations": result.recommendations,
            "metrics": result.metrics,
            "timestamp": datetime.now().isoformat()
        }

    def run_full_verification_with_metrics(self, ticket_file: str, ticket_id: str) -> Dict[str, Any]:
        """Run comprehensive verification including metrics, AI patterns, and existence checks."""
        # Run standard verification
        result = self.run_comprehensive_verification(ticket_file, ticket_id, check_ai_patterns=True)

        # Add quality metrics verification
        metrics_result = self.run_quality_metrics_verification()
        result["quality_metrics"] = metrics_result

        # Update overall status based on metrics
        if not metrics_result["success"]:
            result["overall_status"] = "FAIL"
            if "failure_reason" in result:
                result["failure_reason"] += f"; Quality metrics failed: {', '.join(metrics_result['failures'])}"
            else:
                result["failure_reason"] = f"Quality metrics failed: {', '.join(metrics_result['failures'])}"

        # Generate quality report
        report = MetricsIntegration.generate_quality_report(str(self.project_root))
        result["quality_report"] = report

        return result
