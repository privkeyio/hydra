"""CLI commands for boss agent verification."""

import json
from pathlib import Path
from typing import Optional

import click

from ..ticket_workflow import parse_ticket
from .workflow_hooks import create_standalone_verifier


@click.group()
def boss():
    """Boss agent verification commands."""
    pass


@boss.command()
@click.argument('ticket_file', type=click.Path(exists=True))
@click.argument('ticket_id')
@click.option('--project-path', '-p', default='.', help='Project path to verify')
@click.option('--strictness', '-s',
              type=click.Choice(['lenient', 'moderate', 'strict', 'brutal']),
              default='strict',
              help='Verification strictness level')
@click.option('--min-coverage', type=float, default=80.0,
              help='Minimum test coverage percentage')
@click.option('--min-quality', type=float, default=7.0,
              help='Minimum quality score')
@click.option('--json-output', is_flag=True,
              help='Output result as JSON')
@click.option('--verbose', '-v', is_flag=True,
              help='Verbose output')
@click.option('--generate-report', '-r', is_flag=True,
              help='Generate detailed HTML/JSON report')
@click.option('--report-format',
              type=click.Choice(['json', 'html', 'both']),
              default='both',
              help='Report format when --generate-report is used')
def verify(
    ticket_file: str,
    ticket_id: str,
    project_path: str,
    strictness: str,
    min_coverage: float,
    min_quality: float,
    json_output: bool,
    verbose: bool,
    generate_report: bool,
    report_format: str
):
    """Verify a ticket completion with boss agent.
    
    Example:
        hydra boss verify tickets.yaml 001 --strictness brutal

    """
    # Parse ticket
    ticket_data = parse_ticket(ticket_file, ticket_id)
    if not ticket_data:
        click.echo(f"Error: Could not find ticket {ticket_id} in {ticket_file}", err=True)
        return 1

    # Create verifier
    verifier = create_standalone_verifier(
        strictness=strictness,
        min_coverage=min_coverage,
        min_quality=min_quality
    )

    # Run verification
    if verbose:
        click.echo(f"🔍 Verifying ticket {ticket_id} with {strictness} strictness...")

    result = verifier.verify_ticket_completion(
        ticket_id=ticket_id,
        ticket_data=ticket_data,
        project_path=project_path
    )

    # Generate detailed report if requested
    if generate_report:
        report_paths = verifier.generate_verification_report(
            ticket_id=ticket_id,
            ticket_data=ticket_data,
            verification_result=result,
            format=report_format
        )

        if verbose:
            click.echo("\n📄 Reports generated:")
            for report_type, path in report_paths.items():
                click.echo(f"  - {report_type}: {path}")

    # Output result
    if json_output:
        output = {
            'ticket_id': ticket_id,
            'status': result.status.value,
            'score': result.score,
            'passed_criteria': result.passed_criteria,
            'failed_criteria': result.failed_criteria,
            'failure_reasons': result.failure_reasons,
            'suggestions': result.suggestions,
            'metadata': result.metadata
        }
        click.echo(json.dumps(output, indent=2))
    else:
        # Human-readable output
        if result.status.value == 'pass':
            click.echo(f"✅ Ticket {ticket_id} PASSED verification")
            click.echo(f"Score: {result.score:.1f}/100")

            if result.passed_criteria:
                click.echo(f"\nPassed {len(result.passed_criteria)} criteria:")
                for criterion in result.passed_criteria[:5]:
                    click.echo(f"  ✓ {criterion}")
                if len(result.passed_criteria) > 5:
                    click.echo(f"  ... and {len(result.passed_criteria) - 5} more")

        else:
            click.echo(f"❌ Ticket {ticket_id} FAILED verification")
            click.echo(f"Score: {result.score:.1f}/100")

            if result.failure_reasons:
                click.echo("\nFailure reasons:")
                for reason in result.failure_reasons:
                    click.echo(f"  ✗ {reason}")

            if result.failed_criteria:
                click.echo(f"\nFailed {len(result.failed_criteria)} criteria:")
                for criterion in result.failed_criteria[:5]:
                    click.echo(f"  ✗ {criterion}")
                if len(result.failed_criteria) > 5:
                    click.echo(f"  ... and {len(result.failed_criteria) - 5} more")

            if result.suggestions:
                click.echo("\nSuggestions for improvement:")
                for suggestion in result.suggestions:
                    click.echo(f"  → {suggestion}")

        # Show metadata if verbose
        if verbose and result.metadata:
            click.echo("\nMetadata:")
            for key, value in result.metadata.items():
                click.echo(f"  {key}: {value}")

    # Return exit code
    return 0 if result.status.value == 'pass' else 1


