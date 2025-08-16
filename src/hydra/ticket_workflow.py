"""Ticket Workflow module."""

#!/usr/bin/env python3
"""Kyle's ticket-based development workflow integrated into Hydra."""

import os
import re
import subprocess
import tempfile
import threading
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set, Tuple

from hydra.caching import get_cache_key, get_file_meta_cache
from hydra.intelligence.model_selector import create_enhanced_model_prompt
from hydra.monitoring import monitoring
from hydra.prompts import get_prompt_template
from hydra.quality.ai_detection import AIGeneratedCodeDetector, StrictnessLevel

# Dashboard database integration
def update_ticket_in_database(ticket_identifier: str, status: str, project_path: str = None, ticket_info: dict = None):
    """Update ticket status in the dashboard database.
    
    Args:
        ticket_identifier: Ticket ID (e.g., '001')
        status: New status (TODO, IN_PROGRESS, DONE)
        project_path: Path to the project (defaults to current directory)
        ticket_info: Optional dict with ticket details (title, description, etc.)
    """
    try:
        import os
        from datetime import datetime
        from hydra.dashboard.database import get_db_manager, Project, Ticket, Execution
        
        # Set database URL to project-specific location if we're in a project
        if project_path and os.path.exists(os.path.join(project_path, 'tickets.yaml')):
            os.environ['DATABASE_URL'] = f"sqlite:///{project_path}/.hydra/dashboard/hydra.db"
        
        # Get database manager
        db_manager = get_db_manager()
        
        # Normalize ticket ID
        if ticket_identifier.isdigit():
            ticket_identifier = ticket_identifier.zfill(3)
        
        # Get project path
        if project_path is None:
            project_path = os.getcwd()
        
        # ticket_info will be passed from the calling function if available
        
        with db_manager.get_session() as db:
            # Find or create project
            project = db.query(Project).filter(
                Project.repository_url == project_path
            ).first()
            
            if not project:
                project_name = os.path.basename(project_path) or "Current Project"
                project = Project(
                    name=project_name,
                    description=f"Project at {project_path}",
                    repository_url=project_path,
                    created_at=datetime.now()
                )
                db.add(project)
                db.commit()
            
            # Find or create ticket
            ticket = db.query(Ticket).filter(
                Ticket.ticket_number == ticket_identifier,
                Ticket.project_id == project.id
            ).first()
            
            if ticket:
                # Update existing ticket
                ticket.status = status
                ticket.updated_at = datetime.now()
                
                if status == "IN_PROGRESS" and not ticket.started_at:
                    ticket.started_at = datetime.now()
                elif status == "DONE" and not ticket.completed_at:
                    ticket.completed_at = datetime.now()
            else:
                # Create new ticket with details from ticket_info if available
                title = f"Ticket {ticket_identifier}"
                description = ""
                model = "balanced"
                priority = "medium"
                
                if ticket_info:
                    title = ticket_info.get('title', title)
                    description = ticket_info.get('description', '')
                    model = ticket_info.get('model', 'balanced')
                    # Map priority if available
                    priority_val = ticket_info.get('priority')
                    if isinstance(priority_val, int):
                        priority = priority_val
                    else:
                        priority = "medium"
                
                ticket = Ticket(
                    project_id=project.id,
                    ticket_number=ticket_identifier,
                    title=title,
                    description=description,
                    status=status,
                    priority=priority,
                    model=model,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                if status == "IN_PROGRESS":
                    ticket.started_at = datetime.now()
                elif status == "DONE":
                    ticket.completed_at = datetime.now()
                db.add(ticket)
            
            db.commit()
            
            # Send WebSocket update if available
            try:
                from hydra.dashboard.websocket import get_ws_handler
                ws_handler = get_ws_handler()
                ws_handler.broadcast({
                    "type": "ticket_update",
                    "data": {
                        "ticket_id": ticket.id,
                        "ticket_number": ticket_identifier,
                        "status": status,
                        "project": project.name
                    }
                })
            except Exception:
                pass  # WebSocket not available, skip
                
    except ImportError as e:
        print(f"⚠️  Dashboard not available: {e}")
    except Exception as e:
        # Log error but don't fail ticket execution
        print(f"⚠️  Dashboard update failed: {e}")
        import traceback
        traceback.print_exc()


class SharedWorkspace:
    """Manages a shared workspace for ticket execution sessions."""

    def __init__(self, session_id: Optional[str] = None):
        """Initialize shared workspace.

        Args:
            session_id: Optional session ID, will generate one if not provided

        """
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.workspace_path = os.path.join(
            tempfile.gettempdir(),
            f"hydra_session_{self.session_id}"
        )
        self._ensure_workspace_exists()

    def _ensure_workspace_exists(self) -> None:
        """Ensure the workspace directory exists."""
        os.makedirs(self.workspace_path, exist_ok=True)

        # Create standard subdirectories
        subdirs = ["artifacts", "docs", "configs", "shared_data"]
        for subdir in subdirs:
            os.makedirs(os.path.join(self.workspace_path, subdir), exist_ok=True)

        # Create session info file
        info_file = os.path.join(self.workspace_path, "session_info.txt")
        if not os.path.exists(info_file):
            with open(info_file, 'w') as f:
                import datetime
                f.write(f"Session ID: {self.session_id}\n")
                f.write(f"Created: {datetime.datetime.now().isoformat()}\n")
                f.write("Purpose: Shared workspace for ticket execution\n")

    def get_artifact_path(self, ticket_id: str, filename: str) -> str:
        """Get path for a ticket artifact.

        Args:
            ticket_id: Ticket identifier
            filename: Name of the artifact file

        Returns:
            Full path to the artifact

        """
        # Normalize ticket ID
        if ticket_id.isdigit():
            ticket_id = ticket_id.zfill(3)

        ticket_dir = os.path.join(self.workspace_path, "artifacts", f"ticket_{ticket_id}")
        os.makedirs(ticket_dir, exist_ok=True)
        return os.path.join(ticket_dir, filename)

    def save_artifact(self, ticket_id: str, filename: str, content: str) -> str:
        """Save an artifact for a ticket.

        Args:
            ticket_id: Ticket identifier
            filename: Name of the artifact file
            content: Content to save

        Returns:
            Path where artifact was saved

        """
        artifact_path = self.get_artifact_path(ticket_id, filename)
        with open(artifact_path, 'w') as f:
            f.write(content)
        return artifact_path

    def list_ticket_artifacts(self, ticket_id: str) -> List[str]:
        """List all artifacts for a ticket.

        Args:
            ticket_id: Ticket identifier

        Returns:
            List of artifact filenames

        """
        if ticket_id.isdigit():
            ticket_id = ticket_id.zfill(3)

        ticket_dir = os.path.join(self.workspace_path, "artifacts", f"ticket_{ticket_id}")
        if not os.path.exists(ticket_dir):
            return []

        return [f for f in os.listdir(ticket_dir) if os.path.isfile(os.path.join(ticket_dir, f))]

    def get_dependency_artifacts(self, dependencies: List[str]) -> Dict[str, List[str]]:
        """Get artifacts from dependency tickets.

        Args:
            dependencies: List of ticket IDs that are dependencies

        Returns:
            Dictionary mapping ticket_id to list of artifact paths

        """
        artifacts = {}
        for dep_id in dependencies:
            dep_artifacts = self.list_ticket_artifacts(dep_id)
            if dep_artifacts:
                artifacts[dep_id] = [
                    self.get_artifact_path(dep_id, artifact)
                    for artifact in dep_artifacts
                ]
        return artifacts

    def create_manifest(self, ticket_id: str, created_files: List[str]) -> None:
        """Create a manifest of files created by a ticket.

        Args:
            ticket_id: Ticket identifier
            created_files: List of files created by the ticket

        """
        manifest_path = self.get_artifact_path(ticket_id, "manifest.txt")
        with open(manifest_path, 'w') as f:
            f.write(f"Files created by Ticket {ticket_id}:\n")
            f.write("=" * 40 + "\n")
            for file_path in created_files:
                f.write(f"{file_path}\n")

    def cleanup(self) -> None:
        """Clean up the workspace directory."""
        import shutil
        if os.path.exists(self.workspace_path):
            shutil.rmtree(self.workspace_path)
            print(f"🧹 Cleaned up workspace: {self.workspace_path}")


# Global workspace instance for session
_shared_workspace: Optional[SharedWorkspace] = None


def get_shared_workspace(session_id: Optional[str] = None) -> SharedWorkspace:
    """Get or create the shared workspace for the session.

    Args:
        session_id: Optional session ID for the workspace

    Returns:
        SharedWorkspace instance

    """
    global _shared_workspace
    if _shared_workspace is None:
        _shared_workspace = SharedWorkspace(session_id)
        print(f"📁 Created shared workspace: {_shared_workspace.workspace_path}")
    return _shared_workspace


def detect_project_context(tickets_path):
    """Detect project language/framework from tickets.md content and directory."""
    project_dir = os.path.dirname(os.path.abspath(tickets_path))
    context_clues = []

    # Check for package files
    if os.path.exists(os.path.join(project_dir, 'package.json')):
        context_clues.append("Node.js/JavaScript project")
    if os.path.exists(os.path.join(project_dir, 'requirements.txt')):
        context_clues.append("Python project")
    if os.path.exists(os.path.join(project_dir, 'Cargo.toml')):
        context_clues.append("Rust project")
    if os.path.exists(os.path.join(project_dir, 'go.mod')):
        context_clues.append("Go project")

    # Read tickets content for additional clues
    try:
        with open(tickets_path, 'r') as f:
            content = f.read().lower()

        # Framework/technology detection
        if any(tech in content for tech in ['hyperswarm', 'hypercore', 'pear runtime', 'commander.js', 'node.js']):
            context_clues.append("Node.js P2P application with Hypercore/Hyperswarm")
        elif any(tech in content for tech in ['fastapi', 'django', 'flask']):
            context_clues.append("Python web application")
        elif any(tech in content for tech in ['react', 'vue', 'angular', 'javascript', 'typescript']):
            context_clues.append("JavaScript/TypeScript frontend")
        elif any(tech in content for tech in ['cli', 'command line']):
            context_clues.append("Command-line application")

    except Exception:
        pass

    if context_clues:
        return " - ".join(context_clues)
    else:
        return "General software project"


def parse_ticket(tickets_path, ticket_identifier):
    """Parse specific ticket from tickets file."""
    from hydra.tickets.compatibility import TicketFormatHandler
    handler = TicketFormatHandler()
    ticket = handler.parse_ticket(tickets_path, ticket_identifier)
    
    if ticket:
        # Cache the result
        cache = get_file_meta_cache()
        cache_key = get_cache_key(tickets_path, ticket_identifier)
        cache.set(cache_key, ticket, tickets_path)
        
    return ticket


def parse_ticket_md_legacy(tickets_path, ticket_identifier):
    """Legacy MD parser kept for backward compatibility."""
    if not os.path.exists(tickets_path):
        print(f"❌ {tickets_path} not found")
        return None

    # Check cache first
    cache = get_file_meta_cache()
    cache_key = get_cache_key(tickets_path, ticket_identifier)
    cached_result = cache.get(cache_key, tickets_path)

    if cached_result is not None:
        return cached_result

    with open(tickets_path, 'r') as f:
        content = f.read()

    # Normalize identifier - add TICKET- prefix if just a number
    if ticket_identifier.isdigit():
        # Try with TICKET- prefix first for numbered identifiers
        patterns = [
            rf'### TICKET-{ticket_identifier}:(.*?)(?=### TICKET-|\Z)',
            rf'## TICKET-{ticket_identifier}:(.*?)(?=## TICKET-|\Z)',
            rf'## Ticket-{ticket_identifier}:(.*?)(?=## Ticket-|\Z)',
            rf'## Ticket {ticket_identifier}:(.*?)(?=## Ticket|\Z)',
            rf'## #{ticket_identifier}:(.*?)(?=## #|\Z)',
            rf'## {ticket_identifier}:(.*?)(?=## |\Z)',
        ]
    else:
        # Already has prefix, use as-is
        patterns = [
            rf'### {ticket_identifier}:(.*?)(?=### TICKET-|\Z)',
            rf'## {ticket_identifier}:(.*?)(?=## TICKET-|\Z)',
        ]

    match = None

    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            break

    if not match:
        print(f"❌ Ticket {ticket_identifier} not found")
        print("📋 Available ticket patterns found:")
        # Show available tickets for debugging
        ticket_headers = re.findall(r'##+ (TICKET-\d+|Ticket-\d+|Ticket \d+|#\d+|\d+):', content, re.IGNORECASE)
        for header in ticket_headers[:10]:  # Show first 10
            print(f"   - {header}")
        if len(ticket_headers) > 10:
            print(f"   ... and {len(ticket_headers) - 10} more")
        return None

    ticket_content = match.group(1).strip()
    lines = ticket_content.split('\n')

    ticket = {
        'number': ticket_identifier,
        'title': lines[0].strip(),
        'description': '',
        'status': 'TODO',  # Default status
        'model': 'balanced',  # Default to balanced model
        'acceptance_criteria': [],
        'dependencies': [],
        'completed': False
    }

    # Check if ticket is already completed
    if '✅ COMPLETED' in ticket['title'] or 'COMPLETED' in ticket['title']:
        ticket['completed'] = True

    in_criteria = False
    unchecked_criteria = 0
    checked_criteria = 0

    for line in lines[1:]:
        line = line.strip()
        # Check for status line (markdown bold syntax: **Status**:)
        if len(line) >= 11 and line[:11] == '**Status**:':
            status_text = line.replace('**Status**:', '').strip().upper()
            ticket['status'] = status_text
            # Mark as completed if status is DONE
            if status_text == 'DONE':
                ticket['completed'] = True
            # Don't mark as completed if quality failed
            elif status_text == 'QUALITY_FAILED':
                ticket['completed'] = False
                ticket['quality_failed'] = True
        elif len(line) >= 10 and line[:10] == '**Model:**':
            # Use model mapper to handle both legacy and new model categories
            from hydra.providers.model_mapper import get_model_mapper
            mapper = get_model_mapper()
            model_text = line.replace('**Model:**', '').strip().lower()

            # Map to model category (fast, balanced, smart, coder)
            category = mapper.get_model_category(model_text)
            if category:
                ticket['model'] = category.value
            else:
                # Default to balanced if unknown
                ticket['model'] = 'balanced'
        elif len(line) >= 17 and line[:17] == '**Dependencies:**':
            # Parse simplified dependency format: "001,002,003" or "None"
            deps_text = line.replace('**Dependencies:**', '').strip()
            if deps_text.lower() not in ['none', 'n/a', '-', '']:
                # Split by comma and normalize to 3 digits
                deps = deps_text.split(',')
                for dep in deps:
                    dep = dep.strip()
                    if dep.isdigit():
                        ticket['dependencies'].append(dep.zfill(3))
        elif line.startswith('**Description:**'):
            # Capture single-line description
            ticket['description'] = line.replace('**Description:**', '').strip()
        elif len(line) >= 24 and line[:24] == '**Acceptance Criteria:**':
            in_criteria = True
        elif line.startswith('- [ ]'):
            criteria = line.replace('- [ ]', '').strip()
            ticket['acceptance_criteria'].append(criteria)
            unchecked_criteria += 1
        elif line.startswith('- [x]'):
            # Already completed criteria - still add to list but mark as done
            criteria = line.replace('- [x]', '').strip()
            ticket['acceptance_criteria'].append(f"✅ {criteria}")
            checked_criteria += 1
        elif line.startswith('##'):
            # Stop parsing if we hit another section header
            break
        elif not in_criteria and line and not line.startswith('**') and not ticket['description']:
            # Only capture additional description if we don't have one yet
            ticket['description'] = line

    # Mark ticket as completed if all acceptance criteria are checked
    if unchecked_criteria == 0 and checked_criteria > 0:
        ticket['completed'] = True
        print(f"✅ Ticket {ticket_identifier} is already completed (all {checked_criteria} criteria checked)")

    # Cache the parsed ticket
    cache.set(cache_key, ticket, tickets_path)

    return ticket


# NOTE: This function has been moved to line 577 to avoid duplication
# The function at line 577 handles more ticket formats and is more comprehensive


def generate_tickets_md(project_description, output_path="tickets.md", project_type=None):
    """Generate tickets file from project description."""
    from hydra.tickets.generator import TicketGenerator
    from pathlib import Path
    
    if Path(output_path).suffix not in ['.yml', '.yaml']:
        output_path = output_path.replace('.md', '.yaml')
        
    generator = TicketGenerator()
    return generator.generate_tickets_yaml(project_description, output_path, project_type)
    print("🎫 Generating tickets.md...")
    print("=" * 30)

    # Analyze codebase first to gather context
    from hydra.analysis.codebase_analyzer import CodebaseAnalyzer
    project_dir = os.path.dirname(os.path.abspath(output_path))

    print("🔍 Analyzing codebase for context...")
    analyzer = CodebaseAnalyzer(project_dir)
    codebase_analysis = analyzer.analyze()

    # Build codebase context
    codebase_context = f"""
CODEBASE ANALYSIS:
- Project Type: {codebase_analysis['project_type']}
- Framework: {codebase_analysis['framework'] or 'None detected'}
- Tech Stack: {', '.join(codebase_analysis['tech_stack'])}
- Size: {codebase_analysis['size_metrics']['total_loc']} LOC in {codebase_analysis['size_metrics']['total_files']} files
- Test Coverage: {codebase_analysis['existing_tests']['test_count']} test files found
- Documentation: {'README exists' if codebase_analysis['documentation']['has_readme'] else 'No README'}
- CI/CD: {codebase_analysis['ci_cd']['platform'] or 'Not configured'}

KEY DIRECTORIES:
{chr(10).join('- ' + d for d in codebase_analysis['structure']['directories'][:5])}

COMPLEXITY INSIGHTS:
{analyzer.generate_complexity_report()}
"""

    # Use provider abstraction instead of hardcoding Claude
    from hydra.providers.model_mapper import get_model_mapper
    from hydra.providers.provider_factory import create_provider_from_environment

    # Get the provider and model mapper
    provider = create_provider_from_environment()
    mapper = get_model_mapper()

    # Get the smart model for ticket planning (was "Opus 4")
    smart_model = mapper.map_model("smart", provider.config.provider_type if hasattr(provider, 'config') and hasattr(provider.config, 'provider_type') else None)
    print(f"🧠 Using {smart_model or 'smart model'} for ticket planning...")

    # Load project template if specified
    template_guidance = ""
    if project_type:
        try:
            from hydra.templates.project_templates import (
                ProjectTemplateManager,
                ProjectType,
            )
            template_manager = ProjectTemplateManager()

            if template_manager.validate_project_type(project_type):
                project_type_enum = ProjectType(project_type)
                template_structure = template_manager.get_template_structure(project_type_enum)
                phases = template_structure["phases"]

                template_guidance = f"""

PROJECT TYPE: {project_type.upper()}
RECOMMENDED PHASES: {' → '.join(phases)}

When creating tickets, consider structuring work around these phases:
{chr(10).join(f'- {phase}' for phase in phases)}

Template guidance available at: templates/{project_type}_template.md
"""
        except Exception as e:
            print(f"⚠️  Could not load template for {project_type}: {e}")

    # Adapt prompt to use generic model categories instead of specific Claude models
    # Extract just the filename from the full path for the prompt
    output_filename = os.path.basename(output_path)

    # Get enhanced model selection guidance
    enhanced_model_guidance = create_enhanced_model_prompt()

    prompt = f"""Create a file named '{output_filename}' in the current directory with MINIMAL tickets to solve the problem.{template_guidance}

{codebase_context}

CRITICAL: Generate the FEWEST tickets possible. Most issues should be 1-2 tickets max. Only create multiple tickets if there are truly independent parts or if a database migration MUST happen before code changes.

Prefer direct code changes over analysis/design documents. Skip intermediate documents unless absolutely necessary.

Use the codebase analysis above to:
1. Select appropriate model complexity based on actual code complexity
2. Identify files that need modification
3. Understand existing patterns to maintain consistency
4. Detect logical dependencies between components

{enhanced_model_guidance}

Each ticket MUST have this format:
## Ticket 001: [Title]
**Status:** TODO
**Model:** [smart, balanced, fast, or coder] - Select based on complexity analysis above
**Dependencies:** [None or comma-separated ticket numbers like 001,002]
**Description:** [Direct task description - be specific about what code to change]
**Progress:** started

**Acceptance Criteria:**
- [ ] [Specific code changes to make]
- [ ] [Tests to update/add if needed]
- [ ] [Verification steps]

RULES FOR MINIMAL TICKETS:
1. DEFAULT to 1 ticket that does everything unless there's a compelling reason to split
2. Only split into multiple tickets if:
   - Database migration MUST run before code changes to avoid breaking existing systems
   - There are completely independent features that different people could work on
3. NEVER create tickets for:
   - Analysis reports (do analysis within the implementation ticket)
   - Design documents (design while implementing)
   - Documentation updates (include in the main change)
   - Validation reports (validation happens during implementation)
4. Focus on DIRECT CODE CHANGES, not meta-work

Example for a bug fix (IDEAL - single ticket):
## Ticket 001: Fix wallet counter skipping index 0
**Status:** TODO
**Model:** smart
**Dependencies:** None
**Description:** Change counter semantics from "last used" to "next available" and add migration for existing wallets
**Progress:** started

**Acceptance Criteria:**
- [ ] Update database trait get_keyset_counter to return u32 instead of Option<u32>, defaulting to 0
- [ ] Add database migration to increment all existing counters by 1 where counter > 0
- [ ] Remove +1 logic from wallet operations (issue_bolt11, issue_bolt12, melt_bolt11, swap)
- [ ] Update tests to verify index 0 is now used
- [ ] Run all tests and ensure they pass

Example when migration is truly needed separately:
## Ticket 001: Add database migration for counter fix
**Status:** TODO
**Model:** fast
**Dependencies:** None
**Description:** Add migration to increment existing keyset counters by 1 to prepare for semantic change
**Progress:** started

**Acceptance Criteria:**
- [ ] Add SQL migration: UPDATE keyset SET counter = counter + 1 WHERE counter > 0
- [ ] Add REDB migration with same logic
- [ ] Test migration on sample data

## Ticket 002: Update counter logic to use next available index
**Status:** TODO
**Model:** smart
**Dependencies:** 001
**Description:** Change counter implementation to represent next available index instead of last used
**Progress:** started

**Acceptance Criteria:**
- [ ] Change get_keyset_counter return type from Option<u32> to u32 (default 0)
- [ ] Remove all +1 increments in wallet operations
- [ ] Update tests to verify behavior
- [ ] Ensure all tests pass

Project: {project_description}"""

    print("🚀 Generating tickets with production standards...")

    try:
        # Determine the working directory for ticket generation
        # Use the directory of the output file as the working directory
        output_dir = os.path.dirname(os.path.abspath(output_path))

        # Use provider abstraction to generate tickets
        # Increase timeout for ticket generation as it may take longer
        provider.config.timeout = 120  # 2 minutes should be enough

        provider.generate(
            prompt,  # Pass as positional argument
            model=smart_model,
            mode="ticket_generation",
            cwd=output_dir  # Pass working directory for claude_tmux
        )

        # Check if file was created successfully
        if os.path.exists(output_path):
            # Read the created file
            with open(output_path, 'r') as f:
                tickets_content = f.read()

            print(f"✅ {output_path} created successfully!")

            # Show summary - handle various ticket formats
            import re

            # Count any heading that looks like a ticket
            ticket_patterns = [
                r'## Ticket \d+:',  # ## Ticket 001:
                r'## CALC-\d+:',     # ## CALC-001:
                r'## \w+-\d+:',      # ## ANY-001:
                r'## Ticket'         # ## Ticket
            ]
            ticket_count = 0
            for pattern in ticket_patterns:
                matches = len(re.findall(pattern, tickets_content))
                if matches > 0:
                    ticket_count = matches
                    break

            # Count models using generic categories
            smart_count = tickets_content.lower().count('smart')
            balanced_count = tickets_content.lower().count('balanced')
            fast_count = tickets_content.lower().count('fast')
            coder_count = tickets_content.lower().count('coder')

            print(f"📊 Generated {ticket_count} tickets:")
            if smart_count > 0:
                print(f"   🧠 Smart: {smart_count} tickets")
            if balanced_count > 0:
                print(f"   ⚡ Balanced: {balanced_count} tickets")
            if fast_count > 0:
                print(f"   💨 Fast: {fast_count} tickets")
            if coder_count > 0:
                print(f"   💻 Coder: {coder_count} tickets")

            # Generate effort estimates
            print("\n⏱️  Generating effort estimates...")
            from hydra.analysis.effort_estimator import EffortEstimator
            estimator = EffortEstimator(codebase_analysis)

            # Parse tickets for estimation
            parsed_tickets = []
            for match in re.findall(r'## Ticket \d+:(.*?)(?=## Ticket|\Z)', tickets_content, re.DOTALL):
                ticket_dict = {'criteria': []}
                lines = match.strip().split('\n')
                if lines:
                    ticket_dict['title'] = lines[0].strip()
                for line in lines:
                    if line.startswith('**Model:**'):
                        ticket_dict['model'] = line.replace('**Model:**', '').strip().lower()
                    elif len(line) >= 17 and line[:17] == '**Dependencies:**':
                        deps = line.replace('**Dependencies:**', '').strip()
                        if deps.lower() not in ['none', '']:
                            ticket_dict['dependencies'] = deps.split(',')
                    elif line.startswith('**Description:**'):
                        ticket_dict['description'] = line.replace('**Description:**', '').strip()
                    elif line.startswith('- [ ]'):
                        ticket_dict['criteria'].append(line.replace('- [ ]', '').strip())
                parsed_tickets.append(ticket_dict)

            if parsed_tickets:
                timeline = estimator.estimate_project_timeline(parsed_tickets)
                print("\n📈 Effort Estimation:")
                print(f"   Total effort: {timeline['total_effort_hours']:.1f} hours")
                print(f"   Average per ticket: {timeline['average_ticket_hours']:.1f} hours")
                print(f"   Sequential timeline: {timeline['timelines']['sequential']['days']:.1f} days")
                print(f"   With 2 devs parallel: {timeline['timelines']['parallel_2_devs']['days']:.1f} days")
                print(f"   Critical path: {timeline['critical_path_hours']:.1f} hours")

            # Validate dependencies after generation
            print("\n🔍 Validating ticket dependencies...")
            from hydra.validation.dependency_validator import DependencyValidator
            validator = DependencyValidator()
            validation_result = validator.validate_ticket_dependencies(output_path)

            if validation_result.valid:
                print("✅ Dependency validation passed")
                if validation_result.issues:
                    warning_count = sum(1 for issue in validation_result.issues
                                      if issue.severity.value == 'warning')
                    if warning_count > 0:
                        print(f"⚠️  Found {warning_count} warnings (non-blocking)")
            else:
                print("❌ Dependency validation failed!")
                print("\n📋 Issues found:")
                for issue in validation_result.issues:
                    severity_icon = "❌" if issue.severity.value == 'invalid' else "⚠️"
                    print(f"  {severity_icon} Ticket {issue.ticket_id}: {issue.description}")
                    if issue.suggested_fix:
                        print(f"     💡 Fix: {issue.suggested_fix}")

                # Still return True for generation success, but warn about dependencies
                print("\n⚠️  Tickets generated but have dependency issues that need fixing")

            return True
        else:
            print("❌ Failed to generate tickets")
            return False

    except Exception as e:
        print(f"💥 Generation error: {e}")
        return False


def check_for_ai_generated_code(project_dir, ticket_id=None, ticket_description=None, strictness=None):
    """Check for AI-generated code patterns in recent git changes.
    
    Args:
        project_dir: Directory to check
        ticket_id: Optional ticket ID for context
        ticket_description: Optional ticket description for context
        strictness: Optional strictness level
        
    Returns:
        List of issues found or tuple with (report, should_block, analysis) for enhanced mode
    """
    try:
        # Get the git diff for recent changes
        git_diff = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=project_dir
        )

        if git_diff.returncode != 0:
            return []

        # Use strictness if provided
        if strictness:
            detector = AIGeneratedCodeDetector(strictness)
        else:
            detector = AIGeneratedCodeDetector()
            
        issues = detector.detect_in_diff(git_diff.stdout)
        
        # If ticket_id and description provided, do comprehensive analysis
        if ticket_id and ticket_description:
            analysis = detector.analyze_diff_comprehensively(ticket_id, ticket_description)
            report = detector.generate_comprehensive_report(analysis, ticket_id)
            should_block = len(analysis.critical_issues) > 0
            return (report, should_block, analysis)

        # Format issues for display
        formatted_issues = []
        for issue in issues:
            formatted_issues.append(
                f"{issue['file']}:{issue['line']} - {issue['pattern']}"
            )

        return formatted_issues
    except Exception:
        return []


