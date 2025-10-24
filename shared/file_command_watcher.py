#!/usr/bin/env python3
"""
File-Based Command Watcher
Services watch shared_data/ops/ for command files and act on them
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

class FileCommandWatcher:
    """Watch for file-based commands in shared_data/ops/"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.ops_dir = Path("shared_data/ops")
        self.failed_dir = self.ops_dir / "failed"
        self.ops_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        
        # Command handlers
        self.handlers: Dict[str, Callable[[Dict[str, Any]], bool]] = {}
        
        # Register default handlers
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register default command handlers"""
        self.handlers["riskoff"] = self._handle_riskoff
        self.handlers["riskon"] = self._handle_riskon
        self.handlers["profile.set"] = self._handle_profile_set
        self.handlers["canary.set"] = self._handle_canary_set
        self.handlers["whitelist.add"] = self._handle_whitelist_add
        self.handlers["whitelist.rm"] = self._handle_whitelist_rm
    
    def register_handler(self, op: str, handler: Callable[[Dict[str, Any]], bool]):
        """Register a custom command handler"""
        self.handlers[op] = handler
    
    def _handle_riskoff(self, cmd_data: Dict[str, Any]) -> bool:
        """Handle riskoff command"""
        try:
            cb_file = Path("shared_data/circuit_breaker.json")
            cb_data = {
                "active": True,
                "reason": "FILE_COMMAND",
                "activated_at": time.time(),
                "timestamp": time.time(),
                "until": time.time() + 3600  # 1 hour auto-reset
            }
            
            with open(cb_file, "w", encoding="utf-8") as f:
                json.dump(cb_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[{self.service_name}] Circuit breaker activated via file command")
            return True
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to handle riskoff: {e}")
            return False
    
    def _handle_riskon(self, cmd_data: Dict[str, Any]) -> bool:
        """Handle riskon command"""
        try:
            cb_file = Path("shared_data/circuit_breaker.json")
            cb_data = {
                "active": False,
                "reason": "FILE_COMMAND_RESET",
                "deactivated_at": time.time(),
                "timestamp": time.time()
            }
            
            with open(cb_file, "w", encoding="utf-8") as f:
                json.dump(cb_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[{self.service_name}] Circuit breaker deactivated via file command")
            return True
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to handle riskon: {e}")
            return False
    
    def _handle_profile_set(self, cmd_data: Dict[str, Any]) -> bool:
        """Handle profile.set command"""
        try:
            profile = cmd_data.get("value")
            if profile not in ["conservative", "balanced", "aggressive"]:
                logger.error(f"[{self.service_name}] Invalid profile: {profile}")
                return False
            
            # Update environment variable for next restart
            # Note: This requires service restart to take effect
            profile_file = Path("shared_data/current_risk_profile.json")
            profile_data = {
                "profile": profile,
                "set_at": time.time(),
                "set_by": "file_command"
            }
            
            with open(profile_file, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[{self.service_name}] Risk profile set to {profile} via file command")
            return True
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to handle profile.set: {e}")
            return False
    
    def _handle_canary_set(self, cmd_data: Dict[str, Any]) -> bool:
        """Handle canary.set command"""
        try:
            value = cmd_data.get("value", False)
            
            # Update canary mode setting
            canary_file = Path("shared_data/canary_mode.json")
            canary_data = {
                "enabled": value,
                "set_at": time.time(),
                "set_by": "file_command"
            }
            
            with open(canary_file, "w", encoding="utf-8") as f:
                json.dump(canary_data, f, indent=2, ensure_ascii=False)
            
            status = "enabled" if value else "disabled"
            logger.info(f"[{self.service_name}] Canary mode {status} via file command")
            return True
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to handle canary.set: {e}")
            return False
    
    def _handle_whitelist_add(self, cmd_data: Dict[str, Any]) -> bool:
        """Handle whitelist.add command"""
        try:
            symbol = cmd_data.get("symbol", "").upper()
            if not symbol:
                logger.error(f"[{self.service_name}] No symbol provided for whitelist.add")
                return False
            
            # Update whitelist
            whitelist_file = Path("shared_data/whitelist_commands.json")
            whitelist_data = {"add": symbol, "timestamp": time.time()}
            
            with open(whitelist_file, "w", encoding="utf-8") as f:
                json.dump(whitelist_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[{self.service_name}] Added {symbol} to whitelist via file command")
            return True
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to handle whitelist.add: {e}")
            return False
    
    def _handle_whitelist_rm(self, cmd_data: Dict[str, Any]) -> bool:
        """Handle whitelist.rm command"""
        try:
            symbol = cmd_data.get("symbol", "").upper()
            if not symbol:
                logger.error(f"[{self.service_name}] No symbol provided for whitelist.rm")
                return False
            
            # Update whitelist
            whitelist_file = Path("shared_data/whitelist_commands.json")
            whitelist_data = {"remove": symbol, "timestamp": time.time()}
            
            with open(whitelist_file, "w", encoding="utf-8") as f:
                json.dump(whitelist_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[{self.service_name}] Removed {symbol} from whitelist via file command")
            return True
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to handle whitelist.rm: {e}")
            return False
    
    def _move_to_failed(self, cmd_file: Path, reason: str):
        """Move failed command file to failed directory"""
        try:
            failed_file = self.failed_dir / f"{cmd_file.name}.failed"
            cmd_file.rename(failed_file)
            
            # Write reason file
            reason_file = self.failed_dir / f"{cmd_file.name}.reason.txt"
            with open(reason_file, "w", encoding="utf-8") as f:
                f.write(f"Failed at: {time.time()}\n")
                f.write(f"Service: {self.service_name}\n")
                f.write(f"Reason: {reason}\n")
            
            logger.warning(f"[{self.service_name}] Command file moved to failed: {cmd_file.name}")
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to move command to failed: {e}")
    
    def process_command_file(self, cmd_file: Path) -> bool:
        """Process a single command file"""
        try:
            # Read command file
            with open(cmd_file, "r", encoding="utf-8") as f:
                cmd_data = json.load(f)
            
            op = cmd_data.get("op")
            if not op:
                self._move_to_failed(cmd_file, "Missing 'op' field")
                return False
            
            # Find handler
            handler = self.handlers.get(op)
            if not handler:
                self._move_to_failed(cmd_file, f"Unknown operation: {op}")
                return False
            
            # Execute handler
            success = handler(cmd_data)
            if success:
                # Delete command file on success
                cmd_file.unlink()
                logger.info(f"[{self.service_name}] Command {op} executed successfully")
                return True
            else:
                self._move_to_failed(cmd_file, f"Handler execution failed for {op}")
                return False
                
        except json.JSONDecodeError as e:
            self._move_to_failed(cmd_file, f"Invalid JSON: {e}")
            return False
        except Exception as e:
            self._move_to_failed(cmd_file, f"Unexpected error: {e}")
            return False
    
    def check_for_commands(self) -> int:
        """Check for and process command files"""
        try:
            processed_count = 0
            
            # Look for command files
            for cmd_file in self.ops_dir.glob("*.json"):
                if cmd_file.is_file():
                    if self.process_command_file(cmd_file):
                        processed_count += 1
            
            return processed_count
            
        except Exception as e:
            logger.error(f"[{self.service_name}] Error checking for commands: {e}")
            return 0
    
    def start_watching(self, check_interval: float = 5.0):
        """Start watching for command files (blocking)"""
        logger.info(f"[{self.service_name}] Starting file command watcher (interval: {check_interval}s)")
        
        while True:
            try:
                processed = self.check_for_commands()
                if processed > 0:
                    logger.info(f"[{self.service_name}] Processed {processed} command(s)")
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info(f"[{self.service_name}] File command watcher stopped")
                break
            except Exception as e:
                logger.error(f"[{self.service_name}] Watcher error: {e}")
                time.sleep(check_interval)

# Global instances for different services
_watchers: Dict[str, FileCommandWatcher] = {}

def get_watcher(service_name: str) -> FileCommandWatcher:
    """Get or create a file command watcher for a service"""
    if service_name not in _watchers:
        _watchers[service_name] = FileCommandWatcher(service_name)
    return _watchers[service_name]

def check_commands(service_name: str) -> int:
    """Check for commands for a specific service"""
    watcher = get_watcher(service_name)
    return watcher.check_for_commands()
