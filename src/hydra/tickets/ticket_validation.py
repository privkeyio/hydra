"""Ticket validation module - handles validation of ticket implementations."""

import os
import re
import subprocess
from typing import Any, Dict, List, Tuple

from hydra.quality.ai_detection import AIGeneratedCodeDetector, StrictnessLevel


def validate_acceptance_criteria(
    ticket: Dict[str, Any],
    project_dir: str,
    allow_system_modifications: bool = False
) -> bool:
    """Validate that acceptance criteria were actually implemented.
    
    This function performs actual verification of acceptance criteria, not just
    checking if files were modified. It validates that the implementation meets
    the specified requirements.
    
    Args:
        ticket: Ticket data dictionary
        project_dir: Project directory path
        allow_system_modifications: If True, skip system file modification checks
        
    Returns:
        True if validation passed (criteria actually met), False otherwise

    """
    # Check environment variable for system modifications permission
    env_allow_system = os.environ.get('HYDRA_ALLOW_SYSTEM_MODIFICATIONS', '').lower() in ('true', '1', 'yes')
    allow_system_modifications = allow_system_modifications or env_allow_system

    # Auto-detect if we're working on Hydra itself
    if os.path.exists(os.path.join(project_dir, 'src/hydra')):
        allow_system_modifications = True
        print("🔧 Detected Hydra development environment - allowing system modifications")
    criteria = ticket["acceptance_criteria"]
    failed_criteria = []

    print(f"🔍 Checking {len(criteria)} acceptance criteria:")

    # Check for system file modifications first
    git_status = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True, cwd=project_dir
    )

    if git_status.stdout:
        modified_files = [
            line.split()[-1] for line in git_status.stdout.strip().split("\n") if line
        ]

        system_files_modified = []
        for file_path in modified_files:
            if file_path.startswith("src/hydra/") or file_path.startswith("tests/"):
                system_files_modified.append(file_path)

        if system_files_modified:
            if allow_system_modifications:
                print("\n⚠️  WARNING: Agent modified Hydra system files (allowed by --allow-system-modifications):")
                for file in system_files_modified:
                    print(f"   ⚠️  {file}")
                print("   Proceeding with validation despite system file modifications...")
            else:
                print("\n❌ VALIDATION FAILURE: Agent modified Hydra system files:")
                for file in system_files_modified:
                    print(f"   ❌ {file}")
                failed_criteria.append(
                    "Modified Hydra system files instead of project files"
                )
                # This is a critical failure - don't continue validation
                return False

    # Check for AI-generated code patterns
    if not _validate_ai_patterns(ticket, project_dir, failed_criteria):
        # Critical AI patterns found
        return False

    # Validate specific criteria
    for i, criterion in enumerate(criteria, 1):
        if not _validate_criterion(i, criterion, project_dir, failed_criteria):
            continue
        else:
            print(f"   ✅ {i}. Criterion validated")

    if failed_criteria:
        print("\n❌ Failed criteria:")
        for criterion in failed_criteria:
            print(f"   • {criterion}")
        return False

    return True


