"""Interactive ticket refinement CLI."""

import re
from pathlib import Path
from typing import Dict, List

from hydra.analysis.codebase_analyzer import CodebaseAnalyzer
from hydra.analysis.dependency_detector import DependencyDetector


class InteractiveRefinement:
    """Interactive refinement for generated tickets."""

    def __init__(self, tickets_path: str):
        """Initialize refinement with tickets file.

        Args:
            tickets_path: Path to tickets.md file

        """
        self.tickets_path = Path(tickets_path)
        self.project_path = self.tickets_path.parent
        self.analyzer = CodebaseAnalyzer(str(self.project_path))
        self.detector = DependencyDetector(str(self.project_path))
        self.tickets = []
        self.original_content = ""

    def load_tickets(self) -> bool:
        """Load and parse tickets from file.

        Returns:
            True if successful

        """
        if not self.tickets_path.exists():
            print(f"❌ File not found: {self.tickets_path}")
            return False

        self.original_content = self.tickets_path.read_text()

        # Parse tickets
        ticket_pattern = r'## Ticket (\d+):(.*?)(?=## Ticket|\Z)'
        matches = re.findall(ticket_pattern, self.original_content, re.DOTALL)

        for ticket_num, content in matches:
            ticket = self._parse_ticket_content(ticket_num, content)
            self.tickets.append(ticket)

        return len(self.tickets) > 0

    def _parse_ticket_content(self, ticket_num: str, content: str) -> Dict:
        """Parse individual ticket content.

        Args:
            ticket_num: Ticket number
            content: Ticket content text

        Returns:
            Parsed ticket dictionary

        """
        ticket = {
            "number": ticket_num,
            "title": "",
            "status": "TODO",
            "model": "balanced",
            "dependencies": [],
            "description": "",
            "criteria": [],
            "original_content": content
        }

        lines = content.strip().split('\n')
        if lines:
            ticket["title"] = lines[0].strip()

        for line in lines[1:]:
            line = line.strip()
            if line.startswith("**Status:**"):
                ticket["status"] = line.replace("**Status:**", "").strip()
            elif line.startswith("**Model:**"):
                ticket["model"] = line.replace("**Model:**", "").strip()
            elif line.startswith("**Dependencies:**"):
                deps = line.replace("**Dependencies:**", "").strip()
                if deps.lower() not in ["none", ""]:
                    ticket["dependencies"] = [d.strip() for d in deps.split(",")]
            elif line.startswith("**Description:**"):
                ticket["description"] = line.replace("**Description:**", "").strip()
            elif line.startswith("- [ ]"):
                ticket["criteria"].append(line.replace("- [ ]", "").strip())

        return ticket

    def analyze_and_enhance(self) -> None:
        """Analyze codebase and enhance tickets with context."""
        print("\n🔍 Analyzing codebase...")
        analysis = self.analyzer.analyze()

        print(f"  Project type: {analysis['project_type']}")
        print(f"  Framework: {analysis['framework'] or 'None detected'}")
        print(f"  Tech stack: {', '.join(analysis['tech_stack'])}")
        print(f"  Size: {analysis['size_metrics']['total_loc']} LOC across {analysis['size_metrics']['total_files']} files")

        # Enhance tickets with complexity scores
        print("\n🎯 Enhancing tickets with complexity analysis...")
        for ticket in self.tickets:
            # Extract files mentioned in ticket
            files_mentioned = self._extract_files_from_ticket(ticket)

            if files_mentioned:
                complexities = []
                for file_path in files_mentioned:
                    complexity = self.analyzer.estimate_ticket_complexity(file_path)
                    complexities.append(complexity)

                # Suggest model based on highest complexity
                if "coder" in complexities:
                    suggested_model = "coder"
                elif "smart" in complexities:
                    suggested_model = "smart"
                elif "balanced" in complexities:
                    suggested_model = "balanced"
                else:
                    suggested_model = "fast"

                if suggested_model != ticket["model"]:
                    ticket["suggested_model"] = suggested_model
                    print(f"  Ticket {ticket['number']}: Suggest {suggested_model} model (currently {ticket['model']})")

    def _extract_files_from_ticket(self, ticket: Dict) -> List[str]:
        """Extract file paths mentioned in ticket.

        Args:
            ticket: Ticket dictionary

        Returns:
            List of file paths

        """
        files = []
        text = f"{ticket['title']} {ticket['description']} {' '.join(ticket['criteria'])}"

        # Common file patterns
        patterns = [
            r'(?:src/|tests/|lib/)[a-zA-Z0-9_/]+\.py',
            r'[a-zA-Z0-9_/]+\.(?:py|js|ts|jsx|tsx)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            files.extend(matches)

        return list(set(files))

    def detect_missing_dependencies(self) -> None:
        """Detect missing dependencies between tickets."""
        print("\n🔗 Analyzing ticket dependencies...")

        # Extract tasks from tickets
        tasks = []
        for ticket in self.tickets:
            task = {
                "id": ticket["number"],
                "title": ticket["title"],
                "description": ticket["description"],
                "criteria": ticket["criteria"]
            }
            tasks.append(task)

        # Detect dependencies
        suggested_deps = self.detector.detect_dependencies(tasks)

        # Compare with existing dependencies
        for ticket in self.tickets:
            ticket_id = ticket["number"].zfill(3)
            suggested = suggested_deps.get(ticket_id, [])
            existing = [d.zfill(3) for d in ticket["dependencies"]]

            # Find missing dependencies
            missing = [d for d in suggested if d not in existing and int(d) < int(ticket_id)]

            if missing:
                ticket["missing_dependencies"] = missing
                print(f"  Ticket {ticket['number']}: Missing dependencies on {', '.join(missing)}")

    def interactive_edit(self) -> None:
        """Interactive editing interface."""
        print("\n📝 Interactive Refinement Mode")
        print("=" * 40)
        print("Commands:")
        print("  list - Show all tickets")
        print("  show <num> - Show ticket details")
        print("  model <num> <model> - Change ticket model")
        print("  deps <num> <deps> - Update dependencies (comma-separated)")
        print("  auto - Apply all suggestions")
        print("  save - Save changes")
        print("  quit - Exit without saving")
        print("")

        while True:
            try:
                command = input("refinement> ").strip().lower()

                if command == "quit":
                    print("Exiting without saving.")
                    break
                elif command == "save":
                    self.save_changes()
                    print("✅ Changes saved!")
                    break
                elif command == "list":
                    self.list_tickets()
                elif command.startswith("show "):
                    num = command.split()[1]
                    self.show_ticket(num)
                elif command.startswith("model "):
                    parts = command.split()
                    if len(parts) >= 3:
                        self.update_model(parts[1], parts[2])
                elif command.startswith("deps "):
                    parts = command.split(maxsplit=2)
                    if len(parts) >= 3:
                        self.update_dependencies(parts[1], parts[2])
                elif command == "auto":
                    self.apply_suggestions()
                elif command == "help":
                    print("Commands: list, show <num>, model <num> <model>, deps <num> <deps>, auto, save, quit")
                else:
                    print("Unknown command. Type 'help' for commands.")

            except KeyboardInterrupt:
                print("\nUse 'quit' to exit.")
            except Exception as e:
                print(f"Error: {e}")

    def list_tickets(self) -> None:
        """List all tickets with summary."""
        print("\n📋 Tickets:")
        for ticket in self.tickets:
            status_icon = "✅" if ticket["status"] == "DONE" else "📝"
            model_icon = {"fast": "💨", "balanced": "⚡", "smart": "🧠", "coder": "💻"}.get(ticket["model"], "❓")

            print(f"{status_icon} Ticket {ticket['number']}: {ticket['title'][:50]}...")
            print(f"   {model_icon} Model: {ticket['model']}", end="")

            if "suggested_model" in ticket:
                print(f" → {ticket['suggested_model']} (suggested)", end="")

            if ticket["dependencies"]:
                print(f" | Deps: {','.join(ticket['dependencies'])}", end="")

            if "missing_dependencies" in ticket:
                print(f" | Missing: {','.join(ticket['missing_dependencies'])}", end="")

            print()

    def show_ticket(self, ticket_num: str) -> None:
        """Show detailed ticket information.

        Args:
            ticket_num: Ticket number to show

        """
        for ticket in self.tickets:
            if ticket["number"] == ticket_num:
                print(f"\n## Ticket {ticket['number']}: {ticket['title']}")
                print(f"**Status:** {ticket['status']}")
                print(f"**Model:** {ticket['model']}")

                if "suggested_model" in ticket:
                    print(f"**Suggested Model:** {ticket['suggested_model']}")

                print(f"**Dependencies:** {','.join(ticket['dependencies']) if ticket['dependencies'] else 'None'}")

                if "missing_dependencies" in ticket:
                    print(f"**Missing Dependencies:** {','.join(ticket['missing_dependencies'])}")

                print(f"**Description:** {ticket['description']}")
                print("\n**Acceptance Criteria:**")
                for criterion in ticket["criteria"]:
                    print(f"- [ ] {criterion}")
                return

        print(f"Ticket {ticket_num} not found.")

    def update_model(self, ticket_num: str, model: str) -> None:
        """Update ticket model.

        Args:
            ticket_num: Ticket number
            model: New model (fast/balanced/smart/coder)

        """
        valid_models = ["fast", "balanced", "smart", "coder"]
        if model not in valid_models:
            print(f"Invalid model. Choose from: {', '.join(valid_models)}")
            return

        for ticket in self.tickets:
            if ticket["number"] == ticket_num:
                ticket["model"] = model
                print(f"✅ Updated Ticket {ticket_num} model to {model}")
                return

        print(f"Ticket {ticket_num} not found.")

    def update_dependencies(self, ticket_num: str, deps_str: str) -> None:
        """Update ticket dependencies.

        Args:
            ticket_num: Ticket number
            deps_str: Comma-separated dependency list

        """
        for ticket in self.tickets:
            if ticket["number"] == ticket_num:
                if deps_str.lower() == "none":
                    ticket["dependencies"] = []
                else:
                    ticket["dependencies"] = [d.strip() for d in deps_str.split(",")]
                print(f"✅ Updated Ticket {ticket_num} dependencies")
                return

        print(f"Ticket {ticket_num} not found.")

    def apply_suggestions(self) -> None:
        """Apply all suggested improvements."""
        changes_made = 0

        for ticket in self.tickets:
            # Apply suggested model
            if "suggested_model" in ticket:
                ticket["model"] = ticket["suggested_model"]
                changes_made += 1
                print(f"✅ Ticket {ticket['number']}: Model → {ticket['suggested_model']}")

            # Apply missing dependencies
            if "missing_dependencies" in ticket:
                ticket["dependencies"].extend(ticket["missing_dependencies"])
                changes_made += 1
                print(f"✅ Ticket {ticket['number']}: Added dependencies {','.join(ticket['missing_dependencies'])}")

        if changes_made > 0:
            print(f"\n✅ Applied {changes_made} suggestions")
        else:
            print("No suggestions to apply.")

    def save_changes(self) -> None:
        """Save refined tickets back to file."""
        # Rebuild ticket content
        new_content = []

        for ticket in self.tickets:
            ticket_lines = [
                f"## Ticket {ticket['number']}: {ticket['title']}",
                f"**Status:** {ticket['status']}",
                f"**Model:** {ticket['model']}",
                f"**Dependencies:** {','.join(ticket['dependencies']) if ticket['dependencies'] else 'None'}",
                f"**Description:** {ticket['description']}",
                "**Progress:** started",
                "",
                "**Acceptance Criteria:**"
            ]

            for criterion in ticket["criteria"]:
                ticket_lines.append(f"- [ ] {criterion}")

            ticket_lines.append("")
            new_content.append("\n".join(ticket_lines))

        # Add header if original had one
        if self.original_content.startswith("# "):
            header_end = self.original_content.find("\n## Ticket")
            if header_end > 0:
                header = self.original_content[:header_end]
                final_content = header + "\n" + "\n".join(new_content)
            else:
                final_content = "\n".join(new_content)
        else:
            final_content = "\n".join(new_content)

        # Save to file
        self.tickets_path.write_text(final_content)


def run_interactive_refinement(tickets_path: str) -> int:
    """Run interactive refinement session.

    Args:
        tickets_path: Path to tickets.md file

    Returns:
        Exit code (0 for success)

    """
    refinement = InteractiveRefinement(tickets_path)

    if not refinement.load_tickets():
        return 1

    print(f"📋 Loaded {len(refinement.tickets)} tickets from {tickets_path}")

    # Analyze and enhance
    refinement.analyze_and_enhance()
    refinement.detect_missing_dependencies()

    # Start interactive mode
    refinement.interactive_edit()

    return 0
