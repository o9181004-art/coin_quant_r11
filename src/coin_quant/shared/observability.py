#!/usr/bin/env python3
"""
Observability & Logs System for Coin Quant R11

Standardized logging with structured fields, rotation, and debug bundle export.
Provides consistent observability across all services.
"""

import os
import json
import time
import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

from coin_quant.shared.io import AtomicWriter, AtomicReader
from coin_quant.shared.paths import get_data_dir
from coin_quant.shared.time import utc_now_seconds

logger = logging.getLogger(__name__)


@dataclass
class LogField:
    """Structured log field definition"""
    name: str
    description: str
    type: str
    required: bool = False


class LogFields:
    """Standardized log fields for structured logging"""
    
    # Health & Readiness Fields
    HEALTH_STATUS = LogField("health_status", "Service health status", "str", True)
    READINESS_DECISION = LogField("readiness_decision", "Readiness gate decision", "str", True)
    BLOCKED_REASON = LogField("blocked_reason", "Reason for blocking", "str", False)
    FRESHNESS_SEC = LogField("freshness_sec", "Data freshness in seconds", "float", False)
    DEPENDENCY_STATUS = LogField("dependency_status", "Dependency health status", "str", False)
    
    # Order Execution Fields
    ORDER_ATTEMPT = LogField("order_attempt", "Order attempt details", "dict", True)
    ORDER_RESULT = LogField("order_result", "Order execution result", "str", True)
    ORDER_SIZE = LogField("order_size", "Order size", "float", True)
    ORDER_PRICE = LogField("order_price", "Order price", "float", True)
    ORDER_SYMBOL = LogField("order_symbol", "Trading symbol", "str", True)
    ORDER_SIDE = LogField("order_side", "Order side (BUY/SELL)", "str", True)
    
    # Signal Generation Fields
    SIGNAL_GENERATED = LogField("signal_generated", "Signal generation details", "dict", True)
    SIGNAL_COUNT = LogField("signal_count", "Number of signals generated", "int", True)
    STRATEGY_NAME = LogField("strategy_name", "Trading strategy name", "str", True)
    SIGNAL_CONFIDENCE = LogField("signal_confidence", "Signal confidence score", "float", False)
    
    # Memory Layer Fields
    INTEGRITY_CHECK = LogField("integrity_check", "Memory integrity check result", "dict", True)
    INTEGRITY_STATUS = LogField("integrity_status", "Memory integrity status", "str", True)
    INTEGRITY_ERRORS = LogField("integrity_errors", "Integrity check errors", "list", False)
    QUARANTINE_ACTION = LogField("quarantine_action", "Quarantine action taken", "dict", True)
    
    # System Fields
    SERVICE_NAME = LogField("service_name", "Service name", "str", True)
    EVENT_TYPE = LogField("event_type", "Event type", "str", True)
    TIMESTAMP = LogField("timestamp", "Event timestamp", "float", True)
    CONFIG_HASH = LogField("config_hash", "Configuration hash", "str", False)
    MEMORY_USAGE = LogField("memory_usage", "Memory usage in MB", "float", False)
    CPU_USAGE = LogField("cpu_usage", "CPU usage percentage", "float", False)