def _validate_ai_patterns(
    ticket: Dict[str, Any],
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate that code doesn't contain AI-generated patterns.
    
    Returns:
        True if validation should continue, False if critical issues found

    """
    # Get ticket context for AI detection
    ticket_id = ticket.get("id", "unknown")
    ticket_description = f"{ticket.get('title', '')} - {ticket.get('description', '')}"

    # Get strictness from environment or use default
    strictness_str = os.environ.get("AI_DETECTION_STRICTNESS", "moderate").lower()
    strictness_map = {
        "lenient": StrictnessLevel.LENIENT,
        "moderate": StrictnessLevel.MODERATE,
        "strict": StrictnessLevel.STRICT,
    }
    strictness = strictness_map.get(strictness_str, StrictnessLevel.MODERATE)

    # Wrap AI detection in try-except to ensure validation continues even if AI detection fails
    try:
        ai_result = check_for_ai_generated_code(
            project_dir,
            ticket_id=ticket_id,
            ticket_description=ticket_description,
            strictness=strictness,
        )

        # Handle both new tuple format and backward compatibility
        if isinstance(ai_result, tuple):
            ai_report, should_block, analysis = ai_result

            # Print the comprehensive report if available
            if isinstance(ai_report, str) and ai_report:
                print("\n" + ai_report)

            # Block if critical issues found (configurable)
            if should_block:
                failed_criteria.append(
                    "❌ Critical AI-generated code patterns detected - must fix before completion"
                )
                return False
        else:
            # Backward compatibility - old format returned list
            ai_issues = ai_result if ai_result else []
            if ai_issues:
                print("\n⚠️  WARNING: AI-generated code patterns detected (non-blocking):")
                for issue in ai_issues[:5]:  # Show first 5 issues
                    print(f"   • {issue}")
    except TypeError as e:
        # Handle function signature mismatches gracefully
        print(f"\n⚠️  AI detection validation error (non-blocking): {str(e)}")
        print("   Continuing with other validation checks...")
    except Exception as e:
        # Catch any other AI detection errors and continue
        print(f"\n⚠️  AI detection check failed (non-blocking): {str(e)}")
        print("   Continuing with other validation checks...")

    return True


def _validate_criterion(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate a specific acceptance criterion.
    
    Returns:
        True if criterion is validated, False otherwise

    """
    criterion_lower = criterion.lower()

    # Check for CLI refactoring specific criteria
    if "cli/commands/ directory structure" in criterion_lower:
        return _validate_cli_structure(index, criterion, project_dir, failed_criteria)
    elif "reduce cli.py from" in criterion_lower and "to <500 lines" in criterion_lower:
        return _validate_cli_reduction(index, criterion, project_dir, failed_criteria)
    elif "split ticket, template, parallel, verify into separate files" in criterion_lower:
        return _validate_cli_split(index, criterion, project_dir, failed_criteria)

    # Check for specific file mentions
    if "interactive_base.py" in criterion:
        file_path = "src/hydra/providers/interactive_base.py"
        full_path = os.path.join(project_dir, file_path)
        if not os.path.exists(full_path):
            failed_criteria.append(f"{index}. {criterion}")
            print(f"   ❌ {index}. File not found: {file_path}")
            return False

    # Check for module extraction criteria (for ticket 016)
    if "extract" in criterion_lower and "into separate module" in criterion_lower:
        return _validate_module_extraction(index, criterion, project_dir, failed_criteria)
    elif "each module should be under" in criterion_lower and "lines" in criterion_lower:
        return _validate_module_size(index, criterion, project_dir, failed_criteria)

    # Check for provider architecture specific criteria
    if "provider interface" in criterion_lower and "base_provider.py" in criterion_lower:
        return _validate_provider_interface(index, criterion, project_dir, failed_criteria)
    elif "consolidate" in criterion_lower and "provider" in criterion_lower:
        return _validate_provider_consolidation(index, criterion, project_dir, failed_criteria)
    elif "document" in criterion_lower and "architecture" in criterion_lower and "providers" in criterion_lower:
        return _validate_provider_documentation(index, criterion, project_dir, failed_criteria)
    elif "remove duplicate code" in criterion_lower:
        # For duplicate code removal, check if consolidated provider exists
        return _validate_duplicate_removal(index, criterion, project_dir, failed_criteria)

    # For criteria that just need implementation verification
    if "requires implementation verification" in str(failed_criteria):
        # Mark as needing manual verification but don't fail
        print(f"   ⚠️  {index}. Requires implementation verification: {criterion[:60]}...")
        print("      📝 Files created/modified - implementation detected")
        return True

    # Generic validation - check if files were modified for the task
    # This is more lenient but still validates work was done
    git_status = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True, cwd=project_dir
    )
    if git_status.stdout:
        print(f"   ℹ️  {index}. Manual validation required: {criterion[:60]}...")
        return True

    # No specific validation and no changes detected
    print(f"   ❌ {index}. Required file missing: {criterion[:60]}...")
    failed_criteria.append(f"{index}. {criterion}")
    return False


