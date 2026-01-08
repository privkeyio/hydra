"""Boss agent CLI commands for manual verification."""

import json
import sys
from pathlib import Path


def add_boss_parser(subparsers):
    """Add boss command parser to subparsers."""
    boss_parser = subparsers.add_parser(
        "boss",
        help="Boss agent verification commands"
    )

    boss_subparsers = boss_parser.add_subparsers(
        dest="boss_command",
        help="Boss agent subcommands"
    )

    # Verify command
    verify_parser = boss_subparsers.add_parser(
        "verify",
        help="Manually verify ticket completion with boss agent"
    )
    verify_parser.add_argument(
        "ticket_file",
        help="Path to tickets file (YAML or MD)"
    )
    verify_parser.add_argument(
        "ticket_id",
        help="Ticket ID to verify"
    )
    verify_parser.add_argument(
        "--project-path", "-p",
        default=".",
        help="Project path to verify (default: current directory)"
    )
    verify_parser.add_argument(
        "--strictness", "-s",
        choices=["lenient", "moderate", "strict", "brutal"],
        default="strict",
        help="Verification strictness level"
    )
    verify_parser.add_argument(
        "--min-coverage",
        type=float,
        default=80.0,
        help="Minimum test coverage percentage"
    )
    verify_parser.add_argument(
        "--min-quality",
        type=float,
        default=7.0,
        help="Minimum quality score (0-10)"
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )
    verify_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    verify_parser.add_argument(
        "--report",
        action="store_true",
        help="Generate detailed verification report"
    )
    verify_parser.add_argument(
        "--report-format",
        choices=["json", "html", "both"],
        default="both",
        help="Report format (when --report is used)"
    )

    # Batch verify command
    batch_parser = boss_subparsers.add_parser(
        "verify-all",
        help="Verify all completed tickets in a file"
    )
    batch_parser.add_argument(
        "ticket_file",
        help="Path to tickets file"
    )
    batch_parser.add_argument(
        "--project-path", "-p",
        default=".",
        help="Project path to verify"
    )
    batch_parser.add_argument(
        "--strictness", "-s",
        choices=["lenient", "moderate", "strict", "brutal"],
        default="moderate",
        help="Verification strictness level"
    )
    batch_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    # Report command
    report_parser = boss_subparsers.add_parser(
        "report",
        help="Generate verification report for project"
    )
    report_parser.add_argument(
        "--project-path", "-p",
        default=".",
        help="Project path to analyze"
    )
    report_parser.add_argument(
        "--output", "-o",
        default="verification_report",
        help="Output file name (without extension)"
    )
    report_parser.add_argument(
        "--format",
        choices=["json", "html", "both"],
        default="both",
        help="Report format"
    )


def handle_boss_command(args):
    """Handle boss agent commands."""
    if args.boss_command == "verify":
        return handle_verify_single(args)
    elif args.boss_command == "verify-all":
        return handle_verify_batch(args)
    elif args.boss_command == "report":
        return handle_generate_report(args)
    else:
        print(f"Unknown boss command: {args.boss_command}", file=sys.stderr)
        return 1


