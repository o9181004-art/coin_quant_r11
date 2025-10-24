#!/usr/bin/env python3
"""
JSON BOM (Byte Order Mark) Utilities

Provides BOM-tolerant JSON reading and BOM detection utilities.
Prevents "Unexpected UTF-8 BOM" errors in JSON parsing.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def read_json_bom_tolerant(
    path: Union[str, Path],
    default: Any = None
) -> Any:
    """
    Read JSON file with BOM tolerance.
    Automatically handles utf-8-sig (UTF-8 with BOM) and strips BOM if present.
    
    Args:
        path: File path to read from
        default: Default value if file doesn't exist or read fails
        
    Returns:
        Parsed JSON object or default value
    """
    try:
        path = Path(path)
        
        if not path.exists():
            return default
        
        # Try utf-8-sig first (automatically strips BOM)
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
                return json.loads(content)
        except UnicodeDecodeError:
            # Fallback to utf-8
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Strip BOM manually if present
                if content.startswith('\ufeff'):
                    content = content[1:]
                return json.loads(content)
                
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in {path}: {e}")
        return default
    except Exception as e:
        logger.error(f"Failed to read JSON from {path}: {e}")
        return default


def has_bom(file_path: Union[str, Path]) -> bool:
    """
    Check if a file starts with UTF-8 BOM (0xEF, 0xBB, 0xBF).
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file starts with BOM, False otherwise
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return False
        
        with open(path, 'rb') as f:
            first_bytes = f.read(3)
            return first_bytes == b'\xef\xbb\xbf'
    except Exception as e:
        logger.error(f"Failed to check BOM in {file_path}: {e}")
        return False


def find_json_files_with_bom(
    directory: Union[str, Path],
    recursive: bool = True
) -> List[Path]:
    """
    Find all JSON files with BOM in a directory.
    
    Args:
        directory: Directory to search
        recursive: If True, search recursively
        
    Returns:
        List of file paths with BOM
    """
    directory = Path(directory)
    files_with_bom = []
    
    if not directory.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return files_with_bom
    
    pattern = '**/*.json' if recursive else '*.json'
    
    for json_file in directory.glob(pattern):
        if json_file.is_file() and has_bom(json_file):
            files_with_bom.append(json_file)
    
    return files_with_bom


def strip_bom_from_file(file_path: Union[str, Path]) -> bool:
    """
    Remove BOM from a file (in-place, atomic).
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if BOM was stripped, False otherwise
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            logger.warning(f"File does not exist: {path}")
            return False
        
        # Read with utf-8-sig to strip BOM
        with open(path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        
        # Write back without BOM (atomic)
        temp_path = path.with_suffix('.tmp_nobom')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Atomic replace
        temp_path.replace(path)
        
        logger.info(f"Stripped BOM from {path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to strip BOM from {file_path}: {e}")
        return False


def check_shared_data_bom(repo_root: Union[str, Path] = ".") -> Dict[str, Any]:
    """
    Check all JSON files in shared_data/ for BOM.
    
    Args:
        repo_root: Repository root directory
        
    Returns:
        Dict with check results
    """
    repo_root = Path(repo_root)
    shared_data_dir = repo_root / "shared_data"
    
    if not shared_data_dir.exists():
        return {
            "status": "error",
            "message": f"shared_data directory not found: {shared_data_dir}"
        }
    
    files_with_bom = find_json_files_with_bom(shared_data_dir, recursive=True)
    
    result = {
        "status": "pass" if len(files_with_bom) == 0 else "fail",
        "total_json_files": len(list(shared_data_dir.glob('**/*.json'))),
        "files_with_bom": len(files_with_bom),
        "files_with_bom_list": [str(f.relative_to(repo_root)) for f in files_with_bom]
    }
    
    return result


def write_json_no_bom(
    path: Union[str, Path],
    obj: Any,
    atomic: bool = True,
    indent: int = 2
) -> bool:
    """
    Write JSON file without BOM (UTF-8 encoding).
    Guaranteed to never write BOM.
    
    Args:
        path: File path to write to
        obj: Object to serialize
        atomic: Use atomic write (temp + replace)
        indent: JSON indentation
        
    Returns:
        True if successful, False otherwise
    """
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Serialize to JSON string
        json_str = json.dumps(obj, indent=indent, ensure_ascii=False)
        
        if atomic:
            # Atomic write
            temp_path = path.with_suffix('.tmp_nobom')
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            temp_path.replace(path)
        else:
            # Direct write
            with open(path, 'w', encoding='utf-8') as f:
                f.write(json_str)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to write JSON to {path}: {e}")
        return False


# CLI for BOM checking
def main():
    """CLI entry point for BOM checking"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m shared.json_bom_utils <command> [args]")
        print("Commands:")
        print("  check [directory]   - Check for BOM in JSON files")
        print("  strip <file>        - Strip BOM from a file")
        print("  test-shared-data    - Test shared_data/ directory")
        return
    
    command = sys.argv[1]
    
    if command == "check":
        directory = sys.argv[2] if len(sys.argv) > 2 else "shared_data"
        files_with_bom = find_json_files_with_bom(directory)
        
        if files_with_bom:
            print(f"❌ Found {len(files_with_bom)} file(s) with BOM:")
            for f in files_with_bom:
                print(f"  - {f}")
            sys.exit(1)
        else:
            print("✅ No BOM found in JSON files")
            sys.exit(0)
    
    elif command == "strip":
        if len(sys.argv) < 3:
            print("Error: file path required")
            sys.exit(1)
        
        file_path = sys.argv[2]
        success = strip_bom_from_file(file_path)
        
        if success:
            print(f"✅ Stripped BOM from {file_path}")
            sys.exit(0)
        else:
            print(f"❌ Failed to strip BOM from {file_path}")
            sys.exit(1)
    
    elif command == "test-shared-data":
        result = check_shared_data_bom()
        
        print(f"Status: {result['status']}")
        print(f"Total JSON files: {result['total_json_files']}")
        print(f"Files with BOM: {result['files_with_bom']}")
        
        if result['files_with_bom'] > 0:
            print("\nFiles with BOM:")
            for f in result['files_with_bom_list']:
                print(f"  - {f}")
            sys.exit(1)
        else:
            print("✅ All JSON files are BOM-free")
            sys.exit(0)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()

