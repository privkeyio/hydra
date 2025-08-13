"""Resource monitoring and tracking system for Hydra."""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


class ResourceUsagePrediction:
    """Predictive analytics for resource usage patterns."""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.history: Dict[str, deque] = {
            'cpu': deque(maxlen=window_size),
            'memory': deque(maxlen=window_size),
            'disk': deque(maxlen=window_size),
            'api_calls': deque(maxlen=window_size)
        }

    def add_sample(self, metric: str, value: float, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()

        if metric in self.history:
            self.history[metric].append({
                'value': value,
                'timestamp': timestamp
            })

    def predict_next_hour(self, metric: str) -> Optional[Dict[str, float]]:
        if metric not in self.history or len(self.history[metric]) < 10:
            return None

        samples = list(self.history[metric])
        values = [s['value'] for s in samples]

        if len(values) < 3:
            return {'predicted': values[-1] if values else 0, 'confidence': 0.1}

        # Simple moving average with trend
        recent_avg = sum(values[-5:]) / min(5, len(values))
        overall_avg = sum(values) / len(values)
        trend = (recent_avg - overall_avg) / overall_avg if overall_avg > 0 else 0

        # Predict with trend continuation
        predicted = recent_avg * (1 + trend)

        # Calculate confidence based on variance
        variance = sum((v - recent_avg) ** 2 for v in values[-10:]) / min(
            10, len(values)
        )
        confidence_calc = 1.0 / (1.0 + variance / recent_avg) if recent_avg > 0 else 0.1
        confidence = max(0.1, min(0.95, confidence_calc))

        return {
            'predicted': max(0, predicted),
            'confidence': confidence,
            'trend': trend
        }


class ResourceLimits:
    """Resource limit enforcement and throttling."""

    def __init__(self, limits: Dict[str, float] = None):
        self.limits = limits or {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'api_calls_per_minute': 1000
        }
        self.throttling_active = defaultdict(bool)
        self.throttling_callbacks: Dict[str, List[Callable]] = defaultdict(list)

    def check_limits(self, metrics: Dict[str, float]) -> Dict[str, bool]:
        violations = {}

        for metric, limit in self.limits.items():
            if metric in metrics:
                exceeded = metrics[metric] > limit
                violations[metric] = exceeded

                if exceeded and not self.throttling_active[metric]:
                    self.throttling_active[metric] = True
                    self._trigger_throttling(metric, metrics[metric], limit)
                elif not exceeded and self.throttling_active[metric]:
                    self.throttling_active[metric] = False
                    self._release_throttling(metric)

        return violations

    def _trigger_throttling(self, metric: str, value: float, limit: float):
        msg = (
            f"Resource limit exceeded: {metric}={value:.2f} > {limit:.2f}, "
            f"enabling throttling"
        )
        logger.warning(msg)
        for callback in self.throttling_callbacks[metric]:
            try:
                callback(True, value, limit)
            except Exception as e:
                logger.error(f"Error in throttling callback for {metric}: {e}")

    def _release_throttling(self, metric: str):
        logger.info(f"Resource usage normalized for {metric}, disabling throttling")
        for callback in self.throttling_callbacks[metric]:
            try:
                callback(False, 0, 0)
            except Exception as e:
                logger.error(f"Error in throttling release callback for {metric}: {e}")

    def register_throttling_callback(self, metric: str, callback: Callable):
        """Register callback to be called when throttling is triggered/released."""
        self.throttling_callbacks[metric].append(callback)

    def is_throttling_active(self, metric: str = None) -> bool:
        if metric:
            return self.throttling_active[metric]
        return any(self.throttling_active.values())


class APICallTracker:
    """Track and rate limit API calls."""

    def __init__(self, rate_limits: Dict[str, int] = None):
        self.rate_limits = rate_limits or {
            'default': 60,  # calls per minute
            'claude': 30,
            'openai': 50
        }
        self.call_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.lock = threading.Lock()

    def record_call(self, provider: str = 'default', endpoint: str = None) -> bool:
        """Record an API call and check if rate limit allows it."""
        with self.lock:
            now = datetime.now()
            key = f"{provider}:{endpoint}" if endpoint else provider

            # Clean old entries
            cutoff = now - timedelta(minutes=1)
            while self.call_history[key] and self.call_history[key][0] < cutoff:
                self.call_history[key].popleft()

            # Check rate limit
            limit = self.rate_limits.get(provider, self.rate_limits.get('default', 60))
            if len(self.call_history[key]) >= limit:
                count = len(self.call_history[key])
                msg = f"Rate limit exceeded for {key}: {count} >= {limit}"
                logger.warning(msg)
                return False

            self.call_history[key].append(now)
            return True

    def get_call_counts(self) -> Dict[str, Dict[str, int]]:
        """Get current call counts for all providers."""
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(minutes=1)

            counts = {}
            for key, history in self.call_history.items():
                # Clean old entries
                while history and history[0] < cutoff:
                    history.popleft()

                counts[key] = {
                    'calls_last_minute': len(history),
                    'limit': self.rate_limits.get(
                        key.split(':')[0], self.rate_limits.get('default', 60)
                    )
                }

            return counts


class ResourceAlert:
    """Handle resource exhaustion alerts."""

    def __init__(self, thresholds: Dict[str, float] = None):
        self.thresholds = thresholds or {
            'cpu_critical': 95.0,
            'memory_critical': 95.0,
            'disk_critical': 98.0,
            'cpu_warning': 80.0,
            'memory_warning': 85.0,
            'disk_warning': 90.0
        }
        self.alert_callbacks: List[Callable] = []
        self.active_alerts: Dict[str, Dict] = {}

    def check_and_alert(self, metrics: Dict[str, float]):
        """Check metrics and trigger alerts if needed."""
        new_alerts = {}
        resolved_alerts = []

        # Check for new alerts
        for threshold_name, threshold_value in self.thresholds.items():
            metric_name = (
                threshold_name.replace('_critical', '').replace('_warning', '')
            )
            severity = 'critical' if '_critical' in threshold_name else 'warning'

            if metric_name in metrics and metrics[metric_name] > threshold_value:
                alert_key = f"{metric_name}_{severity}"

                if alert_key not in self.active_alerts:
                    alert = {
                        'metric': metric_name,
                        'severity': severity,
                        'value': metrics[metric_name],
                        'threshold': threshold_value,
                        'timestamp': datetime.now().isoformat(),
                        'resolved': False
                    }
                    new_alerts[alert_key] = alert
                    self.active_alerts[alert_key] = alert

        # Check for resolved alerts
        for alert_key, alert in list(self.active_alerts.items()):
            metric = alert['metric']
            severity = alert['severity']
            threshold_name = f"{metric}_{severity}"

            if metric in metrics and metrics[metric] <= self.thresholds[threshold_name]:
                alert['resolved'] = True
                alert['resolved_at'] = datetime.now().isoformat()
                resolved_alerts.append(alert_key)
                del self.active_alerts[alert_key]

        # Trigger callbacks for new and resolved alerts
        for alert in new_alerts.values():
            self._trigger_alert_callbacks(alert, 'triggered')

        for alert_key in resolved_alerts:
            self._trigger_alert_callbacks({'key': alert_key}, 'resolved')

    def _trigger_alert_callbacks(self, alert: Dict, action: str):
        for callback in self.alert_callbacks:
            try:
                callback(alert, action)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")

    def register_alert_callback(self, callback: Callable):
        """Register callback for alert notifications."""
        self.alert_callbacks.append(callback)

    def get_active_alerts(self) -> List[Dict]:
        """Get all currently active alerts."""
        return list(self.active_alerts.values())


class ResourceTracker:
    """Main resource tracking and monitoring system."""

    def __init__(self,
                 update_interval: float = 1.0,
                 metrics_dir: Optional[str] = None,
                 limits: Dict[str, float] = None):
        self.update_interval = update_interval
        self.metrics_dir = Path(metrics_dir or ".hydra/metrics")
        self.metrics_dir.mkdir(parents=True, exist_ok=True)

        self.running = False
        self.monitor_thread = None

        # Initialize subsystems
        self.limits = ResourceLimits(limits)
        self.predictor = ResourceUsagePrediction()
        self.api_tracker = APICallTracker()
        self.alerter = ResourceAlert()

        # Current metrics
        self.current_metrics = {}
        self.metrics_lock = threading.Lock()

        # Historical data storage
        self.history_file = self.metrics_dir / "resource_history.jsonl"

    def start_monitoring(self):
        """Start the resource monitoring loop."""
        if self.running:
            return

        self.running = True
        try:
            self.monitor_thread = threading.Thread(
                target=self._monitoring_loop, daemon=True
            )
            self.monitor_thread.start()
            logger.info("Resource monitoring started")
        except RuntimeError as e:
            logger.warning(f"Could not start monitoring thread: {e}")
            self.running = False  # Make sure running is set to False on failure

    def stop_monitoring(self):
        """Stop the resource monitoring loop."""
        if not self.running:
            return

        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        logger.info("Resource monitoring stopped")

    def _monitoring_loop(self):
        """Run the monitoring loop in a separate thread."""
        while self.running:
            try:
                metrics = self._collect_system_metrics()

                with self.metrics_lock:
                    self.current_metrics = metrics

                # Update predictive model
                now = datetime.now()
                for metric, value in metrics.items():
                    if metric in ['cpu_percent', 'memory_percent', 'disk_percent']:
                        self.predictor.add_sample(metric, value, now)

                # Check limits and trigger throttling
                self.limits.check_limits(metrics)

                # Check for alerts
                self.alerter.check_and_alert(metrics)

                # Save metrics to disk
                self._save_metrics(metrics)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            time.sleep(self.update_interval)

    def _collect_system_metrics(self) -> Dict[str, float]:
        """Collect current system resource metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Get API call metrics
            api_counts = self.api_tracker.get_call_counts()
            total_api_calls = sum(
                data['calls_last_minute'] for data in api_counts.values()
            )

            metrics = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / (1024**3),
                'memory_available_gb': memory.available / (1024**3),
                'disk_percent': (disk.used / disk.total) * 100,
                'disk_used_gb': disk.used / (1024**3),
                'disk_free_gb': disk.free / (1024**3),
                'api_calls_per_minute': total_api_calls,
                'timestamp': time.time()
            }

            return metrics

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {}

    def _save_metrics(self, metrics: Dict[str, float]):
        """Save metrics to historical data file."""
        try:
            record = {
                'timestamp': datetime.now().isoformat(),
                'metrics': metrics
            }

            with open(self.history_file, 'a') as f:
                f.write(json.dumps(record) + '\n')

        except Exception as e:
            logger.error(f"Error saving metrics: {e}")

    def get_current_metrics(self) -> Dict[str, float]:
        """Get the current resource metrics."""
        with self.metrics_lock:
            return self.current_metrics.copy()

    def get_historical_metrics(self, hours: int = 24) -> List[Dict]:
        """Get historical metrics for the specified number of hours."""
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            historical_data = []

            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            record_time = datetime.fromisoformat(record['timestamp'])
                            if record_time > cutoff:
                                historical_data.append(record)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue

            return historical_data

        except Exception as e:
            logger.error(f"Error reading historical metrics: {e}")
            return []

    def record_api_call(self, provider: str = 'default', endpoint: str = None) -> bool:
        """Record an API call and check rate limits."""
        return self.api_tracker.record_call(provider, endpoint)

    def get_predictions(self) -> Dict[str, Dict]:
        """Get resource usage predictions for the next hour."""
        predictions = {}
        for metric in ['cpu_percent', 'memory_percent', 'disk_percent']:
            prediction = self.predictor.predict_next_hour(metric)
            if prediction:
                predictions[metric] = prediction
        return predictions

    def register_throttling_callback(self, metric: str, callback: Callable):
        """Register a callback for throttling events."""
        self.limits.register_throttling_callback(metric, callback)

    def register_alert_callback(self, callback: Callable):
        """Register a callback for alert notifications."""
        self.alerter.register_alert_callback(callback)

    def is_throttling_active(self, metric: str = None) -> bool:
        """Check if throttling is currently active."""
        return self.limits.is_throttling_active(metric)

    def get_active_alerts(self) -> List[Dict]:
        """Get all currently active alerts."""
        return self.alerter.get_active_alerts()


class ResourceDashboard:
    """Dashboard API for resource visualization."""

    def __init__(self, resource_tracker: ResourceTracker):
        self.tracker = resource_tracker

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data."""
        current_metrics = self.tracker.get_current_metrics()
        historical_data = self.tracker.get_historical_metrics(hours=1)
        predictions = self.tracker.get_predictions()
        active_alerts = self.tracker.get_active_alerts()
        api_counts = self.tracker.api_tracker.get_call_counts()

        return {
            'timestamp': datetime.now().isoformat(),
            'current_metrics': current_metrics,
            'historical_data': historical_data[-60:],  # Last 60 data points
            'predictions': predictions,
            'alerts': {
                'active_count': len(active_alerts),
                'alerts': active_alerts
            },
            'api_usage': api_counts,
            'throttling_status': {
                'cpu': self.tracker.is_throttling_active('cpu_percent'),
                'memory': self.tracker.is_throttling_active('memory_percent'),
                'disk': self.tracker.is_throttling_active('disk_percent'),
                'api': self.tracker.is_throttling_active('api_calls_per_minute')
            },
            'health_status': self._calculate_health_status(
                current_metrics, active_alerts
            )
        }

    def _calculate_health_status(
        self, metrics: Dict[str, float], alerts: List[Dict]
    ) -> str:
        """Calculate overall system health status."""
        if not metrics:
            return 'unknown'

        critical_alerts = [a for a in alerts if a.get('severity') == 'critical']
        if critical_alerts:
            return 'critical'

        warning_alerts = [a for a in alerts if a.get('severity') == 'warning']
        if warning_alerts:
            return 'warning'

        # Check if any metric is above warning thresholds
        warning_thresholds = {
            'cpu_percent': 80,
            'memory_percent': 85,
            'disk_percent': 90
        }
        for metric, threshold in warning_thresholds.items():
            if metrics.get(metric, 0) > threshold:
                return 'warning'

        return 'healthy'

    def get_resource_summary(self) -> Dict[str, Any]:
        """Get a summary of resource usage."""
        metrics = self.tracker.get_current_metrics()
        historical = self.tracker.get_historical_metrics(hours=24)

        if not metrics or not historical:
            return {'status': 'no_data'}

        # Calculate 24-hour averages
        avg_metrics = {}
        for metric in ['cpu_percent', 'memory_percent', 'disk_percent']:
            values = [
                h['metrics'].get(metric, 0) for h in historical
                if metric in h.get('metrics', {})
            ]
            avg_metrics[f'{metric}_24h_avg'] = (
                sum(values) / len(values) if values else 0
            )

        return {
            'current': metrics,
            'averages_24h': avg_metrics,
            'active_alerts': len(self.tracker.get_active_alerts()),
            'throttling_active': self.tracker.limits.is_throttling_active(),
            'predictions': self.tracker.get_predictions()
        }
