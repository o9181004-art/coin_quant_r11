#!/usr/bin/env python3
"""
Structured Alerts System
Replace Telegram with file-based alert persistence
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class StructuredAlerts:
    """File-based structured alerts system"""
    
    def __init__(self):
        self.alerts_file = Path("shared_data/alerts.ndjson")
        self.alerts_dir = Path("shared_data/alerts")
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        
        # Alert cooldowns to prevent spam
        self._last_alert_times: Dict[str, float] = {}
        self._alert_cooldown = 60  # seconds
        
    def _get_alert_key(self, level: str, component: str, code: str) -> str:
        """Generate unique alert key for cooldown tracking"""
        return f"{level}:{component}:{code}"
    
    def _is_cooldown_active(self, alert_key: str) -> bool:
        """Check if alert is in cooldown period"""
        last_time = self._last_alert_times.get(alert_key, 0)
        return (time.time() - last_time) < self._alert_cooldown
    
    def _update_cooldown(self, alert_key: str):
        """Update alert cooldown timestamp"""
        self._last_alert_times[alert_key] = time.time()
    
    def emit_alert(self, level: str, component: str, code: str, 
                   message: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Emit a structured alert to alerts.ndjson"""
        try:
            alert_key = self._get_alert_key(level, component, code)
            
            # Check cooldown
            if self._is_cooldown_active(alert_key):
                return False  # Skip due to cooldown
            
            # Create alert record
            alert = {
                "ts": int(time.time() * 1000),  # milliseconds
                "level": level.upper(),  # INFO, WARN, ERROR
                "component": component,
                "code": code,
                "message": message,
                "context": context or {}
            }
            
            # Append to NDJSON file
            with open(self.alerts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
            
            # Update cooldown
            self._update_cooldown(alert_key)
            
            # Log to console
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] ALERT [{level}] {component}: {message}")
            
            return True
            
        except Exception as e:
            print(f"Failed to emit alert: {e}")
            return False
    
    def get_recent_alerts(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts from the NDJSON file"""
        try:
            if not self.alerts_file.exists():
                return []
            
            alerts = []
            with open(self.alerts_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            alert = json.loads(line)
                            alerts.append(alert)
                        except json.JSONDecodeError:
                            continue
            
            # Return most recent alerts
            return alerts[-count:] if len(alerts) > count else alerts
            
        except Exception as e:
            print(f"Failed to get recent alerts: {e}")
            return []
    
    def rotate_daily_alerts(self):
        """Rotate alerts to daily file at UTC 00:00"""
        try:
            if not self.alerts_file.exists():
                return
            
            # Check if we need to rotate (UTC 00:00)
            now = datetime.utcnow()
            if now.hour != 0 or now.minute != 0:
                return
            
            # Create daily filename
            date_str = now.strftime("%Y%m%d")
            daily_file = self.alerts_dir / f"alerts_{date_str}.ndjson"
            
            # Move current alerts to daily file
            if self.alerts_file.exists():
                self.alerts_file.rename(daily_file)
                print(f"Alerts rotated to {daily_file}")
            
        except Exception as e:
            print(f"Failed to rotate daily alerts: {e}")
    
    def cleanup_old_alerts(self, days_to_keep: int = 30):
        """Clean up old daily alert files"""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            
            for alert_file in self.alerts_dir.glob("alerts_*.ndjson"):
                if alert_file.stat().st_mtime < cutoff_time:
                    alert_file.unlink()
                    print(f"Cleaned up old alert file: {alert_file}")
                    
        except Exception as e:
            print(f"Failed to cleanup old alerts: {e}")

# Global instance
_alerts_instance: Optional[StructuredAlerts] = None

def get_alerts() -> StructuredAlerts:
    """Get global alerts instance"""
    global _alerts_instance
    if _alerts_instance is None:
        _alerts_instance = StructuredAlerts()
    return _alerts_instance

def emit_alert(level: str, component: str, code: str, 
               message: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """Emit a structured alert"""
    return get_alerts().emit_alert(level, component, code, message, context)

def emit_ws_age_alert(ws_age_sec: float, component_name: str = "FEEDER"):
    """Emit WebSocket age alert"""
    if ws_age_sec > 5:
        emit_alert(
            level="WARN",
            component=component_name,
            code="WS_STALE",
            message=f"WebSocket data stale for {ws_age_sec:.1f}s",
            context={"ws_age_sec": ws_age_sec, "threshold": 5}
        )

def emit_uds_age_alert(uds_age_sec: float):
    """Emit UDS age alert"""
    if uds_age_sec > 50:
        emit_alert(
            level="WARN",
            component="UDS",
            code="UDS_STALE",
            message=f"User Data Stream stale for {uds_age_sec:.1f}s",
            context={"uds_age_sec": uds_age_sec, "threshold": 50}
        )

def emit_order_failure_alert(symbol: str, failure_count: int):
    """Emit order failure streak alert"""
    if failure_count >= 3:
        emit_alert(
            level="ERROR",
            component="TRADER",
            code="ORDER_FAILURE_STREAK",
            message=f"Symbol {symbol} has {failure_count} consecutive order failures",
            context={"symbol": symbol, "failure_count": failure_count, "threshold": 3}
        )

def emit_daily_loss_alert(current_pnl: float, max_loss_usdt: float):
    """Emit daily loss breach alert"""
    if current_pnl < -max_loss_usdt:
        emit_alert(
            level="ERROR",
            component="RISK",
            code="DAILY_LOSS_BREACH",
            message=f"Daily loss ${-current_pnl:.2f} breached threshold ${max_loss_usdt:.2f}",
            context={"current_pnl": current_pnl, "max_loss_usdt": max_loss_usdt}
        )

def emit_health_alert(component: str, status: str, age_sec: float):
    """Emit health component alert"""
    if status in ["YELLOW", "RED"]:
        level = "ERROR" if status == "RED" else "WARN"
        emit_alert(
            level=level,
            component=component.upper(),
            code="HEALTH_UNHEALTHY",
            message=f"Component {component} is {status} for {age_sec:.1f}s",
            context={"status": status, "age_sec": age_sec}
        )

def get_recent_alerts(count: int = 20) -> List[Dict[str, Any]]:
    """Get recent alerts"""
    return get_alerts().get_recent_alerts(count)
