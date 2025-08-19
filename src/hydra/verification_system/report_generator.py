"""Report Generator Module

Creates detailed verification reports in JSON and HTML formats.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReportGenerator:
    """Generator for creating detailed verification reports in multiple formats.
    """

    def __init__(self, output_dir: str = ".hydra/reports"):
        """Initialize the report generator."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_summary_data(self, verification_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary data from verification results."""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "ticket_id": verification_results.get("ticket_id"),
            "title": verification_results.get("title"),
            "overall_status": "UNKNOWN",
            "total_score": 0.0,
            "component_scores": {},
            "recommendations": []
        }

        # Calculate overall scores and status
        components = [
            ("file_verification", "File Verification"),
            ("quality_checks", "Code Quality"),
            ("coverage_analysis", "Test Coverage"),
            ("criteria_validation", "Acceptance Criteria")
        ]

        total_score = 0.0
        component_count = 0
        all_passed = True

        for comp_key, comp_name in components:
            if comp_key in verification_results:
                comp_data = verification_results[comp_key]

                if comp_key == "file_verification":
                    score = comp_data.get("success_rate", 0.0)
                    passed = comp_data.get("overall_status") == "PASS"
                elif comp_key == "quality_checks":
                    score = comp_data.get("overall_score", 0.0)
                    passed = comp_data.get("overall_passed", False)
                elif comp_key == "coverage_analysis":
                    score = comp_data.get("overall_assessment", {}).get("coverage_score", 0.0)
                    passed = comp_data.get("overall_assessment", {}).get("has_adequate_coverage", False)
                elif comp_key == "criteria_validation":
                    total_criteria = comp_data.get("total_criteria", 1)
                    verified_criteria = comp_data.get("verified_criteria", 0)
                    score = verified_criteria / total_criteria if total_criteria > 0 else 0.0
                    passed = score >= 0.8  # 80% threshold
                else:
                    score = 0.0
                    passed = False

                summary["component_scores"][comp_name] = {
                    "score": score,
                    "passed": passed,
                    "percentage": f"{score:.1%}"
                }

                total_score += score
                component_count += 1
                all_passed = all_passed and passed

        if component_count > 0:
            summary["total_score"] = total_score / component_count
            summary["overall_status"] = "PASS" if all_passed else "FAIL"

        return summary

    def generate_json_report(self, verification_results: Dict[str, Any],
                           filename: Optional[str] = None) -> str:
        """Generate a detailed JSON report."""
        if not filename:
            ticket_id = verification_results.get("ticket_id", "unknown")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"verification_report_{ticket_id}_{timestamp}.json"

        # Generate summary
        summary = self.generate_summary_data(verification_results)

        # Create comprehensive report
        report_data = {
            "metadata": {
                "report_type": "verification_report",
                "format_version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "generator": "Hydra Verification System"
            },
            "summary": summary,
            "detailed_results": verification_results,
            "recommendations": self._generate_recommendations(verification_results)
        }

        # Write to file
        output_path = self.output_dir / filename
        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)

        return str(output_path)

    def generate_html_report(self, verification_results: Dict[str, Any],
                           filename: Optional[str] = None) -> str:
        """Generate an HTML report."""
        if not filename:
            ticket_id = verification_results.get("ticket_id", "unknown")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"verification_report_{ticket_id}_{timestamp}.html"

        summary = self.generate_summary_data(verification_results)

        html_content = self._generate_html_content(summary, verification_results)

        # Write to file
        output_path = self.output_dir / filename
        with open(output_path, 'w') as f:
            f.write(html_content)

        return str(output_path)

    def _generate_html_content(self, summary: Dict[str, Any],
                             results: Dict[str, Any]) -> str:
        """Generate HTML content for the report."""
        # Generate component sections
        component_html = ""

        if "file_verification" in results:
            component_html += self._generate_file_verification_html(results["file_verification"])

        if "quality_checks" in results:
            component_html += self._generate_quality_checks_html(results["quality_checks"])

        if "coverage_analysis" in results:
            component_html += self._generate_coverage_analysis_html(results["coverage_analysis"])

        if "criteria_validation" in results:
            component_html += self._generate_criteria_validation_html(results["criteria_validation"])

        # Main HTML template
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification Report - {summary.get('ticket_id', 'Unknown')}</title>
    <style>
        {self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Hydra Verification Report</h1>
            <div class="metadata">
                <span><strong>Ticket ID:</strong> {summary.get('ticket_id', 'Unknown')}</span>
                <span><strong>Generated:</strong> {summary.get('timestamp', 'Unknown')}</span>
                <span class="status status-{summary.get('overall_status', 'unknown').lower()}">
                    <strong>Status:</strong> {summary.get('overall_status', 'Unknown')}
                </span>
            </div>
        </header>
        
        <section class="summary">
            <h2>Summary</h2>
            <div class="score-container">
                <div class="overall-score">
                    <div class="score-circle">
                        <span class="score-value">{summary.get('total_score', 0):.1%}</span>
                        <span class="score-label">Overall Score</span>
                    </div>
                </div>
                <div class="component-scores">
                    {self._generate_component_scores_html(summary.get('component_scores', {}))}
                </div>
            </div>
        </section>
        
        {component_html}
        
        <section class="recommendations">
            <h2>Recommendations</h2>
            {self._generate_recommendations_html(results)}
        </section>
        
        <footer>
            <p>Generated by Hydra Verification System v1.0.0</p>
        </footer>
    </div>
</body>
</html>
"""
        return html_template

    def _get_css_styles(self) -> str:
        """Get CSS styles for the HTML report."""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-top: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
        }
        
        header {
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        
        h1 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        
        h2 {
            color: #34495e;
            margin-bottom: 15px;
            border-left: 4px solid #3498db;
            padding-left: 10px;
        }
        
        .metadata {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .status {
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
            text-transform: uppercase;
            font-size: 0.85em;
        }
        
        .status-pass {
            background-color: #d4edda;
            color: #155724;
        }
        
        .status-fail {
            background-color: #f8d7da;
            color: #721c24;
        }
        
        .summary {
            margin-bottom: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 8px;
        }
        
        .score-container {
            display: flex;
            gap: 30px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .overall-score {
            text-align: center;
        }
        
        .score-circle {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            color: white;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        
        .score-value {
            font-size: 1.5em;
            font-weight: bold;
        }
        
        .score-label {
            font-size: 0.8em;
            opacity: 0.9;
        }
        
        .component-scores {
            flex: 1;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .component-score {
            background: white;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #3498db;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        
        .component-score.passed {
            border-left-color: #27ae60;
        }
        
        .component-score.failed {
            border-left-color: #e74c3c;
        }
        
        .section {
            margin-bottom: 30px;
            padding: 20px;
            border: 1px solid #e9ecef;
            border-radius: 8px;
        }
        
        .artifact-list {
            display: grid;
            gap: 10px;
        }
        
        .artifact-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
        }
        
        .artifact-item.passed {
            background: #d4edda;
            border-left: 4px solid #28a745;
        }
        
        .artifact-item.failed {
            background: #f8d7da;
            border-left: 4px solid #dc3545;
        }
        
        .recommendations ul {
            list-style-type: none;
            padding-left: 0;
        }
        
        .recommendations li {
            padding: 10px;
            margin-bottom: 8px;
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            border-radius: 4px;
        }
        
        footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e9ecef;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }
        
        .table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        
        .table th, .table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }
        
        .table th {
            background-color: #f8f9fa;
            font-weight: 600;
        }
        
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75em;
            font-weight: bold;
            text-transform: uppercase;
        }
        
        .badge-success {
            background-color: #d4edda;
            color: #155724;
        }
        
        .badge-danger {
            background-color: #f8d7da;
            color: #721c24;
        }
        """

    def _generate_component_scores_html(self, component_scores: Dict[str, Any]) -> str:
        """Generate HTML for component scores."""
        html_parts = []

        for component_name, score_data in component_scores.items():
            status_class = "passed" if score_data["passed"] else "failed"
            html_parts.append(f"""
                <div class="component-score {status_class}">
                    <h4>{component_name}</h4>
                    <div style="font-size: 1.2em; font-weight: bold; color: {'#27ae60' if score_data['passed'] else '#e74c3c'};">
                        {score_data['percentage']}
                    </div>
                    <div style="font-size: 0.9em; color: #6c757d;">
                        {'✓ Passed' if score_data['passed'] else '✗ Failed'}
                    </div>
                </div>
            """)

        return "".join(html_parts)

    def _generate_file_verification_html(self, file_verification: Dict[str, Any]) -> str:
        """Generate HTML for file verification section."""
        artifacts_html = ""

        for result in file_verification.get("results", []):
            status_class = "passed" if result["passed"] else "failed"
            icon = "✓" if result["passed"] else "✗"

            artifacts_html += f"""
                <div class="artifact-item {status_class}">
                    <span><strong>{result['details']['path']}</strong> ({result['details']['type']})</span>
                    <span>{icon} {result['message']}</span>
                </div>
            """

        return f"""
            <section class="section">
                <h2>File Verification</h2>
                <p><strong>Status:</strong> {file_verification.get('overall_status', 'Unknown')}</p>
                <p><strong>Artifacts:</strong> {file_verification.get('passed_artifacts', 0)}/{file_verification.get('total_artifacts', 0)} passed</p>
                <div class="artifact-list">
                    {artifacts_html}
                </div>
            </section>
        """

    def _generate_quality_checks_html(self, quality_checks: Dict[str, Any]) -> str:
        """Generate HTML for quality checks section."""
        files_html = ""

        for file_result in quality_checks.get("file_results", []):
            status_class = "passed" if file_result["overall_passed"] else "failed"

            checks_html = ""
            for check in file_result.get("checks", []):
                check_status = "✓" if check["passed"] else "✗"
                checks_html += f"<li>{check_status} {check['type']}: {check['score']:.1%}</li>"

            files_html += f"""
                <div class="artifact-item {status_class}">
                    <div>
                        <strong>{file_result['file_path']}</strong>
                        <ul style="margin: 5px 0 0 20px; font-size: 0.9em;">
                            {checks_html}
                        </ul>
                    </div>
                    <span>Score: {file_result['overall_score']:.1%}</span>
                </div>
            """

        return f"""
            <section class="section">
                <h2>Code Quality Checks</h2>
                <p><strong>Overall Score:</strong> {quality_checks.get('overall_score', 0):.1%}</p>
                <p><strong>Files:</strong> {quality_checks.get('passed_files', 0)}/{quality_checks.get('total_files', 0)} passed</p>
                <div class="artifact-list">
                    {files_html}
                </div>
            </section>
        """

    def _generate_coverage_analysis_html(self, coverage_analysis: Dict[str, Any]) -> str:
        """Generate HTML for coverage analysis section."""
        static_analysis = coverage_analysis.get("static_analysis", {})

        files_html = ""
        for file_result in static_analysis.get("file_results", []):
            status_class = "passed" if file_result["meets_threshold"] else "failed"
            test_status = "Has tests" if file_result["has_tests"] else "No tests"

            files_html += f"""
                <div class="artifact-item {status_class}">
                    <div>
                        <strong>{file_result['file_path']}</strong>
                        <div style="font-size: 0.9em; color: #6c757d;">{test_status}</div>
                    </div>
                    <span>Coverage: {file_result['estimated_coverage']:.1%}</span>
                </div>
            """

        recommendations_html = ""
        for rec in coverage_analysis.get("recommendations", []):
            recommendations_html += f"<li>{rec}</li>"

        return f"""
            <section class="section">
                <h2>Test Coverage Analysis</h2>
                <p><strong>Average Coverage:</strong> {static_analysis.get('average_coverage', 0):.1%}</p>
                <p><strong>Files with Tests:</strong> {static_analysis.get('files_with_tests', 0)}/{static_analysis.get('total_files', 0)}</p>
                <div class="artifact-list">
                    {files_html}
                </div>
                {f'<h3>Coverage Recommendations</h3><ul>{recommendations_html}</ul>' if recommendations_html else ''}
            </section>
        """

    def _generate_criteria_validation_html(self, criteria_validation: Dict[str, Any]) -> str:
        """Generate HTML for criteria validation section."""
        criteria_html = ""

        for criterion in criteria_validation.get("criteria", []):
            status_class = "passed" if criterion["verified"] else "failed"
            status_text = "Verified" if criterion["verified"] else ("Completed" if criterion["completed"] else "Not Started")

            criteria_html += f"""
                <div class="artifact-item {status_class}">
                    <div>
                        <strong>{criterion['id']}</strong>
                        <div style="margin-top: 5px;">{criterion['text']}</div>
                        <div style="font-size: 0.9em; color: #6c757d; margin-top: 5px;">
                            Method: {criterion['verification_method']}
                        </div>
                    </div>
                    <span class="badge {'badge-success' if criterion['verified'] else 'badge-danger'}">
                        {status_text}
                    </span>
                </div>
            """

        return f"""
            <section class="section">
                <h2>Acceptance Criteria Validation</h2>
                <p><strong>Progress:</strong> {criteria_validation.get('verified_criteria', 0)}/{criteria_validation.get('total_criteria', 0)} verified</p>
                <div class="artifact-list">
                    {criteria_html}
                </div>
            </section>
        """

    def _generate_recommendations_html(self, results: Dict[str, Any]) -> str:
        """Generate HTML for recommendations section."""
        recommendations = self._generate_recommendations(results)

        if not recommendations:
            return "<p>No recommendations at this time. Great job!</p>"

        recommendations_html = ""
        for rec in recommendations:
            recommendations_html += f"<li>{rec}</li>"

        return f"<ul>{recommendations_html}</ul>"

    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on verification results."""
        recommendations = []

        # File verification recommendations
        if "file_verification" in results:
            file_data = results["file_verification"]
            if file_data.get("overall_status") != "PASS":
                missing_files = []
                for result in file_data.get("results", []):
                    if not result["passed"]:
                        missing_files.append(result["details"]["path"])

                if missing_files:
                    recommendations.append(f"Create missing files: {', '.join(missing_files[:3])}")

        # Quality recommendations
        if "quality_checks" in results:
            quality_data = results["quality_checks"]
            if not quality_data.get("overall_passed", True):
                recommendations.append("Fix code quality issues in failing files")

        # Coverage recommendations
        if "coverage_analysis" in results:
            coverage_data = results["coverage_analysis"]
            coverage_recs = coverage_data.get("recommendations", [])
            recommendations.extend(coverage_recs[:3])  # Limit to 3 recommendations

        # Criteria recommendations
        if "criteria_validation" in results:
            criteria_data = results["criteria_validation"]
            unverified = criteria_data.get("total_criteria", 0) - criteria_data.get("verified_criteria", 0)
            if unverified > 0:
                recommendations.append(f"Complete verification for {unverified} remaining acceptance criteria")

        return recommendations

    def generate_combined_report(self, verification_results: Dict[str, Any]) -> Dict[str, str]:
        """Generate both JSON and HTML reports."""
        json_path = self.generate_json_report(verification_results)
        html_path = self.generate_html_report(verification_results)

        return {
            "json_report": json_path,
            "html_report": html_path
        }