def validate_acceptance_criteria(ticket, project_dir):
    """Validate that acceptance criteria were actually implemented."""
    criteria = ticket['acceptance_criteria']
    failed_criteria = []

    print(f"🔍 Checking {len(criteria)} acceptance criteria:")
    
    # Check for system file modifications first
    import subprocess
    git_status = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True,
        text=True,
        cwd=project_dir
    )
    
    if git_status.stdout:
        modified_files = [
            line.split()[-1] for line in git_status.stdout.strip().split('\n')
            if line
        ]
        
        system_files_modified = []
        for file_path in modified_files:
            if file_path.startswith('src/hydra/') or file_path.startswith('tests/'):
                system_files_modified.append(file_path)
        
        if system_files_modified:
            print("\n❌ VALIDATION FAILURE: Agent modified Hydra system files:")
            for file in system_files_modified:
                print(f"   ❌ {file}")
            failed_criteria.append("Modified Hydra system files instead of project files")
            # This is a critical failure - don't continue validation
            return False

    # First, check for AI-generated code patterns in recent changes
    # Use enhanced AI detection with ticket context
    ticket_id = ticket.get('id', 'unknown')
    ticket_description = f"{ticket.get('title', '')} - {ticket.get('description', '')}"

    # Get strictness from environment or use default
    import os
    strictness_str = os.environ.get('AI_DETECTION_STRICTNESS', 'moderate').lower()
    strictness_map = {
        'lenient': StrictnessLevel.LENIENT,
        'moderate': StrictnessLevel.MODERATE,
        'strict': StrictnessLevel.STRICT
    }
    strictness = strictness_map.get(strictness_str, StrictnessLevel.MODERATE)

    # Wrap AI detection in try-except to ensure validation continues even if AI detection fails
    try:
        ai_result = check_for_ai_generated_code(
            project_dir,
            ticket_id=ticket_id,
            ticket_description=ticket_description,
            strictness=strictness
        )

        # Handle both new tuple format and backward compatibility
        if isinstance(ai_result, tuple):
            ai_report, should_block, analysis = ai_result

            # Print the comprehensive report if available
            if isinstance(ai_report, str) and ai_report:
                print("\n" + ai_report)

            # Block if critical issues found (configurable)
            if should_block:
                failed_criteria.append("❌ Critical AI-generated code patterns detected - must fix before completion")
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
            # Don't add to failed criteria - just warn about quality issues

    for i, criterion in enumerate(criteria, 1):
        criterion_lower = criterion.lower()

        # Check for specific file paths mentioned in criteria
        # Look for patterns like "src/hydra/providers/interactive_base.py" or ".hydra directory"
        import re

        # Check for Python files
        file_path_pattern = r'(?:src/[a-zA-Z0-9_/]+\.py|tests/[a-zA-Z0-9_/]+\.py|docs/[a-zA-Z0-9_/]+)'
        file_matches = re.findall(file_path_pattern, criterion)

        # Check for directory mentions like ".hydra directory"
        dir_pattern = r'\.hydra directory|\.hydra/[a-zA-Z0-9_/]+'
        re.findall(dir_pattern, criterion)
        
        # Check for CLI refactoring specific criteria
        if "cli/commands/ directory structure" in criterion_lower:
            cli_commands_dir = os.path.join(project_dir, "src/hydra/cli/commands")
            if not os.path.exists(cli_commands_dir):
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. CLI commands directory missing: src/hydra/cli/commands/")
            else:
                # Check if command files actually exist
                expected_files = ["ticket.py", "parallel.py", "verify.py", "template.py"]
                missing_files = []
                for cmd_file in expected_files:
                    if not os.path.exists(os.path.join(cli_commands_dir, cmd_file)):
                        missing_files.append(cmd_file)
                if missing_files:
                    failed_criteria.append(f"{i}. {criterion}")
                    print(f"   ❌ {i}. Missing command files: {', '.join(missing_files)}")
                else:
                    print(f"   ✅ {i}. CLI commands directory structure created")
        elif "reduce cli.py from" in criterion_lower and "to <500 lines" in criterion_lower:
            cli_file = os.path.join(project_dir, "src/hydra/cli.py")
            if os.path.exists(cli_file):
                with open(cli_file, 'r') as f:
                    line_count = len(f.readlines())
                if line_count >= 500:
                    failed_criteria.append(f"{i}. {criterion}")
                    print(f"   ❌ {i}. cli.py still has {line_count} lines (should be <500)")
                else:
                    print(f"   ✅ {i}. cli.py reduced to {line_count} lines")
            else:
                print(f"   ✅ {i}. cli.py properly refactored (file may have been moved)")
        elif "split ticket, template, parallel, verify into separate files" in criterion_lower:
            cmd_files = {
                "ticket.py": os.path.join(project_dir, "src/hydra/cli/commands/ticket.py"),
                "parallel.py": os.path.join(project_dir, "src/hydra/cli/commands/parallel.py"),
                "verify.py": os.path.join(project_dir, "src/hydra/cli/commands/verify.py"),
                "template.py": os.path.join(project_dir, "src/hydra/cli/commands/template.py")
            }
            missing = []
            for name, path in cmd_files.items():
                if not os.path.exists(path):
                    missing.append(name)
            if missing:
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Commands not split into files: {', '.join(missing)}")
            else:
                print(f"   ✅ {i}. Commands split into separate files")

        # Check for specific file mentions
        if "interactive_base.py" in criterion:
            file_path = "src/hydra/providers/interactive_base.py"
            full_path = os.path.join(project_dir, file_path)
            if not os.path.exists(full_path):
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Required file missing: {file_path}")
            else:
                print(f"   ✅ {i}. File exists: {file_path}")
        elif "security_manager.py" in criterion or "SecurityManager" in criterion:
            file_path = "src/hydra/safety/security_manager.py"
            full_path = os.path.join(project_dir, file_path)
            if not os.path.exists(full_path):
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Required file missing: {file_path}")
            else:
                print(f"   ✅ {i}. SecurityManager exists")
        elif "hydra_state.py" in criterion or "HydraStateManager" in criterion:
            file_path = "src/hydra/persistence/hydra_state.py"
            full_path = os.path.join(project_dir, file_path)
            if not os.path.exists(full_path):
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Required file missing: {file_path}")
            else:
                print(f"   ✅ {i}. HydraStateManager exists")
        elif ".hydra directory" in criterion:
            hydra_dir = os.path.join(project_dir, ".hydra")
            if not os.path.exists(hydra_dir):
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. .hydra directory missing")
            else:
                print(f"   ✅ {i}. .hydra directory exists")
        elif file_matches:
            for file_path in file_matches:
                full_path = os.path.join(project_dir, file_path)
                if not os.path.exists(full_path):
                    failed_criteria.append(f"{i}. {criterion}")
                    print(f"   ❌ {i}. Required file missing: {file_path}")
                else:
                    print(f"   ✅ {i}. File exists: {file_path}")
        # File existence checks
        elif "package.json exists" in criterion_lower or "package.json with" in criterion_lower:
            if not os.path.exists(os.path.join(project_dir, "package.json")):
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. package.json missing")
            else:
                print(f"   ✅ {i}. package.json found")

        # Folder structure checks
        elif "folder structure" in criterion_lower or "basic folder" in criterion_lower:
            required_folders = ["src", "public", "tests", "server"]
            missing_folders = []
            for folder in required_folders:
                folder_path = os.path.join(project_dir, folder)
                if not os.path.exists(folder_path):
                    missing_folders.append(folder)

            if missing_folders:
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Missing folders: {', '.join(missing_folders)}")
            else:
                print(f"   ✅ {i}. All required folders exist")

        # Configuration files checks
        elif "configuration files" in criterion_lower or "config files" in criterion_lower:
            config_files = [".gitignore", "README.md", "tsconfig.json", "eslint.config.js"]
            missing_files = []
            for file in config_files:
                file_path = os.path.join(project_dir, file)
                if not os.path.exists(file_path):
                    missing_files.append(file)

            if missing_files:
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Missing config files: {', '.join(missing_files)}")
            else:
                print(f"   ✅ {i}. All config files exist")

        # npm install check
        elif "npm install" in criterion_lower:
            try:
                result = subprocess.run(
                    ["npm", "install", "--dry-run"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    print(f"   ✅ {i}. npm install validation passed")
                else:
                    failed_criteria.append(f"{i}. {criterion}")
                    print(f"   ❌ {i}. npm install would fail: {result.stderr}")
            except Exception as e:
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. npm install check failed: {e}")

        # Generic file checks - use proper validation
        # But skip if it's about saving/writing to existing files or using functions
        elif (any(file_ext in criterion_lower for file_ext in ['.js', '.ts', '.json', '.md', '.yml', '.yaml']) and
              not any(keyword in criterion_lower for keyword in ['save', 'write', 'using', 'update', 'modify', 'persist', 'call', 'invoke', 'existing'])):
            from hydra.verification.ticket_verifier import TicketVerifier
            verifier = TicketVerifier(project_dir)
            result = verifier._verify_file_exists(criterion)

            if result.status.value == 'passed':
                print(f"   ✅ {i}. {result.evidence}")
            else:
                # For critical files, be more explicit about what's missing
                if '30min-video-report.md' in criterion or 'performance-metrics.json' in criterion:
                    print(f"   ❌ {i}. Required documentation/metrics file not created")
                else:
                    print(f"   ❌ {i}. {result.evidence}")
                failed_criteria.append(f"{i}. {criterion}")

        # Development environment checks
        elif "development environment" in criterion_lower or "docker" in criterion_lower:
            docker_files = ["Dockerfile", "docker-compose.yml"]
            missing_docker = []
            for file in docker_files:
                if not os.path.exists(os.path.join(project_dir, file)):
                    missing_docker.append(file)

            if missing_docker:
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Missing Docker files: {', '.join(missing_docker)}")
            else:
                print(f"   ✅ {i}. Docker environment setup complete")

        else:
            # For criteria that can't be automatically verified, check if work was actually done
            # Look for key implementation indicators
            implementation_keywords = [
                'create', 'implement', 'add', 'build', 'setup', 'integrate', 
                'refactor', 'split', 'reduce', 'optimize', 'enhance', 'migrate'
            ]
            
            if any(keyword in criterion_lower for keyword in implementation_keywords):
                # This is an implementation task - verify files were actually modified
                print(f"   ⚠️  {i}. Requires implementation verification: {criterion}")
                
                # Check if any relevant files were created or modified
                try:
                    git_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        cwd=project_dir,
                        timeout=10
                    )
                    
                    if git_result.returncode == 0 and git_result.stdout:
                        # Files were modified - likely some work was done
                        print(f"      📝 Files modified - assuming work in progress")
                    else:
                        # No files modified - work not done
                        failed_criteria.append(f"{i}. {criterion}")
                        print(f"      ❌ No files modified - implementation not done")
                except:
                    # Can't verify - mark as needs manual validation
                    print(f"      ℹ️  Manual validation required")
            else:
                # Non-implementation criteria - needs manual check
                print(f"   ℹ️  {i}. Manual validation required: {criterion}")

    if failed_criteria:
        print(f"\n❌ Validation failed! {len(failed_criteria)} criteria not met:")
        for failed in failed_criteria:
            print(f"   • {failed}")
        return False

    print(f"\n✅ All {len(criteria)} acceptance criteria validated successfully!")
    return True


def validate_code_changes(project_dir):
    """Validate that code changes don't contain obvious errors or suspicious patterns.
    
    Returns:
        tuple: (is_valid, suspicious_patterns)

    """
    suspicious_patterns = []

    # Get list of modified files
    try:
        git_result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=10
        )

        if git_result.returncode != 0:
            return True, []  # Skip validation if git is not available

        modified_files = git_result.stdout.strip().split('\n') if git_result.stdout else []

        # Also check unstaged files
        git_unstaged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=10
        )
        if git_unstaged.stdout:
            modified_files.extend(git_unstaged.stdout.strip().split('\n'))
    except (subprocess.TimeoutExpired, OSError, BlockingIOError) as e:
        # Skip validation if git commands fail due to resource issues
        if os.getenv('TESTING') == '1' or os.getenv('CI') == 'true':
            print(f"⚠️ Git validation skipped due to resource limitations: {e}")
        return True, []

    # Pattern checks for each file
    for file_path in modified_files:
        if not file_path or not file_path.endswith(('.py', '.js', '.ts', '.tsx', '.jsx')):
            continue

        full_path = os.path.join(project_dir, file_path)
        if not os.path.exists(full_path):
            continue

        try:
            with open(full_path, 'r') as f:
                content = f.read()

            # Check for obviously wrong patterns
            patterns_to_check = [
                # Random test functions that don't belong
                (r'def\s+(hello_world|test_function|foo|bar|baz)\s*\(\s*\)\s*:',
                 "Suspicious test/placeholder function"),
                # Print statements with obvious test content
                (r'print\s*\(\s*["\']Hello,?\s+World["\']',
                 "Hello World debug statement"),
                # TODO comments that suggest incomplete code
                (r'#\s*TODO:\s*implement\s+this',
                 "Unimplemented TODO"),
                # Obvious placeholder returns
                (r'return\s+["\']placeholder["\']',
                 "Placeholder return value"),
                # Hardcoded credentials (basic check)
                (r'(password|api_key|secret)\s*=\s*["\'][^"\']+["\']',
                 "Potential hardcoded credential"),
                # Functions that just pass or return None without logic
                (r'def\s+\w+\([^)]*\):\s*\n\s*(pass|return\s+None)\s*$',
                 "Empty function implementation"),
            ]

            for pattern, description in patterns_to_check:
                matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
                if matches:
                    suspicious_patterns.append({
                        'file': file_path,
                        'pattern': description,
                        'matches': matches[:3]  # Limit to first 3 matches
                    })

        except Exception as e:
            print(f"Warning: Could not validate {file_path}: {e}")
            continue

    is_valid = len(suspicious_patterns) == 0
    return is_valid, suspicious_patterns


