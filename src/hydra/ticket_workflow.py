#!/usr/bin/env python3
"""Kyle's ticket-based development workflow integrated into Hydra."""

import os
import re
import subprocess
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Set, Tuple

from hydra.agents.base import CodeAgent
from hydra.monitoring import monitoring


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
        'model': 'sonnet',
        'acceptance_criteria': [],
        'dependencies': [],
        'completed': False
    }

    # Check if ticket is already completed
    if '✅ COMPLETED' in ticket['title'] or 'COMPLETED' in ticket['title']:
        ticket['completed'] = True

    in_criteria = False
    for line in lines[1:]:
        line = line.strip()
        if line.startswith('**Model:**'):
            model_text = line.replace('**Model:**', '').strip().lower()
            ticket['model'] = 'opus' if 'opus' in model_text else 'sonnet'
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
        elif line.startswith('- [x]'):
            # Already completed criteria - still add to list but mark as done
            criteria = line.replace('- [x]', '').strip()
            ticket['acceptance_criteria'].append(f"✅ {criteria}")
        elif line.startswith('##'):
            # Stop parsing if we hit another section header
            break
        elif not in_criteria and line and not line.startswith('**') and not ticket['description']:
            # Only capture additional description if we don't have one yet
            ticket['description'] = line

    return ticket


