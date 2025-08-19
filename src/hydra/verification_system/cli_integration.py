"""CLI Integration Module

Provides command line interface for running verification from the command line.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import VerificationConfig
from .coverage_analyzer import CoverageAnalyzer
from .criteria_parser import CriteriaParser
from .engine import VerificationEngine
from .quality_checker import QualityChecker
from .report_generator import ReportGenerator


class CLIIntegration:
    """Command line interface integration for the verification system.
    """

    def __init__(self):
        """Initialize CLI integration."""
        self.verification_engine = None
        self.quality_checker = None
        self.coverage_analyzer = None
        self.criteria_parser = None
        self.report_generator = None
        self.config = None

    def setup_components(self, project_root: str, config_file: Optional[str] = None):
        """Setup all verification components."""
        # Load configuration
        self.config = VerificationConfig(config_file)

        # Initialize components
        self.verification_engine = VerificationEngine(project_root)
        self.quality_checker = QualityChecker(project_root)
        self.coverage_analyzer = CoverageAnalyzer(
            project_root,
            min_coverage=self.config.get_setting("min_coverage", 0.8)
        )
        self.criteria_parser = CriteriaParser()
        self.report_generator = ReportGenerator(
            self.config.get_setting("report_output_dir", ".hydra/reports")
        )

    def create_argument_parser(self) -> argparse.ArgumentParser:
        """Create command line argument parser."""
        parser = argparse.ArgumentParser(
            description="Hydra Verification System CLI",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Verify a single ticket
  hydra-verify verify tickets.yaml verify_001
  
  # Run full verification with reports
  hydra-verify verify tickets.yaml verify_001 --report --html
  
  # Check only file existence
  hydra-verify files tickets.yaml verify_001
  
  # Run only quality checks
  hydra-verify quality tickets.yaml verify_001
  
  # Run only coverage analysis
  hydra-verify coverage tickets.yaml verify_001
  
  # Parse acceptance criteria
  hydra-verify criteria tickets.yaml verify_001 --export criteria_analysis.json
            """
        )

        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        # Main verify command
        verify_parser = subparsers.add_parser('verify', help='Run complete verification')
        verify_parser.add_argument('ticket_file', help='Path to ticket file (YAML/JSON)')
        verify_parser.add_argument('ticket_id', help='Ticket ID to verify')
        verify_parser.add_argument('--project-root', '-p', default='.',
                                 help='Project root directory (default: current directory)')
        verify_parser.add_argument('--config', '-c', help='Configuration file path')
        verify_parser.add_argument('--report', '-r', action='store_true',
                                 help='Generate JSON report')
        verify_parser.add_argument('--html', action='store_true',
                                 help='Generate HTML report')
        verify_parser.add_argument('--output-dir', '-o',
                                 help='Output directory for reports')
        verify_parser.add_argument('--verbose', '-v', action='store_true',
                                 help='Verbose output')

        # File verification command
        files_parser = subparsers.add_parser('files', help='Check file existence only')
        files_parser.add_argument('ticket_file', help='Path to ticket file')
        files_parser.add_argument('ticket_id', help='Ticket ID to verify')
        files_parser.add_argument('--project-root', '-p', default='.')
        files_parser.add_argument('--verbose', '-v', action='store_true')

        # Quality checks command
        quality_parser = subparsers.add_parser('quality', help='Run quality checks only')
        quality_parser.add_argument('ticket_file', help='Path to ticket file')
        quality_parser.add_argument('ticket_id', help='Ticket ID to verify')
        quality_parser.add_argument('--project-root', '-p', default='.')
        quality_parser.add_argument('--verbose', '-v', action='store_true')

        # Coverage analysis command
        coverage_parser = subparsers.add_parser('coverage', help='Run coverage analysis only')
        coverage_parser.add_argument('ticket_file', help='Path to ticket file')
        coverage_parser.add_argument('ticket_id', help='Ticket ID to verify')
        coverage_parser.add_argument('--project-root', '-p', default='.')
        coverage_parser.add_argument('--min-coverage', type=float, default=0.8,
                                   help='Minimum coverage threshold (default: 0.8)')
        coverage_parser.add_argument('--verbose', '-v', action='store_true')

        # Criteria parsing command
        criteria_parser = subparsers.add_parser('criteria', help='Parse acceptance criteria')
        criteria_parser.add_argument('ticket_file', help='Path to ticket file')
        criteria_parser.add_argument('ticket_id', help='Ticket ID to parse')
        criteria_parser.add_argument('--export', '-e', help='Export analysis to file')
        criteria_parser.add_argument('--verbose', '-v', action='store_true')

        # Configuration command
        config_parser = subparsers.add_parser('config', help='Manage configuration')
        config_subparsers = config_parser.add_subparsers(dest='config_action')

        config_subparsers.add_parser('init', help='Initialize default configuration')
        config_subparsers.add_parser('show', help='Show current configuration')
        config_validate_parser = config_subparsers.add_parser('validate', help='Validate configuration')
        config_validate_parser.add_argument('config_file', nargs='?', help='Configuration file to validate')

        return parser

    def run_verify_command(self, args) -> int:
        """Run the main verify command."""
        try:
            self.setup_components(args.project_root, args.config)

            if args.output_dir:
                self.report_generator = ReportGenerator(args.output_dir)

            print(f"🔍 Running verification for ticket {args.ticket_id}")
            print(f"📁 Project root: {Path(args.project_root).absolute()}")
            print(f"📄 Ticket file: {args.ticket_file}")

            # Run complete verification
            results = self.run_complete_verification(args.ticket_file, args.ticket_id)

            if not results["success"]:
                print(f"❌ Verification failed: {results.get('error', 'Unknown error')}")
                return 1

            # Display summary
            self.display_verification_summary(results, args.verbose)

            # Generate reports
            if args.report or args.html:
                report_paths = {}

                if args.report:
                    json_path = self.report_generator.generate_json_report(results)
                    report_paths["json"] = json_path
                    print(f"📊 JSON report generated: {json_path}")

                if args.html:
                    html_path = self.report_generator.generate_html_report(results)
                    report_paths["html"] = html_path
                    print(f"📊 HTML report generated: {html_path}")

            # Determine exit code based on results
            overall_success = self.determine_overall_success(results)
            return 0 if overall_success else 1

        except Exception as e:
            print(f"❌ Error during verification: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return 1

    def run_files_command(self, args) -> int:
        """Run file verification only."""
        try:
            self.setup_components(args.project_root)

            print(f"📁 Checking file existence for ticket {args.ticket_id}")

            result = self.verification_engine.run_verification(args.ticket_file, args.ticket_id)

            if not result["success"]:
                print(f"❌ File verification failed: {result.get('error', 'Unknown error')}")
                return 1

            self.display_file_verification_results(result, args.verbose)

            return 0 if result.get("overall_status") == "PASS" else 1

        except Exception as e:
            print(f"❌ Error during file verification: {e}")
            return 1

    def run_quality_command(self, args) -> int:
        """Run quality checks only."""
        try:
            self.setup_components(args.project_root)

            print(f"🔍 Running quality checks for ticket {args.ticket_id}")

            # Load ticket data
            ticket = self.verification_engine.find_ticket_by_id(args.ticket_file, args.ticket_id)
            if not ticket:
                print(f"❌ Ticket {args.ticket_id} not found")
                return 1

            artifacts = ticket.get("artifacts", [])
            result = self.quality_checker.run_quality_checks_for_artifacts(artifacts)

            self.display_quality_check_results(result, args.verbose)

            return 0 if result.get("overall_passed", False) else 1

        except Exception as e:
            print(f"❌ Error during quality checks: {e}")
            return 1

    def run_coverage_command(self, args) -> int:
        """Run coverage analysis only."""
        try:
            self.coverage_analyzer = CoverageAnalyzer(args.project_root, args.min_coverage)
            self.verification_engine = VerificationEngine(args.project_root)

            print(f"📊 Running coverage analysis for ticket {args.ticket_id}")

            # Load ticket data
            ticket = self.verification_engine.find_ticket_by_id(args.ticket_file, args.ticket_id)
            if not ticket:
                print(f"❌ Ticket {args.ticket_id} not found")
                return 1

            artifacts = ticket.get("artifacts", [])
            result = self.coverage_analyzer.comprehensive_coverage_analysis(artifacts)

            self.display_coverage_analysis_results(result, args.verbose)

            overall_assessment = result.get("overall_assessment", {})
            return 0 if overall_assessment.get("has_adequate_coverage", False) else 1

        except Exception as e:
            print(f"❌ Error during coverage analysis: {e}")
            return 1

    def run_criteria_command(self, args) -> int:
        """Run criteria parsing only."""
        try:
            self.criteria_parser = CriteriaParser()

            print(f"📝 Parsing acceptance criteria for ticket {args.ticket_id}")

            parsed_criteria = self.criteria_parser.load_and_parse_ticket(args.ticket_file, args.ticket_id)

            if not parsed_criteria:
                print(f"❌ Ticket {args.ticket_id} not found")
                return 1

            self.display_criteria_parsing_results(parsed_criteria, args.verbose)

            if args.export:
                success = self.criteria_parser.export_criteria_analysis(parsed_criteria, args.export)
                if success:
                    print(f"📄 Criteria analysis exported to: {args.export}")
                else:
                    print("❌ Failed to export criteria analysis")
                    return 1

            return 0

        except Exception as e:
            print(f"❌ Error during criteria parsing: {e}")
            return 1

    def run_config_command(self, args) -> int:
        """Run configuration commands."""
        try:
            if args.config_action == "init":
                config = VerificationConfig()
                config.create_default_config()
                print("✅ Default configuration created at .hydra/verification_config.yaml")
                return 0

            elif args.config_action == "show":
                config = VerificationConfig()
                config.display_config()
                return 0

            elif args.config_action == "validate":
                config_file = args.config_file or ".hydra/verification_config.yaml"
                config = VerificationConfig(config_file)
                if config.validate_config():
                    print(f"✅ Configuration is valid: {config_file}")
                    return 0
                else:
                    print(f"❌ Configuration is invalid: {config_file}")
                    return 1

            else:
                print("❌ Unknown config action")
                return 1

        except Exception as e:
            print(f"❌ Error in config command: {e}")
            return 1

    def run_complete_verification(self, ticket_file: str, ticket_id: str) -> Dict[str, Any]:
        """Run complete verification including all components."""
        try:
            # Load ticket data
            ticket = self.verification_engine.find_ticket_by_id(ticket_file, ticket_id)
            if not ticket:
                return {
                    "success": False,
                    "error": f"Ticket {ticket_id} not found in {ticket_file}"
                }

            artifacts = ticket.get("artifacts", [])

            # Run all verification components
            results = {
                "success": True,
                "ticket_id": ticket_id,
                "title": ticket.get("title", ""),
                "timestamp": datetime.now().isoformat()
            }

            # File verification
            file_verification = self.verification_engine.verify_ticket_artifacts(ticket)
            results["file_verification"] = file_verification

            # Quality checks
            quality_checks = self.quality_checker.run_quality_checks_for_artifacts(artifacts)
            results["quality_checks"] = quality_checks

            # Coverage analysis
            coverage_analysis = self.coverage_analyzer.comprehensive_coverage_analysis(artifacts)
            results["coverage_analysis"] = coverage_analysis

            # Criteria validation
            parsed_criteria = self.criteria_parser.parse_ticket_criteria(ticket)
            criteria_validation = {
                "ticket_id": parsed_criteria.ticket_id,
                "total_criteria": parsed_criteria.total_count,
                "completed_criteria": parsed_criteria.completed_count,
                "verified_criteria": parsed_criteria.verified_count,
                "criteria": [
                    {
                        "id": c.id,
                        "text": c.text,
                        "status": c.status.value,
                        "completed": c.completed,
                        "verified": c.verified,
                        "verification_method": c.verification_method
                    }
                    for c in parsed_criteria.criteria
                ]
            }
            results["criteria_validation"] = criteria_validation

            return results

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def display_verification_summary(self, results: Dict[str, Any], verbose: bool = False):
        """Display verification summary."""
        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)

        # File verification
        file_data = results.get("file_verification", {})
        file_status = file_data.get("overall_status", "UNKNOWN")
        file_ratio = f"{file_data.get('passed_artifacts', 0)}/{file_data.get('total_artifacts', 0)}"
        print(f"📁 File Verification: {file_status} ({file_ratio})")

        # Quality checks
        quality_data = results.get("quality_checks", {})
        quality_status = "PASS" if quality_data.get("overall_passed", False) else "FAIL"
        quality_score = quality_data.get("overall_score", 0)
        print(f"🔍 Quality Checks: {quality_status} ({quality_score:.1%})")

        # Coverage analysis
        coverage_data = results.get("coverage_analysis", {})
        coverage_assessment = coverage_data.get("overall_assessment", {})
        coverage_status = "PASS" if coverage_assessment.get("has_adequate_coverage", False) else "FAIL"
        coverage_score = coverage_assessment.get("coverage_score", 0)
        print(f"📊 Test Coverage: {coverage_status} ({coverage_score:.1%})")

        # Criteria validation
        criteria_data = results.get("criteria_validation", {})
        verified_ratio = f"{criteria_data.get('verified_criteria', 0)}/{criteria_data.get('total_criteria', 0)}"
        criteria_status = "PASS" if criteria_data.get('verified_criteria', 0) == criteria_data.get('total_criteria', 0) else "FAIL"
        print(f"📝 Acceptance Criteria: {criteria_status} ({verified_ratio})")

        print("="*60)

    def display_file_verification_results(self, results: Dict[str, Any], verbose: bool = False):
        """Display file verification results."""
        print("\n📁 File Verification Results:")
        print(f"Status: {results.get('overall_status', 'UNKNOWN')}")
        print(f"Artifacts: {results.get('passed_artifacts', 0)}/{results.get('total_artifacts', 0)} passed")

        if verbose:
            for result in results.get("results", []):
                status_icon = "✅" if result["passed"] else "❌"
                print(f"  {status_icon} {result['details']['path']}")

    def display_quality_check_results(self, results: Dict[str, Any], verbose: bool = False):
        """Display quality check results."""
        print("\n🔍 Quality Check Results:")
        print(f"Overall Score: {results.get('overall_score', 0):.1%}")
        print(f"Files: {results.get('passed_files', 0)}/{results.get('total_files', 0)} passed")

        if verbose:
            for file_result in results.get("file_results", []):
                status_icon = "✅" if file_result["overall_passed"] else "❌"
                print(f"  {status_icon} {file_result['file_path']} ({file_result['overall_score']:.1%})")

    def display_coverage_analysis_results(self, results: Dict[str, Any], verbose: bool = False):
        """Display coverage analysis results."""
        static_analysis = results.get("static_analysis", {})

        print("\n📊 Coverage Analysis Results:")
        print(f"Average Coverage: {static_analysis.get('average_coverage', 0):.1%}")
        print(f"Files with Tests: {static_analysis.get('files_with_tests', 0)}/{static_analysis.get('total_files', 0)}")

        if verbose:
            for file_result in static_analysis.get("file_results", []):
                test_status = "📝" if file_result["has_tests"] else "❌"
                print(f"  {test_status} {file_result['file_path']} ({file_result['estimated_coverage']:.1%})")

    def display_criteria_parsing_results(self, parsed_criteria, verbose: bool = False):
        """Display criteria parsing results."""
        print("\n📝 Acceptance Criteria Analysis:")
        print(f"Total Criteria: {parsed_criteria.total_count}")
        print(f"Completed: {parsed_criteria.completed_count}")
        print(f"Verified: {parsed_criteria.verified_count}")

        if verbose:
            for criterion in parsed_criteria.criteria:
                status_icon = "✅" if criterion.verified else ("🔄" if criterion.completed else "⏳")
                print(f"  {status_icon} {criterion.id}: {criterion.text[:60]}...")

    def determine_overall_success(self, results: Dict[str, Any]) -> bool:
        """Determine overall success based on all verification results."""
        file_passed = results.get("file_verification", {}).get("overall_status") == "PASS"
        quality_passed = results.get("quality_checks", {}).get("overall_passed", False)
        coverage_passed = results.get("coverage_analysis", {}).get("overall_assessment", {}).get("has_adequate_coverage", False)

        criteria_data = results.get("criteria_validation", {})
        criteria_passed = (criteria_data.get("verified_criteria", 0) ==
                          criteria_data.get("total_criteria", 0))

        return file_passed and quality_passed and coverage_passed and criteria_passed

    def main(self, args: Optional[List[str]] = None) -> int:
        """Main CLI entry point."""
        parser = self.create_argument_parser()
        parsed_args = parser.parse_args(args)

        if not parsed_args.command:
            parser.print_help()
            return 1

        if parsed_args.command == "verify":
            return self.run_verify_command(parsed_args)
        elif parsed_args.command == "files":
            return self.run_files_command(parsed_args)
        elif parsed_args.command == "quality":
            return self.run_quality_command(parsed_args)
        elif parsed_args.command == "coverage":
            return self.run_coverage_command(parsed_args)
        elif parsed_args.command == "criteria":
            return self.run_criteria_command(parsed_args)
        elif parsed_args.command == "config":
            return self.run_config_command(parsed_args)
        else:
            print(f"❌ Unknown command: {parsed_args.command}")
            return 1


def main():
    """Entry point for the CLI."""
    cli = CLIIntegration()
    return cli.main()


if __name__ == "__main__":
    sys.exit(main())
