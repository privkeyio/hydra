"""Quality Metrics Configuration Module

Provides configurable thresholds and settings for quality metrics analysis.
Supports environment-specific configurations and custom quality gates.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class ComplexityThresholds:
    """Thresholds for code complexity metrics"""

    max_cyclomatic_complexity: int = 15
    max_cognitive_complexity: int = 20
    max_nesting_depth: int = 4
    max_function_length: int = 50
    max_duplicate_ratio: float = 0.1
    max_lines_per_file: int = 500


@dataclass
class CoverageThresholds:
    """Thresholds for test coverage metrics"""

    min_line_coverage: float = 70.0
    min_branch_coverage: float = 60.0
    min_function_coverage: float = 80.0
    min_test_to_code_ratio: float = 0.5
    require_test_files: bool = True


@dataclass
class DocumentationThresholds:
    """Thresholds for documentation completeness"""

    min_docstring_coverage: float = 60.0
    min_public_api_documentation: float = 80.0
    require_readme: bool = True
    require_api_docs: bool = False
    min_inline_comment_ratio: float = 0.1


@dataclass
class ErrorHandlingThresholds:
    """Thresholds for error handling coverage"""

    min_try_except_coverage: float = 50.0
    require_error_logging: bool = True
    require_custom_exceptions: bool = False
    min_validation_coverage: float = 30.0
    require_input_sanitization: bool = True


@dataclass
class PerformanceThresholds:
    """Thresholds for performance metrics"""

    max_response_time_ms: float = 1000.0
    max_memory_usage_mb: float = 100.0
    require_caching: bool = False
    require_async_operations: bool = False
    require_connection_pooling: bool = False


@dataclass
class SecurityThresholds:
    """Thresholds for security metrics"""

    allow_secrets_in_code: bool = False
    require_sql_injection_safe: bool = True
    require_xss_protection: bool = True
    require_input_validation: bool = True
    require_authentication: bool = False
    require_authorization: bool = False
    require_audit_logging: bool = False


@dataclass
class QualityGates:
    """Overall quality gate configuration"""

    min_overall_score: float = 70.0
    require_production_ready: bool = True
    max_critical_issues: int = 0
    max_major_issues: int = 5
    max_minor_issues: int = 20


@dataclass
class MetricsConfig:
    """Complete metrics configuration"""

    complexity: ComplexityThresholds = field(default_factory=ComplexityThresholds)
    coverage: CoverageThresholds = field(default_factory=CoverageThresholds)
    documentation: DocumentationThresholds = field(default_factory=DocumentationThresholds)
    error_handling: ErrorHandlingThresholds = field(default_factory=ErrorHandlingThresholds)
    performance: PerformanceThresholds = field(default_factory=PerformanceThresholds)
    security: SecurityThresholds = field(default_factory=SecurityThresholds)
    quality_gates: QualityGates = field(default_factory=QualityGates)

    # Global settings
    strict_mode: bool = False
    enable_ai_detection: bool = True
    enable_performance_benchmarks: bool = True
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "*/venv/*", "*/node_modules/*", "*/__pycache__/*", "*/build/*", "*/dist/*"
    ])
    include_test_files: bool = True
    timeout_seconds: int = 300


class MetricsConfigManager:
    """Manages quality metrics configuration"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize config manager
        
        Args:
            config_path: Path to configuration file (YAML)

        """
        self.config_path = config_path
        self._config: Optional[MetricsConfig] = None
        self._environment_overrides = self._load_environment_overrides()

    def get_config(self, environment: Optional[str] = None) -> MetricsConfig:
        """Get configuration for specified environment
        
        Args:
            environment: Environment name (dev, test, prod, strict)
            
        Returns:
            MetricsConfig instance

        """
        if self._config is None:
            self._config = self._load_config()

        # Apply environment-specific overrides
        config = self._apply_environment_config(self._config, environment)

        # Apply environment variable overrides
        config = self._apply_environment_overrides(config)

        return config

    def _load_config(self) -> MetricsConfig:
        """Load configuration from file or defaults"""
        if self.config_path and Path(self.config_path).exists():
            return self._load_from_file(self.config_path)

        # Try default locations
        default_paths = [
            "quality_metrics.yaml",
            "config/quality_metrics.yaml",
            ".hydra/quality_metrics.yaml"
        ]

        for path in default_paths:
            if Path(path).exists():
                return self._load_from_file(path)

        # Return default configuration
        return MetricsConfig()

    def _load_from_file(self, path: str) -> MetricsConfig:
        """Load configuration from YAML file"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            return self._dict_to_config(data)
        except Exception as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            return MetricsConfig()

    def _dict_to_config(self, data: Dict[str, Any]) -> MetricsConfig:
        """Convert dictionary to MetricsConfig"""
        config = MetricsConfig()

        if 'complexity' in data:
            config.complexity = ComplexityThresholds(**data['complexity'])
        if 'coverage' in data:
            config.coverage = CoverageThresholds(**data['coverage'])
        if 'documentation' in data:
            config.documentation = DocumentationThresholds(**data['documentation'])
        if 'error_handling' in data:
            config.error_handling = ErrorHandlingThresholds(**data['error_handling'])
        if 'performance' in data:
            config.performance = PerformanceThresholds(**data['performance'])
        if 'security' in data:
            config.security = SecurityThresholds(**data['security'])
        if 'quality_gates' in data:
            config.quality_gates = QualityGates(**data['quality_gates'])

        # Global settings
        for key in ['strict_mode', 'enable_ai_detection', 'enable_performance_benchmarks',
                   'exclude_patterns', 'include_test_files', 'timeout_seconds']:
            if key in data:
                setattr(config, key, data[key])

        return config

    def _apply_environment_config(self, config: MetricsConfig, environment: Optional[str]) -> MetricsConfig:
        """Apply environment-specific configuration"""
        if not environment:
            return config

        env_config = MetricsConfig(
            complexity=ComplexityThresholds(**config.complexity.__dict__),
            coverage=CoverageThresholds(**config.coverage.__dict__),
            documentation=DocumentationThresholds(**config.documentation.__dict__),
            error_handling=ErrorHandlingThresholds(**config.error_handling.__dict__),
            performance=PerformanceThresholds(**config.performance.__dict__),
            security=SecurityThresholds(**config.security.__dict__),
            quality_gates=QualityGates(**config.quality_gates.__dict__)
        )

        # Environment-specific adjustments
        if environment.lower() == 'strict':
            env_config.strict_mode = True
            env_config.quality_gates.min_overall_score = 85.0
            env_config.coverage.min_line_coverage = 85.0
            env_config.complexity.max_cyclomatic_complexity = 10
            env_config.documentation.min_docstring_coverage = 80.0
            env_config.error_handling.min_try_except_coverage = 70.0

        elif environment.lower() == 'prod':
            env_config.quality_gates.min_overall_score = 80.0
            env_config.coverage.min_line_coverage = 75.0
            env_config.security.require_authentication = True
            env_config.security.require_audit_logging = True
            env_config.performance.require_caching = True

        elif environment.lower() == 'test':
            env_config.quality_gates.min_overall_score = 60.0
            env_config.coverage.min_line_coverage = 60.0
            env_config.documentation.require_readme = False

        elif environment.lower() == 'dev':
            env_config.quality_gates.min_overall_score = 50.0
            env_config.coverage.min_line_coverage = 40.0
            env_config.documentation.require_readme = False
            env_config.enable_performance_benchmarks = False

        return env_config

    def _load_environment_overrides(self) -> Dict[str, Any]:
        """Load configuration overrides from environment variables"""
        overrides = {}

        # Quality gate overrides
        if os.getenv('HYDRA_MIN_OVERALL_SCORE'):
            overrides['quality_gates.min_overall_score'] = float(os.getenv('HYDRA_MIN_OVERALL_SCORE'))

        # Coverage overrides
        if os.getenv('HYDRA_MIN_COVERAGE'):
            overrides['coverage.min_line_coverage'] = float(os.getenv('HYDRA_MIN_COVERAGE'))

        # Complexity overrides
        if os.getenv('HYDRA_MAX_COMPLEXITY'):
            overrides['complexity.max_cyclomatic_complexity'] = int(os.getenv('HYDRA_MAX_COMPLEXITY'))

        # Security overrides
        if os.getenv('HYDRA_ALLOW_SECRETS'):
            overrides['security.allow_secrets_in_code'] = os.getenv('HYDRA_ALLOW_SECRETS').lower() == 'true'

        # Global overrides
        if os.getenv('HYDRA_STRICT_MODE'):
            overrides['strict_mode'] = os.getenv('HYDRA_STRICT_MODE').lower() == 'true'

        if os.getenv('HYDRA_ENABLE_AI_DETECTION'):
            overrides['enable_ai_detection'] = os.getenv('HYDRA_ENABLE_AI_DETECTION').lower() == 'true'

        return overrides

    def _apply_environment_overrides(self, config: MetricsConfig) -> MetricsConfig:
        """Apply environment variable overrides"""
        for key, value in self._environment_overrides.items():
            self._set_nested_attribute(config, key, value)

        return config

    def _set_nested_attribute(self, obj: Any, key: str, value: Any) -> None:
        """Set nested attribute using dot notation"""
        parts = key.split('.')
        current = obj

        for part in parts[:-1]:
            current = getattr(current, part)

        setattr(current, parts[-1], value)

    def save_config(self, config: MetricsConfig, path: str) -> None:
        """Save configuration to YAML file"""
        config_dict = {
            'complexity': config.complexity.__dict__,
            'coverage': config.coverage.__dict__,
            'documentation': config.documentation.__dict__,
            'error_handling': config.error_handling.__dict__,
            'performance': config.performance.__dict__,
            'security': config.security.__dict__,
            'quality_gates': config.quality_gates.__dict__,
            'strict_mode': config.strict_mode,
            'enable_ai_detection': config.enable_ai_detection,
            'enable_performance_benchmarks': config.enable_performance_benchmarks,
            'exclude_patterns': config.exclude_patterns,
            'include_test_files': config.include_test_files,
            'timeout_seconds': config.timeout_seconds
        }

        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2)

    def validate_config(self, config: MetricsConfig) -> List[str]:
        """Validate configuration and return any issues"""
        issues = []

        # Validate thresholds are reasonable
        if config.quality_gates.min_overall_score < 0 or config.quality_gates.min_overall_score > 100:
            issues.append("min_overall_score must be between 0 and 100")

        if config.coverage.min_line_coverage < 0 or config.coverage.min_line_coverage > 100:
            issues.append("min_line_coverage must be between 0 and 100")

        if config.complexity.max_cyclomatic_complexity < 1:
            issues.append("max_cyclomatic_complexity must be positive")

        if config.complexity.max_function_length < 1:
            issues.append("max_function_length must be positive")

        if config.performance.max_response_time_ms < 0:
            issues.append("max_response_time_ms must be non-negative")

        return issues


