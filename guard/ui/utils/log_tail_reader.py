#!/usr/bin/env python3
"""
Bounded, tail-first log reader with caching and pagination support.

Features:
- Reads only the last N lines or M bytes (configurable)
- File-mtime and size-based caching to avoid re-parsing
- Pagination support via offset tokens
- Fail-soft for huge files
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default limits (overridable by env)
DEFAULT_MAX_LINES = int(os.getenv("UI_LOG_MAX_LINES", "1000"))
DEFAULT_MAX_BYTES = int(os.getenv("UI_LOG_MAX_BYTES", "6000000"))  # 6 MB
DEFAULT_LOAD_MORE_STEP = int(os.getenv("UI_LOAD_MORE_STEP", "2000"))


@dataclass
class LogReadResult:
    """Result from log reader"""
    records: List[Dict[str, Any]]
    next_token: Optional[str]  # For pagination
    meta: Dict[str, Any]  # file_size, mtime, line_count_estimate, etc.
    has_more: bool  # True if more records available


class LogTailReader:
    """
    Efficient tail-first log reader with caching.
    
    Usage:
        reader = LogTailReader("shared_data/trades.jsonl")
        result = reader.read(max_lines=1000)
        
        # Load more (older records)
        more_result = reader.read(max_lines=1000, offset_token=result.next_token)
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._cache: Dict[str, Any] = {}
    
    def read(
        self,
        max_lines: Optional[int] = None,
        max_bytes: Optional[int] = None,
        offset_token: Optional[str] = None,
        reverse: bool = True,  # True = newest first
    ) -> LogReadResult:
        """
        Read log file with bounded I/O.
        
        Args:
            max_lines: Maximum number of lines to read
            max_bytes: Maximum bytes to read
            offset_token: Pagination token from previous read
            reverse: If True, return newest records first
            
        Returns:
            LogReadResult with records, pagination, and metadata
        """
        if not self.file_path.exists():
            return LogReadResult(
                records=[],
                next_token=None,
                meta={"error": "file_not_found"},
                has_more=False
            )
        
        # Get file stats for cache key
        file_stat = self.file_path.stat()
        file_size = file_stat.st_size
        file_mtime = file_stat.st_mtime
        
        # Set defaults
        max_lines = max_lines or DEFAULT_MAX_LINES
        max_bytes = max_bytes or DEFAULT_MAX_BYTES
        
        # Check cache
        cache_key = f"{self.file_path}:{file_size}:{file_mtime}:{max_lines}:{offset_token}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Parse offset token
        start_offset = 0
        if offset_token:
            try:
                start_offset = int(offset_token)
            except (ValueError, TypeError):
                start_offset = 0
        
        # Read file (tail mode)
        try:
            if file_size > max_bytes and start_offset == 0:
                # Read only the tail
                records, has_more = self._read_tail(max_lines, max_bytes)
            else:
                # Read with offset
                records, has_more = self._read_with_offset(
                    start_offset, max_lines, max_bytes
                )
            
            # Reverse if needed
            if reverse and records:
                records = list(reversed(records))
            
            # Generate next token
            next_token = None
            if has_more:
                next_token = str(start_offset + len(records))
            
            # Build result
            result = LogReadResult(
                records=records,
                next_token=next_token,
                meta={
                    "file_size": file_size,
                    "file_mtime": file_mtime,
                    "lines_read": len(records),
                    "file_path": str(self.file_path),
                    "capped": file_size > max_bytes
                },
                has_more=has_more
            )
            
            # Cache result
            self._cache[cache_key] = result
            
            return result
            
        except Exception as e:
            return LogReadResult(
                records=[],
                next_token=None,
                meta={"error": str(e), "file_size": file_size},
                has_more=False
            )
    
    def _read_tail(
        self, max_lines: int, max_bytes: int
    ) -> Tuple[List[Dict], bool]:
        """Read last N lines or M bytes from file"""
        records = []
        has_more = False
        
        file_size = self.file_path.stat().st_size
        
        # Determine read start position
        if file_size > max_bytes:
            # Start from (file_size - max_bytes)
            start_pos = file_size - max_bytes
            has_more = True
        else:
            start_pos = 0
        
        with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(start_pos)
            
            # Skip partial line if not at start
            if start_pos > 0:
                f.readline()
            
            # Read lines
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Try to parse as JSON
                try:
                    record = json.loads(line)
                    records.append(record)
                    
                    if len(records) >= max_lines:
                        has_more = True
                        break
                except json.JSONDecodeError:
                    # Not JSON, store as raw text
                    records.append({"_raw": line})
        
        return records, has_more
    
    def _read_with_offset(
        self, start_offset: int, max_lines: int, max_bytes: int
    ) -> Tuple[List[Dict], bool]:
        """Read with line offset (for pagination)"""
        records = []
        has_more = False
        current_line = 0
        bytes_read = 0
        
        with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Skip until offset
                if current_line < start_offset:
                    current_line += 1
                    continue
                
                line = line.strip()
                if not line:
                    current_line += 1
                    continue
                
                # Check byte limit
                bytes_read += len(line.encode('utf-8'))
                if bytes_read > max_bytes:
                    has_more = True
                    break
                
                # Parse line
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError:
                    records.append({"_raw": line})
                
                current_line += 1
                
                # Check line limit
                if len(records) >= max_lines:
                    # Check if there are more lines
                    try:
                        next(f)
                        has_more = True
                    except StopIteration:
                        has_more = False
                    break
        
        return records, has_more
    
    def clear_cache(self):
        """Clear internal cache"""
        self._cache.clear()


# Convenience functions for common use cases

def read_recent_trades(max_lines: int = 100) -> LogReadResult:
    """Read recent trades from logs"""
    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")
    trade_file = f"logs/trading/trading_{today}.jsonl"
    
    reader = LogTailReader(trade_file)
    return reader.read(max_lines=max_lines)


def read_recent_notifications(max_lines: int = 500) -> LogReadResult:
    """Read recent notifications"""
    reader = LogTailReader("logs/notifications.log")
    return reader.read(max_lines=max_lines)


def read_ares_candidates(symbol: str, max_lines: int = 100) -> LogReadResult:
    """Read ARES candidates for a symbol"""
    candidates_file = f"shared_data/ares/{symbol.lower()}_candidates.json"
    reader = LogTailReader(candidates_file)
    return reader.read(max_lines=max_lines)


# Streamlit-specific caching wrapper
def cached_log_read(
    file_path: str,
    max_lines: int = DEFAULT_MAX_LINES,
    ttl: int = 5,
) -> LogReadResult:
    """
    Cached log read with file-mtime key.
    Use this in Streamlit with @st.cache_data.
    
    Args:
        file_path: Path to log file
        max_lines: Maximum lines to read
        ttl: Cache TTL in seconds
        
    Returns:
        LogReadResult
    """
    reader = LogTailReader(file_path)
    return reader.read(max_lines=max_lines)

