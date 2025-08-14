"""Interactive CLI interface for ticket refinement."""

import sys
from typing import Optional

from hydra.interactive.ticket_refiner import (
    RefinementAction,
    RefinementSuggestion,
    TicketRefiner,
)


class RefinementCLI:
    """Interactive command-line interface for ticket refinement."""

    def __init__(self, tickets_path: str):
        """Initialize the CLI with a tickets file."""
        try:
            self.refiner = TicketRefiner(tickets_path)
            self.tickets_path = tickets_path
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)

    def run(self) -> bool:
        """Run the interactive refinement session."""
        print("🔧 Interactive Ticket Refinement")
        print("=" * 50)
        print(f"Loaded {len(self.refiner.tickets)} tickets from {self.tickets_path}")
        print()

        while True:
            action = self._main_menu()

            if action == 'list':
                self._list_tickets()
            elif action == 'refine':
                ticket_id = self._select_ticket()
                if ticket_id:
                    self._refine_ticket(ticket_id)
            elif action == 'validate':
                self._validate_all_dependencies()
            elif action == 'save':
                if self._save_changes():
                    print("✅ Changes saved successfully")
                else:
                    print("❌ Failed to save changes")
            elif action == 'quit':
                return self._handle_quit()
            else:
                print("Invalid option. Please try again.")

    def _main_menu(self) -> str:
        """Display main menu and get user choice."""
        print("\nMain Menu:")
        print("1. List tickets")
        print("2. Refine ticket")
        print("3. Validate dependencies")
        print("4. Save changes")
        print("5. Quit")

        choice = input("\nSelect option (1-5): ").strip()

        return {
            '1': 'list',
            '2': 'refine',
            '3': 'validate',
            '4': 'save',
            '5': 'quit'
        }.get(choice, 'invalid')

    def _list_tickets(self) -> None:
        """Display list of all tickets."""
        tickets = self.refiner.get_ticket_list()

        print("\n📋 Tickets:")
        print("-" * 60)

        for ticket_id, title, status in tickets:
            status_icon = {
                'TODO': '⏳',
                'IN_PROGRESS': '🔄',
                'DONE': '✅'
            }.get(status, '❓')

            print(f"{status_icon} Ticket {ticket_id}: {title[:50]}...")
            print(f"   Status: {status}")

    def _select_ticket(self) -> Optional[str]:
        """Let user select a ticket to refine."""
        tickets = self.refiner.get_ticket_list()

        print("\nSelect a ticket to refine:")
        for i, (ticket_id, title, _status) in enumerate(tickets, 1):
            print(f"{i}. Ticket {ticket_id}: {title[:40]}...")

        print("0. Back to main menu")

        try:
            choice = int(input("\nEnter ticket number: ").strip())
            if choice == 0:
                return None
            elif 1 <= choice <= len(tickets):
                return tickets[choice - 1][0]
            else:
                print("Invalid choice")
                return None
        except ValueError:
            print("Please enter a valid number")
            return None

    def _refine_ticket(self, ticket_id: str) -> None:
        """Interactive refinement for a specific ticket."""
        ticket = self.refiner.get_ticket_details(ticket_id)
        if not ticket:
            print(f"Ticket {ticket_id} not found")
            return

        print(f"\n🎯 Refining Ticket {ticket_id}: {ticket.title}")
        print("-" * 60)

        # Show current ticket info
        self._display_ticket_details(ticket_id)

        # Get and display suggestions
        suggestions = self.refiner.get_refinement_suggestions(ticket_id)

        if not suggestions:
            print("✅ No refinement suggestions for this ticket")
            input("Press Enter to continue...")
            return

        print(f"\n💡 Found {len(suggestions)} suggestions:")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"{i}. {suggestion.description}")
            print(f"   Reason: {suggestion.reason}")

        print("0. Manual refinement")
        print("99. Back to main menu")

        try:
            choice = int(input("\nSelect suggestion to apply (or 0 for manual): ").strip())

            if choice == 99:
                return
            elif choice == 0:
                self._manual_refinement(ticket_id)
            elif 1 <= choice <= len(suggestions):
                suggestion = suggestions[choice - 1]
                self._apply_suggestion(suggestion)
            else:
                print("Invalid choice")
        except ValueError:
            print("Please enter a valid number")

    def _display_ticket_details(self, ticket_id: str) -> None:
        """Display detailed ticket information."""
        ticket = self.refiner.get_ticket_details(ticket_id)
        if not ticket:
            return

        print("\nTicket Details:")
        print(f"  Title: {ticket.title}")
        print(f"  Status: {ticket.status}")
        print(f"  Model: {ticket.model}")
        print(f"  Dependencies: {', '.join(ticket.dependencies) if ticket.dependencies else 'None'}")
        print(f"  Description: {ticket.description}")
        print(f"  Required Input Files: {len(ticket.required_input_files)}")
        print(f"  Output Files: {len(ticket.output_files)}")
        print(f"  Acceptance Criteria: {len(ticket.acceptance_criteria)}")

    def _apply_suggestion(self, suggestion: RefinementSuggestion) -> None:
        """Apply a refinement suggestion."""
        success = False

        if suggestion.action == RefinementAction.ADJUST_MODEL:
            if suggestion.suggested_value:
                success = self.refiner.adjust_model(
                    suggestion.target_ticket, suggestion.suggested_value
                )

        elif suggestion.action == RefinementAction.ADD_DEPENDENCY:
            if suggestion.suggested_value:
                success = self.refiner.add_dependency(
                    suggestion.target_ticket, suggestion.suggested_value
                )

        elif suggestion.action == RefinementAction.REMOVE_DEPENDENCY:
            # For dependency removal, ask user which one to remove
            ticket = self.refiner.get_ticket_details(suggestion.target_ticket)
            if ticket and ticket.dependencies:
                print("\nSelect dependency to remove:")
                for i, dep in enumerate(ticket.dependencies, 1):
                    print(f"{i}. {dep}")

                try:
                    choice = int(input("Enter number: ").strip())
                    if 1 <= choice <= len(ticket.dependencies):
                        dep_to_remove = ticket.dependencies[choice - 1]
                        success = self.refiner.remove_dependency(
                            suggestion.target_ticket, dep_to_remove
                        )
                except ValueError:
                    print("Invalid choice")

        elif suggestion.action == RefinementAction.SPLIT_TICKET:
            success = self._handle_ticket_split(suggestion.target_ticket)

        elif suggestion.action == RefinementAction.VALIDATE_FLOWS:
            self._validate_ticket_flows(suggestion.target_ticket)
            return

        if success:
            print("✅ Suggestion applied successfully")
        else:
            print("❌ Failed to apply suggestion")

    def _manual_refinement(self, ticket_id: str) -> None:
        """Manual refinement options for a ticket."""
        while True:
            print(f"\nManual Refinement Options for Ticket {ticket_id}:")
            print("1. Adjust model")
            print("2. Add dependency")
            print("3. Remove dependency")
            print("4. Split ticket")
            print("5. Validate file flows")
            print("0. Back")

            choice = input("\nSelect option: ").strip()

            if choice == '0':
                break
            elif choice == '1':
                self._manual_adjust_model(ticket_id)
            elif choice == '2':
                self._manual_add_dependency(ticket_id)
            elif choice == '3':
                self._manual_remove_dependency(ticket_id)
            elif choice == '4':
                self._handle_ticket_split(ticket_id)
            elif choice == '5':
                self._validate_ticket_flows(ticket_id)
            else:
                print("Invalid option")

    def _manual_adjust_model(self, ticket_id: str) -> None:
        """Manually adjust ticket model."""
        models = ['smart', 'balanced', 'coder', 'fast']

        print("\nAvailable models:")
        for i, model in enumerate(models, 1):
            print(f"{i}. {model}")

        try:
            choice = int(input("Select model: ").strip())
            if 1 <= choice <= len(models):
                new_model = models[choice - 1]
                if self.refiner.adjust_model(ticket_id, new_model):
                    print(f"✅ Model changed to {new_model}")
                else:
                    print("❌ Failed to change model")
        except ValueError:
            print("Invalid choice")

    def _manual_add_dependency(self, ticket_id: str) -> None:
        """Manually add a dependency."""
        available_tickets = [
            tid for tid in self.refiner.tickets.keys()
            if tid != ticket_id
        ]

        if not available_tickets:
            print("No other tickets available")
            return

        print("\nAvailable tickets:")
        for i, tid in enumerate(available_tickets, 1):
            title = self.refiner.tickets[tid].title
            print(f"{i}. Ticket {tid}: {title[:40]}...")

        try:
            choice = int(input("Select ticket to add as dependency: ").strip())
            if 1 <= choice <= len(available_tickets):
                dep_ticket = available_tickets[choice - 1]
                if self.refiner.add_dependency(ticket_id, dep_ticket):
                    print(f"✅ Added dependency on Ticket {dep_ticket}")
                else:
                    print("❌ Failed to add dependency")
        except ValueError:
            print("Invalid choice")

    def _manual_remove_dependency(self, ticket_id: str) -> None:
        """Manually remove a dependency."""
        ticket = self.refiner.get_ticket_details(ticket_id)
        if not ticket or not ticket.dependencies:
            print("No dependencies to remove")
            return

        print("\nCurrent dependencies:")
        for i, dep in enumerate(ticket.dependencies, 1):
            print(f"{i}. {dep}")

        try:
            choice = int(input("Select dependency to remove: ").strip())
            if 1 <= choice <= len(ticket.dependencies):
                dep_to_remove = ticket.dependencies[choice - 1]
                if self.refiner.remove_dependency(ticket_id, dep_to_remove):
                    print(f"✅ Removed dependency on {dep_to_remove}")
                else:
                    print("❌ Failed to remove dependency")
        except ValueError:
            print("Invalid choice")

    def _handle_ticket_split(self, ticket_id: str) -> bool:
        """Handle ticket splitting."""
        ticket = self.refiner.get_ticket_details(ticket_id)
        if not ticket or len(ticket.acceptance_criteria) < 2:
            print("Ticket cannot be split (needs at least 2 criteria)")
            return False

        print(f"\nSplitting Ticket {ticket_id}")
        print("Select criteria for the new ticket:")

        for i, criteria in enumerate(ticket.acceptance_criteria):
            print(f"{i + 1}. {criteria}")

        try:
            indices_str = input("\nEnter criteria numbers for new ticket (comma-separated): ")
            indices = [int(x.strip()) - 1 for x in indices_str.split(',')]

            # Validate indices
            if not all(0 <= i < len(ticket.acceptance_criteria) for i in indices):
                print("Invalid criteria numbers")
                return False

            original_id, new_id = self.refiner.split_ticket(ticket_id, indices)
            print("✅ Ticket split successfully:")
            print(f"   Original: Ticket {original_id}")
            print(f"   New: Ticket {new_id}")
            return True

        except ValueError:
            print("Invalid input format")
            return False

    def _validate_ticket_flows(self, ticket_id: str) -> None:
        """Validate file flows for a specific ticket."""
        print(f"\n🔍 Validating file flows for Ticket {ticket_id}...")

        result = self.refiner.validate_file_flows(ticket_id)

        if result['valid']:
            print("✅ File flows are valid")
        else:
            print("❌ File flow issues found:")
            for issue in result['issues']:
                print(f"  - {issue.description}")
                if issue.suggested_fix:
                    print(f"    💡 Fix: {issue.suggested_fix}")

        if result['flows']:
            print(f"\nFile flows ({len(result['flows'])}):")
            for flow in result['flows']:
                print(f"  {flow.source_ticket} → {flow.target_ticket}: {flow.file_path}")

        input("\nPress Enter to continue...")

    def _validate_all_dependencies(self) -> None:
        """Validate all ticket dependencies."""
        print("\n🔍 Validating all dependencies...")

        validation_result = self.refiner.validator.validate_ticket_dependencies(
            self.tickets_path
        )

        print("\nValidation Results:")
        print(f"  Overall Status: {'✅ Valid' if validation_result.valid else '❌ Invalid'}")
        print(f"  Issues Found: {len(validation_result.issues)}")

        if validation_result.issues:
            print("\nIssues:")
            for issue in validation_result.issues:
                severity_icon = {
                    'valid': '✅',
                    'warning': '⚠️',
                    'invalid': '❌'
                }.get(issue.severity.value, '❓')

                print(f"  {severity_icon} Ticket {issue.ticket_id}: {issue.description}")
                if issue.suggested_fix:
                    print(f"     💡 Fix: {issue.suggested_fix}")

        if validation_result.topological_order:
            print("\nExecution Order:")
            print(f"  {' → '.join(validation_result.topological_order)}")

        input("\nPress Enter to continue...")

    def _save_changes(self) -> bool:
        """Save changes with confirmation."""
        print("\n💾 Saving changes...")

        # Show summary of changes (simplified)
        modified_count = len(self.refiner.tickets)
        print(f"Will update {modified_count} tickets in {self.tickets_path}")

        confirm = input("Proceed with save? (y/N): ").strip().lower()
        if confirm == 'y':
            return self.refiner.save_changes()
        else:
            print("Save cancelled")
            return False

    def _handle_quit(self) -> bool:
        """Handle quit with unsaved changes check."""
        print("\n👋 Exiting refinement session...")

        # In a real implementation, we'd track if changes were made
        # For now, just confirm exit
        confirm = input("Are you sure you want to quit? (y/N): ").strip().lower()
        if confirm == 'y':
            print("Goodbye!")
            return True
        else:
            return False


def run_interactive_refinement(tickets_path: str) -> int:
    """Run the interactive refinement CLI."""
    try:
        cli = RefinementCLI(tickets_path)
        success = cli.run()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
