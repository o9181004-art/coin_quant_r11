#!/usr/bin/env python3
"""
Runtime Safety Alerts
Emit structured alerts for critical conditions using file-based alerts
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class RuntimeAlerts:
    """Runtime safety alerts and notifications"""
    
    def __init__(self):
        self.alerts_file = Path("shared_data/runtime_alerts.json")
        self.alert_history: List[Dict[str, Any]] = []
        self._load_alert_history()
        
        # Alert thresholds
        self.ws_age_threshold = 5  # seconds
        self.uds_age_threshold = 50  # seconds
        self.order_failure_threshold = 3  # consecutive failures
        self.daily_loss_threshold = 0.8  # 80% of daily max loss
        
        # Consecutive alert counters
        self.consecutive_ws_alerts = 0
        self.consecutive_uds_alerts = 0
        
    def _load_alert_history(self):
        """Load alert history from file"""
        try:
            if self.alerts_file.exists():
                with open(self.alerts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.alert_history = data.get("alerts", [])
                    # Keep only last 100 alerts
                    if len(self.alert_history) > 100:
                        self.alert_history = self.alert_history[-100:]
        except Exception as e:
            logger.error(f"Failed to load alert history: {e}")
            self.alert_history = []
    
    def _save_alert_history(self):
        """Save alert history to file"""
        try:
            data = {
                "alerts": self.alert_history,
                "last_updated": time.time()
            }
            with open(self.alerts_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save alert history: {e}")
    
    def _emit_alert(self, alert_type: str, symbol: str, reason: str, 
                   suggested_action: str, severity: str = "WARNING") -> bool:
        """Emit a structured alert"""
        try:
            alert = {
                "timestamp": time.time(),
                "alert_type": alert_type,
                "symbol": symbol,
                "reason": reason,
                "suggested_action": suggested_action,
                "severity": severity,
                "resolved": False
            }
            
            # Add to history
            self.alert_history.append(alert)
            self._save_alert_history()
            
            # Log the alert
            logger.warning(f"ALERT [{severity}]: {alert_type} - {symbol} - {reason}")
            logger.info(f"Suggested action: {suggested_action}")
            
            # Emit structured alert
            try:
                from shared.structured_alerts import emit_alert
                emit_alert(
                    level=severity,
                    component=symbol,
                    code=alert_type,
                    message=reason,
                    context={"suggested_action": suggested_action}
                )
            except Exception as e:
                logger.error(f"Failed to emit structured alert: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to emit alert: {e}")
            return False
    
    
    def check_ws_age_alert(self, ws_age_sec: float, symbol: str = "SYSTEM"):
        """Check WebSocket age and emit alert if threshold exceeded"""
        try:
            if ws_age_sec > self.ws_age_threshold:
                self.consecutive_ws_alerts += 1
                
                # Emit alert on 3rd consecutive occurrence
                if self.consecutive_ws_alerts >= 3:
                    reason = f"WebSocket age {ws_age_sec:.1f}s > {self.ws_age_threshold}s (3x consecutive)"
                    suggested_action = "Check Feeder service, restart if necessary, verify network connectivity"
                    
                    self._emit_alert(
                        alert_type="WS_AGE_EXCEEDED",
                        symbol=symbol,
                        reason=reason,
                        suggested_action=suggested_action,
                        severity="WARNING"
                    )
                    
                    # Reset counter after alert
                    self.consecutive_ws_alerts = 0
            else:
                # Reset counter when age is normal
                self.consecutive_ws_alerts = 0
                
        except Exception as e:
            logger.error(f"WS age alert check failed: {e}")
    
    def check_uds_age_alert(self, uds_age_sec: float):
        """Check UDS age and emit alert if threshold exceeded"""
        try:
            if uds_age_sec > self.uds_age_threshold:
                reason = f"UDS heartbeat age {uds_age_sec:.1f}s > {self.uds_age_threshold}s"
                suggested_action = "Check UDS service, verify listenKey renewal, restart if necessary"
                
                self._emit_alert(
                    alert_type="UDS_AGE_EXCEEDED",
                    symbol="UDS",
                    reason=reason,
                    suggested_action=suggested_action,
                    severity="WARNING"
                )
                
        except Exception as e:
            logger.error(f"UDS age alert check failed: {e}")
    
    def check_order_failure_streak(self, symbol: str, failure_count: int):
        """Check order failure streak and emit alert if threshold exceeded"""
        try:
            if failure_count >= self.order_failure_threshold:
                reason = f"Order failure streak: {failure_count} consecutive failures"
                suggested_action = f"Symbol {symbol} entered FAILSAFE mode - no new orders, monitor only"
                
                self._emit_alert(
                    alert_type="ORDER_FAILURE_STREAK",
                    symbol=symbol,
                    reason=reason,
                    suggested_action=suggested_action,
                    severity="ERROR"
                )
                
        except Exception as e:
            logger.error(f"Order failure streak alert check failed: {e}")
    
    def check_daily_loss_breach(self, daily_pnl_usdt: float, daily_max_loss_usdt: float):
        """Check daily loss breach and emit alert"""
        try:
            if daily_pnl_usdt < 0:  # Only check for losses
                loss_pct = abs(daily_pnl_usdt) / daily_max_loss_usdt
                
                if loss_pct >= self.daily_loss_threshold:
                    reason = f"Daily loss {daily_pnl_usdt:.2f} USDT ({loss_pct:.1%} of max {daily_max_loss_usdt:.2f} USDT)"
                    suggested_action = "Global circuit breaker activated - no new entries, risk-off only"
                    
                    self._emit_alert(
                        alert_type="DAILY_LOSS_BREACH",
                        symbol="PORTFOLIO",
                        reason=reason,
                        suggested_action=suggested_action,
                        severity="CRITICAL"
                    )
                    
        except Exception as e:
            logger.error(f"Daily loss breach alert check failed: {e}")
    
    def check_health_component_alert(self, component: str, status: str, age_sec: float):
        """Check health component status and emit alert if unhealthy"""
        try:
            if status != "GREEN":
                reason = f"Component {component} status: {status}, age: {age_sec:.1f}s"
                suggested_action = f"Check {component} service, restart if necessary"
                
                severity = "ERROR" if status == "RED" else "WARNING"
                
                self._emit_alert(
                    alert_type="HEALTH_COMPONENT_UNHEALTHY",
                    symbol=component.upper(),
                    reason=reason,
                    suggested_action=suggested_action,
                    severity=severity
                )
                
        except Exception as e:
            logger.error(f"Health component alert check failed: {e}")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active (unresolved) alerts"""
        try:
            return [alert for alert in self.alert_history if not alert.get("resolved", False)]
        except Exception as e:
            logger.error(f"Failed to get active alerts: {e}")
            return []
    
    def resolve_alert(self, alert_type: str, symbol: str) -> bool:
        """Mark an alert as resolved"""
        try:
            for alert in self.alert_history:
                if (alert.get("alert_type") == alert_type and 
                    alert.get("symbol") == symbol and 
                    not alert.get("resolved", False)):
                    alert["resolved"] = True
                    alert["resolved_at"] = time.time()
                    self._save_alert_history()
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return False
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary for monitoring"""
        try:
            active_alerts = self.get_active_alerts()
            
            summary = {
                "total_alerts": len(self.alert_history),
                "active_alerts": len(active_alerts),
                "alerts_by_type": {},
                "alerts_by_severity": {},
                "latest_alert": None
            }
            
            # Count by type and severity
            for alert in active_alerts:
                alert_type = alert.get("alert_type", "UNKNOWN")
                severity = alert.get("severity", "UNKNOWN")
                
                summary["alerts_by_type"][alert_type] = summary["alerts_by_type"].get(alert_type, 0) + 1
                summary["alerts_by_severity"][severity] = summary["alerts_by_severity"].get(severity, 0) + 1
            
            # Get latest alert
            if self.alert_history:
                summary["latest_alert"] = self.alert_history[-1]
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get alert summary: {e}")
            return {"error": str(e)}

# Global instance
_runtime_alerts = None

def get_runtime_alerts() -> RuntimeAlerts:
    """Get global runtime alerts instance"""
    global _runtime_alerts
    if _runtime_alerts is None:
        _runtime_alerts = RuntimeAlerts()
    return _runtime_alerts

def emit_ws_age_alert(ws_age_sec: float, symbol: str = "SYSTEM"):
    """Emit WebSocket age alert"""
    get_runtime_alerts().check_ws_age_alert(ws_age_sec, symbol)

def emit_uds_age_alert(uds_age_sec: float):
    """Emit UDS age alert"""
    get_runtime_alerts().check_uds_age_alert(uds_age_sec)

def emit_order_failure_alert(symbol: str, failure_count: int):
    """Emit order failure streak alert"""
    get_runtime_alerts().check_order_failure_streak(symbol, failure_count)

def emit_daily_loss_alert(daily_pnl_usdt: float, daily_max_loss_usdt: float):
    """Emit daily loss breach alert"""
    get_runtime_alerts().check_daily_loss_breach(daily_pnl_usdt, daily_max_loss_usdt)

def emit_health_component_alert(component: str, status: str, age_sec: float):
    """Emit health component alert"""
    get_runtime_alerts().check_health_component_alert(component, status, age_sec)

def get_active_alerts() -> List[Dict[str, Any]]:
    """Get active alerts"""
    return get_runtime_alerts().get_active_alerts()

def get_alert_summary() -> Dict[str, Any]:
    """Get alert summary"""
    return get_runtime_alerts().get_alert_summary()
