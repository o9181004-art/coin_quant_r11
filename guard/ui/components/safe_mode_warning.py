#!/usr/bin/env python3
"""
Safe Mode Warning Component
Confirms Safe mode params are non-zero and surfaces warnings if risk caps block all trades
"""

from typing import Any, Dict, List

import streamlit as st


class SafeModeWarning:
    """Safe mode parameter validation and warning system"""
    
    def __init__(self):
        self.warnings = []
        self.blocking_issues = []
    
    def check_safe_mode_params(self) -> Dict[str, Any]:
        """Check Safe mode parameters for non-zero values"""
        try:
            # Get Safe mode parameters
            safe_params = self._get_safe_mode_params()
            
            # Check for zero or invalid values
            issues = []
            warnings = []
            
            # Check daily loss limit
            daily_loss_limit = safe_params.get("daily_loss_limit_pct", 0)
            if daily_loss_limit <= 0:
                issues.append("Daily loss limit is zero or negative")
            elif daily_loss_limit < 0.5:
                warnings.append(f"Daily loss limit is very low: {daily_loss_limit}%")
            
            # Check trade risk per position
            trade_risk = safe_params.get("trade_risk_per_position_pct", 0)
            if trade_risk <= 0:
                issues.append("Trade risk per position is zero or negative")
            elif trade_risk < 0.1:
                warnings.append(f"Trade risk per position is very low: {trade_risk}%")
            
            # Check volatility target
            vol_target = safe_params.get("vol_target_pct", 0)
            if vol_target <= 0:
                issues.append("Volatility target is zero or negative")
            elif vol_target < 5:
                warnings.append(f"Volatility target is very low: {vol_target}%")
            
            # Check max concurrent positions
            max_positions = safe_params.get("max_concurrent_positions", 0)
            if max_positions <= 0:
                issues.append("Max concurrent positions is zero or negative")
            elif max_positions < 2:
                warnings.append(f"Max concurrent positions is very low: {max_positions}")
            
            # Check if any risk caps would block all trades
            blocking_issues = self._check_risk_caps(safe_params)
            
            return {
                "safe_params": safe_params,
                "issues": issues,
                "warnings": warnings,
                "blocking_issues": blocking_issues,
                "has_blocking": len(blocking_issues) > 0,
                "has_warnings": len(warnings) > 0,
                "has_issues": len(issues) > 0
            }
            
        except Exception as e:
            return {
                "safe_params": {},
                "issues": [f"Failed to check Safe mode params: {e}"],
                "warnings": [],
                "blocking_issues": [],
                "has_blocking": True,
                "has_warnings": False,
                "has_issues": True
            }
    
    def _get_safe_mode_params(self) -> Dict[str, Any]:
        """Get Safe mode parameters from environment/config"""
        import os
        
        return {
            "daily_loss_limit_pct": float(os.getenv("DAILY_LOSS_LIMIT_PCT_SAFE", "1.0")),
            "trade_risk_per_position_pct": float(os.getenv("TRADE_RISK_PER_POSITION_PCT_SAFE", "0.15")),
            "vol_target_pct": float(os.getenv("VOL_TARGET_PCT_SAFE", "15")),
            "max_concurrent_positions": int(os.getenv("MAX_CONCURRENT_POSITIONS_SAFE", "3")),
            "slippage_bps": int(os.getenv("SLIPPAGE_BPS_SAFE", "15")),
            "cooldown_min": int(os.getenv("COOLDOWN_MIN_SAFE", "60"))
        }
    
    def _check_risk_caps(self, safe_params: Dict[str, Any]) -> List[str]:
        """Check if risk caps would block all trades"""
        blocking_issues = []
        
        # Check if position size would be too small to trade
        trade_risk = safe_params.get("trade_risk_per_position_pct", 0)
        if trade_risk < 0.05:  # Less than 0.05% risk per position
            blocking_issues.append(f"Trade risk per position too low ({trade_risk}%) - may block all trades")
        
        # Check if max positions is too low
        max_positions = safe_params.get("max_concurrent_positions", 0)
        if max_positions < 1:
            blocking_issues.append("Max concurrent positions is zero - blocks all trading")
        
        # Check if daily loss limit is too restrictive
        daily_loss_limit = safe_params.get("daily_loss_limit_pct", 0)
        if daily_loss_limit < 0.1:  # Less than 0.1% daily loss limit
            blocking_issues.append(f"Daily loss limit too restrictive ({daily_loss_limit}%) - may block all trades")
        
        # Check if volatility target is too low
        vol_target = safe_params.get("vol_target_pct", 0)
        if vol_target < 2:  # Less than 2% volatility target
            blocking_issues.append(f"Volatility target too low ({vol_target}%) - may block all trades")
        
        return blocking_issues
    
    def render_warnings(self):
        """Render Safe mode warnings"""
        check_result = self.check_safe_mode_params()
        
        # Show blocking issues (critical)
        if check_result["has_blocking"]:
            st.error("🚨 **Safe Mode Blocking Issues**")
            for issue in check_result["blocking_issues"]:
                st.error(f"• {issue}")
            st.caption("These issues may prevent all trading in Safe mode")
        
        # Show parameter issues (critical)
        if check_result["has_issues"]:
            st.error("❌ **Safe Mode Parameter Issues**")
            for issue in check_result["issues"]:
                st.error(f"• {issue}")
        
        # Show warnings (non-critical)
        if check_result["has_warnings"]:
            st.warning("⚠️ **Safe Mode Warnings**")
            for warning in check_result["warnings"]:
                st.warning(f"• {warning}")
        
        # Show current parameters
        if check_result["safe_params"]:
            st.info("📋 **Current Safe Mode Parameters**")
            params = check_result["safe_params"]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Daily Loss Limit", f"{params['daily_loss_limit_pct']}%")
                st.metric("Trade Risk/Position", f"{params['trade_risk_per_position_pct']}%")
                st.metric("Volatility Target", f"{params['vol_target_pct']}%")
            
            with col2:
                st.metric("Max Positions", params['max_concurrent_positions'])
                st.metric("Slippage", f"{params['slippage_bps']} bps")
                st.metric("Cooldown", f"{params['cooldown_min']} min")
        
        # Show overall status
        if not check_result["has_blocking"] and not check_result["has_issues"]:
            if check_result["has_warnings"]:
                st.success("✅ Safe mode parameters are valid (with warnings)")
            else:
                st.success("✅ Safe mode parameters are valid")
        else:
            st.error("❌ Safe mode parameters have issues that may block trading")


def render_safe_mode_warning():
    """Render Safe mode warning component"""
    warning = SafeModeWarning()
    warning.render_warnings()
