"""CLI interface for AI pattern detection."""

import argparse
import json
import sys
from pathlib import Path

import yaml

from hydra.verification_system.ai_detector import (
    AIDetector,
    AIPatternConfig,
    SensitivityLevel,
)


def load_config_file(config_path: str) -> dict:
    """Load configuration from JSON or YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        if path.suffix.lower() in ['.yaml', '.yml']:
            return yaml.safe_load(f)
        else:
            return json.load(f)


def create_config_from_args(args) -> AIPatternConfig:
    """Create configuration from command line arguments."""
    config = AIPatternConfig()

    if args.config:
        config_data = load_config_file(args.config)

        if "sensitivity" in config_data:
            config.sensitivity = SensitivityLevel(config_data["sensitivity"])

        if "emoji_allowed" in config_data:
            config.emoji_allowed = config_data["emoji_allowed"]

        if "whitelist_patterns" in config_data:
            config.whitelist_patterns = set(config_data["whitelist_patterns"])

        if "whitelist_files" in config_data:
            config.whitelist_files = set(config_data["whitelist_files"])

        if "custom_patterns" in config_data:
            config.custom_patterns = config_data["custom_patterns"]

        if "thresholds" in config_data:
            config.thresholds.update(config_data["thresholds"])

        if "max_workers" in config_data:
            config.max_workers = config_data["max_workers"]

    # Override with command line arguments
    if args.sensitivity:
        config.sensitivity = SensitivityLevel(args.sensitivity)

    if args.allow_emoji:
        config.emoji_allowed = True

    if args.workers:
        config.max_workers = args.workers

    if args.whitelist:
        config.whitelist_patterns.update(args.whitelist)

    return config


def format_result(result, verbose: bool = False) -> str:
    """Format detection result for display."""
    output = []

    if result.passes:
        output.append(f"✓ {result.file_path}: PASSED (AI Score: {result.ai_score:.2f})")
    else:
        output.append(f"✗ {result.file_path}: FAILED (AI Score: {result.ai_score:.2f})")

        if verbose and result.detected_patterns:
            output.append("  Detected patterns:")

            # Group by category
            patterns_by_category = {}
            for pattern in result.detected_patterns:
                category = pattern["category"]
                if category not in patterns_by_category:
                    patterns_by_category[category] = []
                patterns_by_category[category].append(pattern)

            for category, patterns in patterns_by_category.items():
                output.append(f"    {category}:")
                for pattern in patterns[:3]:  # Show max 3 per category
                    line = pattern.get("line", "?")
                    match = pattern.get("match", "")[:50]
                    output.append(f"      Line {line}: {match}...")

                if len(patterns) > 3:
                    output.append(f"      ... and {len(patterns) - 3} more")

    return "\n".join(output)


def export_report(report: dict, output_path: str, format: str):
    """Export report to file."""
    path = Path(output_path)

    if format == "json":
        with open(path, 'w') as f:
            json.dump(report, f, indent=2)

    elif format == "markdown":
        with open(path, 'w') as f:
            f.write("# AI Pattern Detection Report\n\n")

            summary = report["summary"]
            f.write("## Summary\n\n")
            f.write(f"- Total files scanned: {summary['total_files']}\n")
            f.write(f"- Files passed: {summary['passed']}\n")
            f.write(f"- Files failed: {summary['failed']}\n")
            f.write(f"- Average AI score: {summary['average_ai_score']:.2f}\n")
            f.write(f"- Sensitivity level: {summary['sensitivity_level']}\n\n")

            if report["pattern_distribution"]:
                f.write("## Pattern Distribution\n\n")
                f.write("| Category | Count |\n")
                f.write("|----------|-------|\n")
                for category, count in report["pattern_distribution"].items():
                    f.write(f"| {category} | {count} |\n")
                f.write("\n")

            if report["failed_files"]:
                f.write("## Failed Files\n\n")
                for file_info in report["failed_files"]:
                    f.write(f"- **{file_info['file']}** (Score: {file_info['score']:.2f}, Patterns: {file_info['pattern_count']})\n")
                f.write("\n")

            if report["recommendations"]:
                f.write("## Recommendations\n\n")
                for rec in report["recommendations"]:
                    f.write(f"- {rec}\n")

    elif format == "html":
        with open(path, 'w') as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>AI Pattern Detection Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .passed { color: green; }
        .failed { color: red; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .summary { background-color: #f9f9f9; padding: 10px; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>AI Pattern Detection Report</h1>
""")

            summary = report["summary"]
            f.write('<div class="summary">')
            f.write("<h2>Summary</h2>")
            f.write(f"<p>Total files scanned: {summary['total_files']}</p>")
            f.write(f'<p class="passed">Files passed: {summary["passed"]}</p>')
            f.write(f'<p class="failed">Files failed: {summary["failed"]}</p>')
            f.write(f"<p>Average AI score: {summary['average_ai_score']:.2f}</p>")
            f.write(f"<p>Sensitivity level: {summary['sensitivity_level']}</p>")
            f.write("</div>")

            if report["pattern_distribution"]:
                f.write("<h2>Pattern Distribution</h2>")
                f.write("<table>")
                f.write("<tr><th>Category</th><th>Count</th></tr>")
                for category, count in report["pattern_distribution"].items():
                    f.write(f"<tr><td>{category}</td><td>{count}</td></tr>")
                f.write("</table>")

            if report["failed_files"]:
                f.write("<h2>Failed Files</h2>")
                f.write("<ul>")
                for file_info in report["failed_files"]:
                    f.write(f'<li class="failed">{file_info["file"]} (Score: {file_info["score"]:.2f}, Patterns: {file_info["pattern_count"]})</li>')
                f.write("</ul>")

            f.write("</body></html>")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Detect AI-generated patterns in code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan a single file
  python -m hydra.verification_system.ai_detector_cli file.py
  
  # Scan a directory with high sensitivity
  python -m hydra.verification_system.ai_detector_cli src/ --sensitivity high
  
  # Use custom configuration
  python -m hydra.verification_system.ai_detector_cli src/ --config ai_config.yaml
  
  # Export detailed report
  python -m hydra.verification_system.ai_detector_cli src/ --export report.json --format json
  
  # Allow emojis and use multiple workers
  python -m hydra.verification_system.ai_detector_cli src/ --allow-emoji --workers 8
