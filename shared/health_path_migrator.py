#!/usr/bin/env python3
"""
Health Path Migration
========================================
One-time migration to unified health.json path.

Old: shared_data/health/health.json
New: shared_data/health.json (canonical)

Runs on startup; idempotent.
"""

import json
import shutil
import time
from pathlib import Path
from typing import Dict

# Canonical health path
CANONICAL_HEALTH_PATH = Path("shared_data/health.json")

# Legacy paths to check
LEGACY_HEALTH_PATHS = [
    Path("shared_data/health/health.json"),
    Path("shared_data/health/feeder.json"),
    Path("shared_data/health/trader.json"),
]


def migrate_health_path() -> Dict[str, any]:
    """
    Migrate health files to canonical path.
    
    Returns:
        Migration summary
    """
    migrated = []
    
    # Check canonical path
    if CANONICAL_HEALTH_PATH.exists():
        # Already exists - check if migration needed
        for legacy_path in LEGACY_HEALTH_PATHS:
            if legacy_path.exists() and legacy_path != CANONICAL_HEALTH_PATH:
                # Legacy file exists - backup and note
                try:
                    backup_path = legacy_path.with_suffix('.json.migrated')
                    shutil.copy2(legacy_path, backup_path)
                    print(f"[HealthMigration] Backed up legacy: {legacy_path} → {backup_path.name}")
                    migrated.append(str(legacy_path))
                except Exception as e:
                    print(f"[HealthMigration] Failed to backup {legacy_path}: {e}")
        
        return {
            'canonical_exists': True,
            'migrated': migrated,
            'action': 'backup_legacy'
        }
    
    # Canonical doesn't exist - try to migrate from legacy
    for legacy_path in LEGACY_HEALTH_PATHS:
        if legacy_path.exists():
            try:
                # Ensure canonical parent exists
                CANONICAL_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy to canonical (don't move - keep legacy for safety)
                shutil.copy2(legacy_path, CANONICAL_HEALTH_PATH)
                
                print(f"[HealthMigration] Migrated: {legacy_path} → {CANONICAL_HEALTH_PATH}")
                migrated.append(str(legacy_path))
                
                # Only migrate first found
                break
            
            except Exception as e:
                print(f"[HealthMigration] Failed to migrate {legacy_path}: {e}")
    
    if not migrated:
        # No legacy found - create default canonical
        try:
            CANONICAL_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            default_health = {
                'status': 'UNKNOWN',
                'ts': time.time(),
                'message': 'Initialized'
            }
            
            with open(CANONICAL_HEALTH_PATH, 'w', encoding='utf-8') as f:
                json.dump(default_health, f, indent=2)
            
            print(f"[HealthMigration] Created default: {CANONICAL_HEALTH_PATH}")
            
            return {
                'canonical_exists': False,
                'migrated': [],
                'action': 'created_default'
            }
        
        except Exception as e:
            print(f"[HealthMigration] Failed to create default: {e}")
            return {
                'canonical_exists': False,
                'migrated': [],
                'action': f'error: {e}'
            }
    
    return {
        'canonical_exists': True,
        'migrated': migrated,
        'action': 'migrated_from_legacy'
    }


def get_canonical_health_path() -> Path:
    """Get canonical health file path"""
    return CANONICAL_HEALTH_PATH


def ensure_health_file_exists():
    """Ensure canonical health file exists"""
    if not CANONICAL_HEALTH_PATH.exists():
        migrate_health_path()


# Unit tests
if __name__ == "__main__":
    import tempfile
    
    print("Testing health path migration...")
    
    # Create temp directory
    test_dir = Path(tempfile.mkdtemp())
    
    try:
        # Test with temp paths (no global override needed)
        import shared.health_path_migrator as migrator

        # Save originals
        original_canonical = migrator.CANONICAL_HEALTH_PATH
        original_legacy = migrator.LEGACY_HEALTH_PATHS
        
        # Override for testing
        migrator.CANONICAL_HEALTH_PATH = test_dir / "health.json"
        migrator.LEGACY_HEALTH_PATHS = [
            test_dir / "health" / "health.json",
            test_dir / "health" / "feeder.json"
        ]
        
        # Test 1: No files exist
        print("\n1. No files exist (create default):")
        summary = migrator.migrate_health_path()
        
        assert summary['action'] == 'created_default', "Should create default"
        assert migrator.CANONICAL_HEALTH_PATH.exists(), "Canonical should exist"
        print(f"✅ {summary}")
        
        # Cleanup
        migrator.CANONICAL_HEALTH_PATH.unlink()
        
        # Test 2: Legacy exists
        print("\n2. Legacy exists (migrate):")
        legacy_path = test_dir / "health" / "health.json"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        
        legacy_data = {'status': 'GREEN', 'ts': time.time()}
        with open(legacy_path, 'w') as f:
            json.dump(legacy_data, f)
        
        summary = migrator.migrate_health_path()
        
        assert summary['action'] == 'migrated_from_legacy', "Should migrate"
        assert migrator.CANONICAL_HEALTH_PATH.exists(), "Canonical should exist"
        
        with open(migrator.CANONICAL_HEALTH_PATH, 'r') as f:
            data = json.load(f)
        
        assert data['status'] == 'GREEN', "Data should match"
        print(f"✅ {summary}")
        
        # Test 3: Canonical exists (backup legacy)
        print("\n3. Canonical exists (backup legacy):")
        summary = migrator.migrate_health_path()
        
        assert summary['canonical_exists'], "Canonical should exist"
        assert summary['action'] == 'backup_legacy', "Should backup legacy"
        print(f"✅ {summary}")
        
        print("\n" + "="*50)
        print("All health migration tests passed! ✅")
        print("="*50)
        
        # Restore originals
        migrator.CANONICAL_HEALTH_PATH = original_canonical
        migrator.LEGACY_HEALTH_PATHS = original_legacy
    
    finally:
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)

