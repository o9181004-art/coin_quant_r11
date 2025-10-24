"""
Preflight Compile Check for UI Safety
Prevents Python parse errors from breaking the trading system
"""

import logging
import os
import py_compile
import sys
import traceback
from pathlib import Path
from typing import Optional, Tuple


# Set up logging for UI build errors
def setup_ui_logging():
    """Setup logging for UI build errors"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / "ui_build_errors.log"
    
    # Create logger
    logger = logging.getLogger("ui_build")
    logger.setLevel(logging.ERROR)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add file handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.ERROR)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    return logger

# Global logger instance
_ui_logger = None

def get_ui_logger():
    """Get UI build logger instance"""
    global _ui_logger
    if _ui_logger is None:
        _ui_logger = setup_ui_logging()
    return _ui_logger


class PreflightCheck:
    """Preflight compile check for UI modules"""
    
    def __init__(self):
        self.logger = get_ui_logger()
    
    def check_module(self, module_path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a Python module compiles without errors
        
        Args:
            module_path: Path to the Python module to check
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            # Convert to Path object
            path = Path(module_path)
            
            if not path.exists():
                error_msg = f"Module file not found: {module_path}"
                self.logger.error(error_msg)
                return False, error_msg
            
            # Try to compile the module
            py_compile.compile(str(path), doraise=True)
            
            return True, None
            
        except py_compile.PyCompileError as e:
            error_msg = f"Compile error in {module_path}: {e}"
            self.logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error checking {module_path}: {e}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            return False, error_msg
    
    def check_ui_entry(self) -> Tuple[bool, Optional[str]]:
        """Check the main UI entry point"""
        return self.check_module("app.py")
    
    def check_ui_implementation(self) -> Tuple[bool, Optional[str]]:
        """Check the UI implementation module"""
        return self.check_module("guard/ui/app_impl.py")
    
    def check_all_ui_modules(self) -> Tuple[bool, list]:
        """
        Check all UI modules
        
        Returns:
            Tuple of (all_success: bool, error_list: list)
        """
        modules_to_check = [
            "app.py",
            "guard/ui/app_impl.py",
            "guard/ui/assets/css_loader.py"
        ]
        
        errors = []
        all_success = True
        
        for module in modules_to_check:
            success, error = self.check_module(module)
            if not success:
                all_success = False
                errors.append(error)
        
        return all_success, errors


def create_fallback_banner(error_message: str) -> str:
    """Create a fallback banner for UI build failures"""
    return f"""
    <div style="
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        background-color: #f44336;
        color: white;
        padding: 1rem;
        text-align: center;
        z-index: 10000;
        font-family: Arial, sans-serif;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    ">
        <h3>⚠️ UI Build Failed</h3>
        <p>Trading continues normally. UI will be restored when fixed.</p>
        <p style="font-size: 0.8rem; margin-top: 0.5rem;">
            Error: {error_message}
        </p>
        <p style="font-size: 0.7rem; margin-top: 0.3rem;">
            Check logs/ui_build_errors.log for details
        </p>
    </div>
    """


def safe_ui_load(module_name: str, fallback_function=None):
    """
    Safely load a UI module with fallback
    
    Args:
        module_name: Name of the module to load
        fallback_function: Function to call if module load fails
        
    Returns:
        Loaded module or None if failed
    """
    try:
        # Check if module compiles first
        checker = PreflightCheck()
        success, error = checker.check_module(module_name)
        
        if not success:
            checker.logger.error(f"Preflight check failed for {module_name}: {error}")
            if fallback_function:
                return fallback_function()
            return None
        
        # Try to import the module
        if module_name.endswith('.py'):
            module_name = module_name[:-3]
        
        # Replace path separators with dots
        module_name = module_name.replace('/', '.').replace('\\', '.')
        
        # Import the module
        import importlib
        module = importlib.import_module(module_name)
        
        return module
        
    except Exception as e:
        get_ui_logger().error(f"Failed to load module {module_name}: {e}")
        get_ui_logger().error(traceback.format_exc())
        
        if fallback_function:
            return fallback_function()
        return None


# Global preflight checker instance
_preflight_checker = None

def get_preflight_checker() -> PreflightCheck:
    """Get global preflight checker instance"""
    global _preflight_checker
    if _preflight_checker is None:
        _preflight_checker = PreflightCheck()
    return _preflight_checker
