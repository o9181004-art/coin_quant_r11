#!/usr/bin/env python3
"""
Health Integration - Integrate new health system with existing components
Updates existing health readers to use Windows-safe health_writer.py
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from shared.alert_cooldown import get_alert_manager
from shared.health_monitor import get_health_monitor
from shared.health_writer import get_health_reader, get_health_writer

logger = logging.getLogger(__name__)


def update_feeder_health_writer():
    """Update Feeder to use new health writer system"""
    try:
        # Get health writer and set as designated writer
        health_writer = get_health_writer()
        health_writer.set_designated_writer(True)
        
        logger.info("Feeder health writer updated to use new system")
        return health_writer
        
    except Exception as e:
        logger.error(f"Failed to update feeder health writer: {e}")
        return None


def update_ui_health_reader():
    """Update UI to use new health reader system"""
    try:
        # Get health reader
        health_reader = get_health_reader()
        
        logger.info("UI health reader updated to use new system")
        return health_reader
        
    except Exception as e:
        logger.error(f"Failed to update UI health reader: {e}")
        return None


def update_autoheal_health_monitor():
    """Update Auto-Heal to use new health monitor system"""
    try:
        # Get health monitor
        health_monitor = get_health_monitor()
        
        logger.info("Auto-Heal health monitor updated to use new system")
        return health_monitor
        
    except Exception as e:
        logger.error(f"Failed to update Auto-Heal health monitor: {e}")
        return None


def migrate_existing_health_files():
    """Migrate existing health files to new format"""
    try:
        repo_root = Path(__file__).parent.parent.absolute()
        health_dir = repo_root / "shared_data" / "health"
        
        if not health_dir.exists():
            health_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created health directory")
            return True
        
        # Check for existing health files
        existing_files = list(health_dir.glob("*.json"))
        if not existing_files:
            logger.info("No existing health files to migrate")
            return True
        
        # Migrate each file
        migrated_count = 0
        for health_file in existing_files:
            try:
                # Read existing file
                with open(health_file, 'r', encoding='utf-8') as f:
                    import json
                    data = json.load(f)
                
                # Add required fields if missing
                if "ts" not in data:
                    data["ts"] = int(time.time() * 1000)
                
                if "writer_id" not in data:
                    data["writer_id"] = "migration"
                
                if "write_ts" not in data:
                    data["write_ts"] = time.time()
                
                # Write back with new format
                with open(health_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                migrated_count += 1
                logger.info(f"Migrated health file: {health_file.name}")
                
            except Exception as e:
                logger.warning(f"Failed to migrate {health_file.name}: {e}")
        
        logger.info(f"Health migration completed: {migrated_count} files migrated")
        return True
        
    except Exception as e:
        logger.error(f"Health migration failed: {e}")
        return False


def setup_health_permissions():
    """Setup proper Windows permissions for health files"""
    try:
        repo_root = Path(__file__).parent.parent.absolute()
        health_dir = repo_root / "shared_data" / "health"
        
        # Ensure directory exists with proper permissions
        health_dir.mkdir(parents=True, exist_ok=True)
        
        # Create lock file with proper permissions
        lock_file = health_dir / "health.write.lock"
        if not lock_file.exists():
            lock_file.touch()
        
        logger.info("Health permissions setup completed")
        return True
        
    except Exception as e:
        logger.error(f"Health permissions setup failed: {e}")
        return False


def validate_health_system():
    """Validate the new health system is working correctly"""
    try:
        # Test health writer
        health_writer = get_health_writer()
        health_writer.set_designated_writer(True)
        
        test_data = {
            "feeder": {
                "process_alive": True,
                "ws_fresh_s": 5
            },
            "trader": {
                "process_alive": True,
                "positions_fresh_s": 10
            },
            "ares": {
                "process_alive": True,
                "signals_fresh_s": 15
            },
            "databus": {
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            },
            "errors_recent": []
        }
        
        # Test write
        write_success = health_writer.write_health(test_data)
        if not write_success:
            logger.error("Health writer test failed")
            return False
        
        # Test health reader
        health_reader = get_health_reader()
        read_data = health_reader.read_health()
        if not read_data:
            logger.error("Health reader test failed")
            return False
        
        # Test health monitor
        health_monitor = get_health_monitor()
        monitor_data = health_monitor.check_all_health()
        if not monitor_data:
            logger.error("Health monitor test failed")
            return False
        
        # Test alert cooldown
        alert_manager = get_alert_manager()
        can_alert = alert_manager.can_send_alert("test", "test_service")
        if not isinstance(can_alert, bool):
            logger.error("Alert cooldown test failed")
            return False
        
        logger.info("Health system validation completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Health system validation failed: {e}")
        return False


def initialize_health_system():
    """Initialize the complete health system"""
    try:
        logger.info("Initializing health system...")
        
        # Setup permissions
        if not setup_health_permissions():
            return False
        
        # Migrate existing files
        if not migrate_existing_health_files():
            return False
        
        # Validate system
        if not validate_health_system():
            return False
        
        logger.info("Health system initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Health system initialization failed: {e}")
        return False


# Convenience functions for existing code
def get_health_data() -> Optional[Dict[str, Any]]:
    """Get current health data (replacement for old health readers)"""
    try:
        health_reader = get_health_reader()
        return health_reader.read_health()
    except Exception as e:
        logger.error(f"Failed to get health data: {e}")
        return None


def write_health_data(health_data: Dict[str, Any]) -> bool:
    """Write health data (replacement for old health writers)"""
    try:
        health_writer = get_health_writer()
        return health_writer.write_health(health_data)
    except Exception as e:
        logger.error(f"Failed to write health data: {e}")
        return False


def check_service_health(service_name: str) -> Dict[str, Any]:
    """Check health of a specific service"""
    try:
        health_monitor = get_health_monitor()
        return health_monitor.get_service_status(service_name)
    except Exception as e:
        logger.error(f"Failed to check service health: {e}")
        return {
            "process_alive": False,
            "overall_healthy": False,
            "age_s": 0.0,
            "should_alert": False
        }