"""
    )

    parser.add_argument(
        "path",
        help="File or directory to scan"
    )

    parser.add_argument(
        "-s", "--sensitivity",
        choices=["low", "medium", "high", "paranoid"],
        help="Detection sensitivity level (default: medium)"
    )

    parser.add_argument(
        "-c", "--config",
        help="Path to configuration file (JSON or YAML)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed pattern information"
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Only show summary statistics"
    )

    parser.add_argument(
        "--allow-emoji",
        action="store_true",
        help="Allow emoji characters in code"
    )

    parser.add_argument(
        "-w", "--workers",
        type=int,
        help="Number of parallel workers for directory scanning"
    )

    parser.add_argument(
        "--whitelist",
        nargs="+",
        help="Additional patterns to whitelist"
    )

    parser.add_argument(
        "-e", "--export",
        help="Export report to file"
    )

    parser.add_argument(
        "-f", "--format",
        choices=["json", "markdown", "html"],
        default="json",
        help="Report export format (default: json)"
    )

    parser.add_argument(
        "--extensions",
        nargs="+",
        help="File extensions to scan (e.g., .py .js .ts)"
    )

    parser.add_argument(
        "--fail-on-detection",
        action="store_true",
        help="Exit with non-zero code if AI patterns detected"
    )

    args = parser.parse_args()

    # Create configuration
    config = create_config_from_args(args)

    # Create detector
    detector = AIDetector(config)

    # Determine if path is file or directory
    path = Path(args.path)

    if not path.exists():
        print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
        sys.exit(1)

    results = []

    if path.is_file():
        # Scan single file
        result = detector.detect_file(path)
        results = [result]

        if not args.quiet:
            print(format_result(result, args.verbose))

    elif path.is_dir():
        # Scan directory
        extensions = set(args.extensions) if args.extensions else None
        results = detector.detect_directory(path, extensions)

        if not args.quiet:
            # Sort results by score (highest first)
            results.sort(key=lambda r: r.ai_score, reverse=True)

            for result in results:
                print(format_result(result, args.verbose))

            print("\n" + "="*60)

    # Generate report
    report = detector.generate_report(results)

    if not args.quiet:
        print("\nSummary:")
        print(f"  Total files: {report['summary']['total_files']}")
        print(f"  Passed: {report['summary']['passed']}")
        print(f"  Failed: {report['summary']['failed']}")
        print(f"  Average AI Score: {report['summary']['average_ai_score']:.2f}")
        print(f"  Sensitivity: {report['summary']['sensitivity_level']}")

        if report["recommendations"]:
            print("\nRecommendations:")
            for rec in report["recommendations"]:
                print(f"  - {rec}")

    # Export report if requested
    if args.export:
        export_report(report, args.export, args.format)
        if not args.quiet:
            print(f"\nReport exported to: {args.export}")

    # Exit with appropriate code
    if args.fail_on_detection and report["summary"]["failed"] > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
