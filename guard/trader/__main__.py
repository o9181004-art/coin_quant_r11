#!/usr/bin/env python3
"""
Trader Module Entrypoint
Calls guard.trader.filters_manager.main()
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
    """Main entry point for guard.trader module"""
    logger.info("ENTRYPOINT_OK module=guard.trader")
    
    try:
        # Import and run filters_manager
        from .filters_manager import main
        return main()
    except Exception as e:
        logger.error(f"Failed to start trader: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
