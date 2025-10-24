"""
Resource Monitor
Lightweight process monitoring with memory leak detection and controlled restarts
"""
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env_loader import get_env_hash
from .path_registry import get_absolute_path
from .io_safe import atomic_write


@dataclass
class ProcessMetrics:
    """Process resource metrics"""
    pid: int
    name: str
    rss_mb: float
    vms_mb: float
    cpu_percent: float
    num_threads: int
    num_handles: int
    create_time: float
    status: str
    timestamp: float = 0.0


@dataclass
class ResourceThresholds:
    """Resource monitoring thresholds"""
    memory_warn_mb: float = 1200.0
    memory_hard_mb: float = 1536.0
    cpu_warn_percent: float = 80.0
    cpu_hard_percent: float = 95.0
    handles_warn: int = 1000
    handles_hard: int = 2000
    threads_warn: int = 100
    threads_hard: int = 200
    leak_detection_window: int = 300  # 5 minutes
    leak_threshold_mb: float = 100.0  # 100MB growth


@dataclass
class ResourceAlert:
    """Resource alert"""
    process_name: str
    pid: int
    alert_type: str
    current_value: float
    threshold: float
    severity: str  # "warning", "critical"
    timestamp: float = 0.0


class ResourceMonitor:
    """Resource monitor for core processes"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.thresholds = ResourceThresholds()
        self.monitoring_interval = 10.0  # 10 seconds
        self.running = False
        self.process_history: Dict[int, List[ProcessMetrics]] = {}
        self.active_alerts: Dict[str, ResourceAlert] = {}
        self.core_processes = ['feeder', 'trader', 'ares', 'health', 'ui']
        self.restart_attempts: Dict[str, int] = {}
        self.last_restart: Dict[str, float] = {}
        self.restart_cooldown = 300.0  # 5 minutes
        self.monitor_thread: Optional[threading.Thread] = None
    
    def start_monitoring(self):
        """Start resource monitoring"""
        if self.running:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Resource monitoring started")
    
    def stop_monitoring(self):
        """Stop resource monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        self.logger.info("Resource monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self._collect_process_metrics()
                self._check_thresholds()
                self._detect_memory_leaks()
                self._cleanup_old_data()
                
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.monitoring_interval)
    
    def _collect_process_metrics(self):
        """Collect metrics for core processes"""
        try:
            # Get process list
            if sys.platform == 'win32':
                processes = self._get_windows_processes()
            else:
                processes = self._get_unix_processes()
            
            # Filter for core processes
            core_processes = []
            for proc in processes:
                if any(core_name in proc['name'].lower() for core_name in self.core_processes):
                    core_processes.append(proc)
            
            # Convert to ProcessMetrics
            for proc_data in core_processes:
                metrics = ProcessMetrics(
                    pid=proc_data['pid'],
                    name=proc_data['name'],
                    rss_mb=proc_data['rss_mb'],
                    vms_mb=proc_data['vms_mb'],
                    cpu_percent=proc_data['cpu_percent'],
                    num_threads=proc_data['num_threads'],
                    num_handles=proc_data['num_handles'],
                    create_time=proc_data['create_time'],
                    status=proc_data['status'],
                    timestamp=time.time()
                )
                
                # Store in history
                if metrics.pid not in self.process_history:
                    self.process_history[metrics.pid] = []
                
                self.process_history[metrics.pid].append(metrics)
                
                # Keep only recent history
                if len(self.process_history[metrics.pid]) > 100:
                    self.process_history[metrics.pid] = self.process_history[metrics.pid][-50:]
            
        except Exception as e:
            self.logger.error(f"Failed to collect process metrics: {e}")
    
    def _get_windows_processes(self) -> List[Dict[str, Any]]:
        """Get Windows process information"""
        try:
            import psutil
            
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent', 'num_threads', 'create_time', 'status']):
                try:
                    info = proc.info
                    memory_info = info['memory_info']
                    
                    processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'rss_mb': memory_info.rss / 1024 / 1024,
                        'vms_mb': memory_info.vms / 1024 / 1024,
                        'cpu_percent': info['cpu_percent'],
                        'num_threads': info['num_threads'],
                        'num_handles': 0,  # Windows specific
                        'create_time': info['create_time'],
                        'status': info['status']
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return processes
            
        except ImportError:
            self.logger.warning("psutil not available, using basic process detection")
            return self._get_basic_processes()
    
    def _get_unix_processes(self) -> List[Dict[str, Any]]:
        """Get Unix process information"""
        try:
            import psutil
            
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent', 'num_threads', 'create_time', 'status']):
                try:
                    info = proc.info
                    memory_info = info['memory_info']
                    
                    processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'rss_mb': memory_info.rss / 1024 / 1024,
                        'vms_mb': memory_info.vms / 1024 / 1024,
                        'cpu_percent': info['cpu_percent'],
                        'num_threads': info['num_threads'],
                        'num_handles': 0,  # Unix doesn't have handles
                        'create_time': info['create_time'],
                        'status': info['status']
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return processes
            
        except ImportError:
            self.logger.warning("psutil not available, using basic process detection")
            return self._get_basic_processes()
    
    def _get_basic_processes(self) -> List[Dict[str, Any]]:
        """Basic process detection without psutil"""
        try:
            if sys.platform == 'win32':
                # Windows tasklist command
                result = subprocess.run(['tasklist', '/fo', 'csv'], capture_output=True, text=True)
                processes = []
                
                for line in result.stdout.split('\n')[1:]:  # Skip header
                    if line.strip():
                        parts = line.split(',')
                        if len(parts) >= 2:
                            name = parts[0].strip('"')
                            pid = int(parts[1].strip('"'))
                            
                            processes.append({
                                'pid': pid,
                                'name': name,
                                'rss_mb': 0.0,  # Unknown
                                'vms_mb': 0.0,  # Unknown
                                'cpu_percent': 0.0,  # Unknown
                                'num_threads': 0,  # Unknown
                                'num_handles': 0,  # Unknown
                                'create_time': time.time(),  # Unknown
                                'status': 'running'
                            })
                
                return processes
            else:
                # Unix ps command
                result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
                processes = []
                
                for line in result.stdout.split('\n')[1:]:  # Skip header
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 11:
                            try:
                                pid = int(parts[1])
                                name = parts[10]
                                
                                processes.append({
                                    'pid': pid,
                                    'name': name,
                                    'rss_mb': 0.0,  # Unknown
                                    'vms_mb': 0.0,  # Unknown
                                    'cpu_percent': 0.0,  # Unknown
                                    'num_threads': 0,  # Unknown
                                    'num_handles': 0,  # Unknown
                                    'create_time': time.time(),  # Unknown
                                    'status': 'running'
                                })
                            except (ValueError, IndexError):
                                continue
                
                return processes
                
        except Exception as e:
            self.logger.error(f"Basic process detection failed: {e}")
            return []
    
    def _check_thresholds(self):
        """Check resource usage against thresholds"""
        current_time = time.time()
        
        for pid, history in self.process_history.items():
            if not history:
                continue
            
            latest = history[-1]
            
            # Check memory thresholds
            if latest.rss_mb > self.thresholds.memory_hard_mb:
                self._handle_hard_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="memory_hard",
                    current_value=latest.rss_mb,
                    threshold=self.thresholds.memory_hard_mb,
                    severity="critical",
                    timestamp=current_time
                ))
            elif latest.rss_mb > self.thresholds.memory_warn_mb:
                self._handle_soft_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="memory_warn",
                    current_value=latest.rss_mb,
                    threshold=self.thresholds.memory_warn_mb,
                    severity="warning",
                    timestamp=current_time
                ))
            
            # Check CPU thresholds
            if latest.cpu_percent > self.thresholds.cpu_hard_percent:
                self._handle_hard_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="cpu_hard",
                    current_value=latest.cpu_percent,
                    threshold=self.thresholds.cpu_hard_percent,
                    severity="critical",
                    timestamp=current_time
                ))
            elif latest.cpu_percent > self.thresholds.cpu_warn_percent:
                self._handle_soft_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="cpu_warn",
                    current_value=latest.cpu_percent,
                    threshold=self.thresholds.cpu_warn_percent,
                    severity="warning",
                    timestamp=current_time
                ))
            
            # Check handle thresholds (Windows only)
            if sys.platform == 'win32' and latest.num_handles > self.thresholds.handles_hard:
                self._handle_hard_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="handles_hard",
                    current_value=latest.num_handles,
                    threshold=self.thresholds.handles_hard,
                    severity="critical",
                    timestamp=current_time
                ))
            elif sys.platform == 'win32' and latest.num_handles > self.thresholds.handles_warn:
                self._handle_soft_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="handles_warn",
                    current_value=latest.num_handles,
                    threshold=self.thresholds.handles_warn,
                    severity="warning",
                    timestamp=current_time
                ))
            
            # Check thread thresholds
            if latest.num_threads > self.thresholds.threads_hard:
                self._handle_hard_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="threads_hard",
                    current_value=latest.num_threads,
                    threshold=self.thresholds.threads_hard,
                    severity="critical",
                    timestamp=current_time
                ))
            elif latest.num_threads > self.thresholds.threads_warn:
                self._handle_soft_alert(latest, ResourceAlert(
                    process_name=latest.name,
                    pid=latest.pid,
                    alert_type="threads_warn",
                    current_value=latest.num_threads,
                    threshold=self.thresholds.threads_warn,
                    severity="warning",
                    timestamp=current_time
                ))
    
    def _handle_soft_alert(self, metrics: ProcessMetrics, alert: ResourceAlert):
        """Handle soft alert (warning)"""
        alert_key = f"{alert.process_name}_{alert.alert_type}"
        
        if alert_key not in self.active_alerts:
            self.active_alerts[alert_key] = alert
            self.logger.warning(f"Resource warning: {alert.process_name} {alert.alert_type} "
                              f"{alert.current_value:.1f} > {alert.threshold:.1f}")
    
    def _handle_hard_alert(self, metrics: ProcessMetrics, alert: ResourceAlert):
        """Handle hard alert (critical)"""
        alert_key = f"{alert.process_name}_{alert.alert_type}"
        
        if alert_key not in self.active_alerts:
            self.active_alerts[alert_key] = alert
            self.logger.error(f"Resource critical: {alert.process_name} {alert.alert_type} "
                            f"{alert.current_value:.1f} > {alert.threshold:.1f}")
            
            # Consider restart for critical alerts
            self._consider_restart(alert.process_name, metrics.pid)
    
    def _consider_restart(self, process_name: str, pid: int):
        """Consider restarting a process"""
        current_time = time.time()
        
        # Check cooldown
        if process_name in self.last_restart:
            if current_time - self.last_restart[process_name] < self.restart_cooldown:
                self.logger.info(f"Restart cooldown active for {process_name}")
                return
        
        # Check restart attempts
        attempts = self.restart_attempts.get(process_name, 0)
        if attempts >= 3:
            self.logger.error(f"Too many restart attempts for {process_name}, giving up")
            return
        
        # Attempt restart
        if self._restart_process(process_name, pid):
            self.restart_attempts[process_name] = attempts + 1
            self.last_restart[process_name] = current_time
            self.logger.info(f"Restarted {process_name} (attempt {attempts + 1})")
        else:
            self.logger.error(f"Failed to restart {process_name}")
    
    def _restart_process(self, process_name: str, pid: int) -> bool:
        """Restart a process"""
        try:
            # Gracefully terminate the process
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/PID', str(pid), '/F'], check=False)
            else:
                subprocess.run(['kill', '-TERM', str(pid)], check=False)
            
            # Wait a bit
            time.sleep(2.0)
            
            # Check if process is still running
            if sys.platform == 'win32':
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                      capture_output=True, text=True)
                if str(pid) in result.stdout:
                    return False
            else:
                result = subprocess.run(['ps', '-p', str(pid)], 
                                      capture_output=True, text=True)
                if str(pid) in result.stdout:
                    return False
            
            # Process terminated, restart would be handled by service manager
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to restart process {process_name}: {e}")
            return False
    
    def _detect_memory_leaks(self):
        """Detect memory leaks in processes"""
        current_time = time.time()
        
        for pid, history in self.process_history.items():
            if len(history) < 10:  # Need enough history
                continue
            
            # Get recent history within detection window
            recent_history = [
                h for h in history 
                if current_time - h.timestamp <= self.thresholds.leak_detection_window
            ]
            
            if len(recent_history) < 5:
                continue
            
            # Check for consistent memory growth
            memory_values = [h.rss_mb for h in recent_history]
            if len(memory_values) < 5:
                continue
            
            # Calculate growth rate
            growth = memory_values[-1] - memory_values[0]
            if growth > self.thresholds.leak_threshold_mb:
                # Check if growth is consistent (not just a spike)
                if all(memory_values[i] <= memory_values[i+1] for i in range(len(memory_values)-1)):
                    self.logger.warning(f"Memory leak detected in PID {pid}: "
                                      f"growth {growth:.1f}MB over {self.thresholds.leak_detection_window}s")
    
    def _cleanup_old_data(self):
        """Clean up old monitoring data"""
        current_time = time.time()
        cutoff_time = current_time - 3600  # 1 hour
        
        # Clean up old process history
        for pid in list(self.process_history.keys()):
            self.process_history[pid] = [
                h for h in self.process_history[pid] 
                if h.timestamp > cutoff_time
            ]
            
            if not self.process_history[pid]:
                del self.process_history[pid]
        
        # Clean up old alerts
        for alert_key in list(self.active_alerts.keys()):
            if self.active_alerts[alert_key].timestamp < cutoff_time:
                del self.active_alerts[alert_key]
    
    def get_resource_summary(self) -> Dict[str, Any]:
        """Get resource monitoring summary"""
        current_time = time.time()
        
        # Get latest metrics for each process
        latest_metrics = {}
        for pid, history in self.process_history.items():
            if history:
                latest_metrics[pid] = history[-1]
        
        # Count alerts
        warning_count = sum(1 for alert in self.active_alerts.values() if alert.severity == "warning")
        critical_count = sum(1 for alert in self.active_alerts.values() if alert.severity == "critical")
        
        return {
            "timestamp": current_time,
            "monitoring_active": self.running,
            "process_count": len(latest_metrics),
            "warning_alerts": warning_count,
            "critical_alerts": critical_count,
            "restart_attempts": self.restart_attempts.copy(),
            "processes": {
                str(pid): {
                    "name": metrics.name,
                    "rss_mb": metrics.rss_mb,
                    "cpu_percent": metrics.cpu_percent,
                    "num_threads": metrics.num_threads,
                    "status": metrics.status
                }
                for pid, metrics in latest_metrics.items()
            },
            "active_alerts": [
                {
                    "process_name": alert.process_name,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "current_value": alert.current_value,
                    "threshold": alert.threshold
                }
                for alert in self.active_alerts.values()
            ]
        }
    
    def save_resource_status(self):
        """Save resource status to file"""
        try:
            status_file = get_absolute_path('shared_data_health') / 'resource_status.json'
            summary = self.get_resource_summary()
            atomic_write(status_file, json.dumps(summary, indent=2))
        except Exception as e:
            self.logger.error(f"Failed to save resource status: {e}")


