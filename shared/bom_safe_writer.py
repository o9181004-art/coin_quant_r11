import json
import tempfile
import os
import logging
import time

class BOMSafeWriter:
    """BOM-safe JSON writer for all services"""
    
    def __init__(self):
        self.logger = logging.getLogger("BOMSafeWriter")
        self._write_count = 0
        self._bom_warnings = 0
        self._max_bom_warnings = 3
    
    def write_json_atomic(self, data, target_path, ensure_bom_free=True, log_success=True):
        """
        Write JSON atomically without BOM
        
        Args:
            data: Data to write as JSON
            target_path: Target file path
            ensure_bom_free: Ensure no BOM is written
            log_success: Log successful writes
        """
        target_path = os.path.abspath(target_path)
        target_dir = os.path.dirname(target_path)
        
        # Ensure target directory exists
        os.makedirs(target_dir, exist_ok=True)
        
        # Write to temporary file with explicit UTF-8 (no BOM)
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',  # Python's default is BOM-free
            dir=target_dir,
            delete=False,
            prefix='.bom_safe_',
            suffix='.tmp'
        ) as tmp_file:
            # Write JSON with explicit UTF-8 (no BOM)
            json.dump(data, tmp_file, ensure_ascii=False, indent=2)
            tmp_file.flush()
            
            # Force filesystem sync
            os.fsync(tmp_file.fileno())
            
            tmp_path = tmp_file.name
        
        # Atomic replace
        try:
            os.replace(tmp_path, target_path)
            self._write_count += 1
            
            if log_success:
                self.logger.debug(f"BOMSafeWriter: wrote {target_path} (BOM-free, count={self._write_count})")
            
            return True
        except Exception as e:
            # Cleanup temp file on error
            try:
                os.unlink(tmp_path)
            except:
                pass
            self.logger.error(f"BOMSafeWriter: failed to write {target_path} - {e}")
            return False
    
    def verify_bom_free(self, file_path):
        """Verify that a file is BOM-free"""
        try:
            with open(file_path, 'rb') as f:
                first_bytes = f.read(3)
                if first_bytes == b'\xef\xbb\xbf':
                    if self._bom_warnings < self._max_bom_warnings:
                        self.logger.warning(f"BOM detected in {file_path} - this should not happen with BOMSafeWriter")
                        self._bom_warnings += 1
                    return False
                return True
        except Exception as e:
            self.logger.error(f"BOMSafeWriter: failed to verify BOM in {file_path} - {e}")
            return False

# Global instance
bom_safe_writer = BOMSafeWriter()

# Convenience functions
def write_json_bom_free(data, target_path, log_success=True):
    """Write JSON without BOM"""
    return bom_safe_writer.write_json_atomic(data, target_path, log_success=log_success)

def verify_json_bom_free(file_path):
    """Verify JSON file is BOM-free"""
    return bom_safe_writer.verify_bom_free(file_path)
