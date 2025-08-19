"""Hydra Verification System

A comprehensive automated verification system for validating ticket completion
by checking acceptance criteria against actual implementation.
"""

from .cli_integration import CLIIntegration
from .config import VerificationConfig
from .coverage_analyzer import CoverageAnalyzer
from .criteria_parser import CriteriaParser
from .engine import VerificationEngine
from .quality_checker import QualityChecker
from .report_generator import ReportGenerator

__all__ = [
    'VerificationEngine',
    'QualityChecker',
    'CoverageAnalyzer',
    'CriteriaParser',
    'ReportGenerator',
    'CLIIntegration',
    'VerificationConfig'
]

__version__ = "1.0.0"
