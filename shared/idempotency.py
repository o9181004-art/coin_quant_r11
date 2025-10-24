#!/usr/bin/env python3
"""
Order Idempotency
========================================
Ensure orders are not duplicated across retries/crashes.

Uses signal hash (symbol + ts + side + size) as deduplication key.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Path constants
IDEMPOTENCY_DB_PATH = Path("shared_data/idempotency_db.json")
IDEMPOTENCY_TTL = 3600  # 1 hour


def generate_signal_hash(symbol: str, side: str, size: float, timestamp: float = None) -> str:
    """
    Generate idempotency key from signal parameters.
    
    Args:
        symbol: Trading symbol
        side: BUY/SELL
        size: Order size
        timestamp: Signal timestamp (optional, uses current time if None)
    
    Returns:
        Hash string (16 chars)
    """
    if timestamp is None:
        timestamp = time.time()
    
    # Normalize inputs
    symbol = symbol.upper()
    side = side.upper()
    
    # Create hash input
    hash_input = f"{symbol}|{side}|{size:.8f}|{int(timestamp)}"
    
    # Generate SHA256 hash
    hash_obj = hashlib.sha256(hash_input.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    
    # Return first 16 chars
    return hash_hex[:16]


def is_order_duplicate(idempotency_key: str) -> bool:
    """
    Check if order with this idempotency key was already processed.
    
    Args:
        idempotency_key: Hash from generate_signal_hash()
    
    Returns:
        True if duplicate, False if new
    """
    try:
        if not IDEMPOTENCY_DB_PATH.exists():
            return False
        
        with open(IDEMPOTENCY_DB_PATH, 'r', encoding='utf-8') as f:
            db = json.load(f)
        
        # Check if key exists and not expired
        if idempotency_key in db:
            entry = db[idempotency_key]
            age = time.time() - entry.get('ts', 0)
            
            if age < IDEMPOTENCY_TTL:
                # Still valid - duplicate
                return True
        
        return False
        
    except Exception as e:
        print(f"[Idempotency] Error checking duplicate: {e}")
        return False


def record_order(idempotency_key: str, order_info: Dict[str, Any] = None):
    """
    Record order as processed.
    
    Args:
        idempotency_key: Hash from generate_signal_hash()
        order_info: Optional order details
    """
    try:
        # Load existing DB
        if IDEMPOTENCY_DB_PATH.exists():
            with open(IDEMPOTENCY_DB_PATH, 'r', encoding='utf-8') as f:
                db = json.load(f)
        else:
            db = {}
        
        # Add entry
        db[idempotency_key] = {
            'ts': time.time(),
            'order_info': order_info or {}
        }
        
        # Cleanup expired entries
        current_time = time.time()
        db = {
            k: v for k, v in db.items()
            if current_time - v.get('ts', 0) < IDEMPOTENCY_TTL
        }
        
        # Save atomically
        IDEMPOTENCY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        temp_file = IDEMPOTENCY_DB_PATH.with_suffix('.json.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2)
        
        if IDEMPOTENCY_DB_PATH.exists():
            IDEMPOTENCY_DB_PATH.unlink()
        temp_file.replace(IDEMPOTENCY_DB_PATH)
        
    except Exception as e:
        print(f"[Idempotency] Error recording order: {e}")


def cleanup_expired_entries():
    """Cleanup expired idempotency entries"""
    try:
        if not IDEMPOTENCY_DB_PATH.exists():
            return
        
        with open(IDEMPOTENCY_DB_PATH, 'r', encoding='utf-8') as f:
            db = json.load(f)
        
        # Remove expired
        current_time = time.time()
        original_count = len(db)
        
        db = {
            k: v for k, v in db.items()
            if current_time - v.get('ts', 0) < IDEMPOTENCY_TTL
        }
        
        removed_count = original_count - len(db)
        
        if removed_count > 0:
            # Save cleaned DB
            temp_file = IDEMPOTENCY_DB_PATH.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(db, f, indent=2)
            
            if IDEMPOTENCY_DB_PATH.exists():
                IDEMPOTENCY_DB_PATH.unlink()
            temp_file.replace(IDEMPOTENCY_DB_PATH)
            
            print(f"[Idempotency] Cleaned up {removed_count} expired entries")
        
    except Exception as e:
        print(f"[Idempotency] Error cleaning up: {e}")


if __name__ == "__main__":
    # Test idempotency
    print("Testing idempotency system...")
    
    # Generate key
    key1 = generate_signal_hash("BTCUSDT", "BUY", 0.001, timestamp=time.time())
    print(f"Generated key: {key1}")
    
    # Check if duplicate (should be False)
    is_dup = is_order_duplicate(key1)
    print(f"Is duplicate (before recording): {is_dup}")
    
    # Record order
    record_order(key1, {'symbol': 'BTCUSDT', 'side': 'BUY', 'size': 0.001})
    print("Order recorded")
    
    # Check again (should be True)
    is_dup = is_order_duplicate(key1)
    print(f"Is duplicate (after recording): {is_dup}")
    
    # Generate different key (different timestamp)
    time.sleep(1)
    key2 = generate_signal_hash("BTCUSDT", "BUY", 0.001, timestamp=time.time())
    print(f"\nGenerated new key: {key2}")
    
    is_dup = is_order_duplicate(key2)
    print(f"Is duplicate (new timestamp): {is_dup}")
    
    # Cleanup
    cleanup_expired_entries()
    print("\nCleanup completed")

