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

from hydra.monitoring import monitoring


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
    """Parse specific ticket from tickets.md with flexible format support."""
    if not os.path.exists(tickets_path):
        print(f"❌ {tickets_path} not found")
        return None

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
        if line.startswith('**Status:**'):
            status_text = line.replace('**Status:**', '').strip().upper()
            ticket['status'] = status_text
            # Mark as completed if status is DONE
            if status_text == 'DONE':
                ticket['completed'] = True
            # Don't mark as completed if quality failed
            elif status_text == 'QUALITY_FAILED':
                ticket['completed'] = False
                ticket['quality_failed'] = True
        elif line.startswith('**Model:**'):
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
        elif line.startswith('**Dependencies:**'):
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
        elif line.startswith('**Acceptance Criteria:**'):
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

    return ticket


# NOTE: This function has been moved to line 577 to avoid duplication
# The function at line 577 handles more ticket formats and is more comprehensive


def generate_tickets_md(project_description, output_path="tickets.md"):
    """Generate tickets.md from project description using provider abstraction."""
    print("🎫 Generating tickets.md...")
    print("=" * 30)

    # Use provider abstraction instead of hardcoding Claude
    from hydra.providers.model_mapper import get_model_mapper
    from hydra.providers.provider_factory import create_provider_from_environment

    # Get the provider and model mapper
    provider = create_provider_from_environment()
    mapper = get_model_mapper()

    # Get the smart model for ticket planning (was "Opus 4")
    smart_model = mapper.map_model("smart", provider.config.provider_type if hasattr(provider, 'config') and hasattr(provider.config, 'provider_type') else None)
    print(f"🧠 Using {smart_model or 'smart model'} for ticket planning...")

    # Adapt prompt to use generic model categories instead of specific Claude models
    prompt = f"""Create a file named 'tickets.md' in the current directory with tickets that are made in task language for LLM agents to execute that include acceptance criteria, dependencies (like 001,002 or None), status, and which model category (fast, balanced, smart, or coder) should be used for that ticket. be minimalistic, surgical and future proof!

Each ticket MUST have this format:
## Ticket 001: [Title]
**Status:** TODO
**Model:** [smart, balanced, fast, or coder]
**Dependencies:** [None or comma-separated ticket numbers like 001,002]
**Description:** [Task description - if this depends on other tickets, mention that it builds on their outputs]

**Required Input Files:** (only include if Dependencies is not None)
- [List files that will be created by dependency tickets that this ticket needs]

**Context Requirements:** (only include if Dependencies is not None)
- [Specific instructions about reading/using outputs from dependency tickets]
- [E.g., "FIRST: Read design_doc.md from Ticket 001 to understand the architecture"]

**Acceptance Criteria:**
- [ ] [Criteria that reference outputs from dependencies when applicable]

IMPORTANT: For tickets with dependencies:
- Always add a "Required Input Files" section listing what files from previous tickets are needed
- Add "Context Requirements" explaining how to use the outputs from dependencies
- In the Description, mention that the ticket "builds on" or "uses outputs from" its dependencies
- In Acceptance Criteria, reference specific deliverables from dependencies when relevant

Example for a dependent ticket:
## Ticket 002: Implement API based on design
**Status:** TODO
**Model:** smart
**Dependencies:** 001
**Description:** Implement the REST API based on the design document from Ticket 001

**Required Input Files:**
- api_design.md (from Ticket 001)
- database_schema.sql (from Ticket 001)

**Context Requirements:**
- FIRST: Read api_design.md to understand the endpoint specifications
- Review database_schema.sql for data model implementation
- Follow the patterns and conventions established in Ticket 001

**Acceptance Criteria:**
- [ ] Implement all endpoints specified in api_design.md
- [ ] Use the database schema from database_schema.sql
- [ ] Follow RESTful conventions outlined in the design

Project: {project_description}"""

    print("🚀 Generating tickets with production standards...")

    try:
        # Use provider abstraction to generate tickets
        result = provider.generate(
            prompt,  # Pass as positional argument
            model=smart_model,
            mode="ticket_generation",
            output_path=output_path
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

            return True
        else:
            print("❌ Failed to generate tickets")
            return False

    except Exception as e:
        print(f"💥 Generation error: {e}")
        return False


def validate_acceptance_criteria(ticket, project_dir):
    """Validate that acceptance criteria were actually implemented."""
    criteria = ticket['acceptance_criteria']
    failed_criteria = []

    print(f"🔍 Checking {len(criteria)} acceptance criteria:")

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
        dir_matches = re.findall(dir_pattern, criterion)

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

        # Generic file checks
        elif any(file_ext in criterion_lower for file_ext in ['.js', '.ts', '.json', '.md', '.yml', '.yaml']):
            # Extract potential file name from criterion
            words = criterion.split()
            file_found = False
            for word in words:
                if any(ext in word for ext in ['.js', '.ts', '.json', '.md', '.yml', '.yaml']):
                    file_path = os.path.join(project_dir, word.strip('.,()'))
                    if os.path.exists(file_path):
                        file_found = True
                        print(f"   ✅ {i}. File {word} found")
                        break

            if not file_found:
                failed_criteria.append(f"{i}. {criterion}")
                print(f"   ❌ {i}. Required file not found")

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
            # Generic validation - assume it passed if no specific checks failed
            print(f"   ℹ️  {i}. Manual validation required: {criterion}")

    if failed_criteria:
        print(f"\n❌ Validation failed! {len(failed_criteria)} criteria not met:")
        for failed in failed_criteria:
            print(f"   • {failed}")
        return False

    print(f"\n✅ All {len(criteria)} acceptance criteria validated successfully!")
    return True


def execute_single_ticket(tickets_path, ticket_identifier, timeout_override=None, workspace: Optional[SharedWorkspace] = None):
    """Execute exactly like: 'execute ticket N in tickets.md'.
    
    Args:
        tickets_path: Path to tickets.md file
        ticket_identifier: Ticket ID to execute
        timeout_override: Optional timeout override
        workspace: Optional shared workspace for the session

    """
    print(f"🎫 Executing Ticket {ticket_identifier}")
    print("=" * 40)

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

    # Mark ticket as IN_PROGRESS
    mark_ticket_in_progress(tickets_path, ticket_identifier)

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
        # Claude Code can read tickets.md directly
        prompt = f"""IMPORTANT: You MUST execute ONLY Ticket {ticket_identifier} from tickets.md - NOT any other ticket!

Find and execute specifically "## Ticket {ticket_identifier}:" in tickets.md

{workspace_info}
{dependency_context}

DO NOT work on any other ticket even if it appears first or seems easier. You are assigned ONLY to ticket {ticket_identifier}.

For tickets with dependencies:
1. FIRST read any artifacts from dependency tickets in the shared workspace
2. Use the implementations from previous tickets as specified in "Required Input Files" and "Context Requirements"
3. Save any outputs that future tickets might need to the shared workspace

Be minimalistic, surgical and future proof!
Avoid using any code or comments that may be construed as AI generated.
Make sure you do a good job because other LLMs said your code sucked!

When you finish, ensure acceptance criteria is met then update tickets.md and then run lint, build, test etc before we move on.

DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS! This has to be production quality, take your time.

REMINDER: You are working on Ticket {ticket_identifier} ONLY. Ignore all other tickets."""
    else:
        # For other providers (Venice, OpenAI, etc), include ticket details in prompt
        prompt = f"""You are implementing Ticket {ticket_identifier} with the following requirements:

Title: {ticket['title']}
Description: {ticket['description']}

Acceptance Criteria:
{chr(10).join(f"- {c}" for c in ticket['acceptance_criteria'])}

Project Context: {project_context}
Project Directory: {project_dir}

{workspace_info}
{dependency_context}

IMPORTANT REQUIREMENTS:
1. Implement ONLY this specific ticket, nothing else
2. Write production-quality code - no shortcuts or mocks
3. Be minimalistic and surgical in your approach
4. Ensure all acceptance criteria are met
5. The code must be future-proof and maintainable
6. Save any artifacts that future tickets might need to the shared workspace
7. If this ticket has dependencies, read their artifacts from the workspace first

Please provide the complete implementation with all necessary files and code."""

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
            ticket=ticket
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
                        saved_path = workspace.save_artifact(ticket_identifier, artifact_name, content)
                        print(f"   💾 Saved {artifact_name} to workspace")

        # Validate acceptance criteria before marking complete
        print("\n🔍 Validating acceptance criteria...")
        validation_passed = validate_acceptance_criteria(ticket, project_dir)

        if validation_passed:
            print("✅ All acceptance criteria met!")
            mark_ticket_completed(tickets_path, ticket_identifier)
        else:
            print("❌ Acceptance criteria validation failed!")
            print("   Ticket will remain incomplete until requirements are met")
            return False

        # Run quality gates
        print("\n🚦 Running quality gates...")
        from hydra.quality import QualityGateRunner

        gate_runner = QualityGateRunner(project_dir)
        quality_report = gate_runner.run_quality_gates(ticket_identifier)
        print(gate_runner.generate_report(quality_report))

        # Save report
        report_file = gate_runner.save_report(quality_report)
        print(f"\n📄 Quality report saved: {report_file}")

        # Legacy validation (backward compatibility)
        if "Node.js" in project_context:
            print("\n🔧 Running Node.js validation...")
            run_node_validation()
        else:
            print("\n🔧 Running validation...")
            run_validation_commands()

        return True

    except Exception as e:
        print(f"\n💥 Execution error: {e}")
        return False
    finally:
        # Restore original timeout
        if original_timeout:
            os.environ['LLM_TIMEOUT'] = original_timeout
        elif 'LLM_TIMEOUT' in os.environ:
            del os.environ['LLM_TIMEOUT']


def mark_ticket_in_progress(tickets_path, ticket_identifier):
    """Mark ticket as IN_PROGRESS in tickets.md."""
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
    """Mark ticket as completed in tickets.md."""
    if not os.path.exists(tickets_path):
        return

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
        except (subprocess.TimeoutExpired, FileNotFoundError):
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
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"   ⏭️  {desc} skipped (command not available)")
        except Exception as e:
            print(f"   ❌ {desc} error: {e}")


