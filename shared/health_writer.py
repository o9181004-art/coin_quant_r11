#!/usr/bin/env python3
"""
Health Writer - Windows-safe atomic health file writer
Single-writer policy with cooperative locking and retry logic
"""

import json
import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Configuration
HEALTH_FRESHNESS_S = 120
MAX_RETRY_ATTEMPTS = 8
RETRY_BACKOFF_BASE_MS = 30
RETRY_BACKOFF_MAX_MS = 250
LOCK_TIMEOUT_MS = 250


class HealthWriter:
    """Windows-safe health file writer with single-writer policy"""
    
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            repo_root = Path(__file__).parent.parent.absolute()
        
        self.repo_root = repo_root
        self.health_dir = repo_root / "shared_data" / "health"
        self.health_file = self.health_dir / "health.json"
        self.lock_file = self.health_dir / "health.write.lock"
        
        # Ensure directory exists
        self.health_dir.mkdir(parents=True, exist_ok=True)
        
        # Writer identification
        self.writer_id = f"{os.getpid()}.{int(time.time() * 1000)}"
        self._is_designated_writer = False
        self._lock_acquired = False
        
        # Last good health cache for readers
        self._last_good_health: Optional[Dict[str, Any]] = None
        self._last_good_ts = 0.0
        
        logger.info(f"HealthWriter initialized: writer_id={self.writer_id}")
    
    def set_designated_writer(self, is_designated: bool = True):
        """Set this instance as the designated health writer"""
        self._is_designated_writer = is_designated
        logger.info(f"HealthWriter designated_writer={is_designated}")
    
    def _acquire_lock(self) -> bool:
        """Acquire cooperative lock (non-blocking)"""
        if self._lock_acquired:
            return True
        
        try:
            # Check if lock exists and is recent
            if self.lock_file.exists():
                lock_age = time.time() - self.lock_file.stat().st_mtime
                if lock_age < 5.0:  # Lock is recent, skip
                    logger.debug(f"health_write_skipped reason=lock_held age_s={lock_age:.1f}")
                    return False
            
            # Try to acquire lock
            with open(self.lock_file, 'w') as f:
                f.write(f"{self.writer_id}\n{int(time.time())}\n")
            
            self._lock_acquired = True
            logger.debug(f"health_lock_acquired writer_id={self.writer_id}")
            return True
            
        except Exception as e:
            logger.debug(f"health_lock_failed err={e}")
            return False
    
    def _release_lock(self):
        """Release cooperative lock"""
        if not self._lock_acquired:
            return
        
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
            self._lock_acquired = False
            logger.debug(f"health_lock_released writer_id={self.writer_id}")
        except Exception as e:
            logger.warning(f"health_lock_release_failed err={e}")
    
    def _generate_temp_filename(self) -> str:
        """Generate unique temp filename"""
        monotonic = int(time.time() * 1000000)  # Microsecond precision
        return f"health.{self.writer_id}.{monotonic}.tmp"
    
    def _write_health_atomic(self, health_data: Dict[str, Any]) -> bool:
        """Windows-safe atomic write with retry logic"""
        if not self._is_designated_writer:
            logger.debug("health_write_skipped reason=not_designated_writer")
            return False
        
        if not self._acquire_lock():
            logger.debug("health_write_skipped reason=lock_acquired_failed")
            return False
        
        temp_filename = self._generate_temp_filename()
        temp_file = self.health_dir / temp_filename
        
        try:
            start_time = time.time()
            
            # Compose JSON in memory
            health_data["ts"] = int(time.time() * 1000)  # epoch_ms
            health_data["writer_id"] = self.writer_id
            health_data["write_ts"] = time.time()
            
            json_content = json.dumps(health_data, ensure_ascii=False, indent=2)
            
            # Write to unique temp file
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(json_content)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            # Atomic replace with retry logic
            success = self._atomic_replace_with_retry(temp_file, self.health_file)
            
            if success:
                duration_ms = (time.time() - start_time) * 1000
                logger.info(f"health_write_ok duration_ms={duration_ms:.1f}")
                
                # Update last good health cache
                self._last_good_health = health_data.copy()
                self._last_good_ts = time.time()
                
                return True
            else:
                logger.error("health_write_failed reason=atomic_replace_failed")
                return False
                
        except Exception as e:
            logger.error(f"health_write_error err={e}")
            return False
        finally:
            # Clean up temp file
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass
            
            # Release lock
            self._release_lock()
    
    def _atomic_replace_with_retry(self, temp_file: Path, target_file: Path) -> bool:
        """Atomic replace with Windows-safe retry logic"""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                # Check lock before replace
                if self.lock_file.exists():
                    lock_age = time.time() - self.lock_file.stat().st_mtime
                    if lock_age < 0.1:  # Very recent lock, wait
                        time.sleep(0.01)
                        continue
                
                # Attempt atomic replace
                os.replace(temp_file, target_file)
                logger.debug(f"health_replace_success attempt={attempt + 1}")
                return True
                
            except OSError as e:
                if hasattr(e, 'winerror') and e.winerror == 5:  # WinError 5: Access denied
                    # Calculate jittered backoff
                    backoff_ms = min(
                        RETRY_BACKOFF_BASE_MS * (2 ** attempt),
                        RETRY_BACKOFF_MAX_MS
                    )
                    jitter_ms = random.uniform(0, backoff_ms * 0.1)
                    total_backoff_ms = backoff_ms + jitter_ms
                    
                    logger.warning(
                        f"health_replace_retry attempt={attempt + 1} "
                        f"err=WinError5 backoff_ms={total_backoff_ms:.1f}"
                    )
                    
                    if attempt < MAX_RETRY_ATTEMPTS - 1:
                        time.sleep(total_backoff_ms / 1000.0)
                        continue
                    else:
                        logger.error("health_replace_failed reason=max_retries_exceeded")
                        return False
                else:
                    logger.error(f"health_replace_error err={e}")
                    return False
            except Exception as e:
                logger.error(f"health_replace_unexpected_error err={e}")
                return False
        
        return False
    
    def write_health(self, health_data: Dict[str, Any]) -> bool:
        """Write health data atomically"""
        return self._write_health_atomic(health_data)
    
    def get_last_good_health(self) -> Optional[Dict[str, Any]]:
        """Get last good health data from cache"""
        if self._last_good_health and (time.time() - self._last_good_ts) < HEALTH_FRESHNESS_S:
            return self._last_good_health.copy()
        return None


