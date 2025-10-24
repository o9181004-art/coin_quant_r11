#!/usr/bin/env python3
"""
ARES↔UI Audit Contract Layer
Provides definitive, low-overhead, ops-ready audit trail with signature verification
"""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

class TimeSource(Enum):
    EXCHANGE = "exchange"
    LOCAL = "local"

class ContractStatus(Enum):
    OK = "ok"
    BLOCKED_BY_CONTRACT = "blocked_by_contract"
    STALE = "stale"
    BAD_SIGNATURE = "bad_signature"
    INVALID_TARGET = "invalid_target"
    LOW_RR = "low_rr"

@dataclass
class TradeCandidateV1:
    """Trade candidate with audit trail and signature"""
    # Core fields
    symbol: str
    side: str  # "buy" or "sell"
    entry: float
    target: float
    stop: float
    confidence: float
    snapshot_ts: float  # Exchange/server time
    expires_at: float   # Exchange/server time
    
    # Optional fields with defaults
    cost_bps: float = 0.0
    time_source: TimeSource = TimeSource.EXCHANGE
    trace_id: str = ""
    signature: str = ""
    target_origin: str = "unknown"  # "atr_k", "bb_k", "fixed_pct"
    
    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = self._generate_trace_id()
        if not self.signature:
            self.signature = self._generate_signature()
    
    def _generate_trace_id(self) -> str:
        """Generate deterministic trace ID"""
        data = f"{self.symbol}:{self.side}:{self.entry}:{self.target}:{self.stop}:{self.snapshot_ts}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _generate_signature(self) -> str:
        """Generate HMAC-SHA256 signature"""
        key = os.getenv("CONTRACT_HMAC_KEY", "default_audit_key_change_in_prod")
        # Convert to dict and handle enum serialization
        data = asdict(self)
        data['time_source'] = data['time_source'].value if hasattr(data['time_source'], 'value') else str(data['time_source'])
        payload = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    
    @property
    def age_sec(self) -> float:
        """Calculate age in seconds, clamped to zero"""
        age = time.time() - self.snapshot_ts
        return max(0.0, age)
    
    @property
    def net_confidence(self) -> float:
        """Calculate net confidence after cost adjustment"""
        return round(self.confidence - (self.cost_bps / 10000), 4)
    
    @property
    def risk_reward_ratio(self) -> float:
        """Calculate risk-reward ratio"""
        if self.side == "buy":
            risk = self.entry - self.stop
            reward = self.target - self.entry
        else:
            risk = self.stop - self.entry
            reward = self.entry - self.target
        
        if risk <= 0:
            return 0.0
        return reward / risk

