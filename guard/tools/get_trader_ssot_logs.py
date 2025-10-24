#!/usr/bin/env python3
"""
Operator Helper: Get TRADER_SSOT Logs
====================================
Extract the last 50 lines containing TRADER_SSOT from Trader logs
for operator analysis and debugging.
"""

import os
import sys
from pathlib import Path

def get_trader_ssot_logs():
    """Get last 50 TRADER_SSOT log lines"""
    try:
        # Find trader log file
        log_files = [
            "logs/trader_err.log",
            "logs/trader.log", 
            "logs/trader_service.log"
        ]
        
        log_file = None
        for file_path in log_files:
            if Path(file_path).exists():
                log_file = file_path
                break
        
        if not log_file:
            print("❌ No Trader log file found")
            return
        
        print(f"📋 Reading from: {log_file}")
        print("=" * 80)
        
        # Read all lines and filter for TRADER_SSOT
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Filter for TRADER_SSOT lines
        ssot_lines = [line.strip() for line in lines if 'TRADER_SSOT' in line]
        
        # Get last 50 lines
        recent_lines = ssot_lines[-50:] if len(ssot_lines) > 50 else ssot_lines
        
        if not recent_lines:
            print("⚠️  No TRADER_SSOT lines found")
            print("   Make sure Trader service is running and has logged SSOT paths")
            return
        
        print(f"🔍 Found {len(ssot_lines)} TRADER_SSOT lines (showing last {len(recent_lines)})")
        print("=" * 80)
        
        for line in recent_lines:
            print(line)
        
        print("=" * 80)
        print("💡 Copy these paths to feed the correct files to Trader")
        
        # Also show WhyNotGREEN lines
        print("\n🚨 Recent WhyNotGREEN messages:")
        print("-" * 40)
        
        why_not_green_lines = [line.strip() for line in lines if 'WhyNotGREEN' in line or 'YELLOW' in line]
        recent_why_lines = why_not_green_lines[-10:] if len(why_not_green_lines) > 10 else why_not_green_lines
        
        for line in recent_why_lines:
            print(line)
        
    except Exception as e:
        print(f"❌ Error reading logs: {e}")

if __name__ == "__main__":
    get_trader_ssot_logs()
