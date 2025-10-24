#!/usr/bin/env python3
"""
Risk Mode Manager - Core Risk Engine
Monitors trading activity and automatically switches between AGGRESSIVE and SAFE modes
"""

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from dotenv import load_dotenv

from shared.state.risk_mode_store import get_risk_mode_store, get_kst_now, to_iso8601_kst
from guard.risk.risk_profiles import apply_profile_aggressive, apply_profile_safe, get_profile_manager


# Load environment
config_path = Path(__file__).parent.parent.parent / "config.env"
load_dotenv(config_path)


@dataclass
class RiskTrigger:
    """Risk trigger event"""
    trigger_type: str  # consecutive_losses | intraday_drawdown | hard_cutoff | auto_heal
    timestamp: str  # ISO8601 KST
    value: float
    threshold: float
    details: Dict[str, Any]


@dataclass
class AutoHealEvent:
    """Auto-Heal critical event"""
    event_type: str  # order_failure | data_staleness | rest_timeout
    timestamp: float
    count: int
    window_sec: float
    details: Dict[str, Any]


class RiskModeManager:
    """
    Risk Mode Manager - Observes trading activity and manages mode switches

    Responsibilities:
    - Monitor trade fills and realized PnL
    - Track consecutive losses
    - Calculate intraday PnL percentage
    - Detect risk triggers
    - Switch to SAFE mode when triggers fire
    - Handle recovery to AGGRESSIVE mode (manual or auto)
    - Emit alerts (Telegram, UI, logs)
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # State stores
        self.risk_store = get_risk_mode_store()
        self.profile_manager = get_profile_manager()

        # Configuration
        self.auto_switch_enabled = os.getenv("SAFE_MODE_AUTO_SWITCH_ENABLED", "true").lower() == "true"
        self.return_policy = os.getenv("SAFE_MODE_RETURN_POLICY", "MANUAL").upper()

        # Trigger thresholds
        self.consecutive_loss_trigger = int(os.getenv("CONSECUTIVE_LOSS_TRIGGER", "3"))
        self.intraday_drawdown_trigger_pct = float(os.getenv("INTRADAY_DRAWDOWN_TRIGGER_PCT", "2.0"))
        self.hard_cutoff_daily_loss_pct = float(os.getenv("HARD_CUTOFF_DAILY_LOSS_PCT", "3.0"))

        # Auto-Heal thresholds
        self.order_failure_count = int(os.getenv("ORDER_FAILURE_COUNT", "3"))
        self.order_failure_window_sec = int(os.getenv("ORDER_FAILURE_WINDOW_SEC", "900"))  # 15 min
        self.data_staleness_sec = int(os.getenv("DATA_STALENESS_SEC", "180"))  # 3 min
        self.rest_timeout_count = int(os.getenv("REST_TIMEOUT_COUNT", "5"))
        self.rest_timeout_window_sec = int(os.getenv("REST_TIMEOUT_WINDOW_SEC", "600"))  # 10 min

        # Recovery settings
        self.min_recovery_hours = int(os.getenv("SAFE_MODE_MIN_RECOVERY_HOURS", "12"))
        self.recovery_pnl_pct = float(os.getenv("SAFE_MODE_RECOVERY_PNL_PCT", "1.0"))

        # Event tracking
        self.auto_heal_events = deque(maxlen=100)
        self.triggers_fired = deque(maxlen=50)

        # Callbacks
        self.on_mode_switch_callbacks: List[Callable] = []

        # Threading
        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

        # Paths
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)

        self.logger.info(
            f"RiskModeManager initialized: auto_switch={self.auto_switch_enabled}, "
            f"return_policy={self.return_policy}"
        )

    def start(self):
        """Start risk mode monitoring"""
        if self._running:
            self.logger.warning("RiskModeManager already running")
            return

        self._running = True

        # Start monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        self.logger.info("RiskModeManager started")

    def stop(self):
        """Stop risk mode monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

        self.logger.info("RiskModeManager stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                # Check for midnight reset
                self._check_midnight_reset()

                # Check for auto-recovery (if in SAFE mode and policy is AUTO)
                self._check_auto_recovery()

                # Sleep
                time.sleep(10)

            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
                time.sleep(10)

    def _check_midnight_reset(self):
        """Check if midnight reset is needed (KST 00:00)"""
        try:
            now = get_kst_now()

            # Check if we just crossed midnight
            # Simple approach: check if hour is 0 and we haven't reset in the last hour
            if now.hour == 0:
                state = self.risk_store.get_risk_state()
                last_updated = state.last_updated

                # Parse last_updated timestamp
                if last_updated:
                    try:
                        last_dt = datetime.fromisoformat(last_updated)
                        time_since_update = (now - last_dt).total_seconds()

                        # If last update was more than 1 hour ago, do midnight reset
                        if time_since_update > 3600:
                            self._perform_midnight_reset()
                    except Exception as e:
                        self.logger.error(f"Failed to parse last_updated timestamp: {e}")

        except Exception as e:
            self.logger.error(f"Failed to check midnight reset: {e}")

    def _perform_midnight_reset(self):
        """Perform midnight reset"""
        try:
            # Get current equity (would need to be passed in or retrieved)
            # For now, use the day_open_equity as a placeholder
            state = self.risk_store.get_risk_state()
            current_equity = state.day_open_equity if state.day_open_equity > 0 else 10000.0

            success = self.risk_store.midnight_reset(current_equity)

            if success:
                self.logger.info(f"Midnight reset completed at {to_iso8601_kst()}")
                self._log_structured_event({
                    "event": "midnight_reset",
                    "ts": to_iso8601_kst(),
                    "day_open_equity": current_equity,
                })

        except Exception as e:
            self.logger.error(f"Failed to perform midnight reset: {e}")

    def _check_auto_recovery(self):
        """Check if auto-recovery conditions are met"""
        try:
            if not self.auto_switch_enabled:
                return

            if self.return_policy != "AUTO":
                return

            if not self.risk_store.is_safe_mode():
                return

            state = self.risk_store.get_risk_state()

            # Check time since switch
            if not state.last_switch_ts:
                return

            last_switch_dt = datetime.fromisoformat(state.last_switch_ts)
            hours_since_switch = (get_kst_now() - last_switch_dt).total_seconds() / 3600

            if hours_since_switch < self.min_recovery_hours:
                return

            # Check PnL recovery
            if state.intraday_pnl_pct >= self.recovery_pnl_pct:
                self.logger.info(
                    f"Auto-recovery conditions met: hours={hours_since_switch:.1f}, "
                    f"pnl={state.intraday_pnl_pct:.2f}%"
                )
                self.resume_aggressive(auto=True)

        except Exception as e:
            self.logger.error(f"Failed to check auto-recovery: {e}")

    def on_trade_fill(self, symbol: str, side: str, realized_pnl: float, current_equity: float):
        """
        Handle trade fill event

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            realized_pnl: Realized PnL from this trade
            current_equity: Current account equity
        """
        try:
            with self._lock:
                if not self.auto_switch_enabled:
                    return

                # Update consecutive losses
                if realized_pnl < 0:
                    consecutive_losses = self.risk_store.increment_consecutive_losses()
                    self.logger.info(f"Loss recorded: {symbol} {side} PnL={realized_pnl:.2f}, streak={consecutive_losses}")

                    # Check consecutive loss trigger
                    if consecutive_losses >= self.consecutive_loss_trigger:
                        self._trigger_safe_mode(
                            "consecutive_losses",
                            consecutive_losses,
                            self.consecutive_loss_trigger,
                            {"symbol": symbol, "side": side, "pnl": realized_pnl}
                        )
                else:
                    # Reset on win
                    self.risk_store.reset_consecutive_losses()
                    self.logger.info(f"Win recorded: {symbol} {side} PnL={realized_pnl:.2f}, streak reset")

                # Update intraday PnL
                intraday_pnl_pct = self.risk_store.update_intraday_pnl(current_equity)

                # Check intraday drawdown trigger
                if intraday_pnl_pct <= -self.intraday_drawdown_trigger_pct:
                    self._trigger_safe_mode(
                        "intraday_drawdown",
                        intraday_pnl_pct,
                        -self.intraday_drawdown_trigger_pct,
                        {"symbol": symbol, "side": side, "pnl": realized_pnl, "equity": current_equity}
                    )

                # Check hard cutoff
                if intraday_pnl_pct <= -self.hard_cutoff_daily_loss_pct:
                    self._trigger_safe_mode(
                        "hard_cutoff",
                        intraday_pnl_pct,
                        -self.hard_cutoff_daily_loss_pct,
                        {"symbol": symbol, "side": side, "pnl": realized_pnl, "equity": current_equity}
                    )

        except Exception as e:
            self.logger.error(f"Failed to handle trade fill: {e}")

    def on_auto_heal_event(self, event: AutoHealEvent):
        """
        Handle Auto-Heal critical event

        Args:
            event: Auto-Heal event
        """
        try:
            with self._lock:
                if not self.auto_switch_enabled:
                    return

                self.auto_heal_events.append(event)

                # Check if event should trigger SAFE mode
                should_trigger = False

                if event.event_type == "order_failure":
                    if event.count >= self.order_failure_count:
                        should_trigger = True

                elif event.event_type == "data_staleness":
                    if event.window_sec >= self.data_staleness_sec:
                        should_trigger = True

                elif event.event_type == "rest_timeout":
                    if event.count >= self.rest_timeout_count:
                        should_trigger = True

                if should_trigger:
                    self._trigger_safe_mode(
                        "auto_heal",
                        event.count,
                        0,
                        {
                            "event_type": event.event_type,
                            "details": event.details
                        }
                    )

        except Exception as e:
            self.logger.error(f"Failed to handle auto-heal event: {e}")

    def _trigger_safe_mode(self, reason: str, value: float, threshold: float, details: Dict[str, Any]):
        """Trigger SAFE mode switch"""
        try:
            # Check if already in SAFE mode
            if self.risk_store.is_safe_mode():
                self.logger.info(f"Already in SAFE mode, trigger ignored: {reason}")
                return

            # Create trigger event
            trigger = RiskTrigger(
                trigger_type=reason,
                timestamp=to_iso8601_kst(),
                value=value,
                threshold=threshold,
                details=details
            )

            self.triggers_fired.append(trigger)

            # Switch to SAFE mode
            success = self.risk_store.switch_mode("SAFE", reason, manual_override=False)

            if success:
                # Apply SAFE profile
                apply_profile_safe()

                # Log structured event
                self._log_structured_event({
                    "event": "risk_mode_switch",
                    "from": "AGGRESSIVE",
                    "to": "SAFE",
                    "reason": reason,
                    "value": value,
                    "threshold": threshold,
                    "details": details,
                    "ts": to_iso8601_kst(),
                    "manual_override": False
                })

                # Send alerts
                self._send_alerts("SAFE", reason, details)

                # Emit UI bus event
                self._emit_ui_event("SAFE", reason)

                # Call callbacks
                for callback in self.on_mode_switch_callbacks:
                    try:
                        callback("AGGRESSIVE", "SAFE", reason)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")

                self.logger.warning(
                    f"⚠️ SAFE MODE ACTIVATED - Reason: {reason}, Value: {value}, Threshold: {threshold}"
                )

        except Exception as e:
            self.logger.error(f"Failed to trigger SAFE mode: {e}")

    def resume_aggressive(self, auto: bool = False):
        """Resume AGGRESSIVE mode"""
        try:
            with self._lock:
                # Check if in SAFE mode
                if not self.risk_store.is_safe_mode():
                    self.logger.info("Already in AGGRESSIVE mode")
                    return False

                # Check policy
                if not auto and self.return_policy == "AUTO":
                    self.logger.warning("Manual resume not allowed with AUTO return policy")
                    return False

                # Switch to AGGRESSIVE mode
                reason = "auto_recovery" if auto else "manual_resume"
                success = self.risk_store.switch_mode("AGGRESSIVE", reason, manual_override=not auto)

                if success:
                    # Apply AGGRESSIVE profile
                    apply_profile_aggressive()

                    # Log structured event
                    self._log_structured_event({
                        "event": "risk_mode_switch",
                        "from": "SAFE",
                        "to": "AGGRESSIVE",
                        "reason": reason,
                        "ts": to_iso8601_kst(),
                        "manual_override": not auto
                    })

                    # Send alerts
                    self._send_alerts("AGGRESSIVE", reason, {})

                    # Emit UI bus event
                    self._emit_ui_event("AGGRESSIVE", reason)

                    # Call callbacks
                    for callback in self.on_mode_switch_callbacks:
                        try:
                            callback("SAFE", "AGGRESSIVE", reason)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")

                    self.logger.info(f"✅ AGGRESSIVE MODE RESUMED - Reason: {reason}")

                return success

        except Exception as e:
            self.logger.error(f"Failed to resume aggressive mode: {e}")
            return False

    def _log_structured_event(self, event: Dict[str, Any]):
        """Log structured event to JSON log file"""
        try:
            # System log (JSON lines)
            system_log = self.logs_dir / "system.log"
            with open(system_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + "\n")

            # Risk log (JSON lines)
            risk_log = self.logs_dir / "risk.log"
            with open(risk_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + "\n")

            # Human-readable log
            if event.get("event") == "risk_mode_switch":
                human_log = (
                    f"{event['ts']} | MODE_SWITCH | {event['from']} → {event['to']} | "
                    f"Reason: {event['reason']} | Manual: {event.get('manual_override', False)}\n"
                )
                with open(self.logs_dir / "risk_human.log", 'a', encoding='utf-8') as f:
                    f.write(human_log)

        except Exception as e:
            self.logger.error(f"Failed to log structured event: {e}")

    def _send_alerts(self, new_mode: str, reason: str, details: Dict[str, Any]):
        """Send alerts (Telegram, UI)"""
        try:
            # Get current state for metrics
            state = self.risk_store.get_risk_state()
            profile = self.profile_manager.get_current_profile()

            # Build alert message
            if new_mode == "SAFE":
                message = (
                    f"⚠️ Safety Trigger Activated → Switched to SAFE MODE\n"
                    f"Reason: {reason}\n"
                    f"PnL(day): {state.intraday_pnl_pct:.2f}% | Loss Streak: {state.consecutive_losses}\n"
                    f"Limits: daily {profile.daily_loss_limit_pct}% | max positions {profile.max_concurrent_positions}"
                )
            else:
                message = (
                    f"✅ AGGRESSIVE MODE Resumed\n"
                    f"Reason: {reason}\n"
                    f"PnL(day): {state.intraday_pnl_pct:.2f}%\n"
                    f"Limits: daily {profile.daily_loss_limit_pct}% | max positions {profile.max_concurrent_positions}"
                )

            # Telegram alert
            self._send_telegram_alert(message)

            # UI alert (write to file for UI to pick up)
            self._write_ui_alert(new_mode, reason, message)

        except Exception as e:
            self.logger.error(f"Failed to send alerts: {e}")

    def _send_telegram_alert(self, message: str):
        """Send Telegram alert"""
        try:
            telegram_enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
            if not telegram_enabled:
                return

            # Write to alert file (actual Telegram integration would go here)
            alert_file = Path("shared_data/alerts/telegram_alert.log")
            alert_file.parent.mkdir(parents=True, exist_ok=True)

            with open(alert_file, 'a', encoding='utf-8') as f:
                f.write(f"{to_iso8601_kst()} | {message}\n")

            self.logger.info(f"Telegram alert logged: {message}")

        except Exception as e:
            self.logger.error(f"Failed to send Telegram alert: {e}")

    def _write_ui_alert(self, mode: str, reason: str, message: str):
        """Write UI alert to file"""
        try:
            alert_file = Path("shared_data/alerts/ui_alert.json")
            alert_file.parent.mkdir(parents=True, exist_ok=True)

            alert = {
                "timestamp": to_iso8601_kst(),
                "mode": mode,
                "reason": reason,
                "message": message,
                "sticky": True
            }

            with open(alert_file, 'w', encoding='utf-8') as f:
                json.dump(alert, f, indent=2)

            self.logger.debug(f"UI alert written: {mode}")

        except Exception as e:
            self.logger.error(f"Failed to write UI alert: {e}")

    def _emit_ui_event(self, mode: str, reason: str):
        """Emit UI bus event"""
        try:
            event_file = Path("shared_data/events/risk_mode_change.json")
            event_file.parent.mkdir(parents=True, exist_ok=True)

            event = {
                "event": "RISK_MODE_CHANGE",
                "timestamp": time.time(),
                "mode": mode,
                "reason": reason,
            }

            with open(event_file, 'w', encoding='utf-8') as f:
                json.dump(event, f, indent=2)

            self.logger.debug(f"UI event emitted: RISK_MODE_CHANGE to {mode}")

        except Exception as e:
            self.logger.error(f"Failed to emit UI event: {e}")

    def register_callback(self, callback: Callable):
        """Register callback for mode switch events"""
        self.on_mode_switch_callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Get risk mode manager status"""
        try:
            state = self.risk_store.get_risk_state()
            profile = self.profile_manager.get_current_profile()

            return {
                "current_mode": state.current_mode,
                "auto_switch_enabled": self.auto_switch_enabled,
                "return_policy": self.return_policy,
                "last_switch_reason": state.last_switch_reason,
                "last_switch_ts": state.last_switch_ts,
                "consecutive_losses": state.consecutive_losses,
                "intraday_pnl_pct": state.intraday_pnl_pct,
                "day_open_equity": state.day_open_equity,
                "profile": {
                    "name": profile.name if profile else "UNKNOWN",
                    "daily_loss_limit_pct": profile.daily_loss_limit_pct if profile else 0,
                    "max_concurrent_positions": profile.max_concurrent_positions if profile else 0,
                },
                "triggers": {
                    "consecutive_loss_trigger": self.consecutive_loss_trigger,
                    "intraday_drawdown_trigger_pct": self.intraday_drawdown_trigger_pct,
                    "hard_cutoff_daily_loss_pct": self.hard_cutoff_daily_loss_pct,
                },
                "recent_triggers": [asdict(t) for t in list(self.triggers_fired)[-5:]],
            }

        except Exception as e:
            self.logger.error(f"Failed to get status: {e}")
            return {}


# Global instance
_global_risk_mode_manager: Optional[RiskModeManager] = None


def get_risk_mode_manager() -> RiskModeManager:
    """Get global risk mode manager"""
    global _global_risk_mode_manager
    if _global_risk_mode_manager is None:
        _global_risk_mode_manager = RiskModeManager()
    return _global_risk_mode_manager
