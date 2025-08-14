"""AI-generated code and comment detection for Hydra.

This module detects patterns commonly found in AI-generated code to ensure
all implementations are production-ready and not placeholders.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple


class AIGeneratedCodeDetector:
    """Detects AI-generated code patterns in source files."""

    # Problematic comment patterns that indicate AI-generated or incomplete code
    PROBLEMATIC_COMMENT_PATTERNS = [
        # Overly verbose explanations of simple concepts
        (r'(?i)(this function|this method|this class|this code|the following)\s+(is used to|is responsible for|handles|manages)\s+\w+ing',
         "Overly verbose explanation of simple concepts"),

        # Hedging language - expanded patterns
        (r'(?i)\b(for now|this is a simplified|in production you.d|perhaps|maybe|temporarily|presumably|potentially|possibly)\b',
         "Hedging language suggesting incomplete or uncertain implementation"),

        # Meta-commentary about limitations
        (r'(?i)\b(in a real implementation|would be better|should be|could be|ideally|normally|typically would)\b',
         "Meta-commentary explaining what code should do rather than what it does"),

        # Apologetic tone and explanatory justifications
        (r'(?i)\b(sorry|unfortunately|can.t|cannot|unable to|regrettably|sadly)\b',
         "Apologetic tone explaining limitations"),

        # Since/Because patterns explaining why code can't do something better
        (r'(?i)(since we can.t|because we can.t|since this|because this)\s+.*\s+(we.ll|we will|we.re|we are)',
         "Explanatory justification for suboptimal implementation"),

        # Repetitive phrasing patterns
        (r'(?i)(note that|notice that|remember that|keep in mind|be aware that|it.s worth noting)',
         "Repetitive explanatory phrasing common in AI-generated content"),

        # Template-like formulaic patterns
        (r'(?i)^(step \d+:|first,|second,|third,|finally,|next,|then,|after that)',
         "Template-like step-by-step commentary"),

        # Unnecessary context that belongs in documentation
        (r'(?i)(this is part of|this belongs to|this relates to|in the context of|as part of the)',
         "Unnecessary context that should be in documentation"),

        # Placeholder indicators (keeping the important ones)
        (r'(?i)\b(todo|fixme|hack|stub|placeholder|mock implementation|dummy|fake|sample|example code)\b',
         "Placeholder or incomplete implementation marker"),

        # Implementation excuses
        (r'(?i)\b(not implemented|not yet implemented|simplified version|basic implementation|minimal implementation)\b',
         "Explicitly states implementation is incomplete"),

        # Future tense suggesting work not done
        (r'(?i)\b(will be implemented|to be implemented|needs implementation|pending implementation)\b',
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
        (r'\b[a-z_]{30,}\b',
         "Excessively verbose variable or function names"),

        # Console debugging left in (expanded)
        (r'console\.(log|debug|warn|error)|print\s*\(["\'](?:test|debug|here|check)',
         "Debug output left in code"),

        # Template variable names commonly used by AI
        (r'\b(data1|data2|item1|item2|var1|var2|param1|param2)\b',
         "Template-like numbered variable names"),
    ]

    def __init__(self):
        """Initialize the AI code detector."""
        self.issues_found = []

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


def check_file_for_ai_patterns(file_path: str) -> Tuple[bool, List[Dict[str, any]]]:
    """Check a file for AI-generated code patterns.
    
    Args:
        file_path: Path to file to check
        
    Returns:
        Tuple of (has_issues, list_of_issues)

    """
    detector = AIGeneratedCodeDetector()
    issues = detector.detect_in_file(Path(file_path))
    return len(issues) > 0, issues


def check_diff_for_ai_patterns(diff_text: str) -> Tuple[bool, List[Dict[str, any]]]:
    """Check a git diff for AI-generated code patterns.
    
    Args:
        diff_text: Git diff output
        
    Returns:
        Tuple of (has_issues, list_of_issues)

    """
    detector = AIGeneratedCodeDetector()
    issues = detector.detect_in_diff(diff_text)
    return len(issues) > 0, issues