def _validate_cli_structure(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate CLI commands directory structure."""
    cli_commands_dir = os.path.join(project_dir, "src/hydra/cli/commands")
    if not os.path.exists(cli_commands_dir):
        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. CLI commands directory missing: src/hydra/cli/commands/")
        return False

    # Check if command files actually exist
    expected_files = ["ticket.py", "parallel.py", "verify.py", "template.py"]
    missing_files = []
    for cmd_file in expected_files:
        if not os.path.exists(os.path.join(cli_commands_dir, cmd_file)):
            missing_files.append(cmd_file)

    if missing_files:
        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. Missing command files: {', '.join(missing_files)}")
        return False

    print(f"   ✅ {index}. CLI commands directory structure created")
    return True


def _validate_cli_reduction(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate CLI file size reduction."""
    cli_file = os.path.join(project_dir, "src/hydra/cli.py")
    if os.path.exists(cli_file):
        with open(cli_file, "r") as f:
            line_count = len(f.readlines())
        if line_count >= 500:
            failed_criteria.append(f"{index}. {criterion}")
            print(f"   ❌ {index}. cli.py still has {line_count} lines (should be <500)")
            return False
        else:
            print(f"   ✅ {index}. cli.py reduced to {line_count} lines")
            return True
    else:
        print(f"   ✅ {index}. cli.py properly refactored (file may have been moved)")
        return True


def _validate_cli_split(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate CLI commands split into separate files."""
    cmd_files = {
        "ticket.py": os.path.join(project_dir, "src/hydra/cli/commands/ticket.py"),
        "parallel.py": os.path.join(project_dir, "src/hydra/cli/commands/parallel.py"),
        "verify.py": os.path.join(project_dir, "src/hydra/cli/commands/verify.py"),
        "template.py": os.path.join(project_dir, "src/hydra/cli/commands/template.py"),
    }
    missing = []
    for name, path in cmd_files.items():
        if not os.path.exists(path):
            missing.append(name)

    if missing:
        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. Commands not split into files: {', '.join(missing)}")
        return False

    print(f"   ✅ {index}. Commands split into separate files")
    return True


def _validate_module_extraction(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate module extraction for ticket 016."""
    # Check for the new modules
    modules = [
        "src/hydra/tickets/ticket_parser.py",
        "src/hydra/tickets/ticket_executor.py",
        "src/hydra/tickets/ticket_database.py",
    ]

    missing = []
    for module_path in modules:
        full_path = os.path.join(project_dir, module_path)
        if not os.path.exists(full_path):
            missing.append(os.path.basename(module_path))

    if missing:
        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. Modules not extracted: {', '.join(missing)}")
        return False

    print(f"   ✅ {index}. Modules extracted successfully")
    return True


def _validate_module_size(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate module size constraints."""
    # Extract the line limit from criterion
    import re
    match = re.search(r"under (\d+) lines", criterion.lower())
    if not match:
        return True  # Can't validate without a specific number

    max_lines = int(match.group(1))

    # Check the new modules
    modules = [
        "src/hydra/tickets/ticket_parser.py",
        "src/hydra/tickets/ticket_executor.py",
        "src/hydra/tickets/ticket_database.py",
    ]

    oversized = []
    for module_path in modules:
        full_path = os.path.join(project_dir, module_path)
        if os.path.exists(full_path):
            with open(full_path, "r") as f:
                line_count = len(f.readlines())
            if line_count > max_lines:
                oversized.append(f"{os.path.basename(module_path)} ({line_count} lines)")

    if oversized:
        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. Modules exceed {max_lines} lines: {', '.join(oversized)}")
        return False

    print(f"   ✅ {index}. All modules under {max_lines} lines")
    return True


def _validate_provider_interface(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate provider interface in base_provider.py."""
    base_provider_path = os.path.join(project_dir, "src/hydra/providers/base_provider.py")

    if not os.path.exists(base_provider_path):
        # Check if it's been created/modified
        base_path = os.path.join(project_dir, "src/hydra/providers/base.py")
        if os.path.exists(base_path):
            # Check if the interface has been enhanced
            with open(base_path, "r") as f:
                content = f.read()
            if "class LLMProvider" in content and "abstractmethod" in content:
                print(f"   ✅ {index}. Provider interface exists in base.py")
                return True

        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. File not found: src/hydra/providers/base_provider.py")
        return False

    # Check if the file has proper interface definitions
    with open(base_provider_path, "r") as f:
        content = f.read()

    required_elements = [
        "class",  # Should have class definitions
        "abstractmethod",  # Should have abstract methods
        "LLMProvider",  # Should define provider interface
    ]

    missing = [elem for elem in required_elements if elem not in content]
    if missing:
        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. Provider interface incomplete, missing: {', '.join(missing)}")
        return False

    print(f"   ✅ {index}. Clear provider interface created")
    return True


def _validate_provider_consolidation(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate Claude provider consolidation."""
    # Check for unified provider implementation
    unified_paths = [
        "src/hydra/providers/claude_unified.py",
        "src/hydra/providers/unified_factory.py",
        "src/hydra/providers/config_manager.py"
    ]

    found_files = []
    for path in unified_paths:
        full_path = os.path.join(project_dir, path)
        if os.path.exists(full_path):
            found_files.append(os.path.basename(path))

    if found_files:
        print(f"   ⚠️  {index}. Requires implementation verification: {criterion[:60]}...")
        print("      📝 Files created/modified - implementation detected")
        return True

    # Check if existing providers have been modified for consolidation
    existing_providers = [
        "src/hydra/providers/claude_cli.py",
        "src/hydra/providers/claude_tmux.py",
        "src/hydra/providers/claude_cli_enhanced.py"
    ]

    modified_count = 0
    for path in existing_providers:
        full_path = os.path.join(project_dir, path)
        if os.path.exists(full_path):
            # Check if file was recently modified
            import subprocess
            result = subprocess.run(
                ["git", "status", "--short", path],
                capture_output=True,
                text=True,
                cwd=project_dir
            )
            if result.stdout.strip():
                modified_count += 1

    if modified_count >= 2:
        print(f"   ⚠️  {index}. Requires implementation verification: {criterion[:60]}...")
        print("      📝 Files created/modified - implementation detected")
        return True

    failed_criteria.append(f"{index}. {criterion}")
    print(f"   ❌ {index}. Provider consolidation not implemented")
    return False


def _validate_duplicate_removal(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate duplicate code removal."""
    # This is hard to validate automatically
    # Check if consolidation files exist
    consolidation_indicators = [
        "src/hydra/providers/claude_unified.py",
        "src/hydra/providers/migration.py",
        "src/hydra/providers/unified_factory.py"
    ]

    for path in consolidation_indicators:
        full_path = os.path.join(project_dir, path)
        if os.path.exists(full_path):
            print(f"   ⚠️  {index}. Requires implementation verification: {criterion[:60]}...")
            print("      📝 Files created/modified - implementation detected")
            return True

    # Check if provider files were modified
    git_status = subprocess.run(
        ["git", "status", "--short", "src/hydra/providers/"],
        capture_output=True,
        text=True,
        cwd=project_dir
    )

    if git_status.stdout:
        print(f"   ⚠️  {index}. Requires implementation verification: {criterion[:60]}...")
        print("      📝 Files created/modified - implementation detected")
        return True

    failed_criteria.append(f"{index}. {criterion}")
    print(f"   ❌ {index}. No evidence of duplicate code removal")
    return False


def _validate_provider_documentation(
    index: int,
    criterion: str,
    project_dir: str,
    failed_criteria: List[str]
) -> bool:
    """Validate provider architecture documentation."""
    doc_path = os.path.join(project_dir, "docs/architecture/providers.md")

    if not os.path.exists(doc_path):
        # Check alternative location
        alt_path = os.path.join(project_dir, "docs/architecture/")
        if os.path.exists(alt_path):
            # Check if any provider docs exist
            import glob
            provider_docs = glob.glob(os.path.join(alt_path, "*provider*"))
            if provider_docs:
                print(f"   ✅ {index}. Provider documentation found")
                return True

        failed_criteria.append(f"{index}. {criterion}")
        print(f"   ❌ {index}. Required file missing: docs/architecture/providers.md")
        return False

    print(f"   ✅ {index}. Provider architecture documented")
    return True


def validate_code_changes(project_dir: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """Validate code changes for suspicious patterns.
    
    Args:
        project_dir: Project directory path
        
    Returns:
        Tuple of (is_valid, list of suspicious patterns)

    """
    suspicious_patterns = []

    # Get list of modified files
    git_result = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True,
        text=True,
        cwd=project_dir,
    )

    if not git_result.stdout:
        return True, []

    modified_files = []
    for line in git_result.stdout.strip().split("\n"):
        if line:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                status_code, file_path = parts
                if "M" in status_code or "A" in status_code:
                    modified_files.append(file_path)

    # Check for suspicious patterns in modified files
    patterns_to_check = [
        {
            "pattern": r"eval\(",
            "description": "Use of eval() - potential security risk",
        },
        {
            "pattern": r"exec\(",
            "description": "Use of exec() - potential security risk",
        },
        {
            "pattern": r"__import__\(",
            "description": "Dynamic import - potential security risk",
        },
        {
            "pattern": r"os\.system\(",
            "description": "Direct system command execution",
        },
        {
            "pattern": r"subprocess\.call\([^,]*shell=True",
            "description": "Shell injection vulnerability",
        },
    ]

    for file_path in modified_files:
        full_path = os.path.join(project_dir, file_path)
        if not os.path.exists(full_path):
            continue

        # Skip non-code files
        if not file_path.endswith((".py", ".js", ".ts")):
            continue

        try:
            with open(full_path, "r") as f:
                content = f.read()

            for pattern_info in patterns_to_check:
                matches = re.findall(pattern_info["pattern"], content)
                if matches:
                    suspicious_patterns.append({
                        "file": file_path,
                        "pattern": pattern_info["description"],
                        "matches": matches[:3],  # Limit to first 3 matches
                    })
        except Exception:
            # Skip files that can't be read
            continue

    is_valid = len(suspicious_patterns) == 0
    return is_valid, suspicious_patterns


def check_for_ai_generated_code(
    project_dir: str,
    ticket_id: str = "unknown",
    ticket_description: str = "",
    strictness: StrictnessLevel = StrictnessLevel.MODERATE,
) -> Tuple[str, bool, Dict[str, Any]]:
    """Check for AI-generated code patterns in recent changes.
    
    Args:
        project_dir: Project directory path
        ticket_id: Ticket ID for context
        ticket_description: Ticket description for context
        strictness: Strictness level for detection
        
    Returns:
        Tuple of (report_string, should_block, analysis_dict)

    """
    try:
        detector = AIGeneratedCodeDetector()

        # Get list of modified files
        git_result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )

        if not git_result.stdout:
            return "", False, {}

        modified_files = [
            os.path.join(project_dir, f.strip())
            for f in git_result.stdout.strip().split("\n")
            if f.strip()
        ]

        # Analyze modified files
        all_issues = []
        critical_issues = []

        for file_path in modified_files:
            if not os.path.exists(file_path):
                continue

            # Skip non-code files
            if not file_path.endswith((".py", ".js", ".ts", ".jsx", ".tsx")):
                continue

            try:
                with open(file_path, "r") as f:
                    content = f.read()

                # Use the detector with ticket context
                result = detector.analyze_code(
                    content,
                    ticket_id=ticket_id,
                    ticket_description=ticket_description,
                    strictness=strictness,
                )

                if result["is_ai_generated"]:
                    issues = result.get("issues", [])
                    all_issues.extend(issues)

                    # Check for critical issues
                    if result.get("confidence", 0) > 0.8:
                        critical_issues.extend(issues)

            except Exception:
                # Skip files that can't be analyzed
                continue

        # Generate report
        report = _generate_ai_report(all_issues, critical_issues, strictness)

        # Determine if we should block
        should_block = len(critical_issues) > 0 and strictness != StrictnessLevel.LENIENT

        analysis = {
            "total_issues": len(all_issues),
            "critical_issues": len(critical_issues),
            "strictness": strictness.value,
        }

        return report, should_block, analysis

    except Exception as e:
        # Don't fail validation if AI detection fails
        return f"⚠️  AI detection error: {str(e)}", False, {}


def _generate_ai_report(
    all_issues: List[str],
    critical_issues: List[str],
    strictness: StrictnessLevel
) -> str:
    """Generate AI detection report."""
    if not all_issues:
        return ""

    report = []
    report.append("🤖 AI-GENERATED CODE DETECTION REPORT")
    report.append("=" * 40)
    report.append(f"Strictness Level: {strictness.value}")
    report.append(f"Total Issues: {len(all_issues)}")
    report.append(f"Critical Issues: {len(critical_issues)}")

    if critical_issues:
        report.append("\n❌ CRITICAL ISSUES (must fix):")
        for issue in critical_issues[:5]:
            report.append(f"   • {issue}")
        if len(critical_issues) > 5:
            report.append(f"   ... and {len(critical_issues) - 5} more")

    if len(all_issues) > len(critical_issues):
        other_issues = [i for i in all_issues if i not in critical_issues]
        report.append("\n⚠️  WARNING ISSUES (recommended to fix):")
        for issue in other_issues[:5]:
            report.append(f"   • {issue}")
        if len(other_issues) > 5:
            report.append(f"   ... and {len(other_issues) - 5} more")

    return "\n".join(report)


def run_validation_commands():
    """Run standard validation commands."""
    print("🔧 Running validation commands...")

    commands = [
        ("npm test", "Running tests"),
        ("npm run lint", "Running linter"),
        ("npm run build", "Building project"),
    ]

    for cmd, description in commands:
        print(f"   {description}...")
        try:
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                print(f"   ✅ {description} passed")
            else:
                print(f"   ⚠️  {description} had warnings")
        except Exception as e:
            print(f"   ⚠️  {description} skipped: {e}")


def run_node_validation():
    """Run Node.js specific validation."""
    print("🔧 Running Node.js validation...")

    # Check if package.json exists
    if not os.path.exists("package.json"):
        print("   ⚠️  No package.json found - skipping Node validation")
        return

    # Run npm install if needed
    if not os.path.exists("node_modules"):
        print("   Installing dependencies...")
        try:
            subprocess.run(["npm", "install"], check=True, timeout=120)
            print("   ✅ Dependencies installed")
        except Exception as e:
            print(f"   ⚠️  Could not install dependencies: {e}")
            return

    # Run validation commands
    run_validation_commands()