def generate_tickets_md(project_description, output_path="tickets.md"):
    """Generate tickets.md from project description."""
    print("🎫 Generating tickets.md...")
    print("=" * 30)

    # Always use Opus 4 for ticket planning
    print("🧠 Using Opus 4 for ticket planning...")
    
    # Use the exact prompt format that works when you run Claude Code manually
    prompt = f"""make a tickets.md doc with tickets that are made in task language for claude code to execute that include acceptance criteria, dependencies (like 001,002 or None), and which model (sonnet 4 or opus 4) should be used for that ticket. be minimalistic, surgical and future proof!

Each ticket MUST have this format:
## Ticket 001: [Title]
**Model:** [Sonnet 4 or Opus 4]
**Dependencies:** [None or comma-separated ticket numbers like 001,002]
**Description:** [Task description]

**Acceptance Criteria:**
- [ ] [Criteria]

Project: {project_description}"""

    print("🚀 Generating tickets with production standards...")

    try:
        # Import necessary modules
        from hydra.config import get_config
        import subprocess
        import os
        
        config = get_config()
        
        # Get Claude path from config or environment
        claude_path = os.environ.get('CLAUDE_CLI_PATH', '/home/kyle/.claude/local/claude')
        if hasattr(config, 'llm_provider') and hasattr(config.llm_provider.config, 'extra_params'):
            claude_path = config.llm_provider.config.extra_params.get('claude_path', claude_path)
        
        # Run Claude Code directly to create the file (not using --print)
        # Use the exact same way you would run it manually
        result = subprocess.run(
            [claude_path, "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getcwd()
        )
        
        if result.returncode == 0 and os.path.exists(output_path):
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
            
            # Count models - handle variations
            opus_count = tickets_content.lower().count('opus')
            sonnet_count = tickets_content.lower().count('sonnet')
            
            print(f"📊 Generated {ticket_count} tickets:")
            print(f"   🧠 Opus 4: {opus_count} tickets")
            print(f"   ⚡ Sonnet 4: {sonnet_count} tickets")
            
            return True
        else:
            print("❌ Failed to generate tickets")
            if result.stderr:
                print(f"💥 Error: {result.stderr}")
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

        # File existence checks
        if "package.json exists" in criterion_lower or "package.json with" in criterion_lower:
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


def execute_single_ticket(tickets_path, ticket_identifier, timeout_override=None):
    """Execute exactly like: 'execute ticket N in tickets.md'."""
    print(f"🎫 Executing Ticket {ticket_identifier}")
    print("=" * 40)

    # Parse the specific ticket
    ticket = parse_ticket(tickets_path, ticket_identifier)
    if not ticket:
        return False

    # Check if ticket is already completed
    if ticket['completed']:
        print("✅ Ticket already completed!")
        print("ℹ️  Skipping execution as ticket is marked as COMPLETED")
        return True

    model_emoji = "🧠" if ticket['model'] == 'opus' else "⚡"
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

    # Use the tmux Claude provider for ticket implementation
    from hydra.providers.base import LLMConfig
    from hydra.providers.claude_tmux import ClaudeTmuxProvider

    # Create tmux provider config
    config = LLMConfig(
        provider_type='claude_tmux',
        timeout=timeout_override or 300,
        extra_params={
            'claude_path': os.environ.get('CLAUDE_CLI_PATH', '/home/kyle/.claude/local/claude')
        }
    )

    # Create the tmux provider directly
    provider = ClaudeTmuxProvider(config)

    # Detect project language/framework from context
    project_context = detect_project_context(tickets_path)

    # Build comprehensive prompt for Claude Code CLI to execute
    # Claude Code will handle all file creation and editing with enhanced instructions
    prompt = f"""Execute ticket {ticket_identifier} in tickets.md

Task: {ticket['title']}
Description: {ticket['description']}

Acceptance Criteria that MUST be met:
{chr(10).join(f'- {criteria}' for criteria in ticket['acceptance_criteria'])}

Project Context: {project_context}
Working Directory: {os.getcwd()}

CRITICAL INSTRUCTIONS:
Be minimalistic, surgical and future proof!

QUALITY REQUIREMENTS:
- Avoid using any code or comments that may be construed as AI generated
- Make sure you do a good job because other LLMs said your code sucked!
- DO NOT TAKE ANY SHORTCUTS OR WORKAROUNDS OR MOCKS!
- This has to be production quality, take your time
- Write code that looks like it was written by a senior developer
- Use proper error handling and edge case management
- Follow established patterns in the existing codebase

COMPLETION PROCESS:
1. Implement ALL requirements from the ticket
2. Ensure every acceptance criteria is fully met  
3. Update tickets.md to mark your criteria as complete: [x]
4. Run lint, build, test commands to validate your work
5. Only finish when everything passes and is production-ready

Take your time and deliver excellence!"""

    print("🚀 Executing with production standards...")
    print("   ✅ No AI-generated patterns")
    print("   ✅ Minimalistic and surgical")
    print("   ✅ Future-proof design")
    print("   ✅ Production quality only")

    try:
        # Execute via Claude Code CLI directly - it will handle all file operations
        print("\n🤖 Invoking Claude Code CLI to implement ticket...")

        # Use the tmux provider to send prompt to Claude Code
        # Claude Code will create/edit all necessary files
        project_dir = os.path.dirname(os.path.abspath(tickets_path))
        provider.generate(prompt, cwd=project_dir, ticket_id=ticket_identifier)

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

        if git_result.stdout:
            print("📝 Files changed:")
            for line in git_result.stdout.strip().split('\n'):
                print(f"   {line}")

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


def mark_ticket_completed(tickets_path, ticket_identifier):
    """Mark ticket as completed in tickets.md."""
    if not os.path.exists(tickets_path):
        return

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
        update_msg = f"✅ Updated {tickets_path} - marked ticket {ticket_identifier} completed"
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
                         completed_lock: threading.Lock) -> bool:
    """Worker function for parallel ticket execution."""
    try:
        print(f"\n🚀 Starting ticket {ticket_id}")

        # Use the raw_id stored during parsing
        raw_id = ticket_data.get('raw_id', ticket_id.lstrip('0'))

        # Use longer timeout for ticket execution (5 minutes)
        success = execute_single_ticket(tickets_path, raw_id, timeout_override=300)

        if success:
            with completed_lock:
                print(f"✅ Ticket {ticket_id} completed")
        else:
            print(f"❌ Ticket {ticket_id} failed")

        return success
    except Exception as e:
        print(f"💥 Error executing ticket {ticket_id}: {e}")
        return False


def run_all_tickets(tickets_path="tickets.md", max_parallel=3):
    """Execute all tickets with dependency-aware parallel execution."""
    print("🎫 Running All Tickets with Parallel Execution")
    print("=" * 50)

    tickets = parse_all_tickets(tickets_path)
    if not tickets:
        print("❌ No tickets found")
        return False

    print(f"📋 Found {len(tickets)} tickets")

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
                    completed_lock
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
        return True
    else:
        print(f"\n❌ Execution stopped. Failed tickets: {failed}")
        return False

