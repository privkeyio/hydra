"""Hydra Verification System

A comprehensive automated verification system for validating ticket completion
by checking acceptance criteria against actual implementation.
Includes AI pattern detection for ensuring production-quality code.
"""

from .ai_detector import (
    AIDetector,
    AIPatternConfig,
    DetectionResult,
    SensitivityLevel,
    create_detector,
)
from .boss_agent import (
    BossAgent,
    VerificationResult,
    VerificationStatus,
)
from .boss_agent import (
    StrictnessLevel as BossStrictnessLevel,
)
from .boss_agent import (
    VerificationConfig as BossVerificationConfig,
)
from .cli_integration import CLIIntegration
from .config import VerificationConfig
from .coverage_analyzer import CoverageAnalyzer
from .criteria_parser import CriteriaParser
from .criteria_templates import (
    APIEndpointTemplate,
    BaseCriteriaTemplate,
    BossAgentIntegration,
    CLIToolTemplate,
    CriteriaComposer,
    CriteriaTemplate,
    CriteriaType,
    LibraryTemplate,
    StrictnessLevel,
    VerificationCriteria,
    WebAppTemplate,
    create_template_for_project_type,
    evaluate_project_against_template,
)
from .engine import VerificationEngine
from .quality_checker import QualityChecker
from .report_generator import ReportGenerator
from .workflow_hooks import (
    VerificationHook,
    create_standalone_verifier,
    register_verification_hooks,
)

__all__ = [
    'VerificationEngine',
    'QualityChecker',
    'CoverageAnalyzer',
    'CriteriaParser',
    'ReportGenerator',
    'CLIIntegration',
    'VerificationConfig',
    'BossAgent',
    'BossVerificationConfig',
    'VerificationResult',
    'VerificationStatus',
    'BossStrictnessLevel',
    'VerificationHook',
    'register_verification_hooks',
    'create_standalone_verifier',
    'AIDetector',
    'AIPatternConfig',
    'DetectionResult',
    'SensitivityLevel',
    'create_detector',
    'StrictnessLevel',
    'CriteriaType',
    'VerificationCriteria',
    'CriteriaTemplate',
    'BaseCriteriaTemplate',
    'APIEndpointTemplate',
    'CLIToolTemplate',
    'LibraryTemplate',
    'WebAppTemplate',
    'CriteriaComposer',
    'BossAgentIntegration',
    'create_template_for_project_type',
    'evaluate_project_against_template'
]

__version__ = "1.0.0"
