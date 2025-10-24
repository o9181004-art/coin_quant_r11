"""
CLI Launcher for Coin Quant R11

Module-based launch for all services.
"""

import sys
import argparse
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def launch_feeder():
    """Launch feeder service"""
    try:
        from coin_quant.feeder.service import main
        main()
    except Exception as e:
        print(f"Failed to launch feeder: {e}")
        sys.exit(1)

def launch_ares():
    """Launch ARES service"""
    try:
        from coin_quant.ares.service import main
        main()
    except Exception as e:
        print(f"Failed to launch ARES: {e}")
        sys.exit(1)

def launch_trader():
    """Launch trader service"""
    try:
        from coin_quant.trader.service import main
        main()
    except Exception as e:
        print(f"Failed to launch trader: {e}")
        sys.exit(1)

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Coin Quant R11 CLI Launcher")
    parser.add_argument("service", choices=["feeder", "ares", "trader"], 
                       help="Service to launch")
    
    args = parser.parse_args()
    
    if args.service == "feeder":
        launch_feeder()
    elif args.service == "ares":
        launch_ares()
    elif args.service == "trader":
        launch_trader()

if __name__ == "__main__":
    main()
