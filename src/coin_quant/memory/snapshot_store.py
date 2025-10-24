"""
Memory Layer - Snapshot Store

Periodic snapshots with delta journal.
"""

import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
from coin_quant.shared.io import atomic_write_json, safe_read_json
from coin_quant.shared.time import utc_now_seconds


class SnapshotStore:
    """Periodic snapshots with delta journal"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.snapshots_dir = data_dir / "snapshots"
        self.deltas_file = data_dir / "deltas.jsonl"
        self.schema_version = "1.0"
        
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    def create_snapshot(self, data: Dict[str, Any], 
                       snapshot_type: str = "full") -> bool:
        """
        Create snapshot.
        
        Args:
            data: Snapshot data
            snapshot_type: Type of snapshot
            
        Returns:
            True if created successfully, False otherwise
        """
        try:
            timestamp = utc_now_seconds()
            snapshot_id = f"{snapshot_type}_{int(timestamp)}"
            
            snapshot = {
                "timestamp": timestamp,
                "schema_version": self.schema_version,
                "snapshot_type": snapshot_type,
                "snapshot_id": snapshot_id,
                "data": data
            }
            
            # Write snapshot file
            snapshot_file = self.snapshots_dir / f"{snapshot_id}.json"
            if not atomic_write_json(snapshot_file, snapshot):
                return False
            
            # Record delta
            delta = {
                "timestamp": timestamp,
                "action": "create_snapshot",
                "snapshot_id": snapshot_id,
                "snapshot_type": snapshot_type
            }
            
            with open(self.deltas_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(delta, ensure_ascii=False) + "\n")
                f.flush()
            
            return True
            
        except Exception as e:
            print(f"Failed to create snapshot: {e}")
            return False
    
    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Get snapshot by ID.
        
        Args:
            snapshot_id: Snapshot ID
            
        Returns:
            Snapshot data or None
        """
        try:
            snapshot_file = self.snapshots_dir / f"{snapshot_id}.json"
            if not snapshot_file.exists():
                return None
            
            return safe_read_json(snapshot_file)
            
        except Exception as e:
            print(f"Failed to get snapshot {snapshot_id}: {e}")
            return None
    
    def get_latest_snapshot(self, snapshot_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get latest snapshot.
        
        Args:
            snapshot_type: Filter by snapshot type
            
        Returns:
            Latest snapshot or None
        """
        try:
            snapshots = []
            
            for snapshot_file in self.snapshots_dir.glob("*.json"):
                try:
                    snapshot = safe_read_json(snapshot_file)
                    if snapshot and snapshot.get("schema_version") == self.schema_version:
                        if snapshot_type and snapshot.get("snapshot_type") != snapshot_type:
                            continue
                        snapshots.append(snapshot)
                except Exception:
                    continue
            
            if not snapshots:
                return None
            
            # Sort by timestamp and return latest
            snapshots.sort(key=lambda x: x.get("timestamp", 0))
            return snapshots[-1]
            
        except Exception as e:
            print(f"Failed to get latest snapshot: {e}")
            return None
    
    def get_deltas(self, since: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Get deltas since timestamp.
        
        Args:
            since: Filter deltas since timestamp
            
        Returns:
            List of deltas
        """
        deltas = []
        
        try:
            if not self.deltas_file.exists():
                return deltas
            
            with open(self.deltas_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        delta = json.loads(line.strip())
                        
                        if since and delta.get("timestamp", 0) < since:
                            continue
                        
                        deltas.append(delta)
                        
                    except json.JSONDecodeError:
                        continue  # Skip invalid lines
            
        except Exception as e:
            print(f"Failed to read deltas: {e}")
        
        return deltas