@boss.command()
@click.argument('ticket_file', type=click.Path(exists=True))
@click.option('--strictness', '-s',
              type=click.Choice(['lenient', 'moderate', 'strict', 'brutal']),
              default='strict',
              help='Verification strictness level')
@click.option('--parallel', '-p', is_flag=True,
              help='Verify tickets in parallel')
@click.option('--json-output', is_flag=True,
              help='Output results as JSON')
def verify_all(
    ticket_file: str,
    strictness: str,
    parallel: bool,
    json_output: bool
):
    """Verify all completed tickets in a file.
    
    Example:
        hydra boss verify-all tickets.yaml --strictness strict

    """
    from ..tickets.ticket_parser import TicketParser

    # Parse all tickets
    parser = TicketParser()
    tickets = parser.parse_file(Path(ticket_file))

    if not tickets:
        click.echo(f"Error: No tickets found in {ticket_file}", err=True)
        return 1

    # Filter completed tickets
    completed = [t for t in tickets if t.get('status') in ['DONE', 'COMPLETED']]

    if not completed:
        click.echo("No completed tickets to verify")
        return 0

    click.echo(f"Verifying {len(completed)} completed tickets...")

    # Create verifier
    verifier = create_standalone_verifier(strictness=strictness)

    results = []
    passed = 0
    failed = 0

    for ticket in completed:
        ticket_id = ticket.get('id', 'unknown')
        result = verifier.verify_ticket_completion(
            ticket_id=ticket_id,
            ticket_data=ticket,
            project_path='.'
        )

        if result.status.value == 'pass':
            passed += 1
            status_symbol = '✅'
        else:
            failed += 1
            status_symbol = '❌'

        if not json_output:
            click.echo(f"{status_symbol} Ticket {ticket_id}: {result.status.value.upper()} (score: {result.score:.1f})")

        results.append({
            'ticket_id': ticket_id,
            'status': result.status.value,
            'score': result.score
        })

    # Output summary
    if json_output:
        output = {
            'total': len(completed),
            'passed': passed,
            'failed': failed,
            'results': results
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"\n📊 Summary: {passed} passed, {failed} failed")

        if failed > 0:
            click.echo("\nRun with --verbose to see detailed failure reasons")

    return 0 if failed == 0 else 1


@boss.command()
@click.option('--audit-log', '-l',
              default='.hydra/verification/audit.log',
              help='Path to audit log file')
@click.option('--last', '-n', type=int, default=10,
              help='Show last N verifications')
@click.option('--ticket-id', '-t',
              help='Filter by ticket ID')
def stats(audit_log: str, last: int, ticket_id: Optional[str]):
    """Show verification statistics from audit log.
    
    Example:
        hydra boss stats --last 20

    """
    log_path = Path(audit_log)

    if not log_path.exists():
        click.echo("No audit log found. Run some verifications first.")
        return

    # Read audit log
    entries = []
    with open(log_path) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if not ticket_id or entry.get('ticket_id') == ticket_id:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    if not entries:
        click.echo("No verification entries found")
        return

    # Calculate statistics
    total = len(entries)
    passed = sum(1 for e in entries if e.get('status') == 'pass')
    failed = sum(1 for e in entries if e.get('status') == 'fail')
    errors = sum(1 for e in entries if e.get('status') == 'error')

    avg_score = sum(e.get('score', 0) for e in entries) / total if total > 0 else 0

    # Show statistics
    click.echo("📊 Verification Statistics")
    click.echo(f"Total verifications: {total}")
    click.echo(f"Passed: {passed} ({passed/total*100:.1f}%)")
    click.echo(f"Failed: {failed} ({failed/total*100:.1f}%)")
    if errors > 0:
        click.echo(f"Errors: {errors} ({errors/total*100:.1f}%)")
    click.echo(f"Average score: {avg_score:.1f}")

    # Show recent verifications
    click.echo(f"\n📜 Last {min(last, len(entries))} verifications:")
    for entry in entries[-last:]:
        timestamp = entry.get('timestamp', 'unknown')[:19]
        tid = entry.get('ticket_id', 'unknown')
        status = entry.get('status', 'unknown').upper()
        score = entry.get('score', 0)
        retries = entry.get('retry_count', 0)

        status_symbol = {
            'pass': '✅',
            'fail': '❌',
            'error': '⚠️'
        }.get(entry.get('status'), '❓')

        line = f"{timestamp} {status_symbol} {tid}: {status} (score: {score:.1f})"
        if retries > 0:
            line += f" [retry {retries}]"

        click.echo(line)


if __name__ == '__main__':
    boss()
