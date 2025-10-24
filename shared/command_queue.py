"""
Command Queue System for Decoupled UI Actions

This module implements a command queue system that allows the UI to enqueue
commands without directly executing them, preventing unintended service restarts
during UI refreshes.
"""

import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta


@dataclass
class Command:
    """Command structure for the queue system"""
    id: str
    origin: str = 'ui'
    action: str = ''
    args: Dict[str, Any] = None
    created_at: float = 0.0
    idempotency_key: str = ''
    expires_at: float = 0.0
    status: str = 'pending'  # pending, processing, completed, failed, expired
    processed_at: Optional[float] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.args is None:
            self.args = {}
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 3600  # 1 hour default expiry


class CommandQueue:
    """Thread-safe command queue with idempotency and cooldown support"""
    
    def __init__(self, queue_path: str = "shared_data/commands.jsonl"):
        self.queue_path = Path(queue_path)
        self.queue_path.parent.mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self._cooldowns = {}  # Track cooldowns by idempotency key
        
        # Configuration
        self.trader_restart_cooldown = int(os.getenv('TRADER_RESTART_MIN_INTERVAL', '300'))
        self.feeder_restart_cooldown = int(os.getenv('FEEDER_RESTART_MIN_INTERVAL', '180'))
    
    def _generate_idempotency_key(self, action: str, args: Dict[str, Any], target_spec_hash: str = '') -> str:
        """Generate idempotency key from action and normalized args"""
        normalized_args = {k: v for k, v in sorted(args.items())}
        key_data = f"{action}:{json.dumps(normalized_args, sort_keys=True)}:{target_spec_hash}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    def _check_cooldown(self, idempotency_key: str, action: str) -> bool:
        """Check if action is within cooldown period"""
        if idempotency_key not in self._cooldowns:
            return False
            
        last_execution = self._cooldowns[idempotency_key]
        cooldown_duration = self._get_cooldown_duration(action)
        
        return (time.time() - last_execution) < cooldown_duration
    
    def _get_cooldown_duration(self, action: str) -> int:
        """Get cooldown duration for specific action"""
        if 'trader' in action.lower() and 'restart' in action.lower():
            return self.trader_restart_cooldown
        elif 'feeder' in action.lower() and 'restart' in action.lower():
            return self.feeder_restart_cooldown
        else:
            return 60  # Default 1 minute cooldown
    
    def _update_cooldown(self, idempotency_key: str):
        """Update cooldown timestamp for idempotency key"""
        self._cooldowns[idempotency_key] = time.time()
    
    def enqueue(self, action: str, args: Dict[str, Any] = None, 
                target_spec_hash: str = '', origin: str = 'ui') -> str:
        """Enqueue a new command with idempotency check"""
        if args is None:
            args = {}
            
        with self._lock:
            # Generate idempotency key
            idempotency_key = self._generate_idempotency_key(action, args, target_spec_hash)
            
            # Check for duplicate pending commands
            if self._has_pending_command(idempotency_key):
                return f"duplicate_pending_{idempotency_key}"
            
            # Check cooldown
            if self._check_cooldown(idempotency_key, action):
                remaining = self._get_cooldown_duration(action) - (time.time() - self._cooldowns[idempotency_key])
                return f"cooldown_active_{remaining:.0f}s"
            
            # Create command
            command_id = f"{action}_{int(time.time() * 1000)}_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:8]}"
            command = Command(
                id=command_id,
                origin=origin,
                action=action,
                args=args,
                idempotency_key=idempotency_key,
                expires_at=time.time() + 3600  # 1 hour expiry
            )
            
            # Write to queue
            self._write_command(command)
            
            # Update cooldown
            self._update_cooldown(idempotency_key)
            
            return command_id
    
    def _has_pending_command(self, idempotency_key: str) -> bool:
        """Check if there's already a pending command with this idempotency key"""
        if not self.queue_path.exists():
            return False
            
        try:
            with open(self.queue_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd_data = json.loads(line)
                        if (cmd_data.get('idempotency_key') == idempotency_key and 
                            cmd_data.get('status') in ['pending', 'processing']):
                            return True
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
            
        return False
    
    def _write_command(self, command: Command):
        """Write command to queue file atomically"""
        temp_path = self.queue_path.with_suffix('.tmp')
        
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(asdict(command)) + '\n')
            
            # Atomic replace
            temp_path.replace(self.queue_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise e
    
    def get_pending_commands(self) -> List[Command]:
        """Get all pending commands from the queue"""
        if not self.queue_path.exists():
            return []
        
        commands = []
        current_time = time.time()
        
        try:
            with open(self.queue_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd_data = json.loads(line)
                        
                        # Check if expired
                        if cmd_data.get('expires_at', 0) < current_time:
                            cmd_data['status'] = 'expired'
                        
                        if cmd_data.get('status') == 'pending':
                            commands.append(Command(**cmd_data))
                    except (json.JSONDecodeError, TypeError):
                        continue
        except Exception:
            pass
            
        return commands
    
    def mark_processing(self, command_id: str) -> bool:
        """Mark command as processing"""
        return self._update_command_status(command_id, 'processing')
    
    def mark_completed(self, command_id: str) -> bool:
        """Mark command as completed"""
        return self._update_command_status(command_id, 'completed', processed_at=time.time())
    
    def mark_failed(self, command_id: str, error_message: str) -> bool:
        """Mark command as failed"""
        return self._update_command_status(command_id, 'failed', 
                                         processed_at=time.time(), 
                                         error_message=error_message)
    
    def _update_command_status(self, command_id: str, status: str, 
                              processed_at: Optional[float] = None,
                              error_message: Optional[str] = None) -> bool:
        """Update command status in queue file"""
        if not self.queue_path.exists():
            return False
            
        with self._lock:
            temp_path = self.queue_path.with_suffix('.tmp')
            updated = False
            
            try:
                with open(self.queue_path, 'r', encoding='utf-8') as f_in, \
                     open(temp_path, 'w', encoding='utf-8') as f_out:
                    
                    for line in f_in:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            cmd_data = json.loads(line)
                            if cmd_data.get('id') == command_id:
                                cmd_data['status'] = status
                                if processed_at:
                                    cmd_data['processed_at'] = processed_at
                                if error_message:
                                    cmd_data['error_message'] = error_message
                                updated = True
                            
                            f_out.write(json.dumps(cmd_data) + '\n')
                        except json.JSONDecodeError:
                            f_out.write(line + '\n')
                
                if updated:
                    temp_path.replace(self.queue_path)
                else:
                    temp_path.unlink()
                    
            except Exception as e:
                if temp_path.exists():
                    temp_path.unlink()
                raise e
            
            return updated
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue status information"""
        if not self.queue_path.exists():
            return {
                'total_commands': 0,
                'pending_commands': 0,
                'processing_commands': 0,
                'completed_commands': 0,
                'failed_commands': 0,
                'expired_commands': 0,
                'active_cooldowns': len(self._cooldowns)
            }
        
        stats = {
            'total_commands': 0,
            'pending_commands': 0,
            'processing_commands': 0,
            'completed_commands': 0,
            'failed_commands': 0,
            'expired_commands': 0,
            'active_cooldowns': len(self._cooldowns)
        }
        
        current_time = time.time()
        
        try:
            with open(self.queue_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd_data = json.loads(line)
                        stats['total_commands'] += 1
                        
                        status = cmd_data.get('status', 'unknown')
                        if status == 'pending':
                            stats['pending_commands'] += 1
                        elif status == 'processing':
                            stats['processing_commands'] += 1
                        elif status == 'completed':
                            stats['completed_commands'] += 1
                        elif status == 'failed':
                            stats['failed_commands'] += 1
                        elif status == 'expired':
                            stats['expired_commands'] += 1
                            
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
            
        return stats


# Global command queue instance
_command_queue = None

def get_command_queue() -> CommandQueue:
    """Get global command queue instance"""
    global _command_queue
    if _command_queue is None:
        queue_path = os.getenv('COMMAND_QUEUE_PATH', 'shared_data/commands.jsonl')
        _command_queue = CommandQueue(queue_path)
    return _command_queue


def enqueue_command(action: str, args: Dict[str, Any] = None, 
                   target_spec_hash: str = '', origin: str = 'ui') -> str:
    """Convenience function to enqueue a command"""
    queue = get_command_queue()
    return queue.enqueue(action, args, target_spec_hash, origin)


# Import os at module level
import os
