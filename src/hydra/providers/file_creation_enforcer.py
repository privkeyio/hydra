"""File creation enforcement for Claude Code execution."""

import re
from typing import Any, Dict, List


def extract_required_files(ticket: Dict[str, Any]) -> List[str]:
    """Extract all files that MUST be created from ticket acceptance criteria.

    Args:
        ticket: Parsed ticket dictionary

    Returns:
        List of file paths that must be created

    """
    required_files = []

    # Enhanced patterns that match more documentation requirements
    file_patterns = [
        r"[Cc]reate\s+(?:reusable\s+)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)(?:\s+utility|\s+file)?",
        r"[Aa]dd\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Ii]mplement\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Dd]ocument\s+(?:metrics\s+)?(?:in|to)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Ss]ave\s+(?:performance\s+)?(?:data\s+)?(?:to|in)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Ww]rite\s+(?:to|in)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s+(?:with|containing|that)",
        # More explicit patterns for common documentation files
        r"(?:in|to)\s+(test-results/[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)",
        r"(?:in|to)\s+(docs/[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)",
    ]

    # Check acceptance criteria
    for criteria in ticket.get('acceptance_criteria', []):
        for pattern in file_patterns:
            matches = re.findall(pattern, criteria, re.IGNORECASE)
            for match in matches:
                if match and not any(skip in match.lower() for skip in ['example', 'sample']):
                    # Clean up the path
                    file_path = match.strip()
                    if file_path not in required_files:
                        required_files.append(file_path)

    # Also check output files section
    for output_file in ticket.get('output_files', []):
        if isinstance(output_file, str) and '.' in output_file:
            # Extract just the file path
            file_path = output_file.split('(')[0].strip()
            if file_path not in required_files and not any(skip in file_path.lower() for skip in ['updated', 'modified']):
                required_files.append(file_path)

    return required_files


def build_documentation_emphasis(required_files: List[str]) -> str:
    """Build special emphasis for documentation/reporting files.

    Args:
        required_files: List of required files

    Returns:
        Extra prompt text for documentation files

    """
    doc_files = [f for f in required_files if 'test-results/' in f or '.md' in f or 'metrics.json' in f]
    if not doc_files:
        return ""

    prompt = "\n📊 DOCUMENTATION REQUIREMENTS:\n"
    prompt += "These files MUST be created with actual test results/metrics:\n"
    for doc_file in doc_files:
        if '30min-video-report.md' in doc_file:
            prompt += f"- {doc_file}: Document the ACTUAL test run with timings, segment counts, upload speeds\n"
        elif 'performance-metrics.json' in doc_file:
            prompt += f"- {doc_file}: Save ACTUAL performance data as JSON (memory usage, CPU, timing, etc.)\n"
        elif 'report.md' in doc_file:
            prompt += f"- {doc_file}: Create detailed report with actual test results\n"
        elif '.json' in doc_file:
            prompt += f"- {doc_file}: Save actual metrics/data in JSON format\n"
        else:
            prompt += f"- {doc_file}: Create with actual results/documentation\n"
    prompt += "\nThese are NOT optional - the ticket will FAIL without these files!\n"
    return prompt


def build_file_creation_prompt(ticket_id: str, required_files: List[str]) -> str:
    """Build an explicit file creation prompt for Claude.

    Args:
        ticket_id: Ticket identifier
        required_files: List of files that must be created

    Returns:
        Prompt text emphasizing file creation

    """
    if not required_files:
        return ""

    prompt = f"\n\n🚨🚨🚨 CRITICAL FILE CREATION REQUIREMENTS FOR TICKET {ticket_id} 🚨🚨🚨\n"
    prompt += "YOU MUST CREATE THE FOLLOWING FILES (DO NOT JUST MODIFY EXISTING FILES):\n\n"

    for i, file_path in enumerate(required_files, 1):
        # Suggest common locations if path doesn't include directory
        if '/' not in file_path:
            if file_path.endswith('.ts') or file_path.endswith('.js'):
                if 'hardware' in file_path or 'detector' in file_path:
                    prompt += f"{i}. CREATE NEW FILE: src/utils/{file_path} or src/core/{file_path}\n"
                elif 'exponential' in file_path or 'backoff' in file_path or 'rate' in file_path:
                    prompt += f"{i}. CREATE NEW FILE: src/utils/{file_path}\n"
                elif 'progress' in file_path or 'emitter' in file_path or 'event' in file_path:
                    prompt += f"{i}. CREATE NEW FILE: src/events/{file_path} or src/{file_path}\n"
                elif 'network' in file_path or 'monitor' in file_path:
                    prompt += f"{i}. CREATE NEW FILE: src/utils/{file_path} or src/core/{file_path}\n"
                else:
                    prompt += f"{i}. CREATE NEW FILE: src/{file_path} or src/core/{file_path}\n"
            elif file_path.endswith('.md'):
                if 'test-results' in file_path or 'report' in file_path:
                    prompt += f"{i}. CREATE NEW FILE: {file_path} (exactly as specified)\n"
                else:
                    prompt += f"{i}. CREATE NEW FILE: {file_path} or docs/{file_path}\n"
            elif file_path.endswith('.json'):
                if 'test-results' in file_path or 'metrics' in file_path:
                    prompt += f"{i}. CREATE NEW FILE: {file_path} (exactly as specified)\n"
                else:
                    prompt += f"{i}. CREATE NEW FILE: {file_path}\n"
            else:
                prompt += f"{i}. CREATE NEW FILE: {file_path}\n"
        else:
            prompt += f"{i}. CREATE NEW FILE: {file_path}\n"

    prompt += "\n⚠️ THESE ARE NOT OPTIONAL - YOU MUST CREATE ALL THESE FILES!\n"
    prompt += "⚠️ DO NOT JUST MODIFY EXISTING FILES - CREATE THE NEW FILES LISTED ABOVE!\n"
    prompt += "⚠️ USE THE 'Write' TOOL OR 'touch' COMMAND TO CREATE THESE FILES!\n"

    # Add documentation emphasis if needed
    doc_emphasis = build_documentation_emphasis(required_files)
    if doc_emphasis:
        prompt += doc_emphasis

    prompt += "\nAfter creating these files, implement the functionality as described in the acceptance criteria.\n"
    prompt += "🚨🚨🚨 END OF CRITICAL FILE CREATION REQUIREMENTS 🚨🚨🚨\n\n"

    return prompt


def enforce_file_creation(ticket: Dict[str, Any]) -> str:
    """Generate enforcement prompt for file creation.

    Args:
        ticket: Parsed ticket dictionary

    Returns:
        Enhanced prompt with explicit file creation instructions

    """
    required_files = extract_required_files(ticket)

    if not required_files:
        return ""

    ticket_id = ticket.get('number', 'Unknown')
    return build_file_creation_prompt(ticket_id, required_files)