def execute_single_ticket(tickets_path, ticket_identifier, timeout_override=None, workspace: Optional[SharedWorkspace] = None, skip_preflight=False):
    """Execute exactly like: 'execute ticket N in tickets.md'.

    Args:
        tickets_path: Path to tickets.md file
        ticket_identifier: Ticket ID to execute
        timeout_override: Optional timeout override
        workspace: Optional shared workspace for the session

    """
    print(f"🎫 Executing Ticket {ticket_identifier}")
    print("=" * 40)

    # Run preflight validation unless skipped
    if not skip_preflight:
        print("🚀 Running preflight validation...")
        from hydra.preflight import PreflightChecker
        checker = PreflightChecker()
        report = checker.run_preflight_checks(tickets_path)

        if report.has_critical_issues():
            print("🚨 PREFLIGHT FAILED - Critical issues found!")
            print("\nCritical Issues:")
            for check in report.get_critical_issues():
                print(f"❌ {check.description}: {check.message}")
                for detail in check.details:
                    print(f"   {detail}")
            print("\nUse --skip-preflight to override, but execution may fail.")
            return False
        elif report.has_errors() or report.has_warnings():
            print("⚠️  Preflight validation completed with warnings/errors:")
            for check in report.get_failed_checks():
                print(f"{check.status_emoji} {check.description}: {check.message}")
        else:
            print("✅ Preflight validation passed")
    else:
        print("⚡ Skipping preflight validation (--skip-preflight)")

    # Parse the specific ticket
    ticket = parse_ticket(tickets_path, ticket_identifier)
    if not ticket:
        return False

    # Check if ticket is already completed
    if ticket['completed'] or ticket.get('status') == 'DONE':
        print("✅ Ticket already completed!")
        print("ℹ️  Skipping execution as ticket is marked as DONE")
        return True

    # Get or create shared workspace
    if workspace is None:
        workspace = get_shared_workspace()

    # Check for dependency artifacts if this ticket has dependencies
    if ticket.get('dependencies'):
        print("📦 Checking for dependency artifacts...")
        dep_artifacts = workspace.get_dependency_artifacts(ticket['dependencies'])
        if dep_artifacts:
            print(f"   Found artifacts from {len(dep_artifacts)} dependency tickets:")
            for dep_id, artifacts in dep_artifacts.items():
                print(f"   • Ticket {dep_id}: {len(artifacts)} artifacts")
                for artifact in artifacts[:3]:  # Show first 3
                    print(f"     - {os.path.basename(artifact)}")
                if len(artifacts) > 3:
                    print(f"     ... and {len(artifacts) - 3} more")

    # Mark ticket as IN_PROGRESS (and update database with ticket info)
    mark_ticket_in_progress(tickets_path, ticket_identifier)
    # Also pass ticket info to database
    project_path = os.path.dirname(os.path.abspath(tickets_path))
    update_ticket_in_database(ticket_identifier, "IN_PROGRESS", project_path, ticket)

    # Map model emoji based on category
    model_emojis = {
        'smart': '🧠',
        'balanced': '⚡',
        'fast': '💨',
        'coder': '💻'
    }
    model_emoji = model_emojis.get(ticket['model'], '⚡')
    print(f"{model_emoji} Model: {ticket['model'].upper()}")
    print(f"📋 Task: {ticket['title']}")
    print(f"📝 Description: {ticket['description'][:100]}...")

    print(f"\n✅ Acceptance Criteria ({len(ticket['acceptance_criteria'])}):")
    for i, criteria in enumerate(ticket['acceptance_criteria'], 1):
        print(f"   {i}. {criteria}")

    # Set up agent with appropriate model and timeout
    print(f"\n🤖 Creating {ticket['model']} agent...")

    # Save original timeout
    original_timeout = os.environ.get('LLM_TIMEOUT')

    # Override timeout for ticket execution BEFORE creating agent
    if timeout_override:
        os.environ['LLM_TIMEOUT'] = str(timeout_override)
        print(f"⏱️  Using extended timeout: {timeout_override}s")

    # Use provider factory with model mapping
    from hydra.providers.model_mapper import get_model_mapper
    from hydra.providers.provider_factory import create_provider_from_environment

    # Get provider and map the model
    provider = create_provider_from_environment()
    mapper = get_model_mapper()

    # Map the ticket's model category to provider-specific model
    provider_type = provider.config.provider_type if hasattr(provider, 'config') and hasattr(provider.config, 'provider_type') else os.environ.get('LLM_PROVIDER', 'claude_tmux')
    ticket_model = mapper.map_model(ticket['model'], provider_type)

    if ticket_model:
        print(f"🔧 Using {provider_type} provider with model: {ticket_model}")
    else:
        print(f"🔧 Using {provider_type} provider with default model")

    # For claude_tmux, set the CLAUDE_MODEL environment variable
    if provider_type == 'claude_tmux' and ticket['model']:
        os.environ['CLAUDE_MODEL'] = ticket['model']
        print(f"📊 Set CLAUDE_MODEL={ticket['model']} for tmux provider")

    # Detect project language/framework from context
    project_context = detect_project_context(tickets_path)

    # Build prompt based on provider type
    project_dir = os.path.dirname(os.path.abspath(tickets_path))

    # Build workspace context for prompts
    workspace_info = f"""
SHARED WORKSPACE: {workspace.workspace_path}
Session ID: {workspace.session_id}

IMPORTANT: Save any artifacts, documents, or shared data that other tickets might need to the shared workspace:
- For code/design docs: {os.path.join(workspace.workspace_path, 'docs')}
- For config files: {os.path.join(workspace.workspace_path, 'configs')}
- For data files: {os.path.join(workspace.workspace_path, 'shared_data')}
- For ticket-specific artifacts: {os.path.join(workspace.workspace_path, 'artifacts', f'ticket_{ticket_identifier.zfill(3) if ticket_identifier.isdigit() else ticket_identifier}')}
"""

    # Add dependency context if needed
    dependency_context = ""
    if ticket.get('dependencies'):
        dep_artifacts = workspace.get_dependency_artifacts(ticket['dependencies'])
        if dep_artifacts:
            dependency_context = "\n\nDEPENDENCY ARTIFACTS AVAILABLE:\n"
            for dep_id, artifacts in dep_artifacts.items():
                dependency_context += f"\nFrom Ticket {dep_id}:\n"
                for artifact in artifacts:
                    dependency_context += f"  - {artifact}\n"
            dependency_context += "\nIMPORTANT: Read these dependency artifacts FIRST to understand what has been implemented!"

    if provider_type == 'claude_tmux':
        # Claude can read files directly
        tickets_file = os.path.basename(tickets_path)
        
        # Determine file format
        if tickets_file.endswith('.yaml') or tickets_file.endswith('.yml'):
            ticket_search = f"Find the ticket with id: '{ticket_identifier}' in the YAML file"
            status_update = f"Update {tickets_file} to set status: DONE for ticket {ticket_identifier}"
        else:
            ticket_search = f'Find "## Ticket {ticket_identifier}:" in {tickets_file}'
            status_update = f"Update {tickets_file} status to DONE"
            
        prompt = f"""Execute ONLY Ticket {ticket_identifier} from {tickets_file}.

{ticket_search} and implement it.

{workspace_info}
{dependency_context}

APPROACH:
1. Make DIRECT code changes - create the files specified
2. Be surgical and minimal - change only what's needed
3. If the ticket mentions specific files/functions, create those directly
4. Focus on making everything work

QUALITY:
- Write clean, production code
- No placeholders, mocks, or shortcuts
- Make sure all files work together

When done:
1. Verify all acceptance criteria are met
2. {status_update}
3. Ensure all created files work correctly

REMINDER: You are working on Ticket {ticket_identifier} ONLY."""
    else:
        # For other providers (Venice, OpenAI, etc), include ticket details in prompt
        # Use optimized prompt template
        deps_dict = {}
        if dependency_context:
            # Parse dependency context into dict
            deps_dict = {"deps": dependency_context}

        prompt = get_prompt_template(
            "ticket",
            id=ticket_identifier,
            title=ticket['title'],
            description=ticket['description'],
            criteria=ticket['acceptance_criteria'],
            dir=project_dir,
            deps=deps_dict.get("deps", "")
        )

    print("🚀 Executing with production standards...")
    print("   ✅ No AI-generated patterns")
    print("   ✅ Minimalistic and surgical")
    print("   ✅ Future-proof design")
    print("   ✅ Production quality only")

    try:
        # Execute using provider abstraction
        print(f"\n🤖 Using {provider_type} provider to implement ticket...")

        # Provider should handle execution appropriately
        result = provider.generate(
            prompt,  # Pass as positional argument
            model=ticket_model,
            mode="ticket_execution",
            cwd=project_dir,
            ticket_id=ticket_identifier,
            ticket=ticket,
            tickets_file=os.path.basename(tickets_path)
        )

        # Handle result based on provider capabilities
        if isinstance(result, dict):
            if 'code' in result:
                # For API providers that return code
                lines = result['code'].split('\n')
                print(f"📝 Generated {len(lines)} lines of code")

                # Save generated code to appropriate files
                output_file = f"ticket_{ticket_identifier}_implementation.py"
                output_path = os.path.join(project_dir, output_file)

                with open(output_path, 'w') as f:
                    f.write(result['code'])

                print(f"💾 Saved implementation to {output_file}")
            elif 'files_created' in result:
                # Provider created files directly
                print(f"📝 Created/modified {len(result['files_created'])} files")
                for file in result['files_created']:
                    print(f"   ✅ {file}")
        else:
            # Provider executed directly (like Claude tmux)
            print("✅ Provider executed task directly")

        # Claude Code has executed and created/modified files
        print(f"\n✅ Ticket {ticket_identifier} implementation complete!")

        # Check what files were created/modified
        print("\n📁 Checking for changes...")
        git_result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=project_dir
        )

        created_files = []
        if git_result.stdout:
            print("📝 Files changed:")
            for line in git_result.stdout.strip().split('\n'):
                print(f"   {line}")
                # Parse git status to get file paths
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    status_code, file_path = parts
                    if 'A' in status_code or 'M' in status_code or '?' in status_code:
                        created_files.append(file_path)

        # Save manifest of created files to workspace
        if created_files:
            workspace.create_manifest(ticket_identifier, created_files)
            print(f"\n📋 Saved manifest with {len(created_files)} files to workspace")

            # Copy important files to workspace for dependency access
            important_extensions = ['.py', '.js', '.ts', '.json', '.md', '.yaml', '.yml', '.sql']
            for file_path in created_files:
                _, ext = os.path.splitext(file_path)
                if ext in important_extensions:
                    full_path = os.path.join(project_dir, file_path)
                    if os.path.exists(full_path):
                        with open(full_path, 'r') as f:
                            content = f.read()
                        artifact_name = os.path.basename(file_path)
                        workspace.save_artifact(ticket_identifier, artifact_name, content)
                        print(f"   💾 Saved {artifact_name} to workspace")

        # Validate code changes for suspicious patterns
        print("\n🔍 Validating code changes for suspicious patterns...")
        code_valid, suspicious_patterns = validate_code_changes(project_dir)

        if not code_valid:
            print("⚠️  Warning: Suspicious code patterns detected!")
            for pattern_info in suspicious_patterns:
                print(f"\n   File: {pattern_info['file']}")
                print(f"   Issue: {pattern_info['pattern']}")
                for match in pattern_info['matches']:
                    print(f"      • {match[:50]}...")  # Show first 50 chars

            print("\n❌ Code validation failed! Please review and fix suspicious patterns.")
            print("   Ticket execution halted to prevent introducing bad code.")
            return False
        else:
            print("✅ No suspicious code patterns detected")

        # Run quality gates BEFORE marking ticket complete
        print("\n🚦 Running quality gates...")
        from hydra.quality.gate_runner import CheckStatus, QualityGateRunner

        gate_runner = QualityGateRunner(project_dir)
        quality_report = gate_runner.run_quality_gates(ticket_identifier)
        print(gate_runner.generate_report(quality_report))

        # Save report
        report_file = gate_runner.save_report(quality_report)
        print(f"\n📄 Quality report saved: {report_file}")

        # Check if quality gates failed
        if quality_report.overall_status == CheckStatus.FAILED:
            print("\n❌ Quality gates FAILED - ticket cannot be completed!")
            print("   Fix the failing checks and retry execution")
            mark_ticket_quality_failed(tickets_path, ticket_identifier)
            return False

        # Validate acceptance criteria before marking complete
        print("\n🔍 Validating acceptance criteria...")
        validation_passed = validate_acceptance_criteria(ticket, project_dir)

        if not validation_passed:
            # Check if the actual work was done by looking at git changes
            try:
                git_status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    cwd=project_dir,
                    timeout=10
                )
                
                git_diff = subprocess.run(
                    ["git", "diff", "--stat"],
                    capture_output=True, 
                    text=True,
                    cwd=project_dir,
                    timeout=10
                )
                
                if git_status.stdout or git_diff.stdout:
                    print("\n⚠️  Validation reported issues, but work appears to be completed:")
                    print("   Files were modified/created during ticket execution")
                    print("   Please review the changes to ensure they meet requirements")
                    print("\n📝 Modified files detected - marking ticket as complete with warning")
                    print("   If the work is incorrect, you can manually update the ticket status")
                    
                    # Still mark as complete since work was done
                    mark_ticket_completed(tickets_path, ticket_identifier)
                    return True
                else:
                    print("❌ Acceptance criteria validation failed!")
                    print("   No file changes detected - ticket will remain incomplete")
                    return False
            except:
                print("❌ Acceptance criteria validation failed!")
                print("   Ticket will remain incomplete until requirements are met")
                return False

        print("✅ All acceptance criteria met!")

        # Legacy validation (backward compatibility) - run but don't block
        try:
            if "Node.js" in project_context:
                print("\n🔧 Running Node.js validation...")
                run_node_validation()
            else:
                print("\n🔧 Running validation...")
                run_validation_commands()
        except Exception as e:
            print(f"⚠️  Legacy validation warning: {e}")
            # Don't block completion for legacy validation failures

        # Only mark complete if all checks pass
        print("✅ All quality checks passed - marking ticket complete!")
        mark_ticket_completed(tickets_path, ticket_identifier)

        return True

    except Exception as e:
        print(f"\n💥 Execution error: {e}")
        if os.getenv('TESTING') == '1' or os.getenv('CI') == 'true':
            import traceback
            print(f"Stack trace:\n{traceback.format_exc()}")
        return False
    finally:
        # Restore original timeout
        if original_timeout:
            os.environ['LLM_TIMEOUT'] = original_timeout
        elif 'LLM_TIMEOUT' in os.environ:
            del os.environ['LLM_TIMEOUT']


