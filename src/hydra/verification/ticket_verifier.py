"""Ticket Verification System for Hydra.

Automatically verifies that acceptance criteria are met after ticket execution.
"""

import ast
import os
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from hydra.ticket_workflow import parse_ticket


class CriterionStatus(Enum):
    """Status of a single acceptance criterion."""
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


@dataclass
class VerificationResult:
    """Result of verifying a single criterion."""
    criterion: str
    status: CriterionStatus
    evidence: str
    confidence: float  # 0.0 to 1.0


@dataclass
class TicketVerificationReport:
    """Complete verification report for a ticket."""
    ticket_id: str
    ticket_title: str
    total_criteria: int
    passed: int
    failed: int
    partial: int
    coverage: float  # Percentage of criteria verified
    results: List[VerificationResult]
    recommendations: List[str]


class TicketVerifier:
    """Verifies ticket acceptance criteria through code analysis."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.verification_patterns = self._load_verification_patterns()
    
    def _load_verification_patterns(self) -> Dict[str, List[str]]:
        """Load patterns for detecting common acceptance criteria."""
        return {
            "file_created": [
                r"[Cc]reate\s+(\S+)",
                r"[Aa]dd\s+(\S+)\s+file",
                r"[Gg]enerate\s+(\S+)"
            ],
            "directory_created": [
                r"[Cc]reate\s+(\S+/)\s+directory",
                r"[Mm]ake\s+(\S+/)\s+folder",
                r"[Aa]dd\s+(\S+/)\s+structure"
            ],
            "function_implemented": [
                r"[Ii]mplement\s+(\w+)\s+function",
                r"[Cc]reate\s+(\w+)\s+method",
                r"[Aa]dd\s+(\w+)\s+endpoint"
            ],
            "dependency_added": [
                r"[Aa]dd\s+(\S+)\s+to\s+requirements",
                r"[Ii]nstall\s+(\S+)",
                r"[Aa]dd\s+(\S+)\s+dependency"
            ],
            "test_created": [
                r"[Ww]rite\s+test\s+for\s+(\S+)",
                r"[Aa]dd\s+(\S+)\s+test",
                r"[Cc]reate\s+unit\s+test"
            ],
            "configuration": [
                r"[Cc]onfigure\s+(\S+)",
                r"[Ss]et\s+up\s+(\S+)",
                r"[Aa]dd\s+(\S+)\s+configuration"
            ]
        }
    
    def verify_ticket(self, tickets_path: str, ticket_id: str) -> TicketVerificationReport:
        """Verify all acceptance criteria for a ticket."""
        ticket = parse_ticket(tickets_path, ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")
        
        results = []
        for criterion in ticket['acceptance_criteria']:
            # Skip already completed criteria
            if criterion.startswith('✅'):
                results.append(VerificationResult(
                    criterion=criterion,
                    status=CriterionStatus.PASSED,
                    evidence="Already marked as completed",
                    confidence=1.0
                ))
                continue
            
            result = self._verify_criterion(criterion)
            results.append(result)
        
        # Calculate statistics
        passed = sum(1 for r in results if r.status == CriterionStatus.PASSED)
        failed = sum(1 for r in results if r.status == CriterionStatus.FAILED)
        partial = sum(1 for r in results if r.status == CriterionStatus.PARTIAL)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(results)
        
        return TicketVerificationReport(
            ticket_id=ticket_id,
            ticket_title=ticket['title'],
            total_criteria=len(results),
            passed=passed,
            failed=failed,
            partial=partial,
            coverage=(passed + partial * 0.5) / len(results) * 100 if results else 0,
            results=results,
            recommendations=recommendations
        )
    
    def _verify_criterion(self, criterion: str) -> VerificationResult:
        """Verify a single acceptance criterion."""
        criterion_lower = criterion.lower()
        
        # Check for file creation
        if any(keyword in criterion_lower for keyword in ['create', 'add', 'generate']) and 'file' in criterion_lower:
            return self._verify_file_exists(criterion)
        
        # Check for directory creation
        if any(keyword in criterion_lower for keyword in ['directory', 'folder', 'structure']):
            return self._verify_directory_exists(criterion)
        
        # Check for endpoint creation
        if 'endpoint' in criterion_lower:
            return self._verify_endpoint_exists(criterion)
        
        # Check for function/method implementation
        if any(keyword in criterion_lower for keyword in ['function', 'method', 'implement']):
            return self._verify_function_exists(criterion)
        
        # Check for dependency installation
        if any(keyword in criterion_lower for keyword in ['dependency', 'requirement', 'install']):
            return self._verify_dependency_exists(criterion)
        
        # Check for test creation
        if 'test' in criterion_lower:
            return self._verify_test_exists(criterion)
        
        # Check for configuration
        if any(keyword in criterion_lower for keyword in ['configure', 'configuration', 'setting']):
            return self._verify_configuration_exists(criterion)
        
        # Default: unable to automatically verify
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.UNKNOWN,
            evidence="Unable to automatically verify this criterion",
            confidence=0.0
        )
    
    def _verify_file_exists(self, criterion: str) -> VerificationResult:
        """Verify that a file was created."""
        # Extract potential file paths from criterion
        patterns = [
            r'[\'"`]([^\'"`]+\.\w+)[\'"`]',  # Quoted filenames
            r'(\w+/\w+\.\w+)',  # Path-like patterns
            r'(\w+\.\w+)',  # Simple filenames
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, criterion)
            for match in matches:
                file_path = self.project_root / match
                if file_path.exists():
                    return VerificationResult(
                        criterion=criterion,
                        status=CriterionStatus.PASSED,
                        evidence=f"File {match} exists",
                        confidence=0.9
                    )
        
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.FAILED,
            evidence="File not found",
            confidence=0.7
        )
    
    def _verify_directory_exists(self, criterion: str) -> VerificationResult:
        """Verify that a directory was created."""
        patterns = [
            r'(\w+/)',  # Directory with trailing slash
            r'(\w+)\s+directory',  # Directory name before 'directory'
            r'(\w+)\s+folder',  # Directory name before 'folder'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, criterion, re.IGNORECASE)
            for match in matches:
                dir_path = self.project_root / match.rstrip('/')
                if dir_path.exists() and dir_path.is_dir():
                    return VerificationResult(
                        criterion=criterion,
                        status=CriterionStatus.PASSED,
                        evidence=f"Directory {match} exists",
                        confidence=0.9
                    )
        
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.FAILED,
            evidence="Directory not found",
            confidence=0.7
        )
    
    def _verify_endpoint_exists(self, criterion: str) -> VerificationResult:
        """Verify that an API endpoint was created."""
        # Extract endpoint path
        patterns = [
            r'[\'"`](/[^\'"`]+)[\'"`]',  # Quoted paths
            r'(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)',  # HTTP method + path
            r'(/\w+(?:/\w+)*)',  # Path-like patterns
        ]
        
        endpoint_path = None
        for pattern in patterns:
            matches = re.findall(pattern, criterion)
            if matches:
                if isinstance(matches[0], tuple):
                    endpoint_path = matches[0][1]
                else:
                    endpoint_path = matches[0]
                break
        
        if not endpoint_path:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.UNKNOWN,
                evidence="Could not extract endpoint path",
                confidence=0.3
            )
        
        # Search for endpoint in code
        found = self._search_in_files(endpoint_path, ['.py', '.js', '.ts'])
        
        if found:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.PASSED,
                evidence=f"Endpoint {endpoint_path} found in {found[0]}",
                confidence=0.85
            )
        
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.FAILED,
            evidence=f"Endpoint {endpoint_path} not found in code",
            confidence=0.6
        )
    
    def _verify_function_exists(self, criterion: str) -> VerificationResult:
        """Verify that a function/method was implemented."""
        # Extract function name
        patterns = [
            r'[\'"`](\w+)[\'"`]',  # Quoted function name
            r'(\w+)\s+function',  # Function name before 'function'
            r'(\w+)\s+method',  # Method name before 'method'
            r'implement\s+(\w+)',  # After 'implement'
        ]
        
        func_name = None
        for pattern in patterns:
            matches = re.findall(pattern, criterion, re.IGNORECASE)
            if matches:
                func_name = matches[0]
                break
        
        if not func_name:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.UNKNOWN,
                evidence="Could not extract function name",
                confidence=0.3
            )
        
        # Search for function definition
        found = self._search_function_definition(func_name)
        
        if found:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.PASSED,
                evidence=f"Function {func_name} found in {found[0]}",
                confidence=0.9
            )
        
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.FAILED,
            evidence=f"Function {func_name} not found",
            confidence=0.7
        )
    
    def _verify_dependency_exists(self, criterion: str) -> VerificationResult:
        """Verify that a dependency was added."""
        # Extract package name
        patterns = [
            r'[\'"`]([^\'"`]+)[\'"`]',  # Quoted package name
            r'(\w+(?:-\w+)*)',  # Package name pattern
        ]
        
        package_name = None
        for pattern in patterns:
            matches = re.findall(pattern, criterion)
            if matches:
                # Filter out common words
                for match in matches:
                    if match not in ['add', 'install', 'dependency', 'to', 'with', 'in']:
                        package_name = match
                        break
                if package_name:
                    break
        
        if not package_name:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.UNKNOWN,
                evidence="Could not extract package name",
                confidence=0.3
            )
        
        # Check in various dependency files
        found = self._check_dependency_files(package_name)
        
        if found:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.PASSED,
                evidence=f"Package {package_name} found in {found}",
                confidence=0.95
            )
        
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.FAILED,
            evidence=f"Package {package_name} not found in dependency files",
            confidence=0.8
        )
    
    def _verify_test_exists(self, criterion: str) -> VerificationResult:
        """Verify that tests were created."""
        # Look for test files
        test_patterns = ['test_*.py', '*_test.py', '*.test.js', '*.test.ts', '*.spec.js', '*.spec.ts']
        test_files = []
        
        for pattern in test_patterns:
            test_files.extend(self.project_root.rglob(pattern))
        
        if not test_files:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.FAILED,
                evidence="No test files found",
                confidence=0.8
            )
        
        # Check if tests were recently modified
        import time
        current_time = time.time()
        recent_tests = [f for f in test_files if (current_time - f.stat().st_mtime) < 3600]  # Within last hour
        
        if recent_tests:
            return VerificationResult(
                criterion=criterion,
                status=CriterionStatus.PASSED,
                evidence=f"Recent test files: {', '.join([f.name for f in recent_tests[:3]])}",
                confidence=0.85
            )
        
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.PARTIAL,
            evidence="Test files exist but were not recently modified",
            confidence=0.6
        )
    
    def _verify_configuration_exists(self, criterion: str) -> VerificationResult:
        """Verify that configuration was added."""
        config_files = ['.env', '.env.example', 'config.py', 'config.js', 'settings.py', 'settings.json']
        
        for config_file in config_files:
            file_path = self.project_root / config_file
            if file_path.exists():
                # Check if file was recently modified
                import time
                if (time.time() - file_path.stat().st_mtime) < 3600:
                    return VerificationResult(
                        criterion=criterion,
                        status=CriterionStatus.PASSED,
                        evidence=f"Configuration file {config_file} recently modified",
                        confidence=0.8
                    )
        
        return VerificationResult(
            criterion=criterion,
            status=CriterionStatus.PARTIAL,
            evidence="Configuration files exist but were not recently modified",
            confidence=0.5
        )
    
    def _search_in_files(self, pattern: str, extensions: List[str]) -> Optional[List[str]]:
        """Search for a pattern in files with given extensions."""
        found_in = []
        
        for ext in extensions:
            for file_path in self.project_root.rglob(f'*{ext}'):
                try:
                    content = file_path.read_text()
                    if pattern in content:
                        found_in.append(str(file_path.relative_to(self.project_root)))
                except Exception:
                    continue
        
        return found_in if found_in else None
    
    def _search_function_definition(self, func_name: str) -> Optional[List[str]]:
        """Search for function definitions in code files."""
        patterns = [
            rf'def\s+{func_name}\s*\(',  # Python
            rf'function\s+{func_name}\s*\(',  # JavaScript
            rf'const\s+{func_name}\s*=',  # JS arrow function
            rf'{func_name}\s*:\s*function',  # Object method
        ]
        
        found_in = []
        code_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx']
        
        for ext in code_extensions:
            for file_path in self.project_root.rglob(f'*{ext}'):
                try:
                    content = file_path.read_text()
                    for pattern in patterns:
                        if re.search(pattern, content):
                            found_in.append(str(file_path.relative_to(self.project_root)))
                            break
                except Exception:
                    continue
        
        return found_in if found_in else None
    
    def _check_dependency_files(self, package_name: str) -> Optional[str]:
        """Check if a package is listed in dependency files."""
        dependency_files = {
            'requirements.txt': package_name,
            'package.json': f'"{package_name}"',
            'Cargo.toml': f'{package_name}',
            'go.mod': package_name,
            'pom.xml': f'<artifactId>{package_name}</artifactId>',
        }
        
        for file_name, search_pattern in dependency_files.items():
            file_path = self.project_root / file_name
            if file_path.exists():
                try:
                    content = file_path.read_text()
                    if search_pattern in content:
                        return file_name
                except Exception:
                    continue
        
        return None
    
    def _generate_recommendations(self, results: List[VerificationResult]) -> List[str]:
        """Generate recommendations based on verification results."""
        recommendations = []
        
        failed_count = sum(1 for r in results if r.status == CriterionStatus.FAILED)
        unknown_count = sum(1 for r in results if r.status == CriterionStatus.UNKNOWN)
        
        if failed_count > 0:
            recommendations.append(f"Review {failed_count} failed criteria and complete implementation")
        
        if unknown_count > 0:
            recommendations.append(f"Manually verify {unknown_count} criteria that couldn't be automatically checked")
        
        if failed_count == 0 and unknown_count == 0:
            recommendations.append("All verifiable criteria passed - consider marking ticket as complete")
        
        # Specific recommendations based on failure types
        for result in results:
            if result.status == CriterionStatus.FAILED:
                if 'file' in result.criterion.lower():
                    recommendations.append(f"Create missing file: {result.criterion[:50]}")
                elif 'test' in result.criterion.lower():
                    recommendations.append("Add missing tests")
                elif 'endpoint' in result.criterion.lower():
                    recommendations.append("Implement missing API endpoint")
        
        return recommendations[:5]  # Limit to top 5 recommendations
    
    def generate_report(self, report: TicketVerificationReport) -> str:
        """Generate a human-readable report."""
        lines = [
            f"📋 Ticket Verification Report",
            f"{'='*50}",
            f"Ticket: {report.ticket_id} - {report.ticket_title}",
            f"",
            f"📊 Summary:",
            f"  Total Criteria: {report.total_criteria}",
            f"  ✅ Passed: {report.passed}",
            f"  ❌ Failed: {report.failed}",
            f"  ⚠️  Partial: {report.partial}",
            f"  📈 Coverage: {report.coverage:.1f}%",
            f"",
            f"📝 Detailed Results:",
        ]
        
        for result in report.results:
            status_icon = {
                CriterionStatus.PASSED: "✅",
                CriterionStatus.FAILED: "❌",
                CriterionStatus.PARTIAL: "⚠️",
                CriterionStatus.SKIPPED: "⏭️",
                CriterionStatus.UNKNOWN: "❓"
            }.get(result.status, "")
            
            lines.append(f"  {status_icon} {result.criterion[:60]}")
            lines.append(f"     → {result.evidence} (confidence: {result.confidence:.0%})")
        
        if report.recommendations:
            lines.extend([
                "",
                "💡 Recommendations:",
            ])
            for rec in report.recommendations:
                lines.append(f"  • {rec}")
        
        return "\n".join(lines)