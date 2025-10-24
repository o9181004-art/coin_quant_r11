#!/usr/bin/env python3
"""
Memory Drift Guard - Detect Inconsistent Data Flow Patterns

Validates:
- Producer consistency (artifacts only written by declared producers)
- Path consistency (all artifacts remain within SSOT)
- Staleness detection (artifacts not updated within threshold)
"""

import json
import os
import sys
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


# Configure logging
_logger = logging.getLogger('memory_drift_guard')
_logger.setLevel(logging.WARNING)

# Console handler
_console_handler = logging.StreamHandler(sys.stderr)
_console_formatter = logging.Formatter(
    '%(asctime)s - MEMORY_DRIFT - %(levelname)s - %(message)s'
)
_console_handler.setFormatter(_console_formatter)
_logger.addHandler(_console_handler)

# File handler
try:
    _log_dir = Path('logs')
    _log_dir.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.FileHandler(_log_dir / 'memory_drift.log', mode='a')
    _file_handler.setFormatter(_console_formatter)
    _logger.addHandler(_file_handler)
except Exception:
    pass  # If can't create log file, continue without it


class MemoryDriftGuard:
    """Memory drift guard for consistency validation"""
    
    def __init__(self):
        self.project_root = self._find_project_root()
        self.memory_index_path = self.project_root / "memory" / "memory_index.json"
        self.memory_index = {}
        self.load_memory_index()
    
    def _find_project_root(self) -> Path:
        """Find project root by looking for markers"""
        try:
            current = Path(__file__).resolve()
            for parent in current.parents:
                if any((parent / marker).exists() for marker in ['config.env', 'requirements.txt']):
                    return parent
            return current.parent.parent
        except Exception:
            return Path.cwd()
    
    def load_memory_index(self):
        """Load memory index for drift detection"""
        try:
            if self.memory_index_path.exists():
                with open(self.memory_index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.memory_index = data.get('artifacts', {})
        except Exception as e:
            _logger.warning(f"Could not load memory index: {e}")
            self.memory_index = {}
    
    def normalize_path(self, path: str) -> str:
        """Normalize path to be relative to project root"""
        try:
            abs_path = Path(path).resolve()
            rel_path = abs_path.relative_to(self.project_root)
            return str(rel_path).replace('\\', '/')
        except (ValueError, Exception):
            return path.replace('\\', '/')


def validate_producer_consistency(artifact_path: str, current_producer: str) -> bool:
    """
    Validate that artifact is being written by its declared producer
    
    Args:
        artifact_path: Path to artifact being written
        current_producer: Module attempting to write
    
    Returns:
        True if consistent, False if drift detected
    """
    try:
        guard = MemoryDriftGuard()
        norm_path = guard.normalize_path(artifact_path)
        
        # Check if artifact is known
        if norm_path not in guard.memory_index:
            # New artifact - no drift
            return True
        
        artifact = guard.memory_index[norm_path]
        declared_producer = artifact.get('producer', '')
        
        # If no declared producer, accept current
        if not declared_producer:
            return True
        
        # Check if current producer matches declared
        if current_producer != declared_producer:
            _logger.warning(
                f"PRODUCER_DRIFT: Artifact '{norm_path}' "
                f"declared producer: '{declared_producer}', "
                f"current writer: '{current_producer}'"
            )
            return False
        
        return True
        
    except Exception as e:
        _logger.error(f"Error validating producer consistency: {e}")
        return True  # Don't block on validation errors


def validate_path_in_ssot(artifact_path: str) -> bool:
    """
    Validate that artifact path is within SSOT boundaries
    
    Args:
        artifact_path: Path to validate
    
    Returns:
        True if within SSOT, False otherwise
    """
    try:
        guard = MemoryDriftGuard()
        norm_path = guard.normalize_path(artifact_path)
        
        # Check if path starts with shared_data
        if norm_path.startswith('shared_data/') or norm_path.startswith('shared_data\\'):
            return True
        
        # Check if it's a config file (allowed exception)
        if norm_path.startswith('config/') or norm_path.startswith('config\\'):
            return True
        
        _logger.warning(
            f"PATH_DRIFT: Artifact '{norm_path}' is outside SSOT boundaries. "
            f"All data artifacts should be under 'shared_data/'"
        )
        return False
        
    except Exception as e:
        _logger.error(f"Error validating path in SSOT: {e}")
        return True  # Don't block on validation errors


def detect_stale_entries(max_age: float = 3600.0) -> list:
    """
    Detect stale artifacts not updated within max_age seconds
    
    Args:
        max_age: Maximum age in seconds before considering stale
    
    Returns:
        List of stale artifact paths
    """
    try:
        guard = MemoryDriftGuard()
        stale_artifacts = []
        current_time = time.time()
        
        for artifact_path, artifact in guard.memory_index.items():
            updated_at = artifact.get('updated_at', '')
            
            if not updated_at:
                continue
            
            try:
                # Parse ISO timestamp
                if updated_at.endswith('Z'):
                    updated_at = updated_at[:-1]
                
                dt = datetime.fromisoformat(updated_at)
                age = current_time - dt.timestamp()
                
                if age > max_age:
                    stale_artifacts.append({
                        'path': artifact_path,
                        'age': age,
                        'producer': artifact.get('producer', 'unknown'),
                        'updated_at': artifact.get('updated_at', '')
                    })
                    
            except Exception:
                continue
        
        # Log stale artifacts
        if stale_artifacts:
            _logger.warning(
                f"STALE_ARTIFACTS: Found {len(stale_artifacts)} artifacts "
                f"not updated within {max_age}s"
            )
            
            for stale in sorted(stale_artifacts, key=lambda x: x['age'], reverse=True)[:5]:
                _logger.warning(
                    f"  - {stale['path']}: {stale['age']:.1f}s old (producer: {stale['producer']})"
                )
        
        return stale_artifacts
        
    except Exception as e:
        _logger.error(f"Error detecting stale entries: {e}")
        return []


def check_all_consistency():
    """Run all consistency checks"""
    try:
        print("Running memory drift guard checks...")
        
        # Check for stale entries
        stale = detect_stale_entries(max_age=3600.0)
        
        print(f"✓ Stale artifacts: {len(stale)}")
        
        if stale:
            print("\nTop 5 stale artifacts:")
            for artifact in sorted(stale, key=lambda x: x['age'], reverse=True)[:5]:
                print(f"  - {artifact['path']}: {artifact['age']:.1f}s old")
        
        return True
        
    except Exception as e:
        print(f"Error running drift guard checks: {e}")
        return False


# Example usage and testing
if __name__ == "__main__":
    check_all_consistency()

