#!/usr/bin/env python3
"""
IO Probe - Lightweight I/O Monitoring for Data Flow Discovery

Provides context managers and helpers to log file I/O operations without
monkey-patching stdlib globally. Logs to NDJSON format for easy analysis.
"""

import os
import sys
import json
import time
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Union, TextIO, BinaryIO, Any, Dict
import inspect


class IOProbe:
    """I/O probe for monitoring file operations"""
    
    def __init__(self, log_file: str = "shared_data/logs/io_probe.ndjson"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
    def _get_caller_info(self) -> Dict[str, str]:
        """Get information about the calling module"""
        try:
            # Get the frame of the caller
            frame = inspect.currentframe()
            # Go up 3 levels: _log_io -> wrapper function -> actual caller
            for _ in range(3):
                frame = frame.f_back
                if frame is None:
                    break
            
            if frame:
                module_name = frame.f_globals.get('__name__', 'unknown')
                filename = frame.f_code.co_filename
                line_number = frame.f_lineno
                function_name = frame.f_code.co_name
                
                return {
                    'caller_module': module_name,
                    'caller_file': os.path.basename(filename),
                    'caller_function': function_name,
                    'caller_line': str(line_number)
                }
        except Exception:
            pass
        
        return {
            'caller_module': 'unknown',
            'caller_file': 'unknown',
            'caller_function': 'unknown',
            'caller_line': '0'
        }
    
    def _log_io(self, action: str, path: str, **kwargs):
        """Log an I/O operation"""
        try:
            abs_path = os.path.abspath(path)
            rel_path = self._get_relative_path(abs_path)
            
            log_entry = {
                'ts': time.time(),
                'action': action,
                'path_abs': abs_path,
                'path_rel': rel_path,
                'rel_to_ssot': self._get_ssot_relative_path(abs_path),
                'pid': os.getpid(),
                'cwd': os.getcwd(),
                **self._get_caller_info(),
                **kwargs
            }
            
            with self._lock:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry) + '\n')
                    
        except Exception as e:
            # Don't let logging errors break the application
            print(f"IO Probe logging error: {e}", file=sys.stderr)
    
    def _get_relative_path(self, abs_path: str) -> str:
        """Get path relative to current working directory"""
        try:
            return os.path.relpath(abs_path, os.getcwd())
        except ValueError:
            return abs_path
    
    def _get_ssot_relative_path(self, abs_path: str) -> str:
        """Get path relative to Single Source of Truth (shared_data)"""
        try:
            # Find shared_data in the path
            parts = Path(abs_path).parts
            if 'shared_data' in parts:
                ssot_index = parts.index('shared_data')
                ssot_parts = parts[ssot_index:]
                return str(Path(*ssot_parts))
            else:
                return abs_path
        except Exception:
            return abs_path
    
    @contextmanager
    def open_file(self, path: Union[str, Path], mode: str = 'r', **kwargs):
        """Context manager for file operations with logging"""
        path_str = str(path)
        self._log_io('open', path_str, mode=mode, **kwargs)
        
        try:
            with open(path_str, mode, **kwargs) as f:
                self._log_io('open_success', path_str, mode=mode)
                yield f
        except Exception as e:
            self._log_io('open_error', path_str, mode=mode, error=str(e))
            raise
        finally:
            self._log_io('close', path_str, mode=mode)
    
    def read_file(self, path: Union[str, Path], **kwargs) -> str:
        """Read file with logging"""
        path_str = str(path)
        self._log_io('read', path_str, **kwargs)
        
        try:
            with open(path_str, 'r', **kwargs) as f:
                content = f.read()
                self._log_io('read_success', path_str, size=len(content))
                return content
        except Exception as e:
            self._log_io('read_error', path_str, error=str(e))
            raise
    
    def write_file(self, path: Union[str, Path], content: str, **kwargs):
        """Write file with logging"""
        path_str = str(path)
        self._log_io('write', path_str, size=len(content), **kwargs)
        
        try:
            with open(path_str, 'w', **kwargs) as f:
                f.write(content)
                self._log_io('write_success', path_str, size=len(content))
        except Exception as e:
            self._log_io('write_error', path_str, error=str(e))
            raise
    
    def append_file(self, path: Union[str, Path], content: str, **kwargs):
        """Append to file with logging"""
        path_str = str(path)
        self._log_io('append', path_str, size=len(content), **kwargs)
        
        try:
            with open(path_str, 'a', **kwargs) as f:
                f.write(content)
                self._log_io('append_success', path_str, size=len(content))
        except Exception as e:
            self._log_io('append_error', path_str, error=str(e))
            raise
    
    def json_load(self, path: Union[str, Path], **kwargs) -> Any:
        """Load JSON file with logging"""
        path_str = str(path)
        self._log_io('json_load', path_str, **kwargs)
        
        try:
            with open(path_str, 'r', **kwargs) as f:
                data = json.load(f)
                self._log_io('json_load_success', path_str, size=len(str(data)))
                return data
        except Exception as e:
            self._log_io('json_load_error', path_str, error=str(e))
            raise
    
    def json_dump(self, path: Union[str, Path], data: Any, **kwargs):
        """Save JSON file with logging"""
        path_str = str(path)
        self._log_io('json_dump', path_str, **kwargs)
        
        try:
            with open(path_str, 'w', **kwargs) as f:
                json.dump(data, f, **kwargs)
                self._log_io('json_dump_success', path_str, size=len(str(data)))
        except Exception as e:
            self._log_io('json_dump_error', path_str, error=str(e))
            raise
    
    def path_exists(self, path: Union[str, Path]) -> bool:
        """Check if path exists with logging"""
        path_str = str(path)
        self._log_io('exists_check', path_str)
        
        try:
            exists = os.path.exists(path_str)
            self._log_io('exists_result', path_str, exists=exists)
            return exists
        except Exception as e:
            self._log_io('exists_error', path_str, error=str(e))
            raise
    
    def listdir(self, path: Union[str, Path]) -> list:
        """List directory contents with logging"""
        path_str = str(path)
        self._log_io('listdir', path_str)
        
        try:
            contents = os.listdir(path_str)
            self._log_io('listdir_success', path_str, count=len(contents))
            return contents
        except Exception as e:
            self._log_io('listdir_error', path_str, error=str(e))
            raise
    
    def mkdir(self, path: Union[str, Path], parents: bool = False, exist_ok: bool = False):
        """Create directory with logging"""
        path_str = str(path)
        self._log_io('mkdir', path_str, parents=parents, exist_ok=exist_ok)
        
        try:
            os.makedirs(path_str, exist_ok=exist_ok) if parents else os.mkdir(path_str)
            self._log_io('mkdir_success', path_str)
        except Exception as e:
            self._log_io('mkdir_error', path_str, error=str(e))
            raise
    
    def remove(self, path: Union[str, Path]):
        """Remove file with logging"""
        path_str = str(path)
        self._log_io('remove', path_str)
        
        try:
            os.remove(path_str)
            self._log_io('remove_success', path_str)
        except Exception as e:
            self._log_io('remove_error', path_str, error=str(e))
            raise


