#!/usr/bin/env python3
"""
Observability Metrics & Monitoring Endpoints for Coin Quant R11

Provides comprehensive metrics collection, monitoring endpoints, and
real-time system observability for production deployment.
"""

import os
import json
import time
import psutil
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

from coin_quant.shared.io import AtomicWriter, AtomicReader
from coin_quant.shared.paths import get_data_dir
from coin_quant.shared.time import utc_now_seconds
from coin_quant.shared.health import health_manager

logger = logging.getLogger(__name__)

@dataclass
class MetricPoint:
    """Individual metric data point"""
    timestamp: float
    value: Union[float, int, str]
    labels: Dict[str, str]
    metric_type: str  # counter, gauge, histogram

@dataclass
class ServiceMetrics:
    """Service-specific metrics"""
    service_name: str
    timestamp: float
    uptime_seconds: float
    memory_mb: float
    cpu_percent: float
    request_count: int
    error_count: int
    last_activity: float
    custom_metrics: Dict[str, Any]

@dataclass
class SystemMetrics:
    """System-wide metrics"""
    timestamp: float
    total_memory_mb: float
    available_memory_mb: float
    memory_percent: float
    cpu_percent: float
    disk_usage_percent: float
    network_io: Dict[str, float]
    process_count: int
    load_average: List[float]

