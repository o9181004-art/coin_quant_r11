#!/usr/bin/env python3
"""
Last-Known-Good (LKG) UI Manager
Manages UI module snapshots and recovery
"""

import importlib
import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class LKGManager:
    """Manages Last-Known-Good UI versions"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.lkg_dir = project_root / "shared_data" / "lkg_ui"
        self.lkg_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = project_root / "logs" / "lkg_ui.log"
        self.log_file.parent.mkdir(exist_ok=True)
        
        self.current_module = None
        self.last_good_module = None
        self.error_count = 0
        self.max_errors = 3
    
    def log_event(self, event: str, details: str = ""):
        """Log LKG events"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {event}: {details}\n")
    
    def create_lkg_snapshot(self, module_name: str = "app_impl") -> bool:
        """Create a snapshot of the current working UI module"""
        try:
            # Find the current UI implementation
            ui_files = [
                self.project_root / "app_impl.py",
                self.project_root / "app.py"
            ]
            
            source_file = None
            for ui_file in ui_files:
                if ui_file.exists():
                    source_file = ui_file
                    break
            
            if not source_file:
                self.log_event("SNAPSHOT_FAILED", "No UI file found")
                return False
            
            # Create timestamped snapshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_file = self.lkg_dir / f"{module_name}_{timestamp}.py"
            
            # Copy the file
            shutil.copy2(source_file, snapshot_file)
            
            # Create a symlink to the latest
            latest_link = self.lkg_dir / f"{module_name}_latest.py"
            if latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(snapshot_file.name)
            
            self.log_event("SNAPSHOT_CREATED", f"{snapshot_file.name}")
            return True
            
        except Exception as e:
            self.log_event("SNAPSHOT_ERROR", f"Failed to create snapshot: {e}")
            return False
    
    def restore_lkg(self, module_name: str = "app_impl") -> Optional[Any]:
        """Restore the last known good UI module"""
        try:
            latest_snapshot = self.lkg_dir / f"{module_name}_latest.py"
            if not latest_snapshot.exists():
                self.log_event("RESTORE_FAILED", "No LKG snapshot found")
                return None
            
            # Copy the snapshot back to the main location
            target_file = self.project_root / "app_impl.py"
            shutil.copy2(latest_snapshot, target_file)
            
            # Reload the module
            if "app_impl" in sys.modules:
                importlib.reload(sys.modules["app_impl"])
            
            self.log_event("LKG_RESTORED", f"Restored from {latest_snapshot.name}")
            return sys.modules.get("app_impl")
            
        except Exception as e:
            self.log_event("RESTORE_ERROR", f"Failed to restore LKG: {e}")
            return None
    
    def has_lkg(self, module_name: str = "app_impl") -> bool:
        """Check if LKG snapshot exists"""
        latest_snapshot = self.lkg_dir / f"{module_name}_latest.py"
        return latest_snapshot.exists()
    
    def get_lkg_info(self, module_name: str = "app_impl") -> dict:
        """Get information about the LKG snapshot"""
        latest_snapshot = self.lkg_dir / f"{module_name}_latest.py"
        if not latest_snapshot.exists():
            return {"exists": False}
        
        try:
            stat = latest_snapshot.stat()
            return {
                "exists": True,
                "file": str(latest_snapshot),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "age_hours": (datetime.now().timestamp() - stat.st_mtime) / 3600
            }
        except Exception as e:
            return {"exists": True, "error": str(e)}
    
    def cleanup_old_versions(self, keep_count: int = 5):
        """Clean up old LKG versions, keeping only the most recent ones"""
        try:
            # Find all snapshot files
            snapshot_files = list(self.lkg_dir.glob("app_impl_*.py"))
            snapshot_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove old files
            for old_file in snapshot_files[keep_count:]:
                old_file.unlink()
                self.log_event("CLEANUP", f"Removed old snapshot: {old_file.name}")
            
        except Exception as e:
            self.log_event("CLEANUP_ERROR", f"Failed to cleanup old versions: {e}")
    
    def safe_ui_load(self, module_name: str = "app_impl") -> Optional[Any]:
        """Safely load UI module with LKG fallback"""
        try:
            # Try to load the current module
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
            
            # Test if the module has required functions
            if hasattr(module, 'main'):
                self.current_module = module
                self.last_good_module = module
                self.error_count = 0
                self.log_event("UI_LOADED", f"Successfully loaded {module_name}")
                return module
            else:
                raise AttributeError(f"Module {module_name} missing 'main' function")
                
        except Exception as e:
            self.error_count += 1
            self.log_event("UI_LOAD_ERROR", f"Error {self.error_count}: {e}")
            
            # If we have too many errors, try to restore LKG
            if self.error_count >= self.max_errors and self.has_lkg():
                self.log_event("LKG_ATTEMPT", "Too many errors, attempting LKG restore")
                restored_module = self.restore_lkg()
                if restored_module:
                    return restored_module
            
            # Return last known good module if available
            if self.last_good_module:
                self.log_event("LKG_FALLBACK", "Using last known good module")
                return self.last_good_module
            else:
                raise e
    
    def safe_ui_reload(self, module_name: str = "app_impl") -> Optional[Any]:
        """Safely reload UI module with error handling"""
        try:
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
                self.current_module = module
                self.last_good_module = module
                self.error_count = 0
                self.log_event("UI_RELOADED", f"Successfully reloaded {module_name}")
                return module
            else:
                return self.safe_ui_load(module_name)
                
        except Exception as e:
            self.error_count += 1
            self.log_event("UI_RELOAD_ERROR", f"Error {self.error_count}: {e}")
            
            # Keep using last known good module
            if self.last_good_module:
                self.log_event("LKG_FALLBACK", "Keeping last known good module")
                return self.last_good_module
            else:
                raise e


# Global LKG manager instance
_lkg_manager = None

def get_lkg_manager(project_root: Path = None) -> LKGManager:
    """Get the global LKG manager instance"""
    global _lkg_manager
    if _lkg_manager is None:
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent.parent
        _lkg_manager = LKGManager(project_root)
    return _lkg_manager