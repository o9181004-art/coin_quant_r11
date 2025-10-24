#!/usr/bin/env python3
"""
Risk Mode Store - SSOT for Risk Mode State
Atomic read/write with file locking for risk mode state management
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import os

# Windows 호환성을 위한 fcntl 대체
try:
    import fcntl
except ImportError:
    # Windows에서는 fcntl이 없으므로 threading.Lock 사용
    class MockFcntl:
        LOCK_EX = 2
        LOCK_UN = 8
        
        @staticmethod
        def flock(fd, operation):
            pass  # Windows에서는 무시
    fcntl = MockFcntl()


# KST timezone offset (UTC+9)
KST_OFFSET = 9 * 3600


def get_kst_now() -> datetime:
    """Get current time in KST"""
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(seconds=KST_OFFSET)))


def to_iso8601_kst(dt: datetime = None) -> str:
    """Convert datetime to ISO8601 string in KST"""
    if dt is None:
        dt = get_kst_now()
    return dt.isoformat()


@dataclass
class RiskModeState:
    """Risk mode state data structure"""
    # Current mode
    current_mode: str = "AGGRESSIVE"  # AGGRESSIVE | SAFE

    # Switch tracking
    last_switch_reason: str = ""
    last_switch_ts: str = ""  # ISO8601 KST

    # Loss tracking
    consecutive_losses: int = 0

    # PnL tracking
    intraday_pnl_pct: float = 0.0
    day_open_equity: float = 0.0
    today_realized_pnl: float = 0.0
    drawdown_peak_equity: float = 0.0

    # Metadata
    last_updated: str = ""  # ISO8601 KST
    version: str = "1.0.0"


class RiskModeStore:
    """
    Risk Mode Store - Single Source of Truth for risk mode state

    Features:
    - Atomic read/write with file locking
    - KST timezone support
    - Midnight reset handling
    - Thread-safe operations
    """

    def __init__(self, state_file: str = "shared_data/state_bus.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()

        # Initialize state
        self._ensure_risk_state_exists()

    def _ensure_risk_state_exists(self):
        """Ensure risk state exists in state_bus.json"""
        try:
            with self._lock:
                if not self.state_file.exists():
                    # Create new state file with risk section
                    initial_state = {
                        "risk": asdict(RiskModeState(
                            last_updated=to_iso8601_kst()
                        )),
                        "version": "1.0.0",
                        "last_updated": time.time()
                    }
                    self._atomic_write(initial_state)
                    self.logger.info("Created new state file with risk section")
                else:
                    # Check if risk section exists
                    state = self._atomic_read()
                    if "risk" not in state:
                        # Add risk section to existing state
                        state["risk"] = asdict(RiskModeState(
                            last_updated=to_iso8601_kst()
                        ))
                        self._atomic_write(state)
                        self.logger.info("Added risk section to existing state file")
        except Exception as e:
            self.logger.error(f"Failed to ensure risk state exists: {e}")

    def _atomic_read(self) -> Dict[str, Any]:
        """Atomic read with file locking"""
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                # Acquire shared lock for reading
                if os.name != 'nt':  # Unix-like systems
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)

                data = json.load(f)

                if os.name != 'nt':
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

                return data
        except FileNotFoundError:
            return {}
        except Exception as e:
            self.logger.error(f"Atomic read failed: {e}")
            return {}

    def _atomic_write(self, data: Dict[str, Any]):
        """Atomic write with file locking"""
        try:
            # Write to temp file first
            temp_file = self.state_file.with_suffix('.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                # Acquire exclusive lock for writing
                if os.name != 'nt':  # Unix-like systems
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

                if os.name != 'nt':
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Atomic rename
            temp_file.replace(self.state_file)

        except Exception as e:
            self.logger.error(f"Atomic write failed: {e}")
            raise

    def get_risk_state(self) -> RiskModeState:
        """Get current risk mode state"""
        try:
            with self._lock:
                state = self._atomic_read()
                risk_data = state.get("risk", {})

                # Convert dict to RiskModeState
                return RiskModeState(**risk_data)
        except Exception as e:
            self.logger.error(f"Failed to get risk state: {e}")
            return RiskModeState()

    def update_risk_state(self, **kwargs) -> bool:
        """Update risk mode state"""
        try:
            with self._lock:
                state = self._atomic_read()

                if "risk" not in state:
                    state["risk"] = asdict(RiskModeState())

                # Update specified fields
                for key, value in kwargs.items():
                    if key in state["risk"]:
                        state["risk"][key] = value

                # Update timestamp
                state["risk"]["last_updated"] = to_iso8601_kst()
                state["last_updated"] = time.time()

                # Write back
                self._atomic_write(state)

                self.logger.debug(f"Updated risk state: {kwargs}")
                return True

        except Exception as e:
            self.logger.error(f"Failed to update risk state: {e}")
            return False

    def switch_mode(self, new_mode: str, reason: str, manual_override: bool = False) -> bool:
        """Switch risk mode"""
        try:
            with self._lock:
                current_state = self.get_risk_state()

                if current_state.current_mode == new_mode:
                    self.logger.info(f"Already in {new_mode} mode, no switch needed")
                    return True

                # Update mode
                updates = {
                    "current_mode": new_mode,
                    "last_switch_reason": reason,
                    "last_switch_ts": to_iso8601_kst()
                }

                success = self.update_risk_state(**updates)

                if success:
                    self.logger.info(
                        f"Risk mode switched: {current_state.current_mode} → {new_mode} "
                        f"(reason: {reason}, manual: {manual_override})"
                    )

                return success

        except Exception as e:
            self.logger.error(f"Failed to switch mode: {e}")
            return False

    def increment_consecutive_losses(self) -> int:
        """Increment consecutive loss counter"""
        try:
            with self._lock:
                current_state = self.get_risk_state()
                new_count = current_state.consecutive_losses + 1

                self.update_risk_state(consecutive_losses=new_count)

                self.logger.info(f"Consecutive losses: {new_count}")
                return new_count

        except Exception as e:
            self.logger.error(f"Failed to increment consecutive losses: {e}")
            return 0

    def reset_consecutive_losses(self) -> bool:
        """Reset consecutive loss counter"""
        try:
            self.update_risk_state(consecutive_losses=0)
            self.logger.info("Consecutive losses reset to 0")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reset consecutive losses: {e}")
            return False

    def update_intraday_pnl(self, current_equity: float) -> float:
        """Update intraday PnL percentage"""
        try:
            with self._lock:
                current_state = self.get_risk_state()

                # Calculate intraday PnL%
                if current_state.day_open_equity > 0:
                    intraday_pnl_pct = (
                        (current_equity - current_state.day_open_equity) /
                        current_state.day_open_equity * 100
                    )
                else:
                    intraday_pnl_pct = 0.0

                # Update drawdown peak
                drawdown_peak = max(current_state.drawdown_peak_equity, current_equity)

                self.update_risk_state(
                    intraday_pnl_pct=intraday_pnl_pct,
                    drawdown_peak_equity=drawdown_peak
                )

                return intraday_pnl_pct

        except Exception as e:
            self.logger.error(f"Failed to update intraday PnL: {e}")
            return 0.0

    def midnight_reset(self, current_equity: float) -> bool:
        """
        Midnight reset (KST 00:00)
        Reset intraday counters and set day_open_equity
        Keep current_mode unchanged
        """
        try:
            with self._lock:
                updates = {
                    "day_open_equity": current_equity,
                    "today_realized_pnl": 0.0,
                    "intraday_pnl_pct": 0.0,
                    "drawdown_peak_equity": current_equity,
                    # Note: consecutive_losses NOT reset (persists across days)
                    # Note: current_mode NOT reset (persists until manual/auto recovery)
                }

                success = self.update_risk_state(**updates)

                if success:
                    self.logger.info(
                        f"Midnight reset completed (KST 00:00): "
                        f"day_open_equity={current_equity:.2f}"
                    )

                return success

        except Exception as e:
            self.logger.error(f"Failed to perform midnight reset: {e}")
            return False

    def get_mode(self) -> str:
        """Get current risk mode"""
        try:
            state = self.get_risk_state()
            return state.current_mode
        except Exception as e:
            self.logger.error(f"Failed to get mode: {e}")
            return "AGGRESSIVE"  # Safe default

    def is_safe_mode(self) -> bool:
        """Check if currently in SAFE mode"""
        return self.get_mode() == "SAFE"

    def is_aggressive_mode(self) -> bool:
        """Check if currently in AGGRESSIVE mode"""
        return self.get_mode() == "AGGRESSIVE"

    def get_summary(self) -> Dict[str, Any]:
        """Get risk mode summary for display"""
        try:
            state = self.get_risk_state()
            return {
                "current_mode": state.current_mode,
                "last_switch_reason": state.last_switch_reason,
                "last_switch_ts": state.last_switch_ts,
                "consecutive_losses": state.consecutive_losses,
                "intraday_pnl_pct": state.intraday_pnl_pct,
                "day_open_equity": state.day_open_equity,
                "today_realized_pnl": state.today_realized_pnl,
                "last_updated": state.last_updated,
            }
        except Exception as e:
            self.logger.error(f"Failed to get summary: {e}")
            return {}


# Global instance
_global_risk_mode_store: Optional[RiskModeStore] = None


def get_risk_mode_store() -> RiskModeStore:
    """Get global risk mode store instance"""
    global _global_risk_mode_store
    if _global_risk_mode_store is None:
        _global_risk_mode_store = RiskModeStore()
    return _global_risk_mode_store


# Convenience functions
def get_current_mode() -> str:
    """Get current risk mode"""
    return get_risk_mode_store().get_mode()


def is_safe_mode() -> bool:
    """Check if in SAFE mode"""
    return get_risk_mode_store().is_safe_mode()


def is_aggressive_mode() -> bool:
    """Check if in AGGRESSIVE mode"""
    return get_risk_mode_store().is_aggressive_mode()


def switch_to_safe(reason: str, manual: bool = False) -> bool:
    """Switch to SAFE mode"""
    return get_risk_mode_store().switch_mode("SAFE", reason, manual)


def switch_to_aggressive(reason: str, manual: bool = False) -> bool:
    """Switch to AGGRESSIVE mode"""
    return get_risk_mode_store().switch_mode("AGGRESSIVE", reason, manual)


# Fix import for timedelta
from datetime import timedelta
from datetime import timezone as tz


def get_kst_now() -> datetime:
    """Get current time in KST"""
    kst = tz(timedelta(hours=9))
    return datetime.now(kst)