# Global probe instance
_global_probe: Optional[IOProbe] = None


def get_probe() -> IOProbe:
    """Get the global IO probe instance"""
    global _global_probe
    if _global_probe is None:
        _global_probe = IOProbe()
    return _global_probe


def init_probe(log_file: str = "shared_data/logs/io_probe.ndjson") -> IOProbe:
    """Initialize the global IO probe with custom log file"""
    global _global_probe
    _global_probe = IOProbe(log_file)
    return _global_probe


# Convenience functions for quick usage
def probe_open(path: Union[str, Path], mode: str = 'r', **kwargs):
    """Quick file open with probing"""
    return get_probe().open_file(path, mode, **kwargs)


def probe_read(path: Union[str, Path], **kwargs) -> str:
    """Quick file read with probing"""
    return get_probe().read_file(path, **kwargs)


def probe_write(path: Union[str, Path], content: str, **kwargs):
    """Quick file write with probing"""
    get_probe().write_file(path, content, **kwargs)


def probe_json_load(path: Union[str, Path], **kwargs) -> Any:
    """Quick JSON load with probing"""
    return get_probe().json_load(path, **kwargs)


def probe_json_dump(path: Union[str, Path], data: Any, **kwargs):
    """Quick JSON dump with probing"""
    get_probe().json_dump(path, data, **kwargs)


# Example usage and testing
if __name__ == "__main__":
    # Test the IO probe
    probe = IOProbe("test_io_probe.ndjson")
    
    # Test file operations
    test_file = "test_file.txt"
    test_content = "Hello, IO Probe!"
    
    # Write test
    probe.write_file(test_file, test_content)
    
    # Read test
    content = probe.read_file(test_file)
    print(f"Read content: {content}")
    
    # JSON test
    test_data = {"test": "data", "number": 42}
    probe.json_dump("test.json", test_data)
    loaded_data = probe.json_load("test.json")
    print(f"Loaded JSON: {loaded_data}")
    
    # Cleanup
    probe.remove(test_file)
    probe.remove("test.json")
    probe.remove("test_io_probe.ndjson")
    
    print("IO Probe test completed successfully!")
