"""
ARES Data TTL and Purge System
Handles stale ARES data with configurable TTL and daily purge.
"""
import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List


class AresDataManager:
    """ARES data TTL and purge manager"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.ares_dir = self.project_root / "shared_data" / "ares"
        self.ttl_hours = 6  # Files older than 6h are considered stale
        self.purge_hours = 12  # Files older than 12h are purged
        self.last_purge_time = 0
        
    def _get_file_age_hours(self, file_path: Path) -> float:
        """Get file age in hours"""
        try:
            file_age_seconds = time.time() - file_path.stat().st_mtime
            return file_age_seconds / 3600
        except Exception:
            return float('inf')
    
    def is_file_stale(self, file_path: Path) -> bool:
        """Check if ARES file is stale (>6h)"""
        age_hours = self._get_file_age_hours(file_path)
        return age_hours > self.ttl_hours
    
    def load_ares_data(self, symbol: str) -> tuple[Dict[str, Any] | None, bool, str]:
        """Load ARES data with staleness check"""
        file_path = self.ares_dir / f"{symbol.lower()}.json"
        
        if not file_path.exists():
            return None, False, "FILE_MISSING"
        
        if self.is_file_stale(file_path):
            age_hours = self._get_file_age_hours(file_path)
            return None, True, f"STALE: {age_hours:.1f}h > {self.ttl_hours}h"
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, False, "OK"
        except Exception as e:
            return None, False, f"PARSE_ERROR: {str(e)}"
    
    def get_stale_files(self) -> List[tuple[Path, float]]:
        """Get list of stale files with their ages"""
        stale_files = []
        
        if not self.ares_dir.exists():
            return stale_files
        
        for file_path in self.ares_dir.glob("*.json"):
            age_hours = self._get_file_age_hours(file_path)
            if age_hours > self.ttl_hours:
                stale_files.append((file_path, age_hours))
        
        return stale_files
    
    def purge_old_files(self) -> tuple[int, List[str]]:
        """Purge files older than purge_hours"""
        purged_count = 0
        purged_files = []
        
        if not self.ares_dir.exists():
            return purged_count, purged_files
        
        for file_path in self.ares_dir.glob("*.json"):
            age_hours = self._get_file_age_hours(file_path)
            if age_hours > self.purge_hours:
                try:
                    file_path.unlink()
                    purged_count += 1
                    purged_files.append(file_path.name)
                except Exception as e:
                    print(f"[ARES_PURGE] Failed to delete {file_path.name}: {e}")
        
        if purged_count > 0:
            print(f"[ARES_PURGE] Purged {purged_count} files older than {self.purge_hours}h")
        
        return purged_count, purged_files
    
    def should_run_purge(self) -> bool:
        """Check if purge should run (once per day)"""
        now = time.time()
        return now - self.last_purge_time > 86400  # 24 hours
    
    def run_daily_purge_if_needed(self) -> tuple[bool, int]:
        """Run daily purge if needed"""
        if not self.should_run_purge():
            return False, 0
        
        purged_count, _ = self.purge_old_files()
        self.last_purge_time = time.time()
        return True, purged_count
    
    def get_status(self) -> Dict[str, Any]:
        """Get ARES data manager status"""
        stale_files = self.get_stale_files()
        
        return {
            "ttl_hours": self.ttl_hours,
            "purge_hours": self.purge_hours,
            "stale_files_count": len(stale_files),
            "stale_files": [
                {"name": f.name, "age_hours": age_hours}
                for f, age_hours in stale_files
            ],
            "last_purge_time": self.last_purge_time,
            "next_purge_due": self.should_run_purge()
        }


# Global instance
_ares_manager = None

def get_ares_manager() -> AresDataManager:
    """Get singleton ARES manager instance"""
    global _ares_manager
    if _ares_manager is None:
        _ares_manager = AresDataManager()
    return _ares_manager
