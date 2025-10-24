"""
Logging utilities for Coin Quant R11

Centralized logging configuration with structured logging support.
Provides consistent logging across all services.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from .paths import get_logs_dir
from .config import config_manager


class LoggingManager:
    """Logging manager with structured logging support"""
    
    def __init__(self):
        self.logs_dir = get_logs_dir()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._configured_loggers = set()
    
    def setup_logging(self, service_name: str, level: str = "INFO", 
                     log_to_file: bool = True, log_to_console: bool = True) -> logging.Logger:
        """
        Setup logging for a service.
        
        Args:
            service_name: Name of the service
            level: Logging level
            log_to_file: Whether to log to file
            log_to_console: Whether to log to console
            
        Returns:
            Configured logger
        """
        logger = logging.getLogger(service_name)
        
        # Avoid duplicate configuration
        if service_name in self._configured_loggers:
            return logger
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # Set level
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # File handler
        if log_to_file:
            log_file = self.logs_dir / f"{service_name}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
        
        self._configured_loggers.add(service_name)
        return logger
    
    def get_logger(self, service_name: str) -> logging.Logger:
        """
        Get logger for a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Logger instance
        """
        return logging.getLogger(service_name)
    
    def setup_service_logging(self, service_name: str) -> logging.Logger:
        """
        Setup logging for a service with default configuration.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Configured logger
        """
        log_to_file = config_manager.get_cached("log_to_file")
        return self.setup_logging(
            service_name=service_name,
            level="INFO",
            log_to_file=log_to_file,
            log_to_console=True
        )


class StructuredLogger:
    """Structured logger for consistent log formatting"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message with structured data"""
        if kwargs:
            message = f"{message} | {self._format_kwargs(kwargs)}"
        self.logger.info(message)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with structured data"""
        if kwargs:
            message = f"{message} | {self._format_kwargs(kwargs)}"
        self.logger.warning(message)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message with structured data"""
        if kwargs:
            message = f"{message} | {self._format_kwargs(kwargs)}"
        self.logger.error(message)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with structured data"""
        if kwargs:
            message = f"{message} | {self._format_kwargs(kwargs)}"
        self.logger.debug(message)
    
    def _format_kwargs(self, kwargs: dict) -> str:
        """Format keyword arguments for logging"""
        return " ".join(f"{k}={v}" for k, v in kwargs.items())


def get_service_logger(service_name: str) -> logging.Logger:
    """
    Get logger for a service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Logger instance
    """
    logging_manager = LoggingManager()
    return logging_manager.setup_service_logging(service_name)


def get_structured_logger(service_name: str) -> StructuredLogger:
    """
    Get structured logger for a service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        StructuredLogger instance
    """
    logger = get_service_logger(service_name)
    return StructuredLogger(logger)


# Global logging manager instance
logging_manager = LoggingManager()
