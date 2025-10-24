#!/usr/bin/env python3
"""
Memory-efficient streaming and chunking system
WebSocket batching and file I/O optimization for CQ_LEAN mode
"""

import os
import asyncio
import time
from typing import Any, Dict, List, Optional, Iterator, AsyncIterator, Callable
from collections import deque
import json

from shared.lean_mode import is_lean, WS_BATCH_SIZE, lean_cache
from shared.lean_json import write_ndjson_lean, read_ndjson_lean, append_ndjson_lean


class LeanStreamProcessor:
    """Memory-efficient stream processor with batching"""
    
    def __init__(self, batch_size: int = None, max_buffer_size: int = None):
        self.batch_size = batch_size or (WS_BATCH_SIZE if is_lean else 50)
        self.max_buffer_size = max_buffer_size or (100 if is_lean else 500)
        self.buffer = deque(maxlen=self.max_buffer_size)
        self.last_flush_time = time.time()
        self.flush_interval = 1.0  # seconds
        
    def add_data(self, data: Any):
        """Add data to buffer"""
        self.buffer.append({
            'data': data,
            'timestamp': time.time()
        })
        
        # Auto-flush if buffer is full or time interval reached
        if len(self.buffer) >= self.batch_size or self._should_flush():
            return self.flush()
        
        return []
    
    def _should_flush(self) -> bool:
        """Check if buffer should be flushed based on time"""
        return time.time() - self.last_flush_time >= self.flush_interval
    
    def flush(self) -> List[Any]:
        """Flush buffer and return batch"""
        if not self.buffer:
            return []
        
        batch = list(self.buffer)
        self.buffer.clear()
        self.last_flush_time = time.time()
        
        return batch
    
    def get_buffer_size(self) -> int:
        """Get current buffer size"""
        return len(self.buffer)


class LeanWebSocketBatcher:
    """WebSocket message batcher for lean mode"""
    
    def __init__(self, batch_size: int = None):
        self.batch_size = batch_size or WS_BATCH_SIZE
        self.message_buffer = []
        self.last_batch_time = time.time()
        self.batch_timeout = 0.1  # 100ms timeout
        
    async def process_message(self, message: str, processor: Callable):
        """Process WebSocket message with batching"""
        try:
            data = json.loads(message)
            self.message_buffer.append(data)
            
            # Process batch if size limit reached or timeout
            if len(self.message_buffer) >= self.batch_size or self._should_process_batch():
                await self._process_batch(processor)
                
        except json.JSONDecodeError as e:
            print(f"WebSocket message decode error: {e}")
    
    def _should_process_batch(self) -> bool:
        """Check if batch should be processed based on timeout"""
        return time.time() - self.last_batch_time >= self.batch_timeout
    
    async def _process_batch(self, processor: Callable):
        """Process current batch"""
        if not self.message_buffer:
            return
        
        batch = self.message_buffer.copy()
        self.message_buffer.clear()
        self.last_batch_time = time.time()
        
        try:
            await processor(batch)
        except Exception as e:
            print(f"Batch processing error: {e}")
    
    async def force_flush(self, processor: Callable):
        """Force process remaining messages"""
        if self.message_buffer:
            await self._process_batch(processor)


class LeanFileStreamer:
    """Memory-efficient file streaming"""
    
    def __init__(self, file_path: str, chunk_size: int = None):
        self.file_path = file_path
        self.chunk_size = chunk_size or (1024 if is_lean else 4096)  # bytes
        self.position = 0
        
    def read_chunk(self) -> Optional[bytes]:
        """Read next chunk from file"""
        try:
            with open(self.file_path, 'rb') as f:
                f.seek(self.position)
                chunk = f.read(self.chunk_size)
                self.position += len(chunk)
                return chunk if chunk else None
        except Exception as e:
            print(f"File chunk read error: {e}")
            return None
    
    def read_lines_chunk(self, max_lines: int = None) -> List[str]:
        """Read lines in chunks"""
        max_lines = max_lines or (10 if is_lean else 100)
        lines = []
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                f.seek(self.position)
                for _ in range(max_lines):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip('\n'))
                    self.position = f.tell()
        except Exception as e:
            print(f"File lines read error: {e}")
        
        return lines


class LeanDataChunker:
    """Memory-efficient data chunking for large datasets"""
    
    def __init__(self, chunk_size: int = None):
        self.chunk_size = chunk_size or (100 if is_lean else 1000)
    
    def chunk_data(self, data: List[Any]) -> Iterator[List[Any]]:
        """Chunk data into smaller pieces"""
        for i in range(0, len(data), self.chunk_size):
            yield data[i:i + self.chunk_size]
    
    def chunk_dict(self, data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Chunk dictionary data"""
        items = list(data.items())
        for chunk_items in self.chunk_data(items):
            yield dict(chunk_items)
    
    def process_chunks(self, data: List[Any], processor: Callable) -> List[Any]:
        """Process data in chunks"""
        results = []
        
        for chunk in self.chunk_data(data):
            try:
                chunk_result = processor(chunk)
                results.extend(chunk_result if isinstance(chunk_result, list) else [chunk_result])
            except Exception as e:
                print(f"Chunk processing error: {e}")
        
        return results


class LeanStreamingWriter:
    """Memory-efficient streaming writer"""
    
    def __init__(self, file_path: str, use_ndjson: bool = None):
        self.file_path = file_path
        self.use_ndjson = use_ndjson if use_ndjson is not None else is_lean
        self.buffer = []
        self.buffer_size = 50 if is_lean else 200
        
    def write(self, data: Any):
        """Write data to buffer"""
        self.buffer.append(data)
        
        # Flush buffer if full
        if len(self.buffer) >= self.buffer_size:
            self.flush()
    
    def flush(self):
        """Flush buffer to file"""
        if not self.buffer:
            return
        
        try:
            if self.use_ndjson:
                write_ndjson_lean(self.file_path, self.buffer)
            else:
                # Regular JSON array
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.buffer, f, ensure_ascii=False, indent=2)
            
            self.buffer.clear()
        except Exception as e:
            print(f"Streaming write error: {e}")
    
    def close(self):
        """Close writer and flush remaining data"""
        self.flush()


class LeanAsyncStreamProcessor:
    """Async stream processor for WebSocket data"""
    
    def __init__(self, batch_size: int = None):
        self.batch_size = batch_size or WS_BATCH_SIZE
        self.processors = {}
        
    def register_processor(self, symbol: str, processor: Callable):
        """Register processor for symbol"""
        self.processors[symbol] = processor
    
    async def process_symbol_data(self, symbol: str, data: List[Any]):
        """Process data for specific symbol"""
        if symbol not in self.processors:
            return
        
        try:
            processor = self.processors[symbol]
            await processor(data)
        except Exception as e:
            print(f"Symbol {symbol} processing error: {e}")
    
    async def process_batch(self, batch: List[Dict[str, Any]]):
        """Process batch of data"""
        # Group by symbol
        symbol_data = {}
        for item in batch:
            symbol = item.get('symbol', 'unknown')
            if symbol not in symbol_data:
                symbol_data[symbol] = []
            symbol_data[symbol].append(item)
        
        # Process each symbol's data
        tasks = []
        for symbol, data in symbol_data.items():
            task = self.process_symbol_data(symbol, data)
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# Global instances
lean_stream_processor = LeanStreamProcessor()
lean_websocket_batcher = LeanWebSocketBatcher()
lean_data_chunker = LeanDataChunker()
lean_async_stream_processor = LeanAsyncStreamProcessor()