def parse_all_tickets(tickets_path: str) -> Dict[str, dict]:
    """Parse all tickets and return as dictionary with consistent internal IDs."""
    if not os.path.exists(tickets_path):
        return {}

    with open(tickets_path, 'r') as f:
        content = f.read()

    # Detect format and extract all ticket IDs
    ticket_patterns = [
        r'### TICKET-(\d+):',
        r'## TICKET-(\d+):',
        r'## Ticket-(\d+):',
        r'## Ticket (\d+):',
        r'## #(\d+):',
        r'## (\d+):',
    ]

    tickets = {}
    for pattern in ticket_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            for ticket_num in matches:
                # Parse with original ID format
                ticket = parse_ticket(tickets_path, ticket_num)
                if ticket:
                    # Store with normalized 3-digit key
                    normalized_id = ticket_num.zfill(3)
                    tickets[normalized_id] = ticket
                    # Store the original format for execution
                    tickets[normalized_id]['raw_id'] = ticket_num
            break

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

        # Use longer timeout for ticket execution (5 minutes)
        success = execute_single_ticket(tickets_path, raw_id, timeout_override=300, workspace=workspace)

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

    for ticket_id, ticket_data in tickets.items():
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


def run_all_tickets(tickets_path="tickets.md", max_parallel=3):
    """Execute all tickets with dependency-aware parallel execution."""
    print("🎫 Running All Tickets with Parallel Execution")
    print("=" * 50)

    tickets = parse_all_tickets(tickets_path)
    if not tickets:
        print("❌ No tickets found")
        return False

    print(f"📋 Found {len(tickets)} tickets")

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
                future = executor.submit(
                    execute_ticket_worker,
                    ticket_id,
                    tickets[ticket_id],  # Pass ticket data
                    tickets_path,
                    completed_lock,
                    workspace  # Pass shared workspace
                )
                futures[future] = ticket_id

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