class StructuredLogger:
    """Structured logger with standardized fields"""
    
    def __init__(self, service_name: str, log_dir: Optional[Path] = None):
        self.service_name = service_name
        self.log_dir = log_dir or get_data_dir() / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logger
        self.logger = logging.getLogger(f"coin_quant.{service_name}")
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Setup file handler with rotation
        log_file = self.log_dir / f"{service_name}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setLevel(logging.INFO)
        
        # Setup console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Setup formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        logger.info(f"StructuredLogger initialized for {service_name}: {log_file}")
    
    def log_health_update(self, status: str, freshness_sec: float = 0.0, 
                         dependency_status: Optional[str] = None) -> None:
        """Log health status update"""
        self.logger.info(
            f"Health update: {status}",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "health_update",
                LogFields.HEALTH_STATUS.name: status,
                LogFields.FRESHNESS_SEC.name: freshness_sec,
                LogFields.TIMESTAMP.name: utc_now_seconds(),
                LogFields.DEPENDENCY_STATUS.name: dependency_status
            }
        )
    
    def log_readiness_decision(self, decision: str, reason: Optional[str] = None) -> None:
        """Log readiness gate decision"""
        self.logger.info(
            f"Readiness decision: {decision}",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "readiness_decision",
                LogFields.READINESS_DECISION.name: decision,
                LogFields.BLOCKED_REASON.name: reason,
                LogFields.TIMESTAMP.name: utc_now_seconds()
            }
        )
    
    def log_order_attempt(self, symbol: str, side: str, size: float, price: float) -> None:
        """Log order attempt"""
        self.logger.info(
            f"Order attempt: {side} {size} {symbol} @ {price}",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "order_attempt",
                LogFields.ORDER_SYMBOL.name: symbol,
                LogFields.ORDER_SIDE.name: side,
                LogFields.ORDER_SIZE.name: size,
                LogFields.ORDER_PRICE.name: price,
                LogFields.TIMESTAMP.name: utc_now_seconds()
            }
        )
    
    def log_order_result(self, symbol: str, result: str, details: Optional[Dict] = None) -> None:
        """Log order execution result"""
        self.logger.info(
            f"Order result: {symbol} - {result}",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "order_result",
                LogFields.ORDER_SYMBOL.name: symbol,
                LogFields.ORDER_RESULT.name: result,
                LogFields.ORDER_ATTEMPT.name: details or {},
                LogFields.TIMESTAMP.name: utc_now_seconds()
            }
        )
    
    def log_signal_generation(self, signal_count: int, strategy_name: str, 
                            confidence: Optional[float] = None) -> None:
        """Log signal generation"""
        self.logger.info(
            f"Signal generation: {signal_count} signals from {strategy_name}",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "signal_generation",
                LogFields.SIGNAL_COUNT.name: signal_count,
                LogFields.STRATEGY_NAME.name: strategy_name,
                LogFields.SIGNAL_CONFIDENCE.name: confidence,
                LogFields.TIMESTAMP.name: utc_now_seconds()
            }
        )
    
    def log_integrity_check(self, status: str, errors: Optional[List[str]] = None) -> None:
        """Log memory integrity check"""
        self.logger.info(
            f"Integrity check: {status}",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "integrity_check",
                LogFields.INTEGRITY_STATUS.name: status,
                LogFields.INTEGRITY_ERRORS.name: errors or [],
                LogFields.TIMESTAMP.name: utc_now_seconds()
            }
        )
    
    def log_quarantine_action(self, action: str, symbol: str, reason: str) -> None:
        """Log quarantine action"""
        self.logger.info(
            f"Quarantine action: {action} {symbol} - {reason}",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "quarantine_action",
                LogFields.QUARANTINE_ACTION.name: {
                    "action": action,
                    "symbol": symbol,
                    "reason": reason
                },
                LogFields.TIMESTAMP.name: utc_now_seconds()
            }
        )
    
    def log_system_metrics(self, memory_mb: float, cpu_percent: float) -> None:
        """Log system metrics"""
        self.logger.info(
            f"System metrics: Memory {memory_mb:.1f}MB, CPU {cpu_percent:.1f}%",
            extra={
                LogFields.SERVICE_NAME.name: self.service_name,
                LogFields.EVENT_TYPE.name: "system_metrics",
                LogFields.MEMORY_USAGE.name: memory_mb,
                LogFields.CPU_USAGE.name: cpu_percent,
                LogFields.TIMESTAMP.name: utc_now_seconds()
            }
        )


class StartupBanner:
    """Standardized startup banner generator"""
    
    @staticmethod
    def print_banner(service_name: str, config_summary: Dict[str, Any]) -> None:
        """Print standardized startup banner"""
        print("\n" + "="*80)
        print(f"🚀 {service_name.upper()} SERVICE STARTING")
        print("="*80)
        print(f"📦 Package Version: 1.0.0-rc1")
        print(f"🐍 Python Version: {os.sys.version.split()[0]}")
        print(f"🔑 Config Hash: {config_summary.get('config_hash', 'unknown')[:12]}...")
        print(f"📁 Data Directory: {config_summary.get('data_dir', 'unknown')}")
        print(f"🎯 Trading Mode: {config_summary.get('trading_mode', 'unknown')}")
        print(f"🧪 Simulation: {config_summary.get('simulation_mode', 'unknown')}")
        print(f"🌐 Testnet: {config_summary.get('testnet', 'unknown')}")
        print(f"⚠️  Default Signals: {config_summary.get('default_signals', 'unknown')}")
        print(f"📊 Max Symbols: {config_summary.get('max_symbols', 'unknown')}")
        print(f"⏱️  Freshness Threshold: {config_summary.get('freshness_threshold', 'unknown')}s")
        print(f"📝 Log Level: {config_summary.get('log_level', 'unknown')}")
        print("="*80 + "\n")


