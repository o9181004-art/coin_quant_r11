#!/usr/bin/env python3
"""
UI Adapter with Render Discipline
Ensures adapter never recomputes prices or targets
"""

import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from shared.audit_contract import TradeCandidateV1, ContractStatus

@dataclass
class UISnapshot:
    """UI snapshot with read-only derived values"""
    # Core fields (from candidate)
    symbol: str
    side: str
    entry: float
    target: float
    stop: float
    confidence: float
    net_confidence: float
    risk_reward: float
    
    # Audit fields
    trace_id: str
    status: ContractStatus
    age_sec: float
    target_origin: str
    
    # UI-specific fields (read-only, never fed back to state)
    display_price: str
    display_target: str
    display_stop: str
    display_confidence: str
    display_rr: str
    status_badge: str
    status_color: str
    
    # Derived values (computed once, read-only)
    price_change_pct: float
    target_change_pct: float
    stop_change_pct: float
    risk_amount: float
    reward_amount: float
    
    # UI state
    last_update: float
    pulse_class: str = ""

class UIAdapter:
    """UI adapter with strict render discipline"""
    
    def __init__(self):
        self.last_pulse_time = 0
        self.pulse_duration = 1.0  # 1 second pulse
    
    def create_snapshot(self, candidate: TradeCandidateV1, status: ContractStatus) -> UISnapshot:
        """Create UI snapshot from candidate (read-only derived values)"""
        
        # Core fields (direct from candidate)
        core_fields = {
            "symbol": candidate.symbol,
            "side": candidate.side,
            "entry": candidate.entry,
            "target": candidate.target,
            "stop": candidate.stop,
            "confidence": candidate.confidence,
            "net_confidence": candidate.net_confidence,
            "risk_reward": candidate.risk_reward_ratio,
            "trace_id": candidate.trace_id,
            "status": status,
            "age_sec": candidate.age_sec,
            "target_origin": candidate.target_origin
        }
        
        # UI display fields (formatted, read-only)
        display_fields = self._format_display_fields(candidate)
        
        # Derived values (computed once, read-only)
        derived_fields = self._compute_derived_values(candidate)
        
        # UI state
        ui_state = self._create_ui_state(candidate, status)
        
        # Combine all fields
        snapshot_data = {**core_fields, **display_fields, **derived_fields, **ui_state}
        
        return UISnapshot(**snapshot_data)
    
    def _format_display_fields(self, candidate: TradeCandidateV1) -> Dict[str, str]:
        """Format display fields (read-only)"""
        return {
            "display_price": f"{candidate.entry:,.2f}",
            "display_target": f"{candidate.target:,.2f}",
            "display_stop": f"{candidate.stop:,.2f}",
            "display_confidence": f"{candidate.net_confidence:.1%}",
            "display_rr": f"{candidate.risk_reward_ratio:.2f}",
        }
    
    def _compute_derived_values(self, candidate: TradeCandidateV1) -> Dict[str, float]:
        """Compute derived values (read-only, never fed back to state)"""
        if candidate.side == "buy":
            risk_amount = candidate.entry - candidate.stop
            reward_amount = candidate.target - candidate.entry
            price_change_pct = (candidate.target - candidate.entry) / candidate.entry * 100
            target_change_pct = (candidate.target - candidate.entry) / candidate.entry * 100
            stop_change_pct = (candidate.stop - candidate.entry) / candidate.entry * 100
        else:
            risk_amount = candidate.stop - candidate.entry
            reward_amount = candidate.entry - candidate.target
            price_change_pct = (candidate.entry - candidate.target) / candidate.entry * 100
            target_change_pct = (candidate.entry - candidate.target) / candidate.entry * 100
            stop_change_pct = (candidate.entry - candidate.stop) / candidate.entry * 100
        
        return {
            "price_change_pct": price_change_pct,
            "target_change_pct": target_change_pct,
            "stop_change_pct": stop_change_pct,
            "risk_amount": risk_amount,
            "reward_amount": reward_amount
        }
    
    def _create_ui_state(self, candidate: TradeCandidateV1, status: ContractStatus) -> Dict[str, Any]:
        """Create UI state (badges, colors, pulse)"""
        status_badge, status_color = self._get_status_badge(status, candidate.age_sec)
        pulse_class = self._get_pulse_class()
        
        return {
            "status_badge": status_badge,
            "status_color": status_color,
            "last_update": time.time(),
            "pulse_class": pulse_class
        }
    
    def _get_status_badge(self, status: ContractStatus, age_sec: float) -> tuple[str, str]:
        """Get status badge and color"""
        if status == ContractStatus.OK:
            if age_sec < 5:
                return "🟢 LIVE", "green"
            elif age_sec < 30:
                return "🟡 FRESH", "yellow"
            else:
                return "🟠 STALE", "orange"
        elif status == ContractStatus.STALE:
            return "🔴 STALE_ARES", "red"
        elif status == ContractStatus.BLOCKED_BY_CONTRACT:
            return "🚫 BLOCKED", "red"
        elif status == ContractStatus.BAD_SIGNATURE:
            return "🔒 BAD_SIG", "red"
        elif status == ContractStatus.INVALID_TARGET:
            return "❌ INVALID", "red"
        elif status == ContractStatus.LOW_RR:
            return "⚠️ LOW_RR", "orange"
        else:
            return "❓ UNKNOWN", "gray"
    
    def _get_pulse_class(self) -> str:
        """Get pulse class for number changes"""
        current_time = time.time()
        if current_time - self.last_pulse_time < self.pulse_duration:
            return "pulse"
        else:
            self.last_pulse_time = current_time
            return ""
    
    def update_snapshot(self, snapshot: UISnapshot, candidate: TradeCandidateV1, status: ContractStatus) -> UISnapshot:
        """Update existing snapshot (preserves height stability)"""
        # Create new snapshot
        new_snapshot = self.create_snapshot(candidate, status)
        
        # Preserve height stability by keeping same structure
        # Only update values that changed
        if snapshot.display_price != new_snapshot.display_price:
            new_snapshot.pulse_class = "pulse"
        
        return new_snapshot
    
    def get_card_html(self, snapshot: UISnapshot) -> str:
        """Generate card HTML with height stability"""
        return f"""
        <div class="trading-card {snapshot.pulse_class}" style="height: 200px; border: 1px solid #333; padding: 1rem; margin: 0.5rem; border-radius: 0.5rem;">
            <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                <h3 style="margin: 0; color: #fff;">{snapshot.symbol}</h3>
                <span class="status-badge" style="color: {snapshot.status_color}; font-weight: bold;">{snapshot.status_badge}</span>
            </div>
            
            <div class="card-body" style="margin-top: 1rem;">
                <div class="price-info" style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                    <div>
                        <label style="color: #888; font-size: 0.8rem;">Entry</label>
                        <div class="price {snapshot.pulse_class}" style="color: #fff; font-weight: bold;">{snapshot.display_price}</div>
                    </div>
                    <div>
                        <label style="color: #888; font-size: 0.8rem;">Target</label>
                        <div class="target {snapshot.pulse_class}" style="color: #4CAF50; font-weight: bold;">{snapshot.display_target}</div>
                    </div>
                    <div>
                        <label style="color: #888; font-size: 0.8rem;">Stop</label>
                        <div class="stop {snapshot.pulse_class}" style="color: #F44336; font-weight: bold;">{snapshot.display_stop}</div>
                    </div>
                    <div>
                        <label style="color: #888; font-size: 0.8rem;">RR</label>
                        <div class="rr {snapshot.pulse_class}" style="color: #FF9800; font-weight: bold;">{snapshot.display_rr}</div>
                    </div>
                </div>
                
                <div class="confidence-info" style="margin-top: 1rem;">
                    <label style="color: #888; font-size: 0.8rem;">Net Confidence</label>
                    <div class="confidence {snapshot.pulse_class}" style="color: #2196F3; font-weight: bold;">{snapshot.display_confidence}</div>
                </div>
                
                <div class="audit-info" style="margin-top: 1rem; font-size: 0.7rem; color: #666;">
                    <div>Trace: {snapshot.trace_id[:8]}...</div>
                    <div>Age: {snapshot.age_sec:.1f}s | Origin: {snapshot.target_origin}</div>
                </div>
            </div>
        </div>
        """

# Global instance
ui_adapter = UIAdapter()

def create_ui_snapshot(candidate: TradeCandidateV1, status: ContractStatus) -> UISnapshot:
    """Create UI snapshot (convenience function)"""
    return ui_adapter.create_snapshot(candidate, status)

def get_card_html(snapshot: UISnapshot) -> str:
    """Get card HTML (convenience function)"""
    return ui_adapter.get_card_html(snapshot)
