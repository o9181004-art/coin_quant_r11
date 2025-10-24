#!/usr/bin/env python3
"""
Preflight Guard - Check blocking flags before service start
Provides Resolve & Start functionality with manual_override window
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared.io.jsonio import read_json_nobom, write_json_atomic_nobom


@dataclass
class BlockingFlag:
    """Blocking flag information"""
    file_path: Path
    reason: str
    severity: str  # "critical", "warning"
    created_ts: float
    can_auto_resolve: bool


class PreflightGuard:
    """Preflight checks before service start"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent
        self.shared_data = self.repo_root / "shared_data"
        
        # Manual override state
        self.override_file = self.shared_data / "runtime" / "manual_override.json"
        self.override_file.parent.mkdir(parents=True, exist_ok=True)
        self.override_ttl = 600  # 10 minutes
    
    def check_blocking_flags(self) -> Tuple[bool, List[BlockingFlag]]:
        """
        Check for blocking flags
        
        Returns:
            (is_blocked, list_of_flags)
        """
        flags = []
        
        # Check STOP.TXT
        stop_txt = self.shared_data / "STOP.TXT"
        if stop_txt.exists():
            try:
                content = stop_txt.read_text(encoding='utf-8')
                reason = content.strip() or "Emergency stop activated"
                
                # Get file creation time
                created_ts = stop_txt.stat().st_mtime
                
                flags.append(BlockingFlag(
                    file_path=stop_txt,
                    reason=reason,
                    severity="critical",
                    created_ts=created_ts,
                    can_auto_resolve=True
                ))
            except Exception:
                pass
        
        # Check BLOCK_ALL_RESTARTS.flag
        block_restarts = self.shared_data / "BLOCK_ALL_RESTARTS.flag"
        if block_restarts.exists():
            flags.append(BlockingFlag(
                file_path=block_restarts,
                reason="All restarts blocked (manual safety)",
                severity="critical",
                created_ts=block_restarts.stat().st_mtime,
                can_auto_resolve=True
            ))
        
        # Check feeder_block.flag
        feeder_block = self.shared_data / "feeder_block.flag"
        if feeder_block.exists():
            flags.append(BlockingFlag(
                file_path=feeder_block,
                reason="Feeder explicitly blocked",
                severity="warning",
                created_ts=feeder_block.stat().st_mtime,
                can_auto_resolve=True
            ))
        
        is_blocked = len(flags) > 0
        return is_blocked, flags
    
    def resolve_flags_and_set_override(self, flags: List[BlockingFlag]) -> bool:
        """
        Resolve blocking flags and set manual override
        
        Args:
            flags: List of flags to resolve
        
        Returns:
            True if all flags resolved successfully
        """
        try:
            # Remove all flags
            for flag in flags:
                if flag.can_auto_resolve:
                    try:
                        flag.file_path.unlink()
                        print(f"✅ Removed: {flag.file_path.name}")
                    except Exception as e:
                        print(f"❌ Failed to remove {flag.file_path.name}: {e}")
                        return False
            
            # Set manual override with TTL
            override_data = {
                "active": True,
                "created_ts": time.time(),
                "expires_ts": time.time() + self.override_ttl,
                "ttl_seconds": self.override_ttl,
                "reason": "User manual start - flags resolved",
                "resolved_flags": [str(f.file_path.name) for f in flags]
            }
            
            write_json_atomic_nobom(self.override_file, override_data)
            print(f"✅ Manual override set (TTL: {self.override_ttl}s)")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to resolve flags: {e}")
            return False
    
    def is_manual_override_active(self) -> bool:
        """Check if manual override is active and not expired"""
        try:
            if not self.override_file.exists():
                return False
            
            data = read_json_nobom(self.override_file, {})
            
            if not data.get("active", False):
                return False
            
            expires_ts = data.get("expires_ts", 0)
            if time.time() > expires_ts:
                # Expired
                return False
            
            return True
            
        except Exception:
            return False
    
    def should_block_stop_txt_creation(self) -> bool:
        """
        Check if STOP.TXT creation should be blocked (during manual override)
        
        Returns:
            True if STOP.TXT should NOT be created
        """
        return self.is_manual_override_active()
    
    def get_override_info(self) -> Optional[Dict[str, Any]]:
        """Get manual override info"""
        try:
            if not self.override_file.exists():
                return None
            
            data = read_json_nobom(self.override_file, {})
            
            if not data.get("active", False):
                return None
            
            expires_ts = data.get("expires_ts", 0)
            remaining = max(0, expires_ts - time.time())
            
            return {
                "active": True,
                "remaining_seconds": remaining,
                "reason": data.get("reason", ""),
                "resolved_flags": data.get("resolved_flags", [])
            }
            
        except Exception:
            return None


# Global singleton
_preflight_guard: Optional[PreflightGuard] = None


def get_preflight_guard() -> PreflightGuard:
    """Get global preflight guard singleton"""
    global _preflight_guard
    if _preflight_guard is None:
        _preflight_guard = PreflightGuard()
    return _preflight_guard

