import json
import os
import logging
import time

class BOMTolerantReader:
    """BOM-tolerant JSON reader for all services"""
    
    def __init__(self):
        self.logger = logging.getLogger("BOMTolerantReader")
        self._bom_warn_count = 0
        self._max_bom_warnings = 3
        self._read_count = 0
        self._bom_removal_count = 0
    
    def read_json_bom_tolerant(self, file_path, default=None, log_bom_removal=True):
        """
        Read JSON with BOM tolerance
        
        Args:
            file_path: Path to JSON file
            default: Default value if read fails
            log_bom_removal: Log when BOM is removed
            
        Returns:
            dict: Parsed JSON or default value
        """
        if not os.path.exists(file_path):
            self.logger.debug(f"BOMTolerantReader: file not found {file_path}")
            return default
        
        self._read_count += 1
        
        # First attempt: standard UTF-8
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.logger.debug(f"BOMTolerantReader: read {file_path} (standard, count={self._read_count})")
            return data
        
        except json.JSONDecodeError as e:
            # Second attempt: UTF-8-SIG (strip BOM)
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                
                self._bom_removal_count += 1
                
                # Rate-limited warning about BOM removal
                if log_bom_removal and self._bom_warn_count < self._max_bom_warnings:
                    self.logger.info(f"BOMTolerantReader: utf8_bom_removed={file_path} (count={self._bom_removal_count})")
                    self._bom_warn_count += 1
                
                return data
            
            except Exception as e2:
                # Third attempt: manual BOM stripping
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    # Check for BOM
                    if content.startswith(b'\xef\xbb\xbf'):
                        content = content[3:]
                        self._bom_removal_count += 1
                        
                        # Rate-limited warning
                        if log_bom_removal and self._bom_warn_count < self._max_bom_warnings:
                            self.logger.info(f"BOMTolerantReader: utf8_bom_removed={file_path} (manual, count={self._bom_removal_count})")
                            self._bom_warn_count += 1
                    
                    # Decode and parse
                    text = content.decode('utf-8')
                    data = json.loads(text)
                    
                    return data
                
                except Exception as e3:
                    self.logger.warning(f"BOMTolerantReader: failed to read {file_path} - {e3}")
                    return default
        
        except Exception as e:
            self.logger.warning(f"BOMTolerantReader: read error {file_path} - {e}")
            return default
    
    def get_stats(self):
        """Get reading statistics"""
        return {
            "total_reads": self._read_count,
            "bom_removals": self._bom_removal_count,
            "bom_warnings": self._bom_warn_count
        }

# Global instance
bom_tolerant_reader = BOMTolerantReader()

# Convenience functions
def read_json_bom_tolerant(file_path, default=None, log_bom_removal=True):
    """Read JSON with BOM tolerance"""
    return bom_tolerant_reader.read_json_bom_tolerant(file_path, default, log_bom_removal)

def get_bom_reader_stats():
    """Get BOM reader statistics"""
    return bom_tolerant_reader.get_stats()