class LogRotationManager:
    """Log rotation and retention manager"""
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or get_data_dir() / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.writer = AtomicWriter()
        self.reader = AtomicReader()
        
        # Rotation settings
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.max_backup_count = 5
        self.retention_days = 30
        
        logger.info(f"LogRotationManager initialized: {self.log_dir}")
    
    def rotate_logs(self) -> None:
        """Rotate log files"""
        for log_file in self.log_dir.glob("*.log"):
            if log_file.stat().st_size > self.max_file_size:
                self._rotate_file(log_file)
    
    def _rotate_file(self, log_file: Path) -> None:
        """Rotate individual log file"""
        try:
            # Create rotated filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_name = f"{log_file.stem}_{timestamp}.log"
            rotated_file = log_file.parent / rotated_name
            
            # Move current file to rotated name
            log_file.rename(rotated_file)
            
            # Clean up old backups
            self._cleanup_old_backups(log_file.stem)
            
            logger.info(f"Log rotated: {log_file.name} -> {rotated_name}")
            
        except Exception as e:
            logger.error(f"Failed to rotate log {log_file}: {str(e)}")
    
    def _cleanup_old_backups(self, log_stem: str) -> None:
        """Clean up old backup files"""
        try:
            backup_files = list(self.log_dir.glob(f"{log_stem}_*.log"))
            backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # Keep only the most recent backups
            for old_file in backup_files[self.max_backup_count:]:
                old_file.unlink()
                logger.debug(f"Removed old backup: {old_file.name}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {str(e)}")
    
    def cleanup_expired_logs(self) -> None:
        """Clean up expired log files"""
        try:
            cutoff_time = time.time() - (self.retention_days * 24 * 3600)
            
            for log_file in self.log_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    logger.info(f"Removed expired log: {log_file.name}")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup expired logs: {str(e)}")


