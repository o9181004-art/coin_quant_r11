"""
Memory Layer - Event Chain

Append-only events with versioned schema.
"""

import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
from coin_quant.shared.io import atomic_write_json, safe_read_json
from coin_quant.shared.time import utc_now_seconds


class EventChain:
    """Append-only event chain with versioned schema"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.events_file = data_dir / "events.jsonl"
        self.schema_version = "1.0"
        
        # Ensure directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def append_event(self, event_type: str, data: Dict[str, Any], 
                    source: str = "unknown") -> bool:
        """
        Append event to chain.
        
        Args:
            event_type: Type of event
            data: Event data
            source: Source of event
            
        Returns:
            True if appended successfully, False otherwise
        """
        try:
            event = {
                "timestamp": utc_now_seconds(),
                "schema_version": self.schema_version,
                "event_type": event_type,
                "source": source,
                "data": data
            }
            
            # Append to JSONL file
            with open(self.events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                f.flush()
            
            return True
            
        except Exception as e:
            print(f"Failed to append event: {e}")
            return False
    
    def get_events(self, event_type: Optional[str] = None, 
                  since: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Get events from chain.
        
        Args:
            event_type: Filter by event type
            since: Filter events since timestamp
            
        Returns:
            List of events
        """
        events = []
        
        try:
            if not self.events_file.exists():
                return events
            
            with open(self.events_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        
                        # Apply filters
                        if event_type and event.get("event_type") != event_type:
                            continue
                        
                        if since and event.get("timestamp", 0) < since:
                            continue
                        
                        events.append(event)
                        
                    except json.JSONDecodeError:
                        continue  # Skip invalid lines
            
        except Exception as e:
            print(f"Failed to read events: {e}")
        
        return events
    
    def get_latest_event(self, event_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get latest event.
        
        Args:
            event_type: Filter by event type
            
        Returns:
            Latest event or None
        """
        events = self.get_events(event_type)
        return events[-1] if events else None