class MetricsCollector:
    """Centralized metrics collection system"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or get_data_dir()
        self.metrics_dir = self.data_dir / "metrics"
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        self.writer = AtomicWriter()
        self.reader = AtomicReader()
        
        # Metrics storage
        self.metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.service_metrics: Dict[str, ServiceMetrics] = {}
        self.system_metrics: Optional[SystemMetrics] = None
        
        # Collection settings
        self.collection_interval = 10.0  # seconds
        self.retention_hours = 24
        self.running = False
        self.collection_thread: Optional[threading.Thread] = None
        
        logger.info(f"MetricsCollector initialized: {self.metrics_dir}")
    
    def start_collection(self):
        """Start metrics collection"""
        if self.running:
            return
        
        self.running = True
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()
        
        logger.info("Metrics collection started")
    
    def stop_collection(self):
        """Stop metrics collection"""
        self.running = False
        if self.collection_thread:
            self.collection_thread.join(timeout=5)
        
        logger.info("Metrics collection stopped")
    
    def _collection_loop(self):
        """Main metrics collection loop"""
        while self.running:
            try:
                # Collect system metrics
                self._collect_system_metrics()
                
                # Collect service metrics
                self._collect_service_metrics()
                
                # Save metrics
                self._save_metrics()
                
                # Clean up old metrics
                self._cleanup_old_metrics()
                
                time.sleep(self.collection_interval)
                
            except Exception as e:
                logger.error(f"Metrics collection error: {e}")
                time.sleep(5)
    
    def _collect_system_metrics(self):
        """Collect system-wide metrics"""
        try:
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Disk metrics
            disk = psutil.disk_usage(self.data_dir)
            
            # Network metrics
            network = psutil.net_io_counters()
            
            # Process metrics
            process_count = len(psutil.pids())
            
            # Load average (Unix-like systems)
            try:
                load_avg = list(os.getloadavg())
            except AttributeError:
                load_avg = [0.0, 0.0, 0.0]  # Windows fallback
            
            self.system_metrics = SystemMetrics(
                timestamp=utc_now_seconds(),
                total_memory_mb=memory.total / (1024 * 1024),
                available_memory_mb=memory.available / (1024 * 1024),
                memory_percent=memory.percent,
                cpu_percent=cpu_percent,
                disk_usage_percent=disk.percent,
                network_io={
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                },
                process_count=process_count,
                load_average=load_avg
            )
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
    
    def _collect_service_metrics(self):
        """Collect service-specific metrics"""
        try:
            # Get health data for all services
            health_data = health_manager._load_health_data()
            components = health_data.get("components", {})
            
            for service_name, health_info in components.items():
                # Get process info if available
                memory_mb = 0.0
                cpu_percent = 0.0
                
                # Try to find process by name
                try:
                    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
                        if service_name in proc.info['name'].lower():
                            memory_mb = proc.info['memory_info'].rss / (1024 * 1024)
                            cpu_percent = proc.info['cpu_percent']
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                # Calculate uptime
                last_update = health_info.get("last_update_ts", 0)
                uptime_seconds = utc_now_seconds() - last_update if last_update > 0 else 0
                
                # Extract custom metrics from health info
                custom_metrics = {
                    "status": health_info.get("status", "UNKNOWN"),
                    "freshness_sec": health_info.get("updated_within_sec", 0),
                    "last_update_ts": last_update
                }
                
                # Add service-specific metrics
                if service_name == "feeder":
                    custom_metrics.update({
                        "symbols_count": health_info.get("symbols_count", 0),
                        "ws_connected": health_info.get("ws_connected", False),
                        "rest_api_ok": health_info.get("rest_api_ok", False)
                    })
                elif service_name == "ares":
                    custom_metrics.update({
                        "signal_count": health_info.get("signal_count", 0),
                        "feeder_health_ok": health_info.get("feeder_health_ok", False),
                        "default_signals_blocked": health_info.get("default_signals_blocked", False)
                    })
                elif service_name == "trader":
                    custom_metrics.update({
                        "orders_count": health_info.get("orders_count", 0),
                        "fills_count": health_info.get("fills_count", 0),
                        "quarantined_symbols": len(health_info.get("quarantined_symbols", [])),
                        "simulation_mode": health_info.get("simulation_mode", False)
                    })
                
                self.service_metrics[service_name] = ServiceMetrics(
                    service_name=service_name,
                    timestamp=utc_now_seconds(),
                    uptime_seconds=uptime_seconds,
                    memory_mb=memory_mb,
                    cpu_percent=cpu_percent,
                    request_count=0,  # TODO: Implement request counting
                    error_count=0,    # TODO: Implement error counting
                    last_activity=last_update,
                    custom_metrics=custom_metrics
                )
                
        except Exception as e:
            logger.error(f"Failed to collect service metrics: {e}")
    
    def _save_metrics(self):
        """Save metrics to files"""
        try:
            timestamp = int(utc_now_seconds())
            
            # Save system metrics
            if self.system_metrics:
                system_file = self.metrics_dir / f"system_{timestamp}.json"
                self.writer.write_json(system_file, asdict(self.system_metrics))
            
            # Save service metrics
            for service_name, metrics in self.service_metrics.items():
                service_file = self.metrics_dir / f"{service_name}_{timestamp}.json"
                self.writer.write_json(service_file, asdict(metrics))
            
            # Save aggregated metrics
            aggregated = {
                "timestamp": timestamp,
                "system": asdict(self.system_metrics) if self.system_metrics else None,
                "services": {name: asdict(metrics) for name, metrics in self.service_metrics.items()}
            }
            
            aggregated_file = self.metrics_dir / f"aggregated_{timestamp}.json"
            self.writer.write_json(aggregated_file, aggregated)
            
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def _cleanup_old_metrics(self):
        """Clean up old metrics files"""
        try:
            cutoff_time = time.time() - (self.retention_hours * 3600)
            
            for metrics_file in self.metrics_dir.glob("*.json"):
                if metrics_file.stat().st_mtime < cutoff_time:
                    metrics_file.unlink()
                    logger.debug(f"Removed old metrics file: {metrics_file.name}")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")
    
    def get_metrics_summary(self, hours_back: int = 1) -> Dict[str, Any]:
        """Get metrics summary for the last N hours"""
        try:
            cutoff_time = time.time() - (hours_back * 3600)
            
            # Find relevant metrics files
            metrics_files = []
            for metrics_file in self.metrics_dir.glob("aggregated_*.json"):
                if metrics_file.stat().st_mtime >= cutoff_time:
                    metrics_files.append(metrics_file)
            
            metrics_files.sort(key=lambda f: f.stat().st_mtime)
            
            if not metrics_files:
                return {"error": "No metrics data available"}
            
            # Load and aggregate metrics
            summary = {
                "timestamp": utc_now_seconds(),
                "hours_back": hours_back,
                "data_points": len(metrics_files),
                "system": {
                    "avg_cpu_percent": 0.0,
                    "avg_memory_percent": 0.0,
                    "avg_disk_percent": 0.0,
                    "peak_cpu_percent": 0.0,
                    "peak_memory_percent": 0.0
                },
                "services": {}
            }
            
            cpu_values = []
            memory_values = []
            disk_values = []
            
            for metrics_file in metrics_files:
                try:
                    data = self.reader.read_json(metrics_file)
                    if not data:
                        continue
                    
                    # System metrics
                    system_data = data.get("system")
                    if system_data:
                        cpu_values.append(system_data.get("cpu_percent", 0))
                        memory_values.append(system_data.get("memory_percent", 0))
                        disk_values.append(system_data.get("disk_usage_percent", 0))
                    
                    # Service metrics
                    services_data = data.get("services", {})
                    for service_name, service_data in services_data.items():
                        if service_name not in summary["services"]:
                            summary["services"][service_name] = {
                                "avg_cpu_percent": 0.0,
                                "avg_memory_mb": 0.0,
                                "uptime_hours": 0.0,
                                "status_counts": defaultdict(int),
                                "data_points": 0
                            }
                        
                        service_summary = summary["services"][service_name]
                        service_summary["avg_cpu_percent"] += service_data.get("cpu_percent", 0)
                        service_summary["avg_memory_mb"] += service_data.get("memory_mb", 0)
                        service_summary["uptime_hours"] += service_data.get("uptime_seconds", 0) / 3600
                        service_summary["status_counts"][service_data.get("custom_metrics", {}).get("status", "UNKNOWN")] += 1
                        service_summary["data_points"] += 1
                        
                except Exception as e:
                    logger.error(f"Failed to process metrics file {metrics_file}: {e}")
                    continue
            
            # Calculate averages
            if cpu_values:
                summary["system"]["avg_cpu_percent"] = sum(cpu_values) / len(cpu_values)
                summary["system"]["peak_cpu_percent"] = max(cpu_values)
            
            if memory_values:
                summary["system"]["avg_memory_percent"] = sum(memory_values) / len(memory_values)
                summary["system"]["peak_memory_percent"] = max(memory_values)
            
            if disk_values:
                summary["system"]["avg_disk_percent"] = sum(disk_values) / len(disk_values)
            
            # Calculate service averages
            for service_name, service_summary in summary["services"].items():
                if service_summary["data_points"] > 0:
                    service_summary["avg_cpu_percent"] /= service_summary["data_points"]
                    service_summary["avg_memory_mb"] /= service_summary["data_points"]
                    service_summary["uptime_hours"] /= service_summary["data_points"]
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {"error": str(e)}

class MonitoringEndpoint:
    """HTTP monitoring endpoint for metrics and health checks"""
    
    def __init__(self, port: int = 8080, data_dir: Optional[Path] = None):
        self.port = port
        self.data_dir = data_dir or get_data_dir()
        self.metrics_collector = MetricsCollector(self.data_dir)
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        
        logger.info(f"MonitoringEndpoint initialized on port {port}")
    
    def start(self):
        """Start monitoring endpoint"""
        try:
            self.metrics_collector.start_collection()
            
            self.server = HTTPServer(('localhost', self.port), MonitoringHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            logger.info(f"Monitoring endpoint started on http://localhost:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start monitoring endpoint: {e}")
            raise
    
    def stop(self):
        """Stop monitoring endpoint"""
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            
            self.metrics_collector.stop_collection()
            
            logger.info("Monitoring endpoint stopped")
            
        except Exception as e:
            logger.error(f"Failed to stop monitoring endpoint: {e}")

class MonitoringHandler(BaseHTTPRequestHandler):
    """HTTP request handler for monitoring endpoints"""
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            query_params = urllib.parse.parse_qs(parsed_path.query)
            
            if path == "/health":
                self._handle_health()
            elif path == "/metrics":
                self._handle_metrics(query_params)
            elif path == "/status":
                self._handle_status()
            elif path == "/debug":
                self._handle_debug()
            else:
                self._handle_404()
                
        except Exception as e:
            self._handle_500(str(e))
    
    def _handle_health(self):
        """Handle health check endpoint"""
        try:
            # Get health data
            health_data = health_manager._load_health_data()
            overall_status = health_manager.get_overall_status()
            
            response = {
                "status": overall_status,
                "timestamp": utc_now_seconds(),
                "components": health_data.get("components", {})
            }
            
            # Determine HTTP status code
            if overall_status == "GREEN":
                status_code = 200
            elif overall_status == "YELLOW":
                status_code = 200
            else:
                status_code = 503
            
            self._send_json_response(response, status_code)
            
        except Exception as e:
            self._handle_500(f"Health check failed: {e}")
    
    def _handle_metrics(self, query_params):
        """Handle metrics endpoint"""
        try:
            hours_back = int(query_params.get("hours", ["1"])[0])
            
            # Get metrics summary
            metrics_summary = self.server.metrics_collector.get_metrics_summary(hours_back)
            
            self._send_json_response(metrics_summary)
            
        except Exception as e:
            self._handle_500(f"Metrics retrieval failed: {e}")
    
    def _handle_status(self):
        """Handle status endpoint"""
        try:
            # Get comprehensive status
            health_data = health_manager._load_health_data()
            overall_status = health_manager.get_overall_status()
            
            # Get system metrics
            system_metrics = self.server.metrics_collector.system_metrics
            
            response = {
                "timestamp": utc_now_seconds(),
                "overall_status": overall_status,
                "system": {
                    "cpu_percent": system_metrics.cpu_percent if system_metrics else 0,
                    "memory_percent": system_metrics.memory_percent if system_metrics else 0,
                    "disk_percent": system_metrics.disk_usage_percent if system_metrics else 0
                },
                "services": health_data.get("components", {}),
                "uptime": self._get_uptime()
            }
            
            self._send_json_response(response)
            
        except Exception as e:
            self._handle_500(f"Status retrieval failed: {e}")
    
    def _handle_debug(self):
        """Handle debug endpoint"""
        try:
            # Get debug information
            debug_info = {
                "timestamp": utc_now_seconds(),
                "python_version": os.sys.version,
                "platform": os.name,
                "data_directory": str(self.server.metrics_collector.data_dir),
                "metrics_directory": str(self.server.metrics_collector.metrics_dir),
                "collection_running": self.server.metrics_collector.running,
                "collection_interval": self.server.metrics_collector.collection_interval,
                "retention_hours": self.server.metrics_collector.retention_hours
            }
            
            self._send_json_response(debug_info)
            
        except Exception as e:
            self._handle_500(f"Debug info retrieval failed: {e}")
    
    def _handle_404(self):
        """Handle 404 Not Found"""
        response = {
            "error": "Not Found",
            "message": f"Endpoint {self.path} not found",
            "available_endpoints": ["/health", "/metrics", "/status", "/debug"]
        }
        self._send_json_response(response, 404)
    
    def _handle_500(self, error_message: str):
        """Handle 500 Internal Server Error"""
        response = {
            "error": "Internal Server Error",
            "message": error_message,
            "timestamp": utc_now_seconds()
        }
        self._send_json_response(response, 500)
    
    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        json_data = json.dumps(data, indent=2, default=str)
        self.wfile.write(json_data.encode('utf-8'))
    
    def _get_uptime(self) -> float:
        """Get system uptime in seconds"""
        try:
            return time.time() - psutil.boot_time()
        except:
            return 0.0
    
    def log_message(self, format, *args):
        """Override to reduce log noise"""
        pass

def create_monitoring_endpoint(port: int = 8080, data_dir: Optional[Path] = None) -> MonitoringEndpoint:
    """Create monitoring endpoint"""
    return MonitoringEndpoint(port, data_dir)

def start_monitoring_server(port: int = 8080, data_dir: Optional[Path] = None) -> MonitoringEndpoint:
    """Start monitoring server"""
    endpoint = create_monitoring_endpoint(port, data_dir)
    endpoint.start()
    return endpoint

if __name__ == "__main__":
    # Start monitoring server
    import logging
    logging.basicConfig(level=logging.INFO)
    
    server = start_monitoring_server()
    
    try:
        print(f"Monitoring server running on http://localhost:{server.port}")
        print("Available endpoints:")
        print("  GET /health - Health check")
        print("  GET /metrics?hours=1 - Metrics summary")
        print("  GET /status - System status")
        print("  GET /debug - Debug information")
        print("\nPress Ctrl+C to stop...")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down monitoring server...")
        server.stop()
