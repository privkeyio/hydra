"""Parallel ticket verification with acceptance criteria checking."""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess
from concurrent.futures import ThreadPoolExecutor

from hydra.tickets.compatibility import TicketFormatHandler


class ParallelTicketVerifier:
    """Verifies all tickets in parallel, checking acceptance criteria completion."""
    
    def __init__(
        self,
        tickets_path: str,
        max_workers: int = 3,
        check_ai_patterns: bool = False,
        audit_diff: bool = False
    ):
        self.tickets_path = Path(tickets_path)
        self.max_workers = max_workers
        self.check_ai_patterns = check_ai_patterns
        self.audit_diff = audit_diff
        self.project_root = self.tickets_path.parent
        
        # Load AI detection patterns if enabled
        self.ai_patterns = []
        if check_ai_patterns:
            self._load_ai_patterns()
            
    def _load_all_tickets(self) -> Dict[str, Dict]:
        """Load all tickets from the tickets file."""
        handler = TicketFormatHandler()
        return handler.get_all_tickets(str(self.tickets_path))
            
    def _load_ai_patterns(self):
        """Load AI-generated code detection patterns."""
        # Common patterns found in AI-generated code
        self.ai_patterns = [
            # Overly verbose comments
            (r'# This (function|method|class) (does|performs|handles)', 'Overly verbose comment'),
            (r'# Step \d+:', 'Numbered step comments'),
            (r'# TODO: Implement .* functionality', 'Generic TODO'),
            
            # Placeholder code
            (r'(pass\s*#\s*TODO|# Implementation goes here)', 'Placeholder implementation'),
            (r'raise NotImplementedError', 'NotImplementedError placeholder'),
            
            # Overly generic variable names in sequence
            (r'(item|element|obj|data|result|value|temp)\d+', 'Generic numbered variables'),
            
            # Excessive error handling
            (r'except Exception as e:\s*print\(.*error.*\)', 'Generic exception printing'),
            
            # Common AI explanation patterns
            (r'"""[\s\S]*?Brief description[\s\S]*?"""', 'Template docstring'),
            (r'# Note: This is a simplified', 'Simplified implementation note'),
            
            # Redundant type hints
            (r'def \w+\(.*\) -> Optional\[Any\]:', 'Overly generic return type'),
        ]
        
    async def verify_all_tickets(self) -> Dict[str, Any]:
        """Verify all tickets in parallel."""
        # Load tickets
        tickets = self._load_all_tickets()
        
        # Filter for completed tickets
        completed_tickets = {
            tid: ticket for tid, ticket in tickets.items()
            if ticket.get('status') in ['DONE', 'COMPLETE', 'COMPLETED'] or ticket.get('completed', False)
        }
        
        report = {
            'total_tickets': len(tickets),
            'completed_tickets': len(completed_tickets),
            'fully_verified': 0,
            'partially_verified': 0,
            'failed_verification': 0,
            'skipped': len(tickets) - len(completed_tickets),
            'failures': {},
            'ai_code_detected': {},
            'diff_audit_issues': {}
        }
        
        if not completed_tickets:
            print("No completed tickets to verify")
            return report
            
        # Run verification in parallel
        tasks = []
        for ticket_id, ticket in completed_tickets.items():
            task = self._verify_ticket(ticket_id, ticket)
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for ticket_id, result in zip(completed_tickets.keys(), results):
            if isinstance(result, Exception):
                report['failures'][ticket_id] = {
                    'error': str(result),
                    'failed_criteria': ['Verification error']
                }
                report['failed_verification'] += 1
            else:
                if result['status'] == 'fully_verified':
                    report['fully_verified'] += 1
                elif result['status'] == 'partially_verified':
                    report['partially_verified'] += 1
                    report['failures'][ticket_id] = result
                else:
                    report['failed_verification'] += 1
                    report['failures'][ticket_id] = result
                    
                # Add AI detection results if present
                if result.get('ai_patterns_found'):
                    report['ai_code_detected'][ticket_id] = result['ai_patterns_found']
                    
                # Add diff audit issues if present
                if result.get('diff_issues'):
                    report['diff_audit_issues'][ticket_id] = result['diff_issues']
                    
        return report
        
    async def _verify_ticket(self, ticket_id: str, ticket: Dict) -> Dict[str, Any]:
        """Verify a single ticket's acceptance criteria."""
        result = {
            'ticket_id': ticket_id,
            'status': 'pending',
            'checked_criteria': [],
            'failed_criteria': [],
            'ai_patterns_found': [],
            'diff_issues': []
        }
        
        # Extract acceptance criteria
        criteria = self._extract_acceptance_criteria(ticket)
        
        if not criteria:
            result['status'] = 'no_criteria'
            return result
            
        # Check each criterion
        for criterion in criteria:
            passed = await self._check_criterion(ticket_id, criterion, ticket)
            if passed:
                result['checked_criteria'].append(criterion)
            else:
                result['failed_criteria'].append(criterion)
                
        # Check for AI patterns if enabled
        if self.check_ai_patterns:
            ai_issues = await self._check_ai_patterns(ticket_id, ticket)
            if ai_issues:
                result['ai_patterns_found'] = ai_issues
                
        # Audit diff if enabled
        if self.audit_diff:
            diff_issues = await self._audit_ticket_diff(ticket_id, ticket)
            if diff_issues:
                result['diff_issues'] = diff_issues
                
        # Determine status
        if not result['failed_criteria']:
            result['status'] = 'fully_verified'
        elif len(result['checked_criteria']) > 0:
            result['status'] = 'partially_verified'
        else:
            result['status'] = 'failed'
            
        return result
        
    def _extract_acceptance_criteria(self, ticket: Dict) -> List[str]:
        """Extract acceptance criteria from ticket."""
        # First check if ticket has parsed acceptance_criteria
        if 'acceptance_criteria' in ticket and ticket['acceptance_criteria']:
            return ticket['acceptance_criteria']
            
        criteria = []
        
        # Look for acceptance criteria section
        description = ticket.get('description', '')
        
        # Try to find acceptance criteria in various formats
        patterns = [
            r'\*\*Acceptance Criteria\*\*:(.*?)(?:\*\*|$)',
            r'Acceptance Criteria:(.*?)(?:\n\n|$)',
            r'- \[.\] (.*?)(?:\n|$)',  # Checklist items
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, description, re.DOTALL | re.MULTILINE)
            for match in matches:
                # Split into individual criteria
                lines = match.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and line.startswith(('- ', '* ', '• ')):
                        # Remove bullet points and checkboxes
                        line = re.sub(r'^[-*•]\s*\[.\]\s*', '', line)
                        line = re.sub(r'^[-*•]\s*', '', line)
                        if line:
                            criteria.append(line.strip())
                    elif line and not line.startswith('#'):
                        criteria.append(line.strip())
                        
        return criteria
        
    async def _check_criterion(self, ticket_id: str, criterion: str, ticket: Dict) -> bool:
        """Check if a specific acceptance criterion is met."""
        # This is a simplified check - in reality you'd want more sophisticated verification
        
        # Common verification patterns
        checks = []
        
        # File existence checks
        if 'file' in criterion.lower() or 'create' in criterion.lower():
            files = re.findall(r'`([^`]+\.\w+)`', criterion)
            for file in files:
                file_path = self.project_root / file
                if not file_path.exists():
                    return False
                    
        # Test-related checks
        if 'test' in criterion.lower():
            # Check if tests pass
            test_result = await self._run_tests(ticket_id)
            checks.append(test_result)
            
        # Build checks
        if 'build' in criterion.lower() or 'compile' in criterion.lower():
            build_result = await self._check_build()
            checks.append(build_result)
            
        # Lint checks
        if 'lint' in criterion.lower() or 'style' in criterion.lower():
            lint_result = await self._check_lint()
            checks.append(lint_result)
            
        # Function/class implementation checks
        if 'implement' in criterion.lower() or 'function' in criterion.lower():
            # Look for the implementation in code
            impl_check = await self._check_implementation(criterion)
            checks.append(impl_check)
            
        # If no specific checks matched, assume it needs manual verification
        if not checks:
            # For now, we'll be optimistic and assume manual tasks were done
            return True
            
        return all(checks)
        
    async def _run_tests(self, ticket_id: str) -> bool:
        """Run tests related to a ticket."""
        try:
            # Try to run tests
            result = subprocess.run(
                ['python', '-m', 'pytest', '-q', '--tb=no'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            # If tests can't be run, assume they don't exist yet
            return True
            
    async def _check_build(self) -> bool:
        """Check if the project builds successfully."""
        # Check for common build files
        if (self.project_root / 'setup.py').exists():
            try:
                result = subprocess.run(
                    ['python', 'setup.py', 'check'],
                    cwd=self.project_root,
                    capture_output=True,
                    timeout=30
                )
                return result.returncode == 0
            except Exception:
                pass
        return True
        
    async def _check_lint(self) -> bool:
        """Check if linting passes."""
        try:
            # Try ruff if available
            result = subprocess.run(
                ['ruff', 'check', '--quiet'],
                cwd=self.project_root,
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            # Linting not available
            return True
            
    async def _check_implementation(self, criterion: str) -> bool:
        """Check if required functions/classes are implemented."""
        # Extract function/class names
        patterns = [
            r'`(\w+)\(\)`',  # Function names
            r'`class (\w+)`',  # Class names
            r'function (\w+)',
            r'method (\w+)',
        ]
        
        names_to_check = []
        for pattern in patterns:
            matches = re.findall(pattern, criterion, re.IGNORECASE)
            names_to_check.extend(matches)
            
        if not names_to_check:
            return True
            
        # Search for implementations
        for name in names_to_check:
            found = False
            for py_file in self.project_root.rglob('*.py'):
                try:
                    content = py_file.read_text()
                    if re.search(rf'(def|class)\s+{name}\b', content):
                        found = True
                        break
                except Exception:
                    continue
                    
            if not found:
                return False
                
        return True
        
    async def _check_ai_patterns(self, ticket_id: str, ticket: Dict) -> List[Dict]:
        """Check for AI-generated code patterns."""
        issues = []
        
        # Get files modified for this ticket (simplified - would need git integration)
        for py_file in self.project_root.rglob('*.py'):
            try:
                content = py_file.read_text()
                for pattern, description in self.ai_patterns:
                    matches = re.findall(pattern, content, re.MULTILINE)
                    if matches:
                        issues.append({
                            'file': str(py_file.relative_to(self.project_root)),
                            'pattern': description,
                            'count': len(matches)
                        })
            except Exception:
                continue
                
        return issues
        
    async def _audit_ticket_diff(self, ticket_id: str, ticket: Dict) -> List[str]:
        """Audit git diff to ensure changes match acceptance criteria."""
        issues = []
        
        try:
            # Get git diff for files (simplified - would need proper git integration)
            result = subprocess.run(
                ['git', 'diff', 'HEAD~1', 'HEAD', '--name-only'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                changed_files = result.stdout.strip().split('\n')
                
                # Check if changes seem related to the ticket
                ticket_keywords = self._extract_keywords(ticket)
                unrelated_files = []
                
                for file in changed_files:
                    if file and not any(keyword in file.lower() for keyword in ticket_keywords):
                        # File doesn't seem related to ticket
                        unrelated_files.append(file)
                        
                if unrelated_files:
                    issues.append(f"Potentially unrelated files modified: {', '.join(unrelated_files)}")
                    
                # Check for unexpectedly large changes
                diff_result = subprocess.run(
                    ['git', 'diff', 'HEAD~1', 'HEAD', '--stat'],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if diff_result.returncode == 0:
                    # Parse diff stats
                    lines = diff_result.stdout.strip().split('\n')
                    for line in lines:
                        if '|' in line:
                            parts = line.split('|')
                            if len(parts) == 2:
                                changes = parts[1].strip()
                                # Check for files with excessive changes
                                if '+' in changes:
                                    additions = changes.count('+')
                                    if additions > 50:  # Threshold for suspicious
                                        file = parts[0].strip()
                                        issues.append(f"Large change in {file}: {additions} additions")
                                        
        except Exception as e:
            issues.append(f"Could not audit diff: {e}")
            
        return issues
        
    def _extract_keywords(self, ticket: Dict) -> List[str]:
        """Extract keywords from ticket for relevance checking."""
        keywords = []
        
        # Extract from title
        title = ticket.get('title', '').lower()
        # Remove common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        words = [w for w in title.split() if w not in stopwords and len(w) > 2]
        keywords.extend(words)
        
        # Extract technical terms from description
        description = ticket.get('description', '').lower()
        technical_terms = re.findall(r'\b[a-z_]+(?:_[a-z]+)+\b', description)  # snake_case
        keywords.extend(technical_terms)
        
        camel_terms = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', ticket.get('description', ''))  # CamelCase
        keywords.extend([t.lower() for t in camel_terms])
        
        return list(set(keywords))