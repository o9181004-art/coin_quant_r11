#!/usr/bin/env python3
"""
Safe JSON Writer with Queue-Based Single Writer Task
Prevents concurrent JSON corruption by using a single writer task
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WriteRequest:
    """JSON write request"""
    file_path: Path
    data: Dict[str, Any]
    category: str  # "UDS", "DATABUS", "ACCOUNT", etc.


class SafeJSONWriter:
    """Single-task JSON writer with queue"""
    
    def __init__(self, max_queue_size: int = 100):
        self.write_queue: asyncio.Queue[WriteRequest] = asyncio.Queue(maxsize=max_queue_size)
        self.running = False
        self.writer_task: Optional[asyncio.Task] = None
        self.write_stats: Dict[str, int] = {
            "success": 0,
            "failed": 0,
            "schema_invalid": 0
        }
    
    async def start(self):
        """Start the writer task"""
        if self.running:
            return
        
        self.running = True
        self.writer_task = asyncio.create_task(self._writer_loop())
        logger.info("SafeJSONWriter started")
    
    async def stop(self):
        """Stop the writer task"""
        self.running = False
        if self.writer_task:
            self.writer_task.cancel()
            try:
                await self.writer_task
            except asyncio.CancelledError:
                pass
        logger.info("SafeJSONWriter stopped")
    
    async def queue_write(self, file_path: Path, data: Dict[str, Any], category: str = "GENERAL"):
        """Queue a JSON write request"""
        try:
            # Validate schema: ensure 'ts' field is present
            if 'ts' not in data:
                logger.warning(f"[SCHEMA_TS_MISSING] {category} at {file_path} - adding ts field")
                data['ts'] = time.time()
                self.write_stats["schema_invalid"] += 1
            
            request = WriteRequest(file_path=file_path, data=data, category=category)
            
            # Non-blocking put with timeout
            try:
                await asyncio.wait_for(self.write_queue.put(request), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning(f"[IO_WRITE] Write queue full for {category}, dropping oldest")
                # Try to make room by getting one item (will be lost)
                try:
                    self.write_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                await self.write_queue.put(request)
                
        except Exception as e:
            logger.error(f"[IO_WRITE] Failed to queue write for {category}: {e}")
    
    async def _writer_loop(self):
        """Main writer loop - single task processing all writes"""
        logger.info("JSON writer loop started")
        
        while self.running:
            try:
                # Get write request with timeout
                try:
                    request = await asyncio.wait_for(self.write_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # Perform atomic write
                success = await self._atomic_write(request)
                
                if success:
                    self.write_stats["success"] += 1
                else:
                    self.write_stats["failed"] += 1
                    # Retry logic: put back in queue with delay
                    await asyncio.sleep(1.0)
                    try:
                        await asyncio.wait_for(self.write_queue.put(request), timeout=0.5)
                        logger.warning(f"[IO_WRITE] Retrying write for {request.category}")
                    except (asyncio.TimeoutError, asyncio.QueueFull):
                        logger.error(f"[IO_WRITE] Failed to retry {request.category}, dropping")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[IO_WRITE] Writer loop error: {e}")
                await asyncio.sleep(1.0)
        
        logger.info("JSON writer loop stopped")
    
    async def _atomic_write(self, request: WriteRequest) -> bool:
        """Perform atomic JSON write (temp-then-replace)"""
        try:
            # Ensure parent directory exists
            request.file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file
            temp_path = request.file_path.with_suffix('.tmp')
            
            # Use asyncio file I/O (non-blocking)
            json_content = json.dumps(request.data, ensure_ascii=False, indent=2)
            
            # Write synchronously (file I/O is fast enough)
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(json_content)
            
            # Get file size for logging
            file_size = temp_path.stat().st_size
            
            # Atomic replace
            temp_path.replace(request.file_path)
            
            # Compact log
            logger.debug(f"WROTE {request.category} path={request.file_path} age=0s size={file_size}B")
            return True
            
        except Exception as e:
            logger.error(f"[IO_WRITE] Atomic write failed for {request.category} at {request.file_path}: {e}")
            
            # Clean up temp file if it exists
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except:
                pass
            
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get write statistics"""
        return self.write_stats.copy()


# Global instance
_writer: Optional[SafeJSONWriter] = None


async def get_writer() -> SafeJSONWriter:
    """Get or create global writer instance"""
    global _writer
    if _writer is None:
        _writer = SafeJSONWriter()
        await _writer.start()
    return _writer


async def safe_json_write(file_path: Path, data: Dict[str, Any], category: str = "GENERAL"):
    """Queue a safe JSON write"""
    writer = await get_writer()
    await writer.queue_write(file_path, data, category)