class ContractValidator:
    """Validates trade candidates against contract rules"""
    
    def __init__(self):
        self.negative_age_flags = set()  # Track symbols with negative age anomalies
        self.hmac_key = os.getenv("CONTRACT_HMAC_KEY", "default_audit_key_change_in_prod")
    
    def validate(self, candidate: TradeCandidateV1) -> Tuple[ContractStatus, str]:
        """Validate candidate and return status with reason"""
        
        # 1. Signature verification
        if not self._verify_signature(candidate):
            return ContractStatus.BAD_SIGNATURE, "Invalid signature"
        
        # 2. Age check (stale detection)
        if candidate.age_sec >= 120:
            return ContractStatus.STALE, f"Age {candidate.age_sec:.1f}s >= 120s"
        
        # 3. Negative age anomaly flagging
        if candidate.age_sec < 0 and candidate.symbol not in self.negative_age_flags:
            self.negative_age_flags.add(candidate.symbol)
            # Log once per symbol
            print(f"ANOMALY: negative_age for {candidate.symbol}")
        
        # 4. Target/stop coherence
        if not self._validate_target_stop(candidate):
            return ContractStatus.INVALID_TARGET, "Target/stop coherence failed"
        
        # 5. Risk-reward ratio check
        if candidate.risk_reward_ratio < 1.1:
            return ContractStatus.LOW_RR, f"RR {candidate.risk_reward_ratio:.2f} < 1.1"
        
        # 6. Net confidence threshold
        if candidate.net_confidence < 0.5:
            return ContractStatus.BLOCKED_BY_CONTRACT, f"Net confidence {candidate.net_confidence:.4f} < 0.5"
        
        return ContractStatus.OK, "All checks passed"
    
    def _verify_signature(self, candidate: TradeCandidateV1) -> bool:
        """Verify HMAC signature"""
        try:
            # Recreate signature without the signature field
            candidate_dict = asdict(candidate)
            candidate_dict.pop('signature', None)
            # Handle enum serialization
            if 'time_source' in candidate_dict and hasattr(candidate_dict['time_source'], 'value'):
                candidate_dict['time_source'] = candidate_dict['time_source'].value
            payload = json.dumps(candidate_dict, sort_keys=True, separators=(',', ':'))
            
            expected_sig = hmac.new(
                self.hmac_key.encode(), 
                payload.encode(), 
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(candidate.signature, expected_sig)
        except Exception:
            return False
    
    def _validate_target_stop(self, candidate: TradeCandidateV1) -> bool:
        """Validate target/stop coherence"""
        if candidate.side == "buy":
            return candidate.target > candidate.entry > candidate.stop
        else:
            return candidate.target < candidate.entry < candidate.stop

class AuditLogger:
    """Atomic file logging with rotation"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self._backpressure_threshold = 1000
        self._current_backlog = 0
    
    def log_candidate(self, candidate: TradeCandidateV1, status: ContractStatus, reason: str):
        """Log candidate with atomic write"""
        try:
            # Apply backpressure control
            if self._current_backlog > self._backpressure_threshold:
                if status == ContractStatus.OK:
                    return  # Drop OK candidates under backpressure

            # Create log entry with both timestamp and snapshot_ts (epoch seconds)
            current_ts = int(time.time())
            entry = {
                "timestamp": current_ts,  # epoch seconds (int)
                "snapshot_ts": current_ts,  # duplicate for compatibility
                "trace_id": candidate.trace_id,
                "symbol": candidate.symbol,
                "side": candidate.side,
                "status": status.value,
                "reason": reason,
                "age_sec": candidate.age_sec,
                "net_confidence": candidate.net_confidence,
                "risk_reward": candidate.risk_reward_ratio,
                "target_origin": candidate.target_origin
            }

            # Write to canonical path: shared_data/logs/candidates.ndjson
            log_file = Path("shared_data/logs/candidates.ndjson")
            log_file.parent.mkdir(parents=True, exist_ok=True)

            # Append with UTF-8, no BOM
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

            self._current_backlog += 1
            
        except Exception as e:
            print(f"Audit log error: {e}")
    
    def log_ui_snapshot(self, symbol: str, snapshot_data: Dict[str, Any]):
        """Log UI snapshot with atomic write"""
        try:
            entry = {
                "timestamp": time.time(),
                "symbol": symbol,
                "snapshot": snapshot_data
            }
            
            log_file = self.log_dir / "ui_snapshots.ndjson"
            temp_file = log_file.with_suffix('.tmp')
            
            with open(temp_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
            
            temp_file.replace(log_file)
            
        except Exception as e:
            print(f"UI snapshot log error: {e}")
    
    def rotate_logs(self):
        """Daily log rotation"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            
            # Rotate candidates
            candidates_file = self.log_dir / "candidates.ndjson"
            if candidates_file.exists():
                rotated_file = self.log_dir / f"candidates-{today}.ndjson"
                candidates_file.rename(rotated_file)
            
            # Rotate UI snapshots
            snapshots_file = self.log_dir / "ui_snapshots.ndjson"
            if snapshots_file.exists():
                rotated_file = self.log_dir / f"ui_snapshots-{today}.ndjson"
                snapshots_file.rename(rotated_file)
            
            # Create current symlink (Windows-safe)
            current_link = self.log_dir / "current"
            if current_link.exists():
                current_link.unlink()
            current_link.symlink_to(f"candidates-{today}.ndjson")
            
        except Exception as e:
            print(f"Log rotation error: {e}")

class AuditSummary:
    """Daily audit summary generator"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.reports_dir = Path("shared_data/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_summary(self, date_str: Optional[str] = None) -> str:
        """Generate daily audit summary"""
        if not date_str:
            yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday = yesterday.replace(day=yesterday.day - 1)
            date_str = yesterday.strftime("%Y%m%d")
        
        log_file = self.log_dir / f"candidates-{date_str}.ndjson"
        
        if not log_file.exists():
            return f"No audit data found for {date_str}"
        
        # Parse log entries
        entries = []
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        except Exception as e:
            return f"Error reading log file: {e}"
        
        # Generate summary
        summary = self._create_summary_report(entries, date_str)
        
        # Save to file
        summary_file = self.reports_dir / f"contract_audit_summary_{date_str}.md"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        return summary
    
    def _create_summary_report(self, entries: List[Dict], date_str: str) -> str:
        """Create markdown summary report"""
        total_entries = len(entries)
        
        # Count by status
        status_counts = {}
        symbol_counts = {}
        target_origins = {}
        
        for entry in entries:
            status = entry.get('status', 'unknown')
            symbol = entry.get('symbol', 'unknown')
            origin = entry.get('target_origin', 'unknown')
            
            status_counts[status] = status_counts.get(status, 0) + 1
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
            target_origins[origin] = target_origins.get(origin, 0) + 1
        
        # Top 5 symbols by anomaly count
        anomaly_symbols = sorted(
            [(symbol, count) for symbol, count in symbol_counts.items()],
            key=lambda x: x[1], reverse=True
        )[:5]
        
        # Generate report
        report = f"""# Contract Audit Summary - {date_str}

## Totals
- **Total entries**: {total_entries}
- **OK**: {status_counts.get('ok', 0)}
- **Blocked by contract**: {status_counts.get('blocked_by_contract', 0)}
- **Stale blocked**: {status_counts.get('stale', 0)}
- **Bad signature**: {status_counts.get('bad_signature', 0)}
- **Invalid target**: {status_counts.get('invalid_target', 0)}
- **Low RR**: {status_counts.get('low_rr', 0)}

## Top 5 Symbols by Activity
"""
        
        for symbol, count in anomaly_symbols:
            report += f"- **{symbol}**: {count} entries\n"
        
        report += "\n## Target Origin Distribution\n"
        total_origins = sum(target_origins.values())
        for origin, count in target_origins.items():
            pct = (count / total_origins * 100) if total_origins > 0 else 0
            report += f"- **{origin}**: {count} ({pct:.1f}%)\n"
        
        # Example trace IDs
        report += "\n## Example Trace IDs\n"
        for entry in entries[:3]:  # First 3 entries
            trace_id = entry.get('trace_id', 'N/A')
            symbol = entry.get('symbol', 'N/A')
            status = entry.get('status', 'N/A')
            report += f"- `{trace_id}` ({symbol}, {status})\n"
        
        return report

# Global instances
validator = ContractValidator()
logger = AuditLogger()
summary_generator = AuditSummary()

def create_candidate(
    symbol: str,
    side: str,
    entry: float,
    target: float,
    stop: float,
    confidence: float,
    cost_bps: float = 0.0,
    target_origin: str = "unknown",
    time_source: TimeSource = TimeSource.EXCHANGE
) -> TradeCandidateV1:
    """Create a new trade candidate with audit trail"""
    now = time.time()
    return TradeCandidateV1(
        symbol=symbol,
        side=side,
        entry=entry,
        target=target,
        stop=stop,
        confidence=confidence,
        cost_bps=cost_bps,
        snapshot_ts=now,
        expires_at=now + 300,  # 5 minutes
        time_source=time_source,
        target_origin=target_origin
    )

def validate_and_log(candidate: TradeCandidateV1) -> Tuple[ContractStatus, str]:
    """Validate candidate and log result"""
    status, reason = validator.validate(candidate)
    logger.log_candidate(candidate, status, reason)
    return status, reason

def log_ui_snapshot(symbol: str, snapshot_data: Dict[str, Any]):
    """Log UI snapshot for audit trail"""
    logger.log_ui_snapshot(symbol, snapshot_data)

def generate_daily_summary(date_str: Optional[str] = None) -> str:
    """Generate daily audit summary"""
    return summary_generator.generate_summary(date_str)

def rotate_audit_logs():
    """Rotate audit logs (call daily)"""
    logger.rotate_logs()