class DebugBundleExporter:
    """Debug bundle exporter for troubleshooting"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or get_data_dir()
        self.writer = AtomicWriter()
        self.reader = AtomicReader()
        
        logger.info(f"DebugBundleExporter initialized: {self.data_dir}")
    
    def export_bundle(self, output_dir: Optional[Path] = None, 
                     minutes_back: int = 30) -> Path:
        """Export debug bundle with recent logs and system state"""
        if not output_dir:
            timestamp = int(time.time())
            output_dir = self.data_dir / "debug_bundles" / f"bundle_{timestamp}"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export recent logs
        self._export_recent_logs(output_dir, minutes_back)
        
        # Export health status
        self._export_health_status(output_dir)
        
        # Export configuration
        self._export_configuration(output_dir)
        
        # Export memory integrity
        self._export_memory_integrity(output_dir)
        
        # Export system state
        self._export_system_state(output_dir)
        
        # Create incident timeline
        self._create_incident_timeline(output_dir, minutes_back)
        
        logger.info(f"Debug bundle exported to: {output_dir}")
        return output_dir
    
    def _export_recent_logs(self, output_dir: Path, minutes_back: int) -> None:
        """Export recent log entries"""
        try:
            logs_dir = self.data_dir / "logs"
            if not logs_dir.exists():
                return
            
            cutoff_time = time.time() - (minutes_back * 60)
            recent_logs = {}
            
            for log_file in logs_dir.glob("*.log"):
                service_name = log_file.stem
                recent_entries = []
                
                with open(log_file, 'r') as f:
                    for line in f:
                        # Simple timestamp extraction (assumes ISO format)
                        if line.startswith('20'):  # ISO timestamp
                            try:
                                # Extract timestamp from log line
                                timestamp_str = line.split(' - ')[0]
                                timestamp = datetime.fromisoformat(timestamp_str.replace(',', '.')).timestamp()
                                
                                if timestamp >= cutoff_time:
                                    recent_entries.append(line.strip())
                            except (ValueError, IndexError):
                                continue
                
                if recent_entries:
                    recent_logs[service_name] = recent_entries[-100:]  # Last 100 entries
            
            self.writer.write_json(output_dir / "recent_logs.json", recent_logs)
            
        except Exception as e:
            logger.error(f"Failed to export recent logs: {str(e)}")
    
    def _export_health_status(self, output_dir: Path) -> None:
        """Export current health status"""
        try:
            health_file = self.data_dir / "health" / "health.json"
            if health_file.exists():
                health_data = self.reader.read_json(health_file)
                self.writer.write_json(output_dir / "health_status.json", health_data)
        except Exception as e:
            logger.error(f"Failed to export health status: {str(e)}")
    
    def _export_configuration(self, output_dir: Path) -> None:
        """Export current configuration"""
        try:
            config_file = self.data_dir / "ssot" / "env.json"
            if config_file.exists():
                config_data = self.reader.read_json(config_file)
                # Remove sensitive data
                if "BINANCE_API_KEY" in config_data:
                    config_data["BINANCE_API_KEY"] = "***REDACTED***"
                if "BINANCE_API_SECRET" in config_data:
                    config_data["BINANCE_API_SECRET"] = "***REDACTED***"
                
                self.writer.write_json(output_dir / "configuration.json", config_data)
        except Exception as e:
            logger.error(f"Failed to export configuration: {str(e)}")
    
    def _export_memory_integrity(self, output_dir: Path) -> None:
        """Export memory integrity status"""
        try:
            integrity_file = self.data_dir / "memory" / "integrity.json"
            if integrity_file.exists():
                integrity_data = self.reader.read_json(integrity_file)
                self.writer.write_json(output_dir / "memory_integrity.json", integrity_data)
        except Exception as e:
            logger.error(f"Failed to export memory integrity: {str(e)}")
    
    def _export_system_state(self, output_dir: Path) -> None:
        """Export system state information"""
        try:
            import psutil
            
            system_info = {
                "timestamp": utc_now_seconds(),
                "python_version": os.sys.version,
                "platform": os.name,
                "cpu_count": psutil.cpu_count(),
                "memory_total": psutil.virtual_memory().total,
                "memory_available": psutil.virtual_memory().available,
                "disk_usage": psutil.disk_usage(self.data_dir).percent,
                "process_count": len(psutil.pids())
            }
            
            self.writer.write_json(output_dir / "system_state.json", system_info)
            
        except Exception as e:
            logger.error(f"Failed to export system state: {str(e)}")
    
    def _create_incident_timeline(self, output_dir: Path, minutes_back: int) -> None:
        """Create incident timeline from logs"""
        try:
            logs_dir = self.data_dir / "logs"
            if not logs_dir.exists():
                return
            
            cutoff_time = time.time() - (minutes_back * 60)
            timeline = []
            
            for log_file in logs_dir.glob("*.log"):
                service_name = log_file.stem
                
                with open(log_file, 'r') as f:
                    for line in f:
                        if line.startswith('20'):  # ISO timestamp
                            try:
                                timestamp_str = line.split(' - ')[0]
                                timestamp = datetime.fromisoformat(timestamp_str.replace(',', '.')).timestamp()
                                
                                if timestamp >= cutoff_time:
                                    # Extract log level and message
                                    parts = line.split(' - ')
                                    if len(parts) >= 3:
                                        level = parts[1]
                                        message = ' - '.join(parts[2:])
                                        
                                        timeline.append({
                                            "timestamp": timestamp,
                                            "service": service_name,
                                            "level": level,
                                            "message": message.strip()
                                        })
                            except (ValueError, IndexError):
                                continue
            
            # Sort by timestamp
            timeline.sort(key=lambda x: x["timestamp"])
            
            self.writer.write_json(output_dir / "incident_timeline.json", timeline)
            
        except Exception as e:
            logger.error(f"Failed to create incident timeline: {str(e)}")


def create_structured_logger(service_name: str) -> StructuredLogger:
    """Create structured logger for service"""
    return StructuredLogger(service_name)


def create_debug_bundle(minutes_back: int = 30) -> Path:
    """Create debug bundle for troubleshooting"""
    exporter = DebugBundleExporter()
    return exporter.export_bundle(minutes_back=minutes_back)
