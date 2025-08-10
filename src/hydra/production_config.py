"""Production settings for Hydra automation workflows.

Optimized configuration for safe, efficient parallel code generation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProductionConfig:
    """Production configuration for Hydra."""
    
    # Parallel execution settings
    max_parallel_tickets: int = 3  # Optimal for most systems
    enable_smart_scheduling: bool = True  # Use conflict detection
    enable_file_locking: bool = True  # Always lock files in production
    
    # Safety settings
    enable_git_safety: bool = True  # Block dangerous git operations
    require_approval_for_git: bool = True  # Require manual approval for git
    enable_rollback: bool = True  # Enable automatic rollback on failure
    max_retry_attempts: int = 2  # Retry failed operations
    
    # Performance settings  
    use_session_pooling: bool = True  # Pre-warm Claude sessions
    session_pool_size: int = 5  # Number of pre-warmed sessions
    cache_analysis_results: bool = True  # Cache file analysis
    batch_small_tickets: bool = True  # Batch compatible small tickets
    
    # Conflict resolution
    conflict_detection_threshold: float = 0.3  # Sensitivity for conflicts
    auto_resolve_conflicts: bool = False  # Manual resolution for safety
    stagger_start_delay: tuple = (2, 10)  # Random delay range in seconds
    
    # Resource limits
    max_execution_time_per_ticket: int = 300  # 5 minutes per ticket
    max_total_execution_time: int = 3600  # 1 hour total
    max_memory_per_session: str = "2GB"  # Memory limit per session
    
    # Monitoring and logging
    enable_detailed_logging: bool = True
    save_execution_reports: bool = True
    enable_dashboard: bool = True
    dashboard_port: int = 8080
    
    # File operation settings
    file_lock_timeout: int = 30  # Seconds to wait for file lock
    file_lock_retry_count: int = 3  # Number of retries for locks
    track_file_modifications: bool = True  # Track all file changes
    
    # Quality gates
    run_quality_checks: bool = True  # Always run quality gates
    enforce_quality_gates: bool = True  # Block on quality failures
    auto_fix_quality_issues: bool = True  # Try to auto-fix issues
    
    # Recovery settings
    checkpoint_frequency: int = 60  # Save state every 60 seconds
    enable_crash_recovery: bool = True  # Resume after crashes
    preserve_partial_work: bool = True  # Keep partial completions
    
    def to_env_vars(self) -> dict:
        """Convert config to environment variables."""
        return {
            "HYDRA_MAX_PARALLEL": str(self.max_parallel_tickets),
            "HYDRA_SMART_SCHEDULING": "1" if self.enable_smart_scheduling else "0",
            "HYDRA_FILE_LOCKING": "1" if self.enable_file_locking else "0",
            "HYDRA_GIT_SAFETY": "1" if self.enable_git_safety else "0",
            "HYDRA_SESSION_POOLING": "1" if self.use_session_pooling else "0",
            "HYDRA_QUALITY_GATES": "1" if self.run_quality_checks else "0",
            "HYDRA_AUTO_RECOVERY": "1" if self.enable_crash_recovery else "0",
        }


def get_production_config() -> ProductionConfig:
    """Get the recommended production configuration."""
    return ProductionConfig()


def get_development_config() -> ProductionConfig:
    """Get a more permissive development configuration."""
    config = ProductionConfig()
    config.enable_git_safety = False  # Allow git operations in dev
    config.require_approval_for_git = False
    config.enforce_quality_gates = False  # Warning only in dev
    config.max_parallel_tickets = 1  # Sequential for debugging
    config.enable_detailed_logging = True
    return config


def get_ci_config() -> ProductionConfig:
    """Get configuration optimized for CI/CD pipelines."""
    config = ProductionConfig()
    config.max_parallel_tickets = 5  # More parallel in CI
    config.enable_dashboard = False  # No UI in CI
    config.max_execution_time_per_ticket = 600  # 10 min for CI
    config.auto_resolve_conflicts = True  # Auto-resolve in CI
    return config