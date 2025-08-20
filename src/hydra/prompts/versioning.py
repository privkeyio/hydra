"""Prompt versioning and hot-reload system for Hydra.

Provides advanced version control, hot-reload, A/B testing, performance tracking,
and optimization capabilities for prompt management.
"""

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    class FileSystemEventHandler:
        def on_modified(self, event):
            pass

    class Observer:
        def schedule(self, handler, path, recursive=False):
            pass
        def start(self):
            pass
        def stop(self):
            pass
        def join(self):
            pass

    WATCHDOG_AVAILABLE = False


@dataclass
class PromptVersionInfo:
    """Extended version information with performance data."""

    version_id: str
    content_hash: str
    timestamp: datetime
    content: Dict[str, Any]
    performance_score: float = 0.0
    usage_count: int = 0
    success_rate: float = 0.0
    avg_execution_time: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ABTestConfig:
    """A/B testing configuration for prompts."""

    test_id: str
    variants: Dict[str, str]  # variant_name -> prompt_template
    traffic_split: Dict[str, float]  # variant_name -> percentage
    success_metric: str = "success_rate"
    start_time: datetime = None
    end_time: datetime = None
    active: bool = True

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()


@dataclass
class PromptMetrics:
    """Performance metrics for a prompt."""

    prompt_name: str
    variant: str = "default"
    execution_time: float = 0.0
    success: bool = True
    timestamp: datetime = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}


class PromptWatcher(FileSystemEventHandler):
    """File system watcher for prompt hot-reload."""

    def __init__(self, version_manager: 'PromptVersionManager'):
        self.version_manager = version_manager
        self.last_reload = time.time()
        self.reload_cooldown = 1.0  # Minimum seconds between reloads

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        current_time = time.time()
        if current_time - self.last_reload < self.reload_cooldown:
            return

        if event.src_path.endswith(('.yaml', '.yml', '.py')):
            self.last_reload = current_time
            self.version_manager._handle_file_change(event.src_path)