class HealthReader:
    """Tolerant health file reader with retry logic"""
    
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            repo_root = Path(__file__).parent.parent.absolute()
        
        self.repo_root = repo_root
        self.health_dir = repo_root / "shared_data" / "health"
        self.health_file = self.health_dir / "health.json"
        
        # Last good health cache
        self._last_good_health: Optional[Dict[str, Any]] = None
        self._last_good_ts = 0.0
        
        logger.info("HealthReader initialized")
    
    def _read_with_retry(self) -> Optional[Dict[str, Any]]:
        """Read health file with retry logic"""
        for attempt in range(5):
            try:
                if not self.health_file.exists():
                    logger.debug("health_file_not_found")
                    return None
                
                # Check if file is being written (recent modification)
                file_age = time.time() - self.health_file.stat().st_mtime
                if file_age < 0.1:  # Very recent, might be mid-write
                    if attempt < 4:
                        jitter_ms = random.uniform(20, 40)
                        time.sleep(jitter_ms / 1000.0)
                        continue
                
                # Read file
                with open(self.health_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse JSON
                health_data = json.loads(content)
                
                # Validate required fields
                if "ts" not in health_data:
                    logger.warning("health_read_invalid missing_ts")
                    return None
                
                age_s = (time.time() * 1000 - health_data["ts"]) / 1000.0
                logger.debug(f"health_read_ok age_s={age_s:.1f}")
                
                # Update last good health cache
                self._last_good_health = health_data.copy()
                self._last_good_ts = time.time()
                
                return health_data
                
            except json.JSONDecodeError as e:
                logger.warning(f"health_read_retry attempt={attempt + 1} err=json_decode")
                if attempt < 4:
                    jitter_ms = random.uniform(20, 40)
                    time.sleep(jitter_ms / 1000.0)
                    continue
                else:
                    logger.error("health_read_failed reason=json_decode_failed")
                    return None
                    
            except Exception as e:
                logger.warning(f"health_read_retry attempt={attempt + 1} err={e}")
                if attempt < 4:
                    jitter_ms = random.uniform(20, 40)
                    time.sleep(jitter_ms / 1000.0)
                    continue
                else:
                    logger.error(f"health_read_failed err={e}")
                    return None
        
        return None
    
    def read_health(self) -> Optional[Dict[str, Any]]:
        """Read health data with fallback to last good"""
        health_data = self._read_with_retry()
        
        if health_data is None and self._last_good_health:
            age_s = time.time() - self._last_good_ts
            logger.info(f"health_last_good_used age_s={age_s:.1f}")
            return self._last_good_health.copy()
        
        return health_data
    
    def is_health_fresh(self, health_data: Optional[Dict[str, Any]] = None) -> bool:
        """Check if health data is fresh"""
        if health_data is None:
            health_data = self.read_health()
        
        if health_data is None:
            return False
        
        age_s = (time.time() * 1000 - health_data.get("ts", 0)) / 1000.0
        return age_s <= HEALTH_FRESHNESS_S


# Global instances
_health_writer: Optional[HealthWriter] = None
_health_reader: Optional[HealthReader] = None
_lock = threading.Lock()


def get_health_writer(repo_root: Optional[Path] = None) -> HealthWriter:
    """Get singleton health writer instance"""
    global _health_writer
    with _lock:
        if _health_writer is None:
            _health_writer = HealthWriter(repo_root)
        return _health_writer


def get_health_reader(repo_root: Optional[Path] = None) -> HealthReader:
    """Get singleton health reader instance"""
    global _health_reader
    with _lock:
        if _health_reader is None:
            _health_reader = HealthReader(repo_root)
        return _health_reader


def write_health(health_data: Dict[str, Any], repo_root: Optional[Path] = None) -> bool:
    """Convenience function to write health data"""
    writer = get_health_writer(repo_root)
    return writer.write_health(health_data)


def read_health(repo_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Convenience function to read health data"""
    reader = get_health_reader(repo_root)
    return reader.read_health()
