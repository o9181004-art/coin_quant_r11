"""
Memory Layer - Hash Chain

Merkle roots and proofs with V1/V2 backward compatibility.
"""

import hashlib
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from coin_quant.shared.io import atomic_write_json, safe_read_json
from coin_quant.shared.time import utc_now_seconds


class HashChain:
    """Merkle roots and proofs with V1/V2 backward compatibility"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.chain_file = data_dir / "hash_chain.json"
        self.schema_version = "1.0"
        
        # Ensure directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _calculate_merkle_root(self, data: List[Dict[str, Any]]) -> str:
        """
        Calculate Merkle root for data.
        
        Args:
            data: List of data items
            
        Returns:
            Merkle root hash
        """
        if not data:
            return hashlib.sha256(b"").hexdigest()
        
        # Convert data to hashable strings
        hashes = []
        for item in data:
            item_str = json.dumps(item, sort_keys=True, ensure_ascii=False)
            item_hash = hashlib.sha256(item_str.encode()).hexdigest()
            hashes.append(item_hash)
        
        # Build Merkle tree
        while len(hashes) > 1:
            next_level = []
            for i in range(0, len(hashes), 2):
                left = hashes[i]
                right = hashes[i + 1] if i + 1 < len(hashes) else left
                combined = left + right
                next_level.append(hashlib.sha256(combined.encode()).hexdigest())
            hashes = next_level
        
        return hashes[0]
    
    def add_block(self, data: List[Dict[str, Any]], 
                  block_type: str = "data") -> bool:
        """
        Add block to hash chain.
        
        Args:
            data: Block data
            block_type: Type of block
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            timestamp = utc_now_seconds()
            
            # Calculate Merkle root
            merkle_root = self._calculate_merkle_root(data)
            
            # Get previous block
            chain_data = self._load_chain()
            previous_hash = chain_data.get("last_hash", "")
            
            # Create new block
            block = {
                "timestamp": timestamp,
                "schema_version": self.schema_version,
                "block_type": block_type,
                "merkle_root": merkle_root,
                "previous_hash": previous_hash,
                "data_count": len(data)
            }
            
            # Calculate block hash
            block_str = json.dumps(block, sort_keys=True, ensure_ascii=False)
            block_hash = hashlib.sha256(block_str.encode()).hexdigest()
            block["block_hash"] = block_hash
            
            # Add to chain
            chain_data["blocks"] = chain_data.get("blocks", [])
            chain_data["blocks"].append(block)
            chain_data["last_hash"] = block_hash
            chain_data["last_update"] = timestamp
            
            # Save chain
            if not atomic_write_json(self.chain_file, chain_data):
                return False
            
            return True
            
        except Exception as e:
            print(f"Failed to add block: {e}")
            return False
    
    def verify_chain(self) -> Tuple[bool, List[str]]:
        """
        Verify hash chain integrity.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        try:
            chain_data = self._load_chain()
            blocks = chain_data.get("blocks", [])
            
            if not blocks:
                return True, []
            
            errors = []
            previous_hash = ""
            
            for i, block in enumerate(blocks):
                # Verify block hash
                block_copy = block.copy()
                block_copy.pop("block_hash", None)
                block_str = json.dumps(block_copy, sort_keys=True, ensure_ascii=False)
                expected_hash = hashlib.sha256(block_str.encode()).hexdigest()
                
                if block.get("block_hash") != expected_hash:
                    errors.append(f"Block {i} hash mismatch")
                
                # Verify previous hash
                if block.get("previous_hash") != previous_hash:
                    errors.append(f"Block {i} previous hash mismatch")
                
                previous_hash = block.get("block_hash", "")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            return False, [f"Failed to verify chain: {e}"]
    
    def get_proof(self, data_item: Dict[str, Any], 
                  block_index: int) -> Optional[Dict[str, Any]]:
        """
        Get Merkle proof for data item.
        
        Args:
            data_item: Data item to prove
            block_index: Block index
            
        Returns:
            Merkle proof or None
        """
        try:
            chain_data = self._load_chain()
            blocks = chain_data.get("blocks", [])
            
            if block_index >= len(blocks):
                return None
            
            block = blocks[block_index]
            
            # Create proof structure
            proof = {
                "block_index": block_index,
                "merkle_root": block.get("merkle_root"),
                "block_hash": block.get("block_hash"),
                "timestamp": block.get("timestamp")
            }
            
            return proof
            
        except Exception as e:
            print(f"Failed to get proof: {e}")
            return None
    
    def _load_chain(self) -> Dict[str, Any]:
        """Load hash chain data"""
        chain_data = safe_read_json(self.chain_file)
        if not chain_data:
            chain_data = {
                "schema_version": self.schema_version,
                "blocks": [],
                "last_hash": "",
                "last_update": 0
            }
        return chain_data
