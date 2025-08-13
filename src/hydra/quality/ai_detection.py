"""AI-generated code and comment detection for Hydra.

This module detects patterns commonly found in AI-generated code to ensure
all implementations are production-ready and not placeholders.
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple


class AIGeneratedCodeDetector:
    """Detects AI-generated code patterns in source files."""
    
    # Problematic comment patterns that indicate AI-generated or incomplete code
    PROBLEMATIC_COMMENT_PATTERNS = [
        # Hedging language
        (r'(?i)\b(for now|this is a simplified|in production you.d|perhaps|maybe|temporarily)\b',
         "Hedging language suggesting incomplete implementation"),
        
        # Meta-commentary about limitations
        (r'(?i)\b(in a real implementation|would be|should be|could be)\b',
         "Meta-commentary about what the code should do instead of doing it"),
        
        # Apologetic tone
        (r'(?i)\b(sorry|unfortunately|can.t|cannot|unable to)\b',
         "Apologetic tone explaining limitations"),
        
        # Placeholder indicators
        (r'(?i)\b(todo|fixme|hack|stub|placeholder|mock|dummy|fake|sample|example)\b',
         "Placeholder or incomplete implementation marker"),
        
        # Implementation excuses
        (r'(?i)\b(not implemented|not yet implemented|simplified version|basic implementation)\b',
         "Explicitly states implementation is incomplete"),
        
        # Future tense suggesting work not done
        (r'(?i)\b(will be implemented|to be implemented|needs implementation)\b',
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
        
        # Mock/fake implementations
        (r'class\s+(Mock|Fake|Dummy|Stub)\w+',
         "Mock or fake class implementation"),
        
        # Console debugging left in
        (r'console\.(log|debug|warn|error)\s*\(["\']test|print\s*\(["\']test',
         "Debug output left in code"),
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
                                'content': line.strip()
                            })
                
                # Check code patterns
                for pattern, description in self.PROBLEMATIC_CODE_PATTERNS:
                    if re.search(pattern, line):
                        issues.append({
                            'file': str(file_path),
                            'line': line_num,
                            'type': 'code',
                            'pattern': description,
                            'content': line.strip()
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
        
        # Check for empty function implementations
        empty_func_pattern = r'def\s+(\w+)\([^)]*\):\s*\n\s*(pass|return\s+None|return\s+\[\]|return\s+\{\})\s*$'
        for match in re.finditer(empty_func_pattern, content, re.MULTILINE):
            func_name = match.group(1)
            # Find line number
            line_num = content[:match.start()].count('\n') + 1
            issues.append({
                'file': file_path,
                'line': line_num,
                'type': 'code',
                'pattern': f"Empty function implementation: {func_name}",
                'content': match.group(0).replace('\n', ' ')[:100]
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
        
        report = ["❌ AI-Generated Code Patterns Detected", "=" * 50, ""]
        
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
            
            for issue in file_issues:
                icon = "💬" if issue['type'] == 'comment' else "🔧"
                report.append(f"{icon} Line {issue['line']}: {issue['pattern']}")
                report.append(f"   Content: {issue['content'][:80]}")
        
        report.append("")
        report.append(f"Total issues: {len(issues)}")
        report.append("")
        report.append("⚠️  These patterns suggest incomplete or placeholder implementations.")
        report.append("Please ensure all code is production-ready before marking tickets complete.")
        
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