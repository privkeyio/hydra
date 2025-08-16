"""AI-generated code and comment detection for Hydra.

This module detects patterns commonly found in AI-generated code to ensure
all implementations are production-ready and not placeholders.
"""

import json
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Set, Tuple


class StrictnessLevel(Enum):
    """Strictness levels for AI detection."""

    LENIENT = "lenient"  # Only critical issues (NotImplementedError, etc.)
    MODERATE = "moderate"  # Critical + suspicious patterns (default)
    STRICT = "strict"  # All patterns including style issues


@dataclass
class DiffAnalysisReport:
    """Detailed report of changes in a diff."""

    files_modified: int
    lines_added: int
    lines_removed: int
    ai_patterns_found: int
    critical_issues: List[Dict]
    warnings: List[Dict]
    unrelated_changes: List[str]
    ticket_scope_violations: List[str]


class AIGeneratedCodeDetector:
    """Detects AI-generated code patterns in source files."""

    # Problematic comment patterns that indicate AI-generated or incomplete code
    PROBLEMATIC_COMMENT_PATTERNS = [
        # Overly verbose explanations of simple concepts
        (r'(?i)(this function|this method|this class|this code|the following)'
         r'\s+(is used to|is responsible for|handles|manages)\s+\w+ing',
         "Overly verbose explanation of simple concepts"),

        # Hedging language - expanded patterns
        (r'(?i)\b(for now|this is a simplified|in production you.d|perhaps|maybe|'
         r'temporarily|presumably|potentially|possibly)\b',
         "Hedging language suggesting incomplete or uncertain implementation"),

        # Meta-commentary about limitations
        (r'(?i)\b(in a real implementation|would be better|should be|could be|'
         r'ideally|normally|typically would)\b',
         "Meta-commentary explaining what code should do rather than what it does"),

        # Apologetic tone and explanatory justifications
        (r'(?i)\b(sorry|unfortunately|can.t|cannot|unable to|regrettably|sadly)\b',
         "Apologetic tone explaining limitations"),

        # Since/Because patterns explaining why code can't do something better
        (r'(?i)(since we can.t|because we can.t|since this|because this)'
         r'\s+.*\s+(we.ll|we will|we.re|we are)',
         "Explanatory justification for suboptimal implementation"),

        # Repetitive phrasing patterns
        (r'(?i)(note that|notice that|remember that|keep in mind|'
         r'be aware that|it.s worth noting)',
         "Repetitive explanatory phrasing common in AI-generated content"),

        # Template-like formulaic patterns
        (r'(?i)^(step \d+:|first,|second,|third,|finally,|next,|then,|after that)',
         "Template-like step-by-step commentary"),

        # Unnecessary context that belongs in documentation
        (r'(?i)(this is part of|this belongs to|this relates to|'
         r'in the context of|as part of the)',
         "Unnecessary context that should be in documentation"),

        # Placeholder indicators (keeping the important ones)
        (r'(?i)\b(todo|fixme|hack|stub|placeholder|mock implementation|dummy|'
         r'fake|sample|example code)\b',
         "Placeholder or incomplete implementation marker"),

        # Implementation excuses
        (r'(?i)\b(not implemented|not yet implemented|simplified version|'
         r'basic implementation|minimal implementation)\b',
         "Explicitly states implementation is incomplete"),

        # Future tense suggesting work not done
        (r'(?i)\b(will be implemented|to be implemented|needs implementation|'
         r'pending implementation)\b',
         "Future tense indicating work not completed"),
    ]

    # Problematic code patterns
    PROBLEMATIC_CODE_PATTERNS = [
        # Empty or stub implementations
        (r'def\s+\w+\([^)]*\):\s*\n\s*(pass|return\s+None|raise\s+NotImplementedError)',
         "Empty or stub function implementation"),

        # Hardcoded placeholder values
        (r'return\s+["\']placeholder["\']|return\s+["\']todo["\']|return\s+\[\]|return\s+\{\}',
         "Returns placeholder or empty value"),

        # Mock/fake implementations (but not in test files)
        (r'class\s+(Mock|Fake|Dummy|Stub|Sample|Example)\w+',
         "Mock or fake class implementation"),

        # Overly defensive error handling with verbose messages
        (r'\.expect\(["\'][A-Z][^"\']{50,}["\']',
         "Overly verbose error messages in expect() calls"),

        # Redundant variable naming patterns
        (r'\b(result_value|final_result|temp_variable|temp_value|output_result|return_value)\b',
         "Redundant or template-like variable names"),

        # Verbose function/variable names that are unnecessarily descriptive
        # Only flag names over 40 chars that contain redundant words
        (r'\b(?:get_|set_|check_|validate_|process_|handle_)?[a-z_]*(?:_data|_value|_result|_object|_instance|_method|_function|_parameter|_variable){2,}[a-z_]*\b',
         "Excessively verbose variable or function names with redundant suffixes"),

        # Console debugging left in (expanded)
        (r'console\.(log|debug|warn|error)|print\s*\(["\'](?:test|debug|here|check)',
         "Debug output left in code"),

        # Template variable names commonly used by AI
        (r'\b(data1|data2|item1|item2|var1|var2|param1|param2)\b',
         "Template-like numbered variable names"),
    ]

    def __init__(self, strictness: StrictnessLevel = StrictnessLevel.MODERATE):
        """Initialize the AI code detector.
        
        Args:
            strictness: Level of strictness for detection

        """
        self.strictness = strictness
        self.issues_found = []
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load AI detection configuration."""
        config_file = Path(".hydra") / "ai_detection.json"

        if config_file.exists():
            with open(config_file, 'r') as f:
                return json.load(f)

        # Default configuration
        return {
            "strictness": self.strictness.value,
            "blocking_on_critical": True,
            "max_warnings_before_block": 50,
            "ignore_paths": [
                "venv", ".venv", "node_modules", "build", "dist",
                "__pycache__", ".git", ".pytest_cache"
            ],
            "custom_patterns": [],
            "check_unrelated_changes": True,
            "scope_analysis": True
        }

    def _should_check_pattern(self, pattern_type: str) -> bool:
        """Determine if a pattern should be checked based on strictness."""
        if self.strictness == StrictnessLevel.LENIENT:
            # Only check critical patterns
            return pattern_type in ['NotImplementedError', 'Empty', 'stub']
        elif self.strictness == StrictnessLevel.MODERATE:
            # Check critical and suspicious patterns
            return pattern_type not in ['verbose', 'style']
        else:  # STRICT
            # Check all patterns
            return True

    def detect_in_file(self, file_path: Path) -> List[Dict[str, any]]:
        """Detect AI-generated patterns in a single file.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            List of issues found with details

        """
        issues = []

        if not file_path.exists():
            return issues

        # Skip test files for certain patterns
        is_test_file = 'test' in str(file_path).lower() or 'spec' in str(file_path).lower()

        try:
            content = file_path.read_text()
            lines = content.split('\n')

            # Check each line for problematic patterns
            for line_num, line in enumerate(lines, 1):
                # Check comment patterns
                for pattern, description in self.PROBLEMATIC_COMMENT_PATTERNS:
                    if re.search(pattern, line):
                        # Only flag if it's in a comment
                        if self._is_comment(line, file_path.suffix):
                            issues.append({
                                'file': str(file_path),
                                'line': line_num,
                                'type': 'comment',
                                'pattern': description,
                                'content': line.strip(),
                                'severity': 'warning'
                            })

                # Check code patterns
                for pattern, description in self.PROBLEMATIC_CODE_PATTERNS:
                    # Skip mock/fake class patterns in test files
                    if is_test_file and 'Mock or fake' in description:
                        continue

                    if re.search(pattern, line):
                        # Determine severity based on pattern
                        severity = 'warning'
                        if 'NotImplementedError' in line or 'raise NotImplementedError' in line:
                            severity = 'error'
                        elif 'stub' in description.lower() and ('pass' in line or 'return None' in line):
                            severity = 'error'

                        issues.append({
                            'file': str(file_path),
                            'line': line_num,
                            'type': 'code',
                            'pattern': description,
                            'content': line.strip(),
                            'severity': severity
                        })

            # Check for multi-line patterns
            issues.extend(self._check_multiline_patterns(content, str(file_path)))

        except Exception as e:
            print(f"Error checking file {file_path}: {e}")

        return issues

    def _is_comment(self, line: str, file_extension: str) -> bool:
        """Check if a line is a comment based on file type."""
        line = line.strip()

        comment_markers = {
            '.py': ['#'],
            '.js': ['//', '/*', '*'],
            '.ts': ['//', '/*', '*'],
            '.cpp': ['//', '/*', '*'],
            '.c': ['//', '/*', '*'],
            '.java': ['//', '/*', '*'],
            '.go': ['//', '/*', '*'],
            '.rs': ['//', '/*', '*'],
            '.rb': ['#'],
            '.sh': ['#'],
        }

        markers = comment_markers.get(file_extension, ['#', '//', '/*'])
        return any(line.startswith(marker) for marker in markers)

    def _check_multiline_patterns(self, content: str, file_path: str) -> List[Dict[str, any]]:
        """Check for multi-line problematic patterns."""
        issues = []

        # Check for empty function implementations (with pass)
        empty_func_pass = r'def\s+(\w+)\([^)]*\):\s*(?:\n\s*"""[^"]*"""\s*)?(?:\n\s*#[^\n]*)?\n\s*pass\s*$'
        for match in re.finditer(empty_func_pass, content, re.MULTILINE):
            func_name = match.group(1)
            # Find line number
            line_num = content[:match.start()].count('\n') + 1
            issues.append({
                'file': file_path,
                'line': line_num,
                'type': 'code',
                'pattern': f"Empty function implementation with pass: {func_name}",
                'content': match.group(0).replace('\n', ' ')[:100],
                'severity': 'error'  # Empty implementations are errors
            })

        # Check for empty function implementations (return None/[]/{}
        empty_func_return = r'def\s+(\w+)\([^)]*\):\s*\n\s*(return\s+(?:None|\[\]|\{\}))\s*$'
        for match in re.finditer(empty_func_return, content, re.MULTILINE):
            func_name = match.group(1)
            # Find line number
            line_num = content[:match.start()].count('\n') + 1
            issues.append({
                'file': file_path,
                'line': line_num,
                'type': 'code',
                'pattern': f"Empty function returning placeholder: {func_name}",
                'content': match.group(0).replace('\n', ' ')[:100],
                'severity': 'error'  # Empty implementations are errors
            })

        # Check for NotImplementedError anywhere in functions
        # First find all functions
        func_pattern = r'def\s+(\w+)\([^)]*\):[^\n]*'
        for func_match in re.finditer(func_pattern, content):
            func_name = func_match.group(1)
            func_start = func_match.end()

            # Find the next function or class (to limit search scope)
            next_def = re.search(r'\n(?:def|class)\s+', content[func_start:])
            if next_def:
                func_end = func_start + next_def.start()
            else:
                func_end = len(content)

            func_body = content[func_start:func_end]

            # Check for NotImplementedError in this function body
            if 'raise NotImplementedError' in func_body:
                line_num = content[:func_match.start()].count('\n') + 1
                issues.append({
                    'file': file_path,
                    'line': line_num,
                    'type': 'code',
                    'pattern': f"NotImplementedError in function: {func_name}",
                    'content': f"def {func_name}(...): raises NotImplementedError",
                    'severity': 'error'  # NotImplementedError is critical
                })

        return issues

    def detect_in_diff(self, diff_text: str) -> List[Dict[str, any]]:
        """Detect AI-generated patterns in a git diff.
        
        Args:
            diff_text: Git diff output
            
        Returns:
            List of issues found

        """
        issues = []
        current_file = None
        line_num = 0

        for line in diff_text.split('\n'):
            # Track current file
            if line.startswith('+++'):
                current_file = line[4:].strip()
                if current_file.startswith('b/'):
                    current_file = current_file[2:]
                line_num = 0

            # Track line numbers
            elif line.startswith('@@'):
                # Extract line number from @@ -old +new @@ format
                match = re.search(r'\+(\d+)', line)
                if match:
                    line_num = int(match.group(1)) - 1

            # Check added lines only
            elif line.startswith('+') and not line.startswith('+++'):
                line_num += 1
                content = line[1:]  # Remove the + prefix

                # Check for problematic patterns
                for pattern, description in self.PROBLEMATIC_COMMENT_PATTERNS:
                    if re.search(pattern, content):
                        issues.append({
                            'file': current_file or 'unknown',
                            'line': line_num,
                            'type': 'comment',
                            'pattern': description,
                            'content': content.strip()
                        })

                for pattern, description in self.PROBLEMATIC_CODE_PATTERNS:
                    if re.search(pattern, content):
                        issues.append({
                            'file': current_file or 'unknown',
                            'line': line_num,
                            'type': 'code',
                            'pattern': description,
                            'content': content.strip()
                        })

            # Track line numbers for context lines
            elif not line.startswith('-'):
                line_num += 1

        return issues

    def generate_report(self, issues: List[Dict[str, any]]) -> str:
        """Generate a human-readable report of issues found.
        
        Args:
            issues: List of issues from detection
            
        Returns:
            Formatted report string

        """
        if not issues:
            return "✅ No AI-generated code patterns detected"

        # Count severities
        errors = [i for i in issues if i.get('severity') == 'error']
        warnings = [i for i in issues if i.get('severity', 'warning') == 'warning']

        # Choose appropriate header based on severity
        if errors:
            header = "🚨 AI-Generated Code Patterns Detected (with errors)"
        else:
            header = "⚠️  AI-Generated Code Patterns Detected (warnings only)"

        report = [header, "=" * 50, ""]
        report.append(f"Summary: {len(errors)} errors, {len(warnings)} warnings")
        report.append("")

        # Group by file
        by_file = {}
        for issue in issues:
            file_path = issue['file']
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(issue)

        for file_path, file_issues in by_file.items():
            report.append(f"\n📄 {file_path}")
            report.append("-" * 40)

            # Sort by severity (errors first) then line number
            file_issues.sort(key=lambda x: (0 if x.get('severity') == 'error' else 1, x['line']))

            for issue in file_issues:
                severity = issue.get('severity', 'warning')
                if severity == 'error':
                    icon = "❌"
                elif issue['type'] == 'comment':
                    icon = "💬"
                else:
                    icon = "⚠️"

                report.append(f"{icon} Line {issue['line']}: {issue['pattern']}")
                report.append(f"   Severity: {severity.upper()}")
                report.append(f"   Content: {issue['content'][:80]}")

        report.append("")
        report.append(f"Total issues: {len(issues)} ({len(errors)} errors, {len(warnings)} warnings)")
        report.append("")

        if errors:
            report.append("❌ Critical issues found - these MUST be fixed:")
            report.append("   - NotImplementedError or empty stub implementations")
            report.append("")

        report.append("⚠️  Warning patterns suggest AI-generated or incomplete code.")
        report.append("Review these patterns and ensure code is production-ready.")
        report.append("")
        report.append("Note: This check should NOT block ticket completion,")
        report.append("but serves as a quality flag for human review.")

        return "\n".join(report)


    def analyze_diff_comprehensively(self, ticket_id: str, ticket_description: str = "") -> DiffAnalysisReport:
        """Perform comprehensive analysis of git diff for a ticket.
        
        Args:
            ticket_id: ID of the ticket being verified
            ticket_description: Description of what the ticket should do
            
        Returns:
            Detailed analysis report

        """
        try:
            # Get git diff
            git_diff = subprocess.run(
                ["git", "diff", "HEAD"],
                capture_output=True,
                text=True,
                check=False
            )

            if git_diff.returncode != 0:
                return DiffAnalysisReport(
                    files_modified=0,
                    lines_added=0,
                    lines_removed=0,
                    ai_patterns_found=0,
                    critical_issues=[],
                    warnings=[],
                    unrelated_changes=[],
                    ticket_scope_violations=[]
                )

            diff_text = git_diff.stdout

            # Parse diff statistics
            files_modified = len(re.findall(r'^diff --git', diff_text, re.MULTILINE))
            lines_added = len(re.findall(r'^\+[^+]', diff_text, re.MULTILINE))
            lines_removed = len(re.findall(r'^-[^-]', diff_text, re.MULTILINE))

            # Detect AI patterns
            issues = self.detect_in_diff(diff_text)
            critical_issues = [i for i in issues if i.get('severity') == 'error']
            warnings = [i for i in issues if i.get('severity', 'warning') == 'warning']

            # Check for unrelated changes
            unrelated_changes = []
            ticket_scope_violations = []

            if self.config.get('check_unrelated_changes'):
                unrelated_changes = self._detect_unrelated_changes(
                    diff_text, ticket_id, ticket_description
                )

            if self.config.get('scope_analysis'):
                ticket_scope_violations = self._detect_scope_violations(
                    diff_text, ticket_description
                )

            return DiffAnalysisReport(
                files_modified=files_modified,
                lines_added=lines_added,
                lines_removed=lines_removed,
                ai_patterns_found=len(issues),
                critical_issues=critical_issues,
                warnings=warnings,
                unrelated_changes=unrelated_changes,
                ticket_scope_violations=ticket_scope_violations
            )

        except Exception:
            # Return empty report on error
            return DiffAnalysisReport(
                files_modified=0,
                lines_added=0,
                lines_removed=0,
                ai_patterns_found=0,
                critical_issues=[],
                warnings=[],
                unrelated_changes=[],
                ticket_scope_violations=[]
            )

    def _detect_unrelated_changes(self, diff_text: str, ticket_id: str,
                                  ticket_description: str) -> List[str]:
        """Detect changes that seem unrelated to the ticket.
        
        Args:
            diff_text: Git diff output
            ticket_id: Ticket identifier
            ticket_description: What the ticket should do
            
        Returns:
            List of potentially unrelated changes

        """
        unrelated = []

        # Parse files from diff
        modified_files = re.findall(r'^\+\+\+ b/(.+)$', diff_text, re.MULTILINE)

        # Check for changes in unrelated directories
        ticket_keywords = self._extract_keywords(ticket_description.lower())

        for file_path in modified_files:
            file_lower = file_path.lower()

            # Check if file seems unrelated to ticket keywords
            seems_related = any(keyword in file_lower for keyword in ticket_keywords)

            # Special cases that are often unrelated
            if not seems_related:
                if any(unrelated_pattern in file_lower for unrelated_pattern in [
                    'test', 'spec', 'readme', 'doc', 'config', 'package-lock',
                    'yarn.lock', '.gitignore', 'changelog'
                ]):
                    # These might be related, check more carefully
                    if 'test' in ticket_keywords or 'doc' in ticket_keywords:
                        seems_related = True

            if not seems_related and file_path not in ['.hydra', 'tickets.md']:
                unrelated.append(f"File {file_path} seems unrelated to ticket scope")

        # Check for large number of changes
        lines_changed = len(re.findall(r'^[+-][^+-]', diff_text, re.MULTILINE))
        if lines_changed > 500:
            unrelated.append(
                f"Large number of changes ({lines_changed} lines) - "
                "verify all are necessary"
            )

        # Check for changes to critical files
        critical_files = ['setup.py', 'pyproject.toml', 'requirements.txt',
                         'package.json', 'Cargo.toml', 'go.mod']
        for critical_file in critical_files:
            if critical_file in modified_files:
                if critical_file.split('.')[0] not in ticket_description.lower():
                    unrelated.append(
                        f"Critical file {critical_file} modified - "
                        "ensure this is intentional"
                    )

        return unrelated

    def _detect_scope_violations(self, diff_text: str, ticket_description: str) -> List[str]:
        """Detect changes that violate the ticket's scope.
        
        Args:
            diff_text: Git diff output
            ticket_description: What the ticket should do
            
        Returns:
            List of scope violations

        """
        violations = []

        # Extract what the ticket should NOT do based on description
        negative_patterns = [
            (r'without\s+(\w+)', "Changes found for explicitly excluded: "),
            (r'don\'t\s+(\w+)', "Changes found for 'don't': "),
            (r'no\s+(\w+)\s+changes', "Changes found despite 'no changes': "),
            (r'keep\s+(\w+)\s+as\s+is', "Modified despite 'keep as is': ")
        ]

        for pattern, message in negative_patterns:
            matches = re.findall(pattern, ticket_description.lower())
            for match in matches:
                if match in diff_text.lower():
                    violations.append(f"{message}{match}")

        return violations

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract relevant keywords from text.
        
        Args:
            text: Text to extract keywords from
            
        Returns:
            Set of keywords

        """
        # Remove common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
                    'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was',
                    'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
                    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
                    'might', 'must', 'can', 'shall', 'need', 'add', 'update',
                    'modify', 'change', 'implement', 'fix', 'create', 'remove'}

        # Split into words and filter
        words = re.findall(r'\b[a-z]+\b', text)
        keywords = {word for word in words if len(word) > 3 and word not in stopwords}

        # Add specific technical terms found in text
        tech_terms = re.findall(r'\b(?:api|cli|gui|sdk|ai|ml|db|sql|auth|oauth|jwt|rest|graphql|grpc)\b', text)
        keywords.update(tech_terms)

        return keywords

    def generate_comprehensive_report(self, analysis: DiffAnalysisReport,
                                     ticket_id: str) -> str:
        """Generate a comprehensive report from diff analysis.
        
        Args:
            analysis: Analysis report
            ticket_id: Ticket identifier
            
        Returns:
            Formatted report string

        """
        lines = [
            f"🔍 AI Detection Report for Ticket {ticket_id}",
            "=" * 60,
            "",
            "📊 CHANGE STATISTICS:",
            f"  Files Modified: {analysis.files_modified}",
            f"  Lines Added: {analysis.lines_added}",
            f"  Lines Removed: {analysis.lines_removed}",
            "",
            "🤖 AI PATTERN DETECTION:",
            f"  Total Patterns Found: {analysis.ai_patterns_found}",
            f"  Critical Issues: {len(analysis.critical_issues)}",
            f"  Warnings: {len(analysis.warnings)}",
            ""
        ]

        if analysis.critical_issues:
            lines.append("❌ CRITICAL ISSUES (Must Fix):")
            for issue in analysis.critical_issues[:5]:
                lines.append(
                    f"  • {issue['file']}:{issue['line']} - "
                    f"{issue['pattern']}"
                )
            if len(analysis.critical_issues) > 5:
                lines.append(f"  ... and {len(analysis.critical_issues) - 5} more")
            lines.append("")

        if analysis.warnings:
            lines.append("⚠️  WARNINGS (Review Recommended):")
            for warning in analysis.warnings[:5]:
                lines.append(
                    f"  • {warning['file']}:{warning['line']} - "
                    f"{warning['pattern']}"
                )
            if len(analysis.warnings) > 5:
                lines.append(f"  ... and {len(analysis.warnings) - 5} more")
            lines.append("")

        if analysis.unrelated_changes:
            lines.append("🔄 POTENTIALLY UNRELATED CHANGES:")
            for change in analysis.unrelated_changes[:5]:
                lines.append(f"  • {change}")
            lines.append("")

        if analysis.ticket_scope_violations:
            lines.append("⛔ SCOPE VIOLATIONS:")
            for violation in analysis.ticket_scope_violations:
                lines.append(f"  • {violation}")
            lines.append("")

        # Determine blocking status
        should_block = False
        if self.config.get('blocking_on_critical') and analysis.critical_issues:
            should_block = True
            lines.append("🚫 BLOCKING: Critical AI patterns detected")
        elif len(analysis.warnings) > self.config.get('max_warnings_before_block', 50):
            should_block = True
            max_warnings = self.config.get('max_warnings_before_block', 50)
            lines.append(
                f"🚫 BLOCKING: Too many warnings "
                f"({len(analysis.warnings)} > {max_warnings})"
            )
        elif analysis.ticket_scope_violations:
            lines.append("⚠️  WARNING: Scope violations detected (non-blocking)")
        else:
            lines.append("✅ PASSED: No blocking issues found")

        lines.append("")
        lines.append(f"Strictness Level: {self.strictness.value.upper()}")

        return "\n".join(lines)


def check_file_for_ai_patterns(
    file_path: str,
    strictness: StrictnessLevel = StrictnessLevel.MODERATE
) -> Tuple[bool, List[Dict[str, any]]]:
    """Check a file for AI-generated code patterns.
    
    Args:
        file_path: Path to file to check
        strictness: Level of strictness for detection
        
    Returns:
        Tuple of (has_issues, list_of_issues)

    """
    detector = AIGeneratedCodeDetector(strictness)
    issues = detector.detect_in_file(Path(file_path))
    return len(issues) > 0, issues


def check_diff_for_ai_patterns(
    diff_text: str,
    strictness: StrictnessLevel = StrictnessLevel.MODERATE
) -> Tuple[bool, List[Dict[str, any]]]:
    """Check a git diff for AI-generated code patterns.
    
    Args:
        diff_text: Git diff output
        strictness: Level of strictness for detection
        
    Returns:
        Tuple of (has_issues, list_of_issues)

    """
    detector = AIGeneratedCodeDetector(strictness)
    issues = detector.detect_in_diff(diff_text)
    return len(issues) > 0, issues