class PromptVersionManager:
    """Advanced prompt version management with hot-reload and A/B testing."""

    def __init__(self,
                 db_path: Optional[str] = None,
                 enable_hot_reload: bool = True,
                 watch_directories: Optional[List[str]] = None):
        """Initialize prompt version manager.
        
        Args:
            db_path: Path to SQLite database for version storage
            enable_hot_reload: Enable file watching for hot-reload
            watch_directories: Directories to watch for changes

        """
        self.db_path = db_path or self._get_default_db_path()
        self.enable_hot_reload = enable_hot_reload
        self.watch_directories = watch_directories or [str(Path(__file__).parent)]

        self._lock = threading.RLock()
        self._observers: List[Observer] = []
        self._reload_callbacks: List[Callable] = []
        self._ab_tests: Dict[str, ABTestConfig] = {}
        self._metrics_buffer: List[PromptMetrics] = []
        self._buffer_size = 1000

        self._init_database()

        if enable_hot_reload:
            self._setup_watchers()

    def _get_default_db_path(self) -> str:
        """Get default database path."""
        hydra_dir = Path.home() / '.hydra'
        hydra_dir.mkdir(exist_ok=True)
        return str(hydra_dir / 'prompt_versions.db')

    def _init_database(self):
        """Initialize SQLite database for version storage."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id TEXT UNIQUE,
                    content_hash TEXT,
                    timestamp TEXT,
                    content TEXT,
                    performance_score REAL DEFAULT 0.0,
                    usage_count INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0.0,
                    avg_execution_time REAL DEFAULT 0.0,
                    metadata TEXT DEFAULT '{}'
                );
                
                CREATE TABLE IF NOT EXISTS ab_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id TEXT UNIQUE,
                    config TEXT,
                    created_at TEXT,
                    active INTEGER DEFAULT 1
                );
                
                CREATE TABLE IF NOT EXISTS prompt_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_name TEXT,
                    variant TEXT DEFAULT 'default',
                    execution_time REAL,
                    success INTEGER,
                    timestamp TEXT,
                    metadata TEXT DEFAULT '{}'
                );
                
                CREATE INDEX IF NOT EXISTS idx_prompt_versions_hash 
                ON prompt_versions(content_hash);
                
                CREATE INDEX IF NOT EXISTS idx_metrics_prompt_variant 
                ON prompt_metrics(prompt_name, variant);
                
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp 
                ON prompt_metrics(timestamp);
            ''')

    def _setup_watchers(self):
        """Setup file watchers for hot-reload."""
        if not WATCHDOG_AVAILABLE:
            print("Warning: watchdog not available, hot-reload disabled")
            return

        event_handler = PromptWatcher(self)

        for directory in self.watch_directories:
            if Path(directory).exists():
                observer = Observer()
                observer.schedule(event_handler, directory, recursive=True)
                observer.start()
                self._observers.append(observer)

    def _handle_file_change(self, file_path: str):
        """Handle file change events."""
        try:
            # Trigger reload callbacks
            for callback in self._reload_callbacks:
                callback(file_path)
        except Exception as e:
            print(f"Error handling file change {file_path}: {e}")

    def create_version(self,
                      content: Dict[str, Any],
                      version_id: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new prompt version.
        
        Args:
            content: Prompt configuration content
            version_id: Optional custom version ID
            metadata: Optional metadata
            
        Returns:
            Version ID of created version

        """
        with self._lock:
            content_str = json.dumps(content, sort_keys=True)
            content_hash = hashlib.sha256(content_str.encode()).hexdigest()

            if version_id is None:
                version_id = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}_{content_hash[:8]}"

            version_info = PromptVersionInfo(
                version_id=version_id,
                content_hash=content_hash,
                timestamp=datetime.now(),
                content=content,
                metadata=metadata or {}
            )

            # Store in database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO prompt_versions 
                    (version_id, content_hash, timestamp, content, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    version_info.version_id,
                    version_info.content_hash,
                    version_info.timestamp.isoformat(),
                    json.dumps(version_info.content),
                    json.dumps(version_info.metadata)
                ))

            return version_id

    def get_version(self, version_id: str) -> Optional[PromptVersionInfo]:
        """Get version information by ID.
        
        Args:
            version_id: Version identifier
            
        Returns:
            PromptVersionInfo object or None

        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT version_id, content_hash, timestamp, content, 
                       performance_score, usage_count, success_rate, 
                       avg_execution_time, metadata
                FROM prompt_versions WHERE version_id = ?
            ''', (version_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return PromptVersionInfo(
                version_id=row[0],
                content_hash=row[1],
                timestamp=datetime.fromisoformat(row[2]),
                content=json.loads(row[3]),
                performance_score=row[4],
                usage_count=row[5],
                success_rate=row[6],
                avg_execution_time=row[7],
                metadata=json.loads(row[8])
            )

    def list_versions(self, limit: int = 50) -> List[PromptVersionInfo]:
        """List available versions.
        
        Args:
            limit: Maximum number of versions to return
            
        Returns:
            List of PromptVersionInfo objects

        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT version_id, content_hash, timestamp, content, 
                       performance_score, usage_count, success_rate, 
                       avg_execution_time, metadata
                FROM prompt_versions 
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

            versions = []
            for row in cursor.fetchall():
                versions.append(PromptVersionInfo(
                    version_id=row[0],
                    content_hash=row[1],
                    timestamp=datetime.fromisoformat(row[2]),
                    content=json.loads(row[3]),
                    performance_score=row[4],
                    usage_count=row[5],
                    success_rate=row[6],
                    avg_execution_time=row[7],
                    metadata=json.loads(row[8])
                ))

            return versions

    def rollback_to_version(self, version_id: str) -> bool:
        """Rollback to a specific version.
        
        Args:
            version_id: Version to rollback to
            
        Returns:
            True if rollback successful

        """
        version_info = self.get_version(version_id)
        if not version_info:
            return False

        # Create new version from rollback
        rollback_id = f"rollback_{version_id}_{int(time.time())}"
        self.create_version(
            version_info.content,
            rollback_id,
            {"rollback_from": version_id, "rollback_time": datetime.now().isoformat()}
        )

        return True

    def delete_version(self, version_id: str) -> bool:
        """Delete a version.
        
        Args:
            version_id: Version to delete
            
        Returns:
            True if deletion successful

        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'DELETE FROM prompt_versions WHERE version_id = ?',
                (version_id,)
            )
            return cursor.rowcount > 0

    def create_ab_test(self,
                       test_id: str,
                       variants: Dict[str, str],
                       traffic_split: Optional[Dict[str, float]] = None) -> ABTestConfig:
        """Create A/B test configuration.
        
        Args:
            test_id: Unique test identifier
            variants: Dictionary of variant_name -> prompt_template
            traffic_split: Traffic distribution (defaults to equal split)
            
        Returns:
            ABTestConfig object

        """
        if traffic_split is None:
            # Equal split between variants
            split_value = 1.0 / len(variants)
            traffic_split = {name: split_value for name in variants.keys()}

        # Normalize traffic split to ensure sum is 1.0
        total = sum(traffic_split.values())
        if total > 0:
            traffic_split = {k: v / total for k, v in traffic_split.items()}

        ab_test = ABTestConfig(
            test_id=test_id,
            variants=variants,
            traffic_split=traffic_split
        )

        self._ab_tests[test_id] = ab_test

        # Store in database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO ab_tests (test_id, config, created_at)
                VALUES (?, ?, ?)
            ''', (
                test_id,
                json.dumps(asdict(ab_test), default=str),
                datetime.now().isoformat()
            ))

        return ab_test

    def get_ab_test_variant(self, test_id: str, user_id: str) -> Optional[str]:
        """Get A/B test variant for a user.
        
        Args:
            test_id: Test identifier
            user_id: User identifier for consistent assignment
            
        Returns:
            Variant name or None if test doesn't exist

        """
        if test_id not in self._ab_tests:
            # Load from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT config FROM ab_tests WHERE test_id = ? AND active = 1',
                    (test_id,)
                )
                row = cursor.fetchone()
                if row:
                    config_data = json.loads(row[0])
                    # Convert datetime strings back to datetime objects
                    if 'start_time' in config_data:
                        config_data['start_time'] = datetime.fromisoformat(config_data['start_time'])
                    if 'end_time' in config_data and config_data['end_time']:
                        config_data['end_time'] = datetime.fromisoformat(config_data['end_time'])

                    self._ab_tests[test_id] = ABTestConfig(**config_data)

        if test_id not in self._ab_tests:
            return None

        ab_test = self._ab_tests[test_id]
        if not ab_test.active:
            return None

        # Deterministic assignment based on user_id hash
        hash_val = int(hashlib.md5(f"{test_id}:{user_id}".encode()).hexdigest(), 16)
        normalized_hash = (hash_val % 10000) / 10000.0

        cumulative = 0.0
        for variant, weight in ab_test.traffic_split.items():
            cumulative += weight
            if normalized_hash <= cumulative:
                return variant

        # Fallback to first variant
        return list(ab_test.variants.keys())[0] if ab_test.variants else None

    def record_metrics(self, metrics: PromptMetrics):
        """Record prompt performance metrics.
        
        Args:
            metrics: PromptMetrics object

        """
        self._metrics_buffer.append(metrics)

        # Flush buffer if full
        if len(self._metrics_buffer) >= self._buffer_size:
            self.flush_metrics()

    def flush_metrics(self):
        """Flush metrics buffer to database."""
        if not self._metrics_buffer:
            return

        with sqlite3.connect(self.db_path) as conn:
            for metrics in self._metrics_buffer:
                conn.execute('''
                    INSERT INTO prompt_metrics 
                    (prompt_name, variant, execution_time, success, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    metrics.prompt_name,
                    metrics.variant,
                    metrics.execution_time,
                    1 if metrics.success else 0,
                    metrics.timestamp.isoformat(),
                    json.dumps(metrics.metadata)
                ))

        self._metrics_buffer.clear()

    def get_prompt_performance(self,
                              prompt_name: str,
                              variant: str = "default",
                              time_window: Optional[timedelta] = None) -> Dict[str, float]:
        """Get performance metrics for a prompt.
        
        Args:
            prompt_name: Prompt name
            variant: Prompt variant
            time_window: Optional time window for metrics
            
        Returns:
            Dictionary with performance metrics

        """
        self.flush_metrics()  # Ensure recent metrics are included

        where_clause = "WHERE prompt_name = ? AND variant = ?"
        params = [prompt_name, variant]

        if time_window:
            cutoff_time = datetime.now() - time_window
            where_clause += " AND timestamp >= ?"
            params.append(cutoff_time.isoformat())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f'''
                SELECT 
                    COUNT(*) as total_count,
                    AVG(execution_time) as avg_execution_time,
                    AVG(CAST(success AS FLOAT)) as success_rate,
                    SUM(CAST(success AS INT)) as success_count
                FROM prompt_metrics 
                {where_clause}
            ''', params)

            row = cursor.fetchone()
            if not row or row[0] == 0:
                return {
                    "total_count": 0,
                    "avg_execution_time": 0.0,
                    "success_rate": 0.0,
                    "success_count": 0
                }

            return {
                "total_count": row[0],
                "avg_execution_time": row[1] or 0.0,
                "success_rate": row[2] or 0.0,
                "success_count": row[3] or 0
            }

    def get_optimization_suggestions(self, prompt_name: str) -> List[Dict[str, Any]]:
        """Get optimization suggestions for a prompt.
        
        Args:
            prompt_name: Prompt name
            
        Returns:
            List of optimization suggestions

        """
        suggestions = []

        # Get recent performance data
        recent_perf = self.get_prompt_performance(
            prompt_name,
            time_window=timedelta(days=7)
        )
        overall_perf = self.get_prompt_performance(prompt_name)

        # Success rate suggestions
        if recent_perf["success_rate"] < 0.8:
            suggestions.append({
                "type": "success_rate",
                "severity": "high" if recent_perf["success_rate"] < 0.5 else "medium",
                "message": f"Success rate is {recent_perf['success_rate']:.1%}. Consider revising prompt clarity.",
                "metric_value": recent_perf["success_rate"]
            })

        # Performance suggestions
        if recent_perf["avg_execution_time"] > 5.0:
            suggestions.append({
                "type": "performance",
                "severity": "medium",
                "message": f"Average execution time is {recent_perf['avg_execution_time']:.1f}s. Consider shorter prompts.",
                "metric_value": recent_perf["avg_execution_time"]
            })

        # Usage pattern suggestions
        if overall_perf["total_count"] < 10:
            suggestions.append({
                "type": "usage",
                "severity": "low",
                "message": "Low usage detected. Consider promoting this prompt or deprecating it.",
                "metric_value": overall_perf["total_count"]
            })

        # Trend analysis
        if overall_perf["total_count"] > 100:
            old_perf = self.get_prompt_performance(
                prompt_name,
                time_window=timedelta(days=30)
            )
            if old_perf["success_rate"] > recent_perf["success_rate"] + 0.1:
                suggestions.append({
                    "type": "trend",
                    "severity": "high",
                    "message": "Declining success rate trend detected. Immediate review recommended.",
                    "metric_value": recent_perf["success_rate"] - old_perf["success_rate"]
                })

        return suggestions

    def add_reload_callback(self, callback: Callable[[str], None]):
        """Add callback for file change events.
        
        Args:
            callback: Function called with file path on change

        """
        self._reload_callbacks.append(callback)

    def update_version_performance(self,
                                  version_id: str,
                                  performance_score: float,
                                  usage_count: int,
                                  success_rate: float,
                                  avg_execution_time: float):
        """Update version performance metrics.
        
        Args:
            version_id: Version identifier
            performance_score: Overall performance score
            usage_count: Number of times used
            success_rate: Success rate percentage
            avg_execution_time: Average execution time

        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE prompt_versions 
                SET performance_score = ?, usage_count = ?, 
                    success_rate = ?, avg_execution_time = ?
                WHERE version_id = ?
            ''', (performance_score, usage_count, success_rate, avg_execution_time, version_id))

    @contextmanager
    def test_version(self, version_id: str):
        """Context manager for testing a version without persistence.
        
        Args:
            version_id: Version to test
            
        Yields:
            PromptVersionInfo object for testing

        """
        version_info = self.get_version(version_id)
        if not version_info:
            raise ValueError(f"Version {version_id} not found")

        try:
            yield version_info
        finally:
            # Cleanup or rollback logic could go here
            pass

    def cleanup(self):
        """Cleanup resources."""
        self.flush_metrics()

        for observer in self._observers:
            observer.stop()
            observer.join()

        self._observers.clear()


# Global instance
_global_version_manager: Optional[PromptVersionManager] = None


def get_version_manager(**kwargs) -> PromptVersionManager:
    """Get global prompt version manager instance."""
    global _global_version_manager
    if _global_version_manager is None:
        _global_version_manager = PromptVersionManager(**kwargs)
    return _global_version_manager


def record_prompt_usage(prompt_name: str,
                       execution_time: float,
                       success: bool,
                       variant: str = "default",
                       metadata: Optional[Dict[str, Any]] = None):
    """Record prompt usage metrics.
    
    Args:
        prompt_name: Name of the prompt
        execution_time: Time taken to execute
        success: Whether execution was successful
        variant: Prompt variant used
        metadata: Additional metadata

    """
    metrics = PromptMetrics(
        prompt_name=prompt_name,
        variant=variant,
        execution_time=execution_time,
        success=success,
        metadata=metadata or {}
    )

    get_version_manager().record_metrics(metrics)


def create_prompt_version(content: Dict[str, Any],
                         version_id: Optional[str] = None) -> str:
    """Create a new prompt version.
    
    Args:
        content: Prompt configuration content
        version_id: Optional custom version ID
        
    Returns:
        Version ID of created version

    """
    return get_version_manager().create_version(content, version_id)


def get_ab_test_prompt(test_id: str,
                      user_id: str,
                      default_prompt: str) -> str:
    """Get A/B test prompt variant for user.
    
    Args:
        test_id: A/B test identifier
        user_id: User identifier
        default_prompt: Default prompt if no test active
        
    Returns:
        Prompt template for the user

    """
    version_manager = get_version_manager()
    variant = version_manager.get_ab_test_variant(test_id, user_id)

    if variant and test_id in version_manager._ab_tests:
        return version_manager._ab_tests[test_id].variants.get(variant, default_prompt)

    return default_prompt
