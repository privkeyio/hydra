"""Production Quality Metrics Package

Provides comprehensive quality analysis and metrics for production code:
- Code complexity analysis (cyclomatic, cognitive)
- Test coverage requirements and validation
- Documentation completeness checking
- Error handling coverage analysis
- Performance benchmarks and optimization detection
- Security best practices validation
- Configurable thresholds and quality gates
- Integration with verification system
"""

from hydra.metrics.config import (
    PRESET_CONFIGS,
    MetricsConfig,
    MetricsConfigManager,
    create_preset_config,
    get_config_manager,
    get_metrics_config,
)
from hydra.metrics.quality_metrics import (
    ComplexityMetrics,
    CoverageMetrics,
    DocumentationMetrics,
    ErrorHandlingMetrics,
    PerformanceMetrics,
    QualityMetricsAnalyzer,
    QualityReport,
    SecurityMetrics,
    analyze_code_quality,
    get_quality_metrics_for_verification,
)

__all__ = [
    # Main analyzer and report types
    'QualityMetricsAnalyzer',
    'QualityReport',
    'ComplexityMetrics',
    'CoverageMetrics',
    'DocumentationMetrics',
    'ErrorHandlingMetrics',
    'PerformanceMetrics',
    'SecurityMetrics',

    # Configuration management
    'MetricsConfig',
    'MetricsConfigManager',
    'get_config_manager',
    'get_metrics_config',
    'create_preset_config',
    'PRESET_CONFIGS',

    # Entry point functions
    'analyze_code_quality',
    'get_quality_metrics_for_verification',
]
