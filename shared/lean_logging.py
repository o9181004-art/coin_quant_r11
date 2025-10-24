#!/usr/bin/env python3
"""
Memory-efficient logging system for CQ_LEAN mode
Rotating file handlers and memory-conscious log formatting
"""

import os
import logging
import logging.handlers
from typing import Optional, Dict, Any
from pathlib import Path

from shared.lean_mode import is_lean


class LeanLogFormatter(logging.Formatter):
    """Memory-efficient log formatter"""
    
    def __init__(self):
        if is_lean:
            # Compact format for lean mode
            fmt = "%(asctime)s|%(levelname)s|%(name)s|%(message)s"
        else:
            # Full format for normal mode
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        super().__init__(fmt, datefmt="%H:%M:%S")


class LeanRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Memory-efficient rotating file handler"""
    
    def __init__(self, filename: str, max_bytes: int = None, backup_count: int = None):
        if max_bytes is None:
            max_bytes = 5 * 1024 * 1024 if is_lean else 10 * 1024 * 1024  # 5MB vs 10MB
        
        if backup_count is None:
            backup_count = 3 if is_lean else 5
        
        super().__init__(filename, maxBytes=max_bytes, backupCount=backup_count)
        self.setFormatter(LeanLogFormatter())


def setup_lean_logging(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    console: bool = True
) -> logging.Logger:
    """Setup memory-efficient logging"""
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(LeanLogFormatter())
        logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = LeanRotatingFileHandler(str(log_path))
        logger.addHandler(file_handler)
    
    # Disable debug logs in lean mode
    if is_lean:
        logger.setLevel(logging.INFO)
    
    return logger


def log_memory_efficient(logger: logging.Logger, level: int, message: str, **kwargs):
    """Log message with memory efficiency"""
    
    # Avoid logging large objects
    if is_lean:
        # Log shapes instead of full data
        for key, value in kwargs.items():
            if hasattr(value, 'shape'):
                kwargs[key] = f"shape={value.shape}"
            elif hasattr(value, '__len__') and len(str(value)) > 100:
                kwargs[key] = f"len={len(value)}"
    
    if kwargs:
        message = f"{message} | {kwargs}"
    
    logger.log(level, message)


def log_dataframe_info(logger: logging.Logger, df: Any, name: str = "DataFrame"):
    """Log dataframe information efficiently"""
    if not is_lean:
        return
    
    try:
        if hasattr(df, 'shape'):
            logger.info(f"{name}: shape={df.shape}")
        if hasattr(df, 'memory_usage'):
            memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
            logger.info(f"{name}: memory={memory_mb:.1f}MB")
    except Exception as e:
        logger.warning(f"DataFrame info logging error: {e}")


def log_performance_stats(logger: logging.Logger, stats: Dict[str, Any]):
    """Log performance statistics efficiently"""
    if not is_lean:
        return
    
    # Only log key metrics
    key_metrics = ['memory_mb', 'processing_time', 'records_count', 'error_count']
    
    filtered_stats = {k: v for k, v in stats.items() if k in key_metrics}
    
    if filtered_stats:
        logger.info(f"Performance: {filtered_stats}")


class LeanLoggerAdapter(logging.LoggerAdapter):
    """Memory-efficient logger adapter"""
    
    def __init__(self, logger: logging.Logger, extra: Dict[str, Any] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Process log message for memory efficiency"""
        
        # Remove large objects from kwargs
        if is_lean:
            for key, value in kwargs.items():
                if hasattr(value, '__len__') and len(str(value)) > 200:
                    kwargs[key] = f"<large_object:{type(value).__name__}>"
        
        return msg, kwargs


def get_lean_logger(name: str, **kwargs) -> LeanLoggerAdapter:
    """Get lean logger adapter"""
    logger = setup_lean_logging(name, **kwargs)
    return LeanLoggerAdapter(logger)


# Global lean logger
lean_logger = get_lean_logger("lean_mode", log_file="logs/lean_mode.log")