# Global instance
_resource_monitor = ResourceMonitor()


def start_resource_monitoring():
    """Start global resource monitoring"""
    _resource_monitor.start_monitoring()


def stop_resource_monitoring():
    """Stop global resource monitoring"""
    _resource_monitor.stop_monitoring()


def get_resource_summary() -> Dict[str, Any]:
    """Get resource monitoring summary"""
    return _resource_monitor.get_resource_summary()


def save_resource_status():
    """Save resource status to file"""
    _resource_monitor.save_resource_status()


if __name__ == '__main__':
    # Test resource monitor
    print("Resource Monitor Test:")
    
    monitor = ResourceMonitor()
    monitor.start_monitoring()
    
    try:
        # Run for a short time
        time.sleep(30)
        
        # Get summary
        summary = monitor.get_resource_summary()
        print(f"Monitoring active: {summary['monitoring_active']}")
        print(f"Process count: {summary['process_count']}")
        print(f"Warning alerts: {summary['warning_alerts']}")
        print(f"Critical alerts: {summary['critical_alerts']}")
        
        if summary['processes']:
            print("\nProcesses:")
            for pid, proc in summary['processes'].items():
                print(f"  {proc['name']} (PID {pid}): {proc['rss_mb']:.1f}MB, {proc['cpu_percent']:.1f}% CPU")
        
        if summary['active_alerts']:
            print("\nActive alerts:")
            for alert in summary['active_alerts']:
                print(f"  {alert['severity'].upper()}: {alert['process_name']} {alert['alert_type']} "
                      f"{alert['current_value']:.1f} > {alert['threshold']:.1f}")
        
    finally:
        monitor.stop_monitoring()