def handle_verify_single(args):
    """Handle single ticket verification."""
    from hydra.ticket_workflow import parse_ticket
    from hydra.verification_system.boss_agent import BossAgent, StrictnessLevel
    from hydra.verification_system.report_generator import ReportGenerator

    # Parse ticket
    ticket_data = parse_ticket(args.ticket_file, args.ticket_id)
    if not ticket_data:
        print(f"Error: Could not find ticket {args.ticket_id} in {args.ticket_file}", file=sys.stderr)
        return 1

    # Create boss agent
    strictness = StrictnessLevel[args.strictness.upper()]
    boss = BossAgent(
        strictness=strictness,
        min_coverage=args.min_coverage,
        min_quality=args.min_quality
    )

    if args.verbose:
        print(f"🔍 Verifying ticket {args.ticket_id} with {args.strictness} strictness...")
        print(f"   Project path: {args.project_path}")
        print(f"   Min coverage: {args.min_coverage}%")
        print(f"   Min quality: {args.min_quality}/10")
        print()

    # Run verification
    result = boss.verify(
        project_dir=args.project_path,
        ticket_id=args.ticket_id,
        acceptance_criteria=ticket_data.get("acceptance_criteria", [])
    )

    # Generate report if requested
    if args.report:
        report_gen = ReportGenerator()
        report_paths = report_gen.generate_report(
            ticket_id=args.ticket_id,
            ticket_data=ticket_data,
            verification_result=result,
            format=args.report_format,
            output_dir=Path(args.project_path) / ".hydra" / "reports"
        )

        if args.verbose:
            print("\n📄 Reports generated:")
            for report_type, path in report_paths.items():
                print(f"  - {report_type}: {path}")

    # Output result
    if args.json:
        output = {
            "ticket_id": args.ticket_id,
            "status": result.status.value,
            "score": result.score,
            "passed_criteria": result.passed_criteria,
            "failed_criteria": result.failed_criteria,
            "failure_reasons": result.failure_reasons,
            "suggestions": result.suggestions,
            "metadata": result.metadata
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        status_emoji = "✅" if result.status.value == "pass" else "❌"
        print(f"\n{status_emoji} Verification Result: {result.status.value.upper()}")
        print(f"📊 Quality Score: {result.score:.1f}/10")

        if result.passed_criteria:
            print(f"\n✅ Passed Criteria ({len(result.passed_criteria)}):")
            for criterion in result.passed_criteria[:5]:  # Show first 5
                print(f"  - {criterion}")
            if len(result.passed_criteria) > 5:
                print(f"  ... and {len(result.passed_criteria) - 5} more")

        if result.failed_criteria:
            print(f"\n❌ Failed Criteria ({len(result.failed_criteria)}):")
            for criterion in result.failed_criteria:
                print(f"  - {criterion}")

        if result.failure_reasons:
            print("\n⚠️ Failure Reasons:")
            for reason in result.failure_reasons:
                print(f"  - {reason}")

        if result.suggestions:
            print("\n💡 Suggestions:")
            for suggestion in result.suggestions[:3]:  # Show top 3
                print(f"  - {suggestion}")

        # Summary
        print("\n📋 Summary:")
        coverage = result.metadata.get("coverage", {})
        if coverage:
            print(f"  Test Coverage: {coverage.get('line_coverage', 0):.1f}%")

        complexity = result.metadata.get("complexity", {})
        if complexity:
            print(f"  Code Complexity: {complexity.get('average', 0):.1f}")

        ai_detection = result.metadata.get("ai_detection", {})
        if ai_detection:
            print(f"  AI Patterns: {ai_detection.get('pattern_count', 0)} detected")

    # Return exit code
    return 0 if result.status.value == "pass" else 1


def handle_verify_batch(args):
    """Handle batch ticket verification."""
    from hydra.ticket_workflow import parse_tickets_from_file
    from hydra.verification_system.boss_agent import BossAgent, StrictnessLevel

    # Parse all tickets
    tickets = parse_tickets_from_file(args.ticket_file)
    if not tickets:
        print(f"Error: No tickets found in {args.ticket_file}", file=sys.stderr)
        return 1

    # Filter completed tickets
    completed_tickets = {
        tid: data for tid, data in tickets.items()
        if data.get("status") in ["DONE", "COMPLETED"]
    }

    if not completed_tickets:
        print("No completed tickets to verify")
        return 0

    print(f"Found {len(completed_tickets)} completed tickets to verify")

    # Create boss agent
    strictness = StrictnessLevel[args.strictness.upper()]
    boss = BossAgent(strictness=strictness)

    results = {}
    passed = 0
    failed = 0

    # Verify each ticket
    for ticket_id, ticket_data in completed_tickets.items():
        print(f"\n🔍 Verifying ticket {ticket_id}: {ticket_data.get('title', 'Untitled')}...")

        result = boss.verify(
            project_dir=args.project_path,
            ticket_id=ticket_id,
            acceptance_criteria=ticket_data.get("acceptance_criteria", [])
        )

        results[ticket_id] = {
            "status": result.status.value,
            "score": result.score,
            "failed_count": len(result.failed_criteria)
        }

        if result.status.value == "pass":
            passed += 1
            print(f"  ✅ PASSED (score: {result.score:.1f})")
        else:
            failed += 1
            print(f"  ❌ FAILED (score: {result.score:.1f}, {len(result.failed_criteria)} issues)")

    # Output summary
    if args.json:
        output = {
            "total": len(completed_tickets),
            "passed": passed,
            "failed": failed,
            "results": results
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'='*50}")
        print("Verification Summary:")
        print(f"  Total: {len(completed_tickets)} tickets")
        print(f"  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  Success Rate: {(passed/len(completed_tickets)*100):.1f}%")

    return 0 if failed == 0 else 1


def handle_generate_report(args):
    """Generate comprehensive verification report."""
    from hydra.metrics.quality_metrics import QualityMetricsAnalyzer
    from hydra.verification_system.boss_agent import BossAgent, StrictnessLevel
    from hydra.verification_system.report_generator import ReportGenerator

    print(f"📊 Generating verification report for {args.project_path}...")

    # Analyze project quality
    analyzer = QualityMetricsAnalyzer()
    quality_report = analyzer.analyze_project(args.project_path)

    # Create boss agent for verification
    boss = BossAgent(strictness=StrictnessLevel.MODERATE)

    # Generate comprehensive report
    report_gen = ReportGenerator()
    output_dir = Path(args.project_path) / ".hydra" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_data = {
        "project_path": args.project_path,
        "quality_metrics": {
            "overall_score": quality_report.overall_score,
            "production_ready": quality_report.production_ready,
            "complexity": quality_report.complexity.__dict__,
            "coverage": quality_report.coverage.__dict__,
            "documentation": quality_report.documentation.__dict__,
            "security": quality_report.security.__dict__
        },
        "timestamp": quality_report.timestamp.isoformat()
    }

    # Generate output files
    report_paths = {}

    if args.format in ["json", "both"]:
        json_path = output_dir / f"{args.output}.json"
        with open(json_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)
        report_paths["json"] = json_path
        print(f"  ✅ JSON report: {json_path}")

    if args.format in ["html", "both"]:
        html_path = output_dir / f"{args.output}.html"
        html_content = report_gen._generate_html_report(report_data)
        with open(html_path, "w") as f:
            f.write(html_content)
        report_paths["html"] = html_path
        print(f"  ✅ HTML report: {html_path}")

    print("\n📄 Reports generated successfully!")
    print(f"   Overall Score: {quality_report.overall_score:.1f}/10")
    print(f"   Production Ready: {'Yes' if quality_report.production_ready else 'No'}")

    return 0
