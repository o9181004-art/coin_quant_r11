"""
SSOT (Single Source of Truth) Path Registry
Centralized path management for all services
"""
import os
from pathlib import Path
import logging

class SSOTPathRegistry:
    """Centralized SSOT path registry"""
    
    def __init__(self):
        self.logger = logging.getLogger("SSOTPathRegistry")
        self._repo_root = None
        self._shared_data_root = None
        self._paths = {}
        self._initialized = False
    
    def initialize(self, repo_root=None, shared_data_root=None):
        """Initialize the path registry"""
        if self._initialized:
            return
        
        # Determine repo root
        if repo_root:
            self._repo_root = Path(repo_root).resolve()
        else:
            # Auto-detect repo root (look for run_dashboard.ps1)
            current = Path(__file__).parent
            while current != current.parent:
                if (current / "run_dashboard.ps1").exists():
                    self._repo_root = current
                    break
                current = current.parent
            
            if not self._repo_root:
                self._repo_root = Path.cwd()
        
        # Determine shared_data root
        if shared_data_root:
            self._shared_data_root = Path(shared_data_root).resolve()
        else:
            self._shared_data_root = self._repo_root / "shared_data"
        
        # Define canonical paths
        self._paths = {
            "repo_root": self._repo_root,
            "shared_data": self._shared_data_root,
            "health": self._shared_data_root / "health",
            "logs": self._repo_root / "logs",
            "account_snapshot": self._shared_data_root / "account_snapshot.json",
            "ares_candidates": self._shared_data_root / "candidates.ndjson",
            "ares_candidates_compat": self._shared_data_root / "ares" / "candidates.ndjson",
            "databus_snapshot": self._shared_data_root / "databus_snapshot.json",
        }
        
        self._initialized = True
        self.logger.info(f"SSOTPathRegistry initialized:")
        self.logger.info(f"  repo_root: {self._repo_root}")
        self.logger.info(f"  shared_data: {self._shared_data_root}")
    
    def get_path(self, key):
        """Get a canonical path by key"""
        if not self._initialized:
            self.initialize()
        
        if key not in self._paths:
            raise ValueError(f"Unknown path key: {key}")
        
        return self._paths[key]
    
    def get_all_paths(self):
        """Get all canonical paths"""
        if not self._initialized:
            self.initialize()
        
        return self._paths.copy()
    
    def get_account_snapshot_path(self):
        """Get the canonical account snapshot path"""
        return self.get_path("account_snapshot")
    
    def get_health_path(self, service_name):
        """Get health file path for a service"""
        health_dir = self.get_path("health")
        return health_dir / f"{service_name}.json"
    
    def print_banner(self, service_name=None):
        """Print SSOT path banner"""
        if not self._initialized:
            self.initialize()
        
        banner = []
        banner.append("=" * 60)
        banner.append("SSOT Path Registry")
        if service_name:
            banner.append(f"Service: {service_name}")
        banner.append("=" * 60)
        
        for key, path in self._paths.items():
            banner.append(f"{key}: {path}")
        
        banner.append("=" * 60)
        
        banner_text = "\n".join(banner)
        print(banner_text)
        self.logger.info(f"SSOT Banner printed:\n{banner_text}")
        
        return banner_text

# Global instance
ssot_registry = SSOTPathRegistry()

# Convenience functions
def get_ssot_path(key):
    """Get a canonical path by key"""
    return ssot_registry.get_path(key)

def get_account_snapshot_path():
    """Get the canonical account snapshot path"""
    return ssot_registry.get_account_snapshot_path()

def print_ssot_banner(service_name=None):
    """Print SSOT path banner"""
    return ssot_registry.print_banner(service_name)

def initialize_ssot_paths(repo_root=None, shared_data_root=None):
    """Initialize SSOT paths"""
    ssot_registry.initialize(repo_root, shared_data_root)
