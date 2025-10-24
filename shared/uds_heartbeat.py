#!/usr/bin/env python3
"""
UDS Heartbeat System
Ensures UDS heartbeat is emitted every 3-5 seconds with fallback mechanism
"""
import json
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from .path_registry import get_health_uds_path


class UDSHeartbeatManager:
    """UDS heartbeat manager with fallback mechanism"""
    
    def __init__(self, service_name: str, primary_interval: float = 3.0):
        self.service_name = service_name
        self.primary_interval = primary_interval
        self.uds_path = get_health_uds_path()
        self.running = False
        self.thread = None
        self.last_heartbeat = 0
        
        # Ensure UDS health directory exists
        self.uds_path.parent.mkdir(parents=True, exist_ok=True)
    
    def start(self):
        """Start UDS heartbeat emission with immediate boot heartbeat"""
        if self.running:
            return
        
        # Log resolved absolute UDS path at startup
        print(f"[UDSHeartbeat] Resolved UDS path: {self.uds_path.resolve()}", flush=True)
        
        # Emit boot heartbeat immediately (within 0.5-1.0s)
        self._emit_heartbeat()
        print(f"[UDSHeartbeat] Boot heartbeat emitted at {time.time():.3f}", flush=True)
        
        self.running = True
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.thread.start()
        
        print(f"[UDSHeartbeat] Started {self.service_name} heartbeat every {self.primary_interval}s", flush=True)
    
    def stop(self):
        """Stop UDS heartbeat emission"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        
        print(f"[UDSHeartbeat] Stopped {self.service_name} heartbeat", flush=True)
    
    def _heartbeat_loop(self):
        """Main heartbeat loop"""
        while self.running:
            try:
                self._emit_heartbeat()
                time.sleep(self.primary_interval)
            except Exception as e:
                print(f"[UDSHeartbeat] Error in heartbeat loop: {e}", flush=True)
                time.sleep(self.primary_interval)
    
    def _emit_heartbeat(self):
        """Emit UDS heartbeat with operational logging"""
        try:
            current_time = time.time()
            heartbeat_data = {
                "ts": current_time,
                "source": self.service_name,
                "service_name": self.service_name,
                "heartbeat_interval": self.primary_interval,
                "last_update": current_time
            }
            
            # Atomic write (temp file then rename)
            temp_path = self.uds_path.with_suffix('.tmp')
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(heartbeat_data, f, ensure_ascii=False, indent=2)
            
            # Get file size for logging
            file_size = temp_path.stat().st_size
            
            temp_path.replace(self.uds_path)
            
            self.last_heartbeat = current_time
            
            # Operational log: compact write log (every 10 heartbeats to avoid spam)
            if int(current_time) % (int(self.primary_interval * 10)) < self.primary_interval:
                print(f"WROTE uds_heartbeat path={self.uds_path} age=0s size={file_size}B", flush=True)
                print(f"[UDSHeartbeat] {self.service_name} heartbeat emitted: {current_time:.1f}", flush=True)
            
        except Exception as e:
            print(f"[UDSHeartbeat] Failed to emit heartbeat: {e}", flush=True)
    
    def force_heartbeat(self):
        """Force immediate heartbeat emission"""
        self._emit_heartbeat()


class UDSHeartbeatFallback:
    """Fallback UDS heartbeat when primary source is stale"""
    
    def __init__(self, service_name: str, fallback_threshold: float = 15.0):
        self.service_name = service_name
        self.fallback_threshold = fallback_threshold
        self.uds_path = get_health_uds_path()
        self.last_fallback_check = 0
    
    def check_and_emit_fallback(self) -> bool:
        """Check if fallback heartbeat is needed and emit if so"""
        try:
            current_time = time.time()
            
            # Don't check too frequently
            if current_time - self.last_fallback_check < 5.0:
                return False
            
            self.last_fallback_check = current_time
            
            # Check current UDS age
            if not self.uds_path.exists():
                print(f"[UDSFallback] UDS file missing, emitting fallback from {self.service_name}", flush=True)
                self._emit_fallback_heartbeat(current_time)
                return True
            
            try:
                with open(self.uds_path, 'r', encoding='utf-8') as f:
                    uds_data = json.load(f)
                
                last_ts = uds_data.get('ts', 0)
                uds_age = current_time - last_ts
                
                if uds_age > self.fallback_threshold:
                    print(f"[UDSFallback] UDS stale ({uds_age:.1f}s > {self.fallback_threshold}s), emitting fallback from {self.service_name}", flush=True)
                    self._emit_fallback_heartbeat(current_time)
                    return True
                
            except Exception as e:
                print(f"[UDSFallback] Error reading UDS file: {e}, emitting fallback", flush=True)
                self._emit_fallback_heartbeat(current_time)
                return True
            
            return False
            
        except Exception as e:
            print(f"[UDSFallback] Error in fallback check: {e}", flush=True)
            return False
    
    def _emit_fallback_heartbeat(self, current_time: float):
        """Emit fallback heartbeat"""
        try:
            heartbeat_data = {
                "ts": current_time,
                "source": f"{self.service_name}_fallback",
                "service_name": self.service_name,
                "heartbeat_interval": "fallback",
                "last_update": current_time,
                "fallback_reason": "primary_source_stale"
            }
            
            # Atomic write
            temp_path = self.uds_path.with_suffix('.tmp')
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(heartbeat_data, f, ensure_ascii=False, indent=2)
            
            temp_path.replace(self.uds_path)
            
            print(f"[UDSFallback] {self.service_name} fallback heartbeat emitted: {current_time:.1f}", flush=True)
            
        except Exception as e:
            print(f"[UDSFallback] Failed to emit fallback heartbeat: {e}", flush=True)


def normalize_ts(ts_value: float) -> float:
    """
    Normalize timestamp to epoch seconds
    Handles both seconds and milliseconds (≥ 10^12 means milliseconds)
    """
    if ts_value >= 1e12:
        # Looks like milliseconds, convert to seconds
        return ts_value / 1000.0
    return ts_value


def get_uds_age() -> float:
    """Get current UDS age in seconds with strict ts semantics"""
    try:
        uds_path = get_health_uds_path()
        
        if not uds_path.exists():
            return float('inf')
        
        with open(uds_path, 'r', encoding='utf-8') as f:
            uds_data = json.load(f)
        
        # Get ts field with validation
        last_ts = uds_data.get('ts', 0)
        if last_ts <= 0:
            print(f"[UDSHeartbeat] WARN [SCHEMA_TS_MISSING] UDS file has missing/invalid ts", flush=True)
            # Self-correct by rewriting with fresh ts
            uds_data['ts'] = time.time()
            uds_data['source'] = uds_data.get('source', 'corrected')
            
            temp_path = uds_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(uds_data, f, ensure_ascii=False, indent=2)
            temp_path.replace(uds_path)
            
            return 0.0  # Fresh after correction
        
        # Normalize ts (handle milliseconds)
        last_ts = normalize_ts(float(last_ts))
        
        return time.time() - last_ts
        
    except Exception as e:
        print(f"[UDSHeartbeat] Error reading UDS age: {e}", flush=True)
        return float('inf')


def validate_uds_heartbeat() -> Dict[str, Any]:
    """Validate UDS heartbeat and return diagnostic info with strict ts semantics"""
    try:
        uds_path = get_health_uds_path()
        current_time = time.time()
        
        if not uds_path.exists():
            return {
                "status": "missing",
                "age_sec": float('inf'),
                "path": str(uds_path.resolve()),
                "error": "UDS file not found"
            }
        
        with open(uds_path, 'r', encoding='utf-8') as f:
            uds_data = json.load(f)
        
        last_ts_raw = uds_data.get('ts', 0)
        
        if last_ts_raw <= 0:
            return {
                "status": "invalid",
                "age_sec": float('inf'),
                "path": str(uds_path.resolve()),
                "error": "[SCHEMA_TS_MISSING] ts field missing or invalid"
            }
        
        # Normalize ts (handle milliseconds)
        last_ts = normalize_ts(float(last_ts_raw))
        age_sec = current_time - last_ts
        
        return {
            "status": "fresh" if age_sec <= 60 else "stale",
            "age_sec": age_sec,
            "path": str(uds_path.resolve()),
            "source": uds_data.get('source', 'unknown'),
            "last_ts": last_ts,
            "last_ts_raw": last_ts_raw,
            "current_ts": current_time
        }
        
    except Exception as e:
        return {
            "status": "error",
            "age_sec": float('inf'),
            "path": str(get_health_uds_path().resolve()),
            "error": str(e)
        }
