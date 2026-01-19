"""
Performance monitoring and benchmarking utilities for ResilienceGPT
"""

import time
import logging
import psutil
from functools import wraps
from typing import Dict, Any, Optional
import threading
from collections import defaultdict

try:
    import GPUtil

    GPU_UTIL_AVAILABLE = True
except ImportError:
    GPU_UTIL_AVAILABLE = False

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    # Dummy classes for when prometheus is not available
    class Counter:
        def __init__(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Histogram:
        def __init__(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Gauge:
        def __init__(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    def generate_latest(*args, **kwargs):
        return b""


logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor system performance metrics"""

    def __init__(self):
        self.metrics = defaultdict(list)
        self._lock = threading.Lock()

    def record_metric(
        self, name: str, value: float, metadata: Optional[Dict[str, Any]] = None
    ):
        """Record a performance metric"""
        with self._lock:
            self.metrics[name].append(
                {"value": value, "timestamp": time.time(), "metadata": metadata or {}}
            )

            # Keep only last 1000 measurements per metric
            if len(self.metrics[name]) > 1000:
                self.metrics[name] = self.metrics[name][-1000:]

    def get_metrics_summary(self, name: str = None) -> Dict[str, Any]:
        """Get summary statistics for metrics"""
        with self._lock:
            if name:
                metrics = self.metrics.get(name, [])
            else:
                # Return summary for all metrics
                summary = {}
                for metric_name, values in self.metrics.items():
                    if values:
                        vals = [m["value"] for m in values]
                        summary[metric_name] = {
                            "count": len(vals),
                            "avg": sum(vals) / len(vals),
                            "min": min(vals),
                            "max": max(vals),
                            "latest": vals[-1],
                        }
                return summary

            if not metrics:
                return {}

            values = [m["value"] for m in metrics]
            return {
                "count": len(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "latest": values[-1],
            }

    def get_system_stats(self) -> Dict[str, Any]:
        """Get current system resource usage"""
        stats = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_gb": psutil.virtual_memory().used / (1024**3),
            "memory_available_gb": psutil.virtual_memory().available / (1024**3),
        }

        # GPU stats if available
        if GPU_UTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]  # Primary GPU
                    stats.update(
                        {
                            "gpu_memory_used_percent": gpu.memoryUsed
                            * 100.0
                            / gpu.memoryTotal,
                            "gpu_memory_used_mb": gpu.memoryUsed,
                            "gpu_memory_total_mb": gpu.memoryTotal,
                            "gpu_temperature": gpu.temperature,
                        }
                    )
            except:
                pass

        return stats

    def clear_metrics(self, name: str = None):
        """Clear metrics data"""
        with self._lock:
            if name:
                self.metrics[name].clear()
            else:
                self.metrics.clear()

    def get_recent_metrics(self, minutes: int = 5) -> Dict[str, Any]:
        """Get metrics from the last N minutes"""
        cutoff_time = time.time() - (minutes * 60)
        recent_metrics = defaultdict(list)

        with self._lock:
            for metric_name, values in self.metrics.items():
                for value in values:
                    if value["timestamp"] > cutoff_time:
                        recent_metrics[metric_name].append(value)

        return dict(recent_metrics)

    def get_metrics_summary_json(self) -> str:
        """Get metrics summary as JSON string for logging/monitoring"""
        summary = self.get_metrics_summary()
        summary["timestamp"] = datetime.now().isoformat()
        return json.dumps(summary, indent=2)

    def update_prometheus_metrics(self):
        """Update Prometheus gauge metrics with current system stats"""
        if not PROMETHEUS_AVAILABLE:
            return

        try:
            system_stats = self.get_system_stats()
            CPU_USAGE.set(system_stats.get("cpu_percent", 0))
            MEMORY_USAGE.set(system_stats.get("memory_percent", 0))

            if GPU_UTIL_AVAILABLE:
                gpu_stats = system_stats.get("gpu_memory_used_percent")
                if gpu_stats is not None:
                    GPU_MEMORY_USAGE.set(gpu_stats)
        except Exception as e:
            logger.warning(f"Failed to update Prometheus metrics: {e}")


# Prometheus metrics
if PROMETHEUS_AVAILABLE:
    # Request metrics
    REQUEST_COUNT = Counter(
        "chatbot_requests_total",
        "Total number of requests",
        ["method", "endpoint", "status"],
    )
    REQUEST_DURATION = Histogram(
        "chatbot_request_duration_seconds",
        "Request duration in seconds",
        ["method", "endpoint"],
    )

    # LLM metrics
    LLM_REQUEST_COUNT = Counter(
        "chatbot_llm_requests_total",
        "Total number of LLM requests",
        ["model", "operation"],
    )
    LLM_REQUEST_DURATION = Histogram(
        "chatbot_llm_request_duration_seconds",
        "LLM request duration in seconds",
        ["model", "operation"],
    )

    # Vector store metrics
    VECTOR_SEARCH_COUNT = Counter(
        "chatbot_vector_searches_total", "Total number of vector searches", ["mode"]
    )
    VECTOR_SEARCH_DURATION = Histogram(
        "chatbot_vector_search_duration_seconds",
        "Vector search duration in seconds",
        ["mode"],
    )

    # System metrics
    CPU_USAGE = Gauge("chatbot_cpu_usage_percent", "Current CPU usage percentage")
    MEMORY_USAGE = Gauge(
        "chatbot_memory_usage_percent", "Current memory usage percentage"
    )
    GPU_MEMORY_USAGE = Gauge(
        "chatbot_gpu_memory_usage_percent", "Current GPU memory usage percentage"
    )

# Global performance monitor instance
performance_monitor = PerformanceMonitor()


def time_function(func):
    """Decorator to time function execution"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            performance_monitor.record_metric(
                f"function.{func.__name__}",
                execution_time,
                {"args_count": len(args), "kwargs_count": len(kwargs)},
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            performance_monitor.record_metric(
                f"function.{func.__name__}.error", execution_time, {"error": str(e)}
            )
            raise

    return wrapper


def monitor_llm_calls(func):
    """Decorator specifically for LLM calls"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        system_stats_before = performance_monitor.get_system_stats()
        operation = getattr(func, "__name__", "unknown")

        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Prometheus metrics
            if PROMETHEUS_AVAILABLE:
                model_name = getattr(args[0], "model", "unknown") if args else "unknown"
                LLM_REQUEST_COUNT.labels(model=model_name, operation=operation).inc()
                LLM_REQUEST_DURATION.labels(
                    model=model_name, operation=operation
                ).observe(execution_time)

            # Record detailed metrics
            performance_monitor.record_metric(
                "llm.call.duration",
                execution_time,
                {
                    "model": (
                        getattr(args[0], "model", "unknown") if args else "unknown"
                    ),
                    "input_tokens": len(str(kwargs.get("text", "")))
                    // 4,  # Rough estimate
                },
            )

            system_stats_after = performance_monitor.get_system_stats()
            performance_monitor.record_metric(
                "llm.call.memory_delta",
                system_stats_after.get("memory_used_gb", 0)
                - system_stats_before.get("memory_used_gb", 0),
            )

            return result
        except Exception as e:
            execution_time = time.time() - start_time

            # Prometheus error metrics
            if PROMETHEUS_AVAILABLE:
                model_name = getattr(args[0], "model", "unknown") if args else "unknown"
                LLM_REQUEST_COUNT.labels(
                    model=model_name, operation=f"{operation}_error"
                ).inc()

            performance_monitor.record_metric(
                "llm.call.error", execution_time, {"error": str(e)}
            )
            raise

    return wrapper


def monitor_embedding_calls(func):
    """Decorator for embedding operations"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        operation = getattr(func, "__name__", "unknown")

        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Prometheus metrics
            if PROMETHEUS_AVAILABLE:
                VECTOR_SEARCH_COUNT.labels(mode="embedding").inc()
                VECTOR_SEARCH_DURATION.labels(mode="embedding").observe(execution_time)

            performance_monitor.record_metric(
                "embedding.call.duration",
                execution_time,
                {"batch_size": len(args) if args else 1},
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time

            # Prometheus error metrics
            if PROMETHEUS_AVAILABLE:
                VECTOR_SEARCH_COUNT.labels(mode="embedding_error").inc()

            performance_monitor.record_metric(
                "embedding.call.error", execution_time, {"error": str(e)}
            )
            raise

    return wrapper


def get_performance_report() -> Dict[str, Any]:
    """Generate a comprehensive performance report"""
    report = {
        "metrics_summary": performance_monitor.get_metrics_summary(),
        "system_stats": performance_monitor.get_system_stats(),
        "timestamp": time.time(),
        "recent_metrics": performance_monitor.get_recent_metrics(5),  # Last 5 minutes
    }

    # Add performance insights
    insights = []

    llm_metrics = performance_monitor.get_metrics_summary("llm.call.duration")
    if llm_metrics and llm_metrics.get("avg", 0) > 5.0:
        insights.append(
            "LLM response times are high (>5s). Consider model optimization."
        )

    memory_metrics = performance_monitor.get_metrics_summary("llm.call.memory_delta")
    if memory_metrics and memory_metrics.get("avg", 0) > 0.1:
        insights.append(
            "LLM calls are consuming significant memory. Monitor for leaks."
        )

    embedding_metrics = performance_monitor.get_metrics_summary(
        "embedding.call.duration"
    )
    if embedding_metrics and embedding_metrics.get("avg", 0) > 1.0:
        insights.append("Embedding operations are slow. Consider batch processing.")

    report["insights"] = insights
    return report


def get_prometheus_metrics() -> bytes:
    """Get Prometheus metrics in the standard format"""
    if PROMETHEUS_AVAILABLE:
        # Update current system metrics
        performance_monitor.update_prometheus_metrics()
        return generate_latest()
    return b"# Prometheus not available\n"


def monitor_request(method: str, endpoint: str):
    """Decorator to monitor HTTP requests"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                if PROMETHEUS_AVAILABLE:
                    REQUEST_COUNT.labels(
                        method=method, endpoint=endpoint, status=status
                    ).inc()
                    REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
                        duration
                    )

                performance_monitor.record_metric(
                    f"http.request.{endpoint}",
                    duration,
                    {"method": method, "status": status},
                )

        return wrapper

    return decorator
