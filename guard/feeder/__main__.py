#!/usr/bin/env python3
"""
Feeder Module Entrypoint
Calls guard.feeder.state_bus_writer.main()
"""

import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def main():
    """Main entry point for guard.feeder module"""
    logger.info("ENTRYPOINT_OK module=guard.feeder")
    
    try:
        # Import and run state_bus_writer
        from .state_bus_writer import main
        return main()
    except Exception as e:
        logger.error(f"Failed to start feeder: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
