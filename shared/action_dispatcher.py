#!/usr/bin/env python3
"""
Action Dispatcher - Always-on worker that processes UI action commands
Runs in background thread, never gated by read-only mode
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Dict, Optional

import psutil

from shared.action_queue import ActionCommand, get_action_queue
from shared.io.jsonio import read_json_nobom, write_json_atomic_nobom
from shared.service_ack import get_ack_manager

logger = logging.getLogger(__name__)


class ActionDispatcher:
    """Always-on action dispatcher"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent
        self.running = False
        self.worker_thread: Optional[Thread] = None
        self.stop_event = Event()
        
        self.queue = get_action_queue()
        self.ack_manager = get_ack_manager()
        
        # Worker state
        self.last_tick_ts = 0
        self.total_commands_processed = 0
        self.status_file = self.repo_root / "shared_data" / "runtime" / "dispatcher_status.json"
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Timeouts
        self.start_timeout = 10.0  # seconds
        self.stop_timeout = 5.0
        self.force_kill_delay = 3.0
    
    def start(self):
        """Start the dispatcher worker"""
        if self.running:
            return
        
        self.running = True
        self.stop_event.clear()
        self.worker_thread = Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        logger.info("Action Dispatcher started")
        self._update_status("RUNNING")
    
    def stop(self):
        """Stop the dispatcher worker"""
        if not self.running:
            return
        
        self.running = False
        self.stop_event.set()
        
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        
        logger.info("Action Dispatcher stopped")
        self._update_status("STOPPED")
    
    def _worker_loop(self):
        """Main worker loop"""
        while self.running and not self.stop_event.is_set():
            try:
                self.last_tick_ts = time.time()
                self._update_status("RUNNING")
                
                # Get pending commands
                pending = self.queue.get_pending_commands()
                
                for cmd in pending:
                    if not self.running:
                        break
                    
                    try:
                        self._process_command(cmd)
                        self.total_commands_processed += 1
                    except Exception as e:
                        logger.error(f"Error processing command {cmd.id}: {e}")
                        self.queue.update_command(
                            cmd.id,
                            status="failed",
                            finished_ts=time.time(),
                            error_code="DISPATCH_ERROR",
                            error_detail=str(e)
                        )
                
                # Cleanup old commands (>1 hour)
                self.queue.cleanup_old_commands(3600)
                
                # Sleep before next iteration
                self.stop_event.wait(timeout=1.0)
                
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(2)
    
    def _process_command(self, cmd: ActionCommand):
        """Process a single command"""
        logger.info(f"Processing: {cmd.verb} {cmd.target} (id: {cmd.id})")
        
        # Mark as running
        self.queue.update_command(cmd.id, status="running", started_ts=time.time())
        
        try:
            if cmd.verb == "start":
                self._handle_start(cmd)
            elif cmd.verb == "stop":
                self._handle_stop(cmd)
            elif cmd.verb == "restart":
                self._handle_restart(cmd)
            else:
                raise ValueError(f"Unknown verb: {cmd.verb}")
            
            # Mark as succeeded
            self.queue.update_command(
                cmd.id,
                status="succeeded",
                finished_ts=time.time()
            )
            
        except Exception as e:
            logger.error(f"Command failed: {cmd.verb} {cmd.target}: {e}")
            self.queue.update_command(
                cmd.id,
                status="failed",
                finished_ts=time.time(),
                error_code="EXECUTION_ERROR",
                error_detail=str(e)
            )
    
    def _handle_start(self, cmd: ActionCommand):
        """Handle start command"""
        if cmd.target == "all":
            # Start in sequence: Feeder → Trader → ARES
            self._start_service("feeder", cmd)
            time.sleep(2)
            self._start_service("trader", cmd)
            time.sleep(2)
            try:
                self._start_service("ares", cmd)
            except Exception as e:
                logger.warning(f"ARES start failed (degraded mode OK): {e}")
        else:
            self._start_service(cmd.target, cmd)
    
    def _handle_stop(self, cmd: ActionCommand):
        """Handle stop command"""
        if cmd.target == "all":
            # Stop in reverse: ARES → Trader → Feeder
            try:
                self._stop_service("ares", cmd)
            except Exception:
                pass
            time.sleep(1)
            self._stop_service("trader", cmd)
            time.sleep(1)
            self._stop_service("feeder", cmd)
        else:
            self._stop_service(cmd.target, cmd)
    
    def _handle_restart(self, cmd: ActionCommand):
        """Handle restart command"""
        self._handle_stop(cmd)
        time.sleep(2)
        self._handle_start(cmd)
    
    def _start_service(self, service: str, cmd: ActionCommand):
        """Start a single service"""
        logger.info(f"Starting {service}...")
        
        # Clean stale PID/lock files
        self._clean_stale_locks(service)
        
        # Mark launch requested in ACK
        self.ack_manager.set_launch_requested(service)
        
        # Get service script path
        script_map = {
            "feeder": "feeder/main.py",
            "trader": "services/trader_service.py",
            "ares": "guard/optimizer/ares_service.py"
        }
        
        script_path = script_map.get(service)
        if not script_path:
            raise ValueError(f"Unknown service: {service}")
        
        # Get current Python interpreter (deterministic)
        python_exe = sys.executable
        
        # Start as background process
        process = subprocess.Popen(
            [python_exe, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(self.repo_root)
        )
        
        # Wait briefly and check if process started
        time.sleep(2)
        
        if process.poll() is not None:
            # Process terminated immediately
            _, stderr = process.communicate()
            raise Exception(f"Process terminated immediately: {stderr[:500]}")
        
        # Store PID
        pid = process.pid
        logger.info(f"{service} started with PID {pid}")
        
        # Wait for ready_ts with timeout
        start_wait = time.time()
        while time.time() - start_wait < self.start_timeout:
            ack = self.ack_manager.get_ack(service)
            if ack.is_ready():
                logger.info(f"{service} confirmed ready: {ack.ready_reason}")
                return
            time.sleep(0.5)
        
        # Timeout - but process may still be initializing
        logger.warning(f"{service} did not confirm ready within {self.start_timeout}s")
        # Don't fail - service may still become ready later
    
    def _stop_service(self, service: str, cmd: ActionCommand):
        """Stop a single service"""
        logger.info(f"Stopping {service}...")
        
        # Mark stop requested in ACK
        self.ack_manager.set_stop_requested(service)
        
        # Get PID
        ack = self.ack_manager.get_ack(service)
        pid = ack.pid
        
        if pid is None:
            # Try to find PID from file
            pid = self._get_pid_from_file(service)
        
        if pid is None:
            logger.warning(f"{service} PID not found, assuming already stopped")
            self.ack_manager.set_stopped(service)
            return
        
        # Check if process exists
        if not psutil.pid_exists(pid):
            logger.warning(f"{service} PID {pid} does not exist")
            self.ack_manager.set_stopped(service)
            self._clean_stale_locks(service)
            return
        
        try:
            process = psutil.Process(pid)
            
            # Send graceful stop signal
            logger.info(f"Sending SIGTERM to {service} (PID {pid})")
            process.send_signal(signal.SIGTERM)
            
            # Wait for stopped_ack_ts
            stop_wait = time.time()
            while time.time() - stop_wait < self.stop_timeout:
                ack = self.ack_manager.get_ack(service)
                if ack.is_stopped():
                    logger.info(f"{service} confirmed stopped")
                    self._clean_stale_locks(service)
                    return
                
                # Check if process already died
                if not psutil.pid_exists(pid):
                    logger.info(f"{service} process terminated")
                    self.ack_manager.set_stopped(service)
                    self._clean_stale_locks(service)
                    return
                
                time.sleep(0.5)
            
            # Timeout - escalate to force kill
            logger.warning(f"{service} did not stop gracefully, force killing")
            time.sleep(self.force_kill_delay)
            
            if psutil.pid_exists(pid):
                process.kill()
                logger.info(f"{service} force killed")
            
            self.ack_manager.set_stopped(service)
            self._clean_stale_locks(service)
            
        except psutil.NoSuchProcess:
            logger.info(f"{service} process already gone")
            self.ack_manager.set_stopped(service)
            self._clean_stale_locks(service)
    
    def _get_pid_from_file(self, service: str) -> Optional[int]:
        """Get PID from PID file"""
        pid_paths = [
            self.repo_root / "shared_data" / f"{service}.pid",
            self.repo_root / "shared_data" / "pids" / f"{service}.pid"
        ]
        
        for pid_path in pid_paths:
            if pid_path.exists():
                try:
                    with open(pid_path, 'r') as f:
                        return int(f.read().strip())
                except Exception:
                    pass
        
        return None
    
    def _clean_stale_locks(self, service: str):
        """Clean stale PID and lock files"""
        logger.info(f"Cleaning stale locks for {service}")
        
        # PID files
        pid_paths = [
            self.repo_root / "shared_data" / f"{service}.pid",
            self.repo_root / "shared_data" / "pids" / f"{service}.pid"
        ]
        
        for pid_path in pid_paths:
            if pid_path.exists():
                try:
                    pid_path.unlink()
                    logger.info(f"Removed stale PID file: {pid_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove {pid_path}: {e}")
        
        # Lock files
        lock_path = self.repo_root / "shared_data" / f"{service}.singleton.lock"
        if lock_path.exists():
            try:
                lock_path.unlink()
                logger.info(f"Removed stale lock file: {lock_path}")
            except Exception as e:
                logger.warning(f"Failed to remove {lock_path}: {e}")
    
    def _update_status(self, status: str):
        """Update dispatcher status file"""
        try:
            status_data = {
                "status": status,
                "last_tick_ts": self.last_tick_ts,
                "total_commands_processed": self.total_commands_processed,
                "uptime_seconds": time.time() - self.last_tick_ts if self.last_tick_ts > 0 else 0
            }
            write_json_atomic_nobom(self.status_file, status_data)
        except Exception as e:
            logger.error(f"Failed to update dispatcher status: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current dispatcher status"""
        try:
            return read_json_nobom(self.status_file, {
                "status": "UNKNOWN",
                "last_tick_ts": 0,
                "total_commands_processed": 0
            })
        except Exception:
            return {"status": "UNKNOWN", "last_tick_ts": 0}


# Global singleton
_dispatcher: Optional[ActionDispatcher] = None
_dispatcher_lock = Lock()


def get_dispatcher() -> ActionDispatcher:
    """Get global dispatcher singleton"""
    global _dispatcher
    if _dispatcher is None:
        with _dispatcher_lock:
            if _dispatcher is None:
                _dispatcher = ActionDispatcher()
    return _dispatcher


def ensure_dispatcher_running():
    """Ensure dispatcher is running (call at UI startup)"""
    dispatcher = get_dispatcher()
    if not dispatcher.running:
        dispatcher.start()
    return dispatcher

