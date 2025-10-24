"""
Key normalization for environment drift detection

Normalizes keys to handle variations like:
- env.TESTNET → TESTNET
- IS_TESTNET → TESTNET (alias)
- runtime.trading_mode → TRADING_MODE
"""

def normalize_key(key: str) -> str:
    """
    Normalize environment key for comparison
    
    Steps:
    1. Strip whitespace
    2. Convert to UPPERCASE
    3. Remove common prefixes (ENV., RUNTIME., CONFIG., SSOT.)
    4. Apply aliases (IS_TESTNET → TESTNET)
    
    Args:
        key: Raw key name
    
    Returns:
        Normalized key name
    
    Examples:
        >>> normalize_key("env.testnet")
        'TESTNET'
        >>> normalize_key("IS_TESTNET")
        'TESTNET'
        >>> normalize_key("  runtime.trading_mode  ")
        'TRADING_MODE'
    """
    if not key:
        return ""
    
    # 1. Strip and uppercase
    normalized = key.strip().upper()
    
    # 2. Remove common prefixes
    prefixes = ["ENV.", "RUNTIME.", "CONFIG.", "SSOT."]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    
    # 3. Apply aliases
    aliases = {
        "IS_TESTNET": "TESTNET",
        "SIMULATION_MODE": "TESTNET",
        "PAPER_TRADING": "TESTNET",
    }
    
    if normalized in aliases:
        normalized = aliases[normalized]
    
    return normalized


def normalize_key_set(keys: set) -> set:
    """
    Normalize a set of keys
    
    Args:
        keys: Set of raw key names
    
    Returns:
        Set of normalized key names
    
    Examples:
        >>> keys = {"env.testnet", "IS_TESTNET", "BINANCE_API_KEY"}
        >>> normalize_key_set(keys)
        {'TESTNET', 'BINANCE_API_KEY'}
    """
    return {normalize_key(k) for k in keys if k}