# Global configuration manager instance
_config_manager: Optional[MetricsConfigManager] = None


def get_config_manager(config_path: Optional[str] = None) -> MetricsConfigManager:
    """Get global configuration manager instance"""
    global _config_manager
    if _config_manager is None or config_path:
        _config_manager = MetricsConfigManager(config_path)
    return _config_manager


def get_metrics_config(environment: Optional[str] = None) -> MetricsConfig:
    """Get metrics configuration for environment"""
    return get_config_manager().get_config(environment)


# Preset configurations
PRESET_CONFIGS = {
    'strict': {
        'quality_gates': {'min_overall_score': 85.0},
        'coverage': {'min_line_coverage': 85.0},
        'complexity': {'max_cyclomatic_complexity': 10},
        'documentation': {'min_docstring_coverage': 80.0},
        'strict_mode': True
    },
    'production': {
        'quality_gates': {'min_overall_score': 80.0},
        'coverage': {'min_line_coverage': 75.0},
        'security': {
            'require_authentication': True,
            'require_audit_logging': True
        },
        'performance': {'require_caching': True}
    },
    'development': {
        'quality_gates': {'min_overall_score': 50.0},
        'coverage': {'min_line_coverage': 40.0},
        'documentation': {'require_readme': False},
        'enable_performance_benchmarks': False
    }
}


def create_preset_config(preset: str) -> MetricsConfig:
    """Create configuration from preset"""
    if preset not in PRESET_CONFIGS:
        raise ValueError(f"Unknown preset: {preset}. Available: {list(PRESET_CONFIGS.keys())}")

    config = MetricsConfig()
    manager = MetricsConfigManager()

    return manager._dict_to_config(PRESET_CONFIGS[preset])
