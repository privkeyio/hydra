"""Verification and quality commands for Hydra CLI."""

import os
from pathlib import Path


def add_verify_parser(subparsers):
    """Add verification and quality subcommands to ticket parser."""
    # Verify ticket command
    verify_parser = subparsers.add_parser(
        "verify", help="Verify ticket completion and acceptance criteria"
    )
    verify_parser.add_argument("tickets", help="Path to tickets.md file")
    verify_parser.add_argument(
        "identifier", help="Ticket identifier to verify (e.g., 001, 002)"
    )
    verify_parser.add_argument(
        "--report",
        "-r",
        action="store_true",
        help="Generate detailed verification report",
    )

    # Quality gates command
    quality_parser = subparsers.add_parser(
        "quality", help="Run quality gates on ticket implementation"
    )
    quality_parser.add_argument(
        "identifier", help="Ticket identifier for quality checks"
    )
    quality_parser.add_argument(
        "--save", "-s", action="store_true", help="Save quality report to file"
    )
    quality_parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict quality criteria (fail on warnings)",
    )

    # Verify parallel execution results
    verify_parallel_parser = subparsers.add_parser(
        "verify-parallel", help="Verify results from parallel ticket execution"
    )
    verify_parallel_parser.add_argument(
        "execution_id", help="Parallel execution ID to verify"
    )
    verify_parallel_parser.add_argument(
        "--tickets", "-t", help="Path to tickets.md file (default: tickets.md)"
    )
    verify_parallel_parser.add_argument(
        "--report-dir", "-r", help="Directory containing execution reports"
    )
    verify_parallel_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed verification output"
    )
    verify_parallel_parser.add_argument(
        "--save-report", action="store_true", help="Save verification report to file"
    )


def _handle_verify_ticket(args) -> int:
    """Handle ticket verification."""
    from hydra.verification.ticket_verifier import TicketVerifier

    verifier = TicketVerifier(os.path.dirname(args.tickets))

    try:
        report = verifier.verify_ticket(args.tickets, args.identifier)
        print(verifier.generate_report(report))

        if getattr(args, "report", False):
            # Save detailed report
            report_path = f".hydra/reports/verify_{args.identifier}.json"
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)

            import json

            with open(report_path, "w") as f:
                json.dump(report.__dict__, f, indent=2, default=str)
            print(f"\n📄 Report saved: {report_path}")

        if report.coverage >= 80:
            return 0
        else:
            return 1

    except Exception as e:
        print(f"Verification error: {e}")
        return 1


def _handle_quality_gates(args) -> int:
    """Handle quality gates command."""
    from hydra.quality import QualityGateRunner

    runner = QualityGateRunner(os.getcwd())

    try:
        report = runner.run_quality_gates(args.identifier)
        print(runner.generate_report(report))

        if args.save:
            report_file = runner.save_report(report)
            print(f"\n📄 Report saved: {report_file}")

        # Check strictness level
        if getattr(args, "strict", False):
            # Strict mode: fail on warnings
            if report.overall_status.value in ["passed"]:
                return 0
            else:
                return 1
        else:
            # Normal mode: allow warnings
            if report.overall_status.value in ["passed", "warning"]:
                return 0
            else:
                return 1

    except Exception as e:
        print(f"Quality gate error: {e}")
        return 1


def _handle_ticket_verification(args) -> int:
    """Handle parallel ticket verification."""
    import json
    from pathlib import Path

    from hydra.parallel.verification import ParallelVerifier

    tickets_path = args.tickets or "tickets.md"
    report_dir = args.report_dir or ".hydra/reports"

    verifier = ParallelVerifier(tickets_path, report_dir)

    try:
        # Load execution results
        results_file = Path(report_dir) / f"parallel_{args.execution_id}.json"
        if not results_file.exists():
            print(f"❌ Execution results not found: {results_file}")
            return 1

        with open(results_file) as f:
            execution_results = json.load(f)

        # Run verification
        verification_report = verifier.verify_execution(
            execution_results, verbose=args.verbose
        )

        # Display results
        print("\n" + "=" * 60)
        print("PARALLEL EXECUTION VERIFICATION REPORT")
        print("=" * 60)

        print("\n📊 Summary:")
        print(f"  - Total tickets: {verification_report['total_tickets']}")
        print(f"  - Successful: {verification_report['successful']}")
        print(f"  - Failed: {verification_report['failed']}")
        print(f"  - Skipped: {verification_report['skipped']}")

        if verification_report["failed"] > 0:
            print("\n❌ Failed tickets:")
            for ticket_id, details in verification_report["failures"].items():
                print(f"  - {ticket_id}: {details['reason']}")

        if verification_report["warnings"]:
            print("\n⚠️  Warnings:")
            for warning in verification_report["warnings"]:
                print(f"  - {warning}")

        # Save report if requested
        if args.save_report:
            report_path = Path(report_dir) / f"verify_{args.execution_id}.json"
            with open(report_path, "w") as f:
                json.dump(verification_report, f, indent=2)
            print(f"\n📄 Verification report saved: {report_path}")

        # Return status based on failures
        return 0 if verification_report["failed"] == 0 else 1

    except Exception as e:
        print(f"❌ Verification error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def handle_verify_command(args) -> int:
    """Handle verification commands."""
    # This is called from ticket command context
    action = getattr(args, "ticket_action", None)

    if action == "verify":
        return _handle_verify_ticket(args)
    elif action == "quality":
        return _handle_quality_gates(args)
    elif action == "verify-parallel":
        return _handle_ticket_verification(args)
    else:
        print(f"Unknown verify action: {action}")
        return 1
