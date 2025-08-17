"""Acceptance criteria validation for ticket execution."""

import os
import re
from typing import Dict, List, Tuple


def extract_required_files_from_criteria(acceptance_criteria: List[str]) -> List[str]:
    """Extract file names that should be created from acceptance criteria.

    Args:
        acceptance_criteria: List of acceptance criteria strings

    Returns:
        List of file paths that should be created

    """
    required_files = []

    # Patterns to detect file creation requirements
    file_patterns = [
        r"[Cc]reate\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Aa]dd\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Ii]mplement\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Dd]ocument\s+in\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Ss]ave\s+(?:to|in)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Ww]rite\s+to\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Gg]enerate\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        r"[Pp]roduce\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)",
        # Special patterns for common file types
        r"([a-zA-Z0-9_\-]+\.ts)\s+(?:file|utility|module|component)",
        r"([a-zA-Z0-9_\-]+\.js)\s+(?:file|utility|module|component)",
        r"([a-zA-Z0-9_\-]+\.py)\s+(?:file|utility|module|script)",
        r"([a-zA-Z0-9_\-./]+\.md)\s+(?:file|document|documentation)",
        r"([a-zA-Z0-9_\-./]+\.json)\s+(?:file|data|config)",
    ]

    for criteria in acceptance_criteria:
        for pattern in file_patterns:
            matches = re.findall(pattern, criteria, re.IGNORECASE)
            for match in matches:
                # Clean up the file path
                file_path = match.strip()
                # Skip if it's a generic pattern
                if not any(
                    skip in file_path.lower()
                    for skip in ["example", "sample", "template"]
                ):
                    required_files.append(file_path)

    # Remove duplicates while preserving order
    seen = set()
    unique_files = []
    for f in required_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    return unique_files


def validate_files_created(
    project_dir: str, required_files: List[str], check_common_locations: bool = True
) -> Tuple[List[str], List[str]]:
    """Validate that required files were created.

    Args:
        project_dir: Project directory to check
        required_files: List of files that should exist
        check_common_locations: Whether to check common locations for files

    Returns:
        Tuple of (found_files, missing_files)

    """
    found_files = []
    missing_files = []

    # Common locations where files might be created
    common_prefixes = [
        "",
        "src/",
        "src/core/",
        "src/utils/",
        "src/lib/",
        "lib/",
        "utils/",
    ]

    for file_path in required_files:
        file_found = False

        # First check the exact path
        full_path = os.path.join(project_dir, file_path)
        if os.path.exists(full_path):
            found_files.append(file_path)
            file_found = True
        elif check_common_locations:
            # Try common locations
            base_name = os.path.basename(file_path)
            for prefix in common_prefixes:
                test_path = os.path.join(project_dir, prefix + base_name)
                if os.path.exists(test_path):
                    found_files.append(prefix + base_name)
                    file_found = True
                    break

        if not file_found:
            missing_files.append(file_path)

    return found_files, missing_files


def validate_ticket_completion(
    project_dir: str, ticket: Dict, verbose: bool = True
) -> Tuple[bool, str]:
    """Validate that a ticket's acceptance criteria were met.

    Args:
        project_dir: Project directory
        ticket: Parsed ticket dictionary
        verbose: Whether to print validation details

    Returns:
        Tuple of (success, message)

    """
    # Extract required files from acceptance criteria
    required_files = extract_required_files_from_criteria(
        ticket.get("acceptance_criteria", [])
    )

    if verbose and required_files:
        print(f"\n📋 Checking for {len(required_files)} required files:")
        for f in required_files:
            print(f"   - {f}")

    # Validate files were created
    found_files, missing_files = validate_files_created(
        project_dir, required_files, check_common_locations=True
    )

    if missing_files:
        if verbose:
            print(f"\n❌ Missing {len(missing_files)} required files:")
            for f in missing_files:
                print(f"   ❌ {f}")

        message = (
            f"Missing {len(missing_files)} required files: {', '.join(missing_files)}"
        )
        return False, message

    if verbose and found_files:
        print(f"\n✅ Found all {len(found_files)} required files:")
        for f in found_files:
            print(f"   ✅ {f}")

    return True, "All required files created"


def pre_execution_check(ticket: Dict) -> List[str]:
    """Pre-execution check to identify files that need to be created.

    Args:
        ticket: Parsed ticket dictionary

    Returns:
        List of warnings/instructions for file creation

    """
    warnings = []

    # Extract required files
    required_files = extract_required_files_from_criteria(
        ticket.get("acceptance_criteria", [])
    )

    if required_files:
        warnings.append(
            f"⚠️  This ticket requires creating {len(required_files)} new files:"
        )
        for f in required_files:
            warnings.append(f"   📄 {f}")
        warnings.append("   Make sure Claude creates ALL these files!")

    return warnings
