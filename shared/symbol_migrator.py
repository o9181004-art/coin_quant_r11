#!/usr/bin/env python3
"""
Symbol Migration Utility
========================================
One-time migration to canonicalize all persisted symbols.

Migrates:
- File names (e.g., BTCUSDT.ndjson -> btcusdt.ndjson)
- JSON keys (e.g., {"BTCUSDT": ...} -> {"btcusdt": ...})
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from shared.symbols import canonical_symbol


class SymbolMigrator:
    """Migrate persisted artifacts to canonical symbol form"""
    
    def __init__(self, root_dir: str = "shared_data"):
        self.root_dir = Path(root_dir)
        self.migrated_files = 0
        self.migrated_keys = 0
        self.errors: List[str] = []
    
    def migrate_all(self, dry_run: bool = False) -> Dict:
        """
        Migrate all artifacts to canonical form.
        
        Args:
            dry_run: If True, don't modify files, just report what would change
        
        Returns:
            Migration summary dict
        """
        print(f"[SymbolMigrator] Starting migration (dry_run={dry_run})...")
        
        # 1. Migrate file names
        self._migrate_filenames(dry_run=dry_run)
        
        # 2. Migrate JSON keys
        self._migrate_json_keys(dry_run=dry_run)
        
        summary = {
            'migrated_files': self.migrated_files,
            'migrated_keys': self.migrated_keys,
            'errors': len(self.errors),
            'dry_run': dry_run
        }
        
        print(f"[SymbolMigrator] Migration complete: {summary}")
        
        return summary
    
    def _migrate_filenames(self, dry_run: bool = False):
        """Migrate file names containing uppercase symbols"""
        if not self.root_dir.exists():
            return
        
        # Find files with uppercase symbols in name
        patterns = ['*USDT.json', '*USDT.ndjson', '*USDT.csv', '*USDT.md']
        
        for pattern in patterns:
            for file_path in self.root_dir.rglob(pattern):
                try:
                    # Check if filename contains uppercase
                    if any(c.isupper() for c in file_path.name):
                        new_name = file_path.name.lower()
                        new_path = file_path.parent / new_name
                        
                        if dry_run:
                            print(f"[DRY-RUN] Would rename: {file_path} -> {new_path}")
                        else:
                            # Atomic rename
                            if new_path.exists():
                                # Merge or overwrite (prefer existing lowercase)
                                print(f"[SKIP] Target exists: {new_path}")
                            else:
                                file_path.rename(new_path)
                                print(f"[MIGRATED] {file_path.name} -> {new_name}")
                                self.migrated_files += 1
                
                except Exception as e:
                    error_msg = f"Failed to migrate {file_path}: {e}"
                    self.errors.append(error_msg)
                    print(f"[ERROR] {error_msg}")
    
    def _migrate_json_keys(self, dry_run: bool = False):
        """Migrate JSON keys to canonical form"""
        if not self.root_dir.exists():
            return
        
        # Find JSON files
        for json_file in self.root_dir.rglob('*.json'):
            try:
                # Skip if in migrations or backups
                if 'backup' in str(json_file) or 'migration' in str(json_file):
                    continue
                
                # Read JSON
                with open(json_file, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        continue  # Skip invalid JSON
                
                # Check if any keys need migration
                if not isinstance(data, dict):
                    continue
                
                needs_migration = False
                migrated_data = {}
                
                for key, value in data.items():
                    if isinstance(key, str) and 'USDT' in key:
                        canonical_key = canonical_symbol(key)
                        if canonical_key != key:
                            needs_migration = True
                            migrated_data[canonical_key] = value
                            self.migrated_keys += 1
                        else:
                            migrated_data[canonical_key] = value
                    else:
                        migrated_data[key] = value
                
                if needs_migration:
                    if dry_run:
                        print(f"[DRY-RUN] Would migrate keys in: {json_file}")
                    else:
                        # Backup original
                        backup_path = json_file.with_suffix('.json.backup')
                        shutil.copy2(json_file, backup_path)
                        
                        # Write migrated data
                        temp_path = json_file.with_suffix('.json.tmp')
                        with open(temp_path, 'w', encoding='utf-8') as f:
                            json.dump(migrated_data, f, indent=2, ensure_ascii=False)
                        
                        # Atomic replace
                        temp_path.replace(json_file)
                        
                        print(f"[MIGRATED] Keys in {json_file} (backup: {backup_path.name})")
            
            except Exception as e:
                error_msg = f"Failed to migrate {json_file}: {e}"
                self.errors.append(error_msg)
                print(f"[ERROR] {error_msg}")


def run_migration(dry_run: bool = False) -> Dict:
    """
    Run symbol migration.
    
    Args:
        dry_run: If True, report changes without modifying files
    
    Returns:
        Migration summary
    """
    migrator = SymbolMigrator()
    return migrator.migrate_all(dry_run=dry_run)


if __name__ == "__main__":
    import sys
    
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
    
    print("="*60)
    print("Symbol Migration Utility")
    print("="*60)
    print()
    
    summary = run_migration(dry_run=dry_run)
    
    print()
    print("="*60)
    print("Migration Summary:")
    print(f"  Files renamed: {summary['migrated_files']}")
    print(f"  Keys migrated: {summary['migrated_keys']}")
    print(f"  Errors: {summary['errors']}")
    print(f"  Dry run: {summary['dry_run']}")
    print("="*60)
    
    if summary['errors'] > 0:
        sys.exit(1)