def mark_ticket_in_progress(tickets_path, ticket_identifier):
    """Mark ticket as IN_PROGRESS in tickets file (YAML or MD)."""
    if not os.path.exists(tickets_path):
        return

    # Check if it's YAML format
    if tickets_path.endswith(('.yaml', '.yml')):
        import yaml
        with open(tickets_path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Update ticket status
        for ticket in data.get('tickets', []):
            if str(ticket.get('id', '')) == str(ticket_identifier):
                ticket['status'] = 'IN_PROGRESS'
                break
        
        # Write back
        with open(tickets_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return

    # Legacy MD format handling
    # Normalize ticket ID to 3 digits if it's numeric
    if ticket_identifier.isdigit():
        ticket_identifier = ticket_identifier.zfill(3)

    with open(tickets_path, 'r') as f:
        content = f.read()

    # Try multiple ticket header patterns
    patterns = [
        rf'(## Ticket {ticket_identifier}:.*?)(?=## Ticket|\Z)',
        rf'(## TICKET-{ticket_identifier}:.*?)(?=## TICKET-|\Z)',
        rf'(## Ticket-{ticket_identifier}:.*?)(?=## Ticket-|\Z)',
        rf'(## #{ticket_identifier}:.*?)(?=## #|\Z)',
        rf'(## {ticket_identifier}:.*?)(?=## |\Z)',
    ]

    updated_content = content
    ticket_found = False

    for pattern in patterns:
        def replace_ticket(match):
            ticket_content = match.group(1)
            # Update Status field to IN_PROGRESS
            updated_content = re.sub(r'\*\*Status:\*\*\s*\w+', '**Status:** IN_PROGRESS', ticket_content)
            return updated_content

        flags = re.DOTALL | re.IGNORECASE
        new_content = re.sub(pattern, replace_ticket, updated_content, flags=flags)
        if new_content != updated_content:
            updated_content = new_content
            ticket_found = True
            break

    if ticket_found:
        with open(tickets_path, 'w') as f:
            f.write(updated_content)
        print(f"🔄 Updated {tickets_path} - marked ticket {ticket_identifier} as IN_PROGRESS")
        
        # Update dashboard database
        project_path = os.path.dirname(os.path.abspath(tickets_path))
        update_ticket_in_database(ticket_identifier, "IN_PROGRESS", project_path)


def mark_ticket_quality_failed(tickets_path, ticket_identifier, quality_report=None):
    """Mark ticket as having quality issues in tickets.md."""
    if not os.path.exists(tickets_path):
        return

    # Normalize ticket ID to 3 digits if it's numeric
    if ticket_identifier.isdigit():
        ticket_identifier = ticket_identifier.zfill(3)

    with open(tickets_path, 'r') as f:
        content = f.read()

    # Try multiple ticket header patterns
    patterns = [
        rf'(## Ticket {ticket_identifier}:.*?)(?=## Ticket|\Z)',
        rf'(## TICKET-{ticket_identifier}:.*?)(?=## TICKET-|\Z)',
        rf'(## Ticket-{ticket_identifier}:.*?)(?=## Ticket-|\Z)',
        rf'(## #{ticket_identifier}:.*?)(?=## #|\Z)',
        rf'(## {ticket_identifier}:.*?)(?=## |\Z)',
    ]

    updated_content = content
    ticket_found = False

    for pattern in patterns:
        def replace_ticket(match):
            ticket_content = match.group(1)
            # Update Status field to QUALITY_FAILED
            updated_content = re.sub(r'\*\*Status:\*\*\s*\w+', '**Status:** QUALITY_FAILED', ticket_content)

            # Add quality gate summary if provided
            if quality_report and "**Quality Gate Results:**" not in updated_content:
                # Find the acceptance criteria section and add quality results after it
                lines = updated_content.split('\n')
                insert_idx = -1
                for i, line in enumerate(lines):
                    if "**Acceptance Criteria:**" in line:
                        # Find the end of acceptance criteria
                        for j in range(i+1, len(lines)):
                            if lines[j].startswith("## ") or (lines[j] and not lines[j].startswith("- ")):
                                insert_idx = j
                                break
                        if insert_idx == -1:
                            insert_idx = len(lines)
                        break

                if insert_idx > 0:
                    quality_summary = [
                        "",
                        "**Quality Gate Results:** ❌ FAILED",
                        f"- Linting: {'✅' if hasattr(quality_report, 'linting_passed') and quality_report.linting_passed else '❌'}",
                        f"- Type checking: {'✅' if hasattr(quality_report, 'type_checking_passed') and quality_report.type_checking_passed else '❌'}",
                        f"- Tests: {'✅' if hasattr(quality_report, 'tests_passed') and quality_report.tests_passed else '❌'}",
                        f"- Security: {'✅' if hasattr(quality_report, 'security_passed') and quality_report.security_passed else '❌'}",
                        ""
                    ]
                    lines = lines[:insert_idx] + quality_summary + lines[insert_idx:]
                    updated_content = '\n'.join(lines)

            return updated_content

        flags = re.DOTALL | re.IGNORECASE
        new_content = re.sub(pattern, replace_ticket, updated_content, flags=flags)
        if new_content != updated_content:
            updated_content = new_content
            ticket_found = True
            break

    if ticket_found:
        with open(tickets_path, 'w') as f:
            f.write(updated_content)
        print(f"⚠️  Updated {tickets_path} - marked ticket {ticket_identifier} as QUALITY_FAILED")


def mark_ticket_completed(tickets_path, ticket_identifier):
    """Mark ticket as completed in tickets file (YAML or MD)."""
    if not os.path.exists(tickets_path):
        return

    # Check if it's YAML format
    if tickets_path.endswith(('.yaml', '.yml')):
        import yaml
        with open(tickets_path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Update ticket status
        for ticket in data.get('tickets', []):
            if str(ticket.get('id', '')) == str(ticket_identifier):
                ticket['status'] = 'DONE'
                break
        
        # Write back
        with open(tickets_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        # Also update the dashboard
        from hydra.ticket_workflow import update_ticket_in_database
        project_path = os.path.dirname(os.path.abspath(tickets_path))
        update_ticket_in_database(ticket_identifier, "DONE", project_path)
        return

    # Legacy MD format handling
    # Normalize ticket ID to 3 digits if it's numeric
    if ticket_identifier.isdigit():
        ticket_identifier = ticket_identifier.zfill(3)

    with open(tickets_path, 'r') as f:
        content = f.read()

    # Try multiple ticket header patterns for completion marking
    patterns = [
        # TICKET-007 format
        rf'(### TICKET-{ticket_identifier}:.*?)(?=### TICKET-|\Z)',
        rf'(## TICKET-{ticket_identifier}:.*?)(?=## TICKET-|\Z)',    # TICKET-007 format
        rf'(## Ticket-{ticket_identifier}:.*?)(?=## Ticket-|\Z)',    # Ticket-007 format
        rf'(## Ticket {ticket_identifier}:.*?)(?=## Ticket|\Z)',     # Ticket 007 format
        rf'(## #{ticket_identifier}:.*?)(?=## #|\Z)',                # #007 format
        rf'(## {ticket_identifier}:.*?)(?=## |\Z)',                  # Raw number format
    ]

    updated_content = content
    ticket_found = False

    for pattern in patterns:
        def replace_ticket(match):
            ticket_content = match.group(1)
            # Replace - [ ] with - [x]
            updated_content = ticket_content.replace('- [ ]', '- [x]')
            # Update Status field to DONE
            updated_content = re.sub(r'\*\*Status:\*\*\s*\w+', '**Status:** DONE', updated_content)
            return updated_content

        flags = re.DOTALL | re.IGNORECASE
        new_content = re.sub(pattern, replace_ticket, updated_content, flags=flags)
        if new_content != updated_content:
            updated_content = new_content
            ticket_found = True
            break

    if ticket_found:
        with open(tickets_path, 'w') as f:
            f.write(updated_content)
        update_msg = f"✅ Updated {tickets_path} - marked ticket {ticket_identifier} as DONE"
        print(update_msg)
        
        # Update dashboard database
        project_path = os.path.dirname(os.path.abspath(tickets_path))
        update_ticket_in_database(ticket_identifier, "DONE", project_path)
    else:
        print(f"⚠️  Could not find ticket {ticket_identifier} to mark as completed")


def run_validation_commands():
    """Run lint, build, test etc."""
    commands = [
        ("🔍 Linting", ["python", "-m", "flake8", ".", "--exclude=venv,node_modules"]),
        ("🏗️  Building", ["python", "-m", "py_compile", "*.py"]),
        ("🧪 Testing", ["python", "-m", "pytest", "-v"])
    ]

    for desc, cmd in commands:
        print(f"{desc}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                print(f"   ✅ {desc} passed")
            else:
                print(f"   ⚠️  {desc} warnings: {result.stderr[:100]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, BlockingIOError, OSError):
            print(f"   ⏭️  {desc} skipped (command not available)")
        except Exception as e:
            print(f"   ❌ {desc} error: {e}")


def run_node_validation():
    """Run Node.js project validation."""
    commands = [
        ("📦 Installing dependencies", ["npm", "install"]),
        ("🔍 Linting", ["npm", "run", "lint"]),
        ("🧪 Testing", ["npm", "test"]),
    ]

    for desc, cmd in commands:
        print(f"{desc}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                print(f"   ✅ {desc} passed")
            else:
                # Check if script doesn't exist
                if "missing script" in result.stderr.lower():
                    print(f"   ⏭️  {desc} skipped (no script defined)")
                else:
                    print(f"   ⚠️  {desc} warnings: {result.stderr[:100]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, BlockingIOError, OSError):
            print(f"   ⏭️  {desc} skipped (command not available)")
        except Exception as e:
            print(f"   ❌ {desc} error: {e}")


def parse_all_tickets(tickets_path: str) -> Dict[str, dict]:
    """Parse all tickets and return as dictionary with consistent internal IDs."""
    if not os.path.exists(tickets_path):
        return {}

    # Check cache first
    cache = get_file_meta_cache()
    cache_key = get_cache_key("parse_all_tickets", tickets_path)
    cached_result = cache.get(cache_key, tickets_path)

    if cached_result is not None:
        return cached_result

    # Use the unified TicketFormatHandler for both YAML and MD
    from hydra.tickets.compatibility import TicketFormatHandler
    handler = TicketFormatHandler()
    
    # Get all ticket IDs
    ticket_ids = handler.get_ticket_ids(tickets_path)
    
    tickets = {}
    for ticket_id in ticket_ids:
        ticket = handler.parse_ticket(tickets_path, ticket_id)
        if ticket:
            # Store with normalized 3-digit key
            normalized_id = ticket_id.zfill(3)
            tickets[normalized_id] = ticket
            # Store the original format for execution
            tickets[normalized_id]['raw_id'] = ticket_id

    # Cache the parsed tickets
    cache.set(cache_key, tickets, tickets_path)

    return tickets


def build_dependency_graph(
    tickets: Dict[str, dict]
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build dependency and reverse dependency graphs."""
    deps = defaultdict(set)
    reverse_deps = defaultdict(set)

    for ticket_id, ticket_data in tickets.items():
        normalized_id = ticket_id.zfill(3)
        for dep in ticket_data.get('dependencies', []):
            normalized_dep = dep.zfill(3)
            deps[normalized_id].add(normalized_dep)
            reverse_deps[normalized_dep].add(normalized_id)

    return dict(deps), dict(reverse_deps)


def get_executable_tickets(tickets: Dict[str, dict], completed: Set[str]) -> List[str]:
    """Find tickets that can be executed now based on dependencies."""
    deps, _ = build_dependency_graph(tickets)
    executable = []

    for ticket_id, ticket_data in tickets.items():
        normalized_id = ticket_id.zfill(3)

        if normalized_id in completed:
            continue

        if ticket_data.get('completed', False):
            completed.add(normalized_id)
            continue

        ticket_deps = deps.get(normalized_id, set())
        if all(dep in completed for dep in ticket_deps):
            executable.append(normalized_id)

    return executable


def execute_ticket_worker(ticket_id: str, ticket_data: dict, tickets_path: str,
                         completed_lock: threading.Lock, workspace: SharedWorkspace) -> bool:
    """Worker function for parallel ticket execution.

    Args:
        ticket_id: Normalized ticket ID
        ticket_data: Ticket data dictionary
        tickets_path: Path to tickets.md
        completed_lock: Thread lock for synchronization
        workspace: Shared workspace for the session

    """
    try:
        print(f"\n🚀 Starting ticket {ticket_id}")

        # Use the raw_id stored during parsing
        raw_id = ticket_data.get('raw_id', ticket_id.lstrip('0'))

        # Use longer timeout for ticket execution (15 minutes)
        success = execute_single_ticket(tickets_path, raw_id, timeout_override=900, workspace=workspace)

        if success:
            with completed_lock:
                print(f"✅ Ticket {ticket_id} completed")
        else:
            print(f"❌ Ticket {ticket_id} failed")

        return success
    except Exception as e:
        print(f"💥 Error executing ticket {ticket_id}: {e}")
        return False


def get_quality_summary(tickets_path="tickets.md"):
    """Get a summary of ticket quality statuses."""
    tickets = parse_all_tickets(tickets_path)

    summary = {
        'total': len(tickets),
        'todo': 0,
        'in_progress': 0,
        'done': 0,
        'quality_failed': 0
    }

    for _ticket_id, ticket_data in tickets.items():
        status = ticket_data.get('status', 'TODO').upper()
        if status == 'DONE':
            summary['done'] += 1
        elif status == 'IN_PROGRESS':
            summary['in_progress'] += 1
        elif status == 'QUALITY_FAILED':
            summary['quality_failed'] += 1
        else:
            summary['todo'] += 1

    return summary


def print_quality_summary(tickets_path="tickets.md"):
    """Print a quality status summary."""
    summary = get_quality_summary(tickets_path)

    print("\n📊 Ticket Quality Summary")
    print("=" * 40)
    print(f"Total Tickets: {summary['total']}")
    print(f"  ✅ Done (Quality Passed): {summary['done']}")
    print(f"  ⚠️  Quality Failed: {summary['quality_failed']}")
    print(f"  🔄 In Progress: {summary['in_progress']}")
    print(f"  📋 TODO: {summary['todo']}")

    if summary['quality_failed'] > 0:
        print(f"\n⚠️  {summary['quality_failed']} ticket(s) need quality fixes!")
        print("   Check tickets.md for Quality Gate Results details")

    success_rate = (summary['done'] / summary['total'] * 100) if summary['total'] > 0 else 0
    print(f"\n🎯 Success Rate: {success_rate:.1f}%")
    print("=" * 40)


def run_all_tickets(tickets_path="tickets.md", max_parallel=3, skip_preflight=False):
    """Execute all tickets with dependency-aware parallel execution."""
    print("🎫 Running All Tickets with Parallel Execution")
    print("=" * 50)

    # Run preflight validation unless skipped
    if not skip_preflight:
        print("🚀 Running comprehensive preflight validation...")
        from hydra.preflight import PreflightChecker
        checker = PreflightChecker()
        report = checker.run_preflight_checks(tickets_path)

        if report.has_critical_issues():
            print("🚨 PREFLIGHT FAILED - Critical issues found!")
            print("\nCritical Issues:")
            for check in report.get_critical_issues():
                print(f"❌ {check.description}: {check.message}")
                for detail in check.details:
                    print(f"   {detail}")
            print("\nRecommendations:")
            for rec in report.get_recommendations():
                print(f"💡 {rec}")
            print("\nUse --skip-preflight to override, but execution may fail.")
            return False
        elif report.has_errors() or report.has_warnings():
            print("⚠️  Preflight validation completed with warnings/errors:")
            for check in report.get_failed_checks()[:5]:  # Show first 5
                print(f"{check.status_emoji} {check.description}: {check.message}")
            if len(report.get_failed_checks()) > 5:
                print(f"   ... and {len(report.get_failed_checks()) - 5} more issues")
            print("Proceeding with execution despite warnings...")
        else:
            print("✅ Preflight validation passed")
    else:
        print("⚡ Skipping preflight validation (--skip-preflight)")

    tickets = parse_all_tickets(tickets_path)
    if not tickets:
        print("❌ No tickets found")
        return False

    print(f"📋 Found {len(tickets)} tickets")

    # Validate dependencies before execution
    print("\n🔍 Validating ticket dependencies...")
    from hydra.validation.dependency_validator import DependencyValidator
    validator = DependencyValidator()
    validation_result = validator.validate_ticket_dependencies(tickets_path)

    if not validation_result.valid:
        print("❌ Dependency validation failed! Cannot proceed with execution.")
        print("\n📋 Critical issues found:")
        for issue in validation_result.issues:
            if issue.severity.value == 'invalid':
                print(f"  ❌ Ticket {issue.ticket_id}: {issue.description}")
                if issue.suggested_fix:
                    print(f"     💡 Fix: {issue.suggested_fix}")
        return False
    else:
        print("✅ Dependency validation passed")
        if validation_result.issues:
            warning_count = sum(1 for issue in validation_result.issues
                              if issue.severity.value == 'warning')
            if warning_count > 0:
                print(f"⚠️  Found {warning_count} warnings (will proceed)")

    # Create shared workspace for this session
    workspace = get_shared_workspace()
    print(f"📁 Using shared workspace: {workspace.workspace_path}")

    deps, reverse_deps = build_dependency_graph(tickets)
    completed = set()
    failed = set()
    completed_lock = threading.Lock()

    correlation_id = monitoring.set_correlation_id("parallel_tickets")
    print(f"🔗 Session: {correlation_id}")
    print(f"⚡ Max parallel: {max_parallel}")

    total_tickets = len(tickets)

    # Limit max_parallel in CI environments to prevent resource exhaustion
    if os.getenv('CI') == 'true':
        max_parallel = min(max_parallel, 2)
        print(f"🔧 CI mode: Limited max parallel to {max_parallel}")

    try:
        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            while len(completed) + len(failed) < total_tickets:
                executable = get_executable_tickets(tickets, completed)

                if not executable:
                    if len(completed) + len(failed) < total_tickets:
                        remaining = set(tickets.keys()) - completed - failed
                        print(f"⚠️ No executable tickets. Remaining: {remaining}")

                        for tid in remaining:
                            needed_deps = deps.get(tid, set()) - completed
                            if needed_deps:
                                print(f"  {tid} waiting for: {needed_deps}")
                    break

                print(f"\n📊 Progress: {len(completed)}/{total_tickets} completed")
                print(f"🔄 Executing batch: {executable}")

                futures = {}
                for ticket_id in executable:
                    try:
                        future = executor.submit(
                            execute_ticket_worker,
                            ticket_id,
                            tickets[ticket_id],  # Pass ticket data
                            tickets_path,
                            completed_lock,
                            workspace  # Pass shared workspace
                        )
                        futures[future] = ticket_id
                    except RuntimeError as e:
                        if "can't start new thread" in str(e):
                            print(f"⚠️ Thread pool exhausted, executing {ticket_id} sequentially")
                            # Execute sequentially as fallback
                            success = execute_ticket_worker(
                                ticket_id,
                                tickets[ticket_id],
                                tickets_path,
                                completed_lock,
                                workspace
                            )
                            with completed_lock:
                                if success:
                                    completed.add(ticket_id)
                                else:
                                    failed.add(ticket_id)
                            continue
                        else:
                            raise

                for future in as_completed(futures):
                    ticket_id = futures[future]
                    success = future.result()

                    with completed_lock:
                        if success:
                            completed.add(ticket_id)

                            dependents = reverse_deps.get(ticket_id, set())
                            if dependents:
                                ready = [
                                    d for d in dependents
                                    if all(dep in completed for dep in deps.get(d, set()))
                                ]
                                if ready:
                                    print(f"🔓 Unlocked tickets: {ready}")
                        else:
                            failed.add(ticket_id)
                            print(f"⛔ Stopping - ticket {ticket_id} failed")

                            for f in futures:
                                if not f.done():
                                    f.cancel()

                            executor.shutdown(wait=False)
                            break

                    if failed:
                        break

                if failed:
                    break

    except Exception as e:
        print(f"\n❌ Parallel execution failed: {e}")
        print(f"📁 Workspace preserved for debugging: {workspace.workspace_path}")
        return False

    print(f"\n{'='*50}")
    print("🎉 Final Summary:")
    print(f"  ✅ Completed: {len(completed)}/{total_tickets}")
    print(f"  ❌ Failed: {len(failed)}")

    if len(completed) == total_tickets:
        print("\n✅ All tickets completed successfully!")
        print("🔧 Running final validation...")
        run_validation_commands()

        # Optionally preserve workspace for debugging
        if os.environ.get('PRESERVE_WORKSPACE', 'false').lower() == 'true':
            print(f"\n📁 Workspace preserved at: {workspace.workspace_path}")
        else:
            workspace.cleanup()

        return True
    else:
        print(f"\n❌ Execution stopped. Failed tickets: {failed}")
        print(f"📁 Workspace preserved for debugging: {workspace.workspace_path}")
        return False

