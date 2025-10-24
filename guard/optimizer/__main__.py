#!/usr/bin/env python3
"""
Optimizer Module Entrypoint
Calls guard.optimizer.ares_service.main()
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
    """Main entry point for guard.optimizer module"""
    logger.info("ENTRYPOINT_OK module=guard.optimizer")
    
    try:
        # Import and run ares_service
        from .ares_service import main
        return main()
    except Exception as e:
        logger.error(f"Failed to start optimizer: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
