#!/usr/bin/env python3
"""
Action Queue - Command lifecycle tracking for UI actions
Ensures deterministic start/stop with ACK handshakes
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Literal, Optional

from shared.io.jsonio import read_json_nobom, write_json_atomic_nobom


@dataclass
class ActionCommand:
    """Action command with full lifecycle tracking"""
    id: str
    verb: Literal["start", "stop", "restart"]
    target: Literal["feeder", "trader", "ares", "all"]
    created_ts: float
    created_by: str = "ui"
    
    # Lifecycle timestamps
    started_ts: Optional[float] = None
    finished_ts: Optional[float] = None
    
    # Status tracking
    status: Literal["pending", "running", "succeeded", "failed", "timeout"] = "pending"
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    
    # Result data
    result: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict) -> "ActionCommand":
        """Create from dictionary"""
        return ActionCommand(**data)


class ActionQueue:
    """Thread-safe action queue with persistence"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent
        self.queue_file = self.repo_root / "shared_data" / "runtime" / "action_queue.json"
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.lock = Lock()
        self._load_queue()
    
    def _load_queue(self):
        """Load queue from disk"""
        try:
            data = read_json_nobom(self.queue_file, {"commands": {}, "last_id": None})
            self.commands: Dict[str, ActionCommand] = {
                cmd_id: ActionCommand.from_dict(cmd_data)
                for cmd_id, cmd_data in data.get("commands", {}).items()
            }
            self.last_id = data.get("last_id")
        except Exception as e:
            print(f"Error loading action queue: {e}")
            self.commands = {}
            self.last_id = None
    
    def _save_queue(self):
        """Save queue to disk"""
        try:
            data = {
                "commands": {
                    cmd_id: cmd.to_dict()
                    for cmd_id, cmd in self.commands.items()
                },
                "last_id": self.last_id,
                "last_updated": time.time()
            }
            write_json_atomic_nobom(self.queue_file, data)
        except Exception as e:
            print(f"Error saving action queue: {e}")
    
    def create_command(
        self,
        verb: Literal["start", "stop", "restart"],
        target: Literal["feeder", "trader", "ares", "all"],
        created_by: str = "ui"
    ) -> ActionCommand:
        """Create and enqueue a new command"""
        with self.lock:
            cmd_id = f"{verb}_{target}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            cmd = ActionCommand(
                id=cmd_id,
                verb=verb,
                target=target,
                created_ts=time.time(),
                created_by=created_by
            )
            
            self.commands[cmd_id] = cmd
            self.last_id = cmd_id
            self._save_queue()
            
            return cmd
    
    def get_command(self, cmd_id: str) -> Optional[ActionCommand]:
        """Get command by ID"""
        with self.lock:
            return self.commands.get(cmd_id)
    
    def get_latest_command(self) -> Optional[ActionCommand]:
        """Get the most recent command"""
        with self.lock:
            if not self.last_id:
                return None
            return self.commands.get(self.last_id)
    
    def get_pending_commands(self) -> List[ActionCommand]:
        """Get all pending commands"""
        with self.lock:
            return [
                cmd for cmd in self.commands.values()
                if cmd.status == "pending"
            ]
    
    def update_command(
        self,
        cmd_id: str,
        status: Optional[Literal["pending", "running", "succeeded", "failed", "timeout"]] = None,
        started_ts: Optional[float] = None,
        finished_ts: Optional[float] = None,
        error_code: Optional[str] = None,
        error_detail: Optional[str] = None,
        result: Optional[Dict] = None
    ) -> bool:
        """Update command status"""
        with self.lock:
            if cmd_id not in self.commands:
                return False
            
            cmd = self.commands[cmd_id]
            
            if status is not None:
                cmd.status = status
            if started_ts is not None:
                cmd.started_ts = started_ts
            if finished_ts is not None:
                cmd.finished_ts = finished_ts
            if error_code is not None:
                cmd.error_code = error_code
            if error_detail is not None:
                cmd.error_detail = error_detail
            if result is not None:
                cmd.result = result
            
            self._save_queue()
            return True
    
    def cleanup_old_commands(self, max_age_seconds: float = 3600):
        """Remove commands older than max_age_seconds"""
        with self.lock:
            current_time = time.time()
            to_remove = [
                cmd_id for cmd_id, cmd in self.commands.items()
                if current_time - cmd.created_ts > max_age_seconds
            ]
            
            for cmd_id in to_remove:
                del self.commands[cmd_id]
            
            if to_remove:
                self._save_queue()
            
            return len(to_remove)


# Global singleton
_action_queue: Optional[ActionQueue] = None
_queue_lock = Lock()


def get_action_queue() -> ActionQueue:
    """Get global action queue singleton"""
    global _action_queue
    if _action_queue is None:
        with _queue_lock:
            if _action_queue is None:
                _action_queue = ActionQueue()
    return _action_queue

