#!/usr/bin/env python3
"""
ARES Service - Candidates Outbox
Appends trading candidates to CANDIDATES file in NDJSON format
"""

import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from shared.io.jsonio import (add_epoch_timestamp, add_expires_at,
                              append_ndjson_nobom, now_epoch_s)
from shared.io.symbol_utils import to_public_symbol
from shared.paths import CANDIDATES, ensure_all_dirs

# Load environment variables
load_dotenv("config.env")

# Desktop notification support
try:
    from plyer import notification
    NOTIFICATION_AVAILABLE = True
except ImportError:
    NOTIFICATION_AVAILABLE = False


class ARESService:
    """ARES Service - Candidates outbox writer"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.thread = None
        
        # Ensure directories exist
        ensure_all_dirs()
        
        # Configuration
        self.candidate_ttl = 120  # 2 minutes TTL
        self.min_confidence = 0.2
        self.max_candidates_per_minute = 10
        self.heartbeat_interval = 75  # 60-90s average (75s)
        
        # Rate limiting
        self.candidate_times = []
        self.last_cleanup = now_epoch_s()
        self.last_heartbeat = 0
        self.last_ares_signal = 0
        
        # Desktop notification
        self.notification_enabled = NOTIFICATION_AVAILABLE
        
    def start(self):
        """Start the ARES service"""
        if self.running:
            self.logger.warning("ARES service already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._cleanup_loop, daemon=False)
        self.thread.start()
        self.logger.info("ARES service started")
        
    def stop(self):
        """Stop the ARES service"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("ARES service stopped")
        
    def _cleanup_loop(self):
        """Cleanup expired candidates and emit heartbeats"""
        backoff_seconds = 0.5
        max_backoff = 30
        
        while self.running:
            try:
                current_time = now_epoch_s()
                
                # Clean up old candidate times (rate limiting)
                self.candidate_times = [
                    t for t in self.candidate_times 
                    if current_time - t < 60  # Keep last minute
                ]
                
                # Clean up old candidates from file (every 5 minutes)
                if current_time - self.last_cleanup > 300:
                    self._cleanup_expired_candidates()
                    self.last_cleanup = current_time
                
                # Generate actual ARES signals every 150s (2.5 minutes)
                if current_time - self.last_ares_signal > 150:
                    self._generate_ares_signals()
                    self.last_ares_signal = current_time
                
                # Emit heartbeat candidate every 75s when idle
                if current_time - self.last_heartbeat > self.heartbeat_interval:
                    self._emit_heartbeat_candidate()
                    self.last_heartbeat = current_time
                
                # Reset backoff on successful iteration
                backoff_seconds = 0.5
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                # Log crash evidence
                from shared.crash_evidence import log_crash
                log_crash(e, "ARES cleanup loop", f"ares_cleanup_{now_epoch_s()}")
                
                # Exponential backoff on errors
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, max_backoff)
                
    def _cleanup_expired_candidates(self):
        """Remove expired candidates from file"""
        try:
            if not CANDIDATES.exists():
                return
                
            from shared.io.jsonio import read_ndjson_lines

            # Read all lines
            lines = read_ndjson_lines(CANDIDATES)
            current_time = int(time.time())
            
            # Filter out expired candidates
            valid_lines = []
            for line in lines:
                expires_at = line.get('expires_at', 0)
                if expires_at > current_time:
                    valid_lines.append(line)
                    
            # Write back valid lines
            if len(valid_lines) < len(lines):
                # Backup original file
                backup_path = CANDIDATES.with_suffix('.backup')
                CANDIDATES.rename(backup_path)
                
                # Write valid lines
                for line in valid_lines:
                    append_ndjson_nobom(CANDIDATES, line)
                    
                # Remove backup
                backup_path.unlink(missing_ok=True)
                
                self.logger.info(f"Cleaned up {len(lines) - len(valid_lines)} expired candidates")
                
        except Exception as e:
            self.logger.error(f"Cleanup expired candidates error: {e}")
            
    def _emit_heartbeat_candidate(self):
        """Emit a periodic heartbeat candidate"""
        try:
            current_time = now_epoch_s()
            
            # Rate limit: max 1 heartbeat per minute when idle
            if len(self.candidate_times) > 0:
                last_candidate_time = max(self.candidate_times)
                if current_time - last_candidate_time < 60:
                    return  # Skip heartbeat if we had a candidate within 60s
            
            # Create heartbeat candidate
            candidate = {
                "symbol": to_public_symbol("BTCUSDT"),
                "side": "buy",
                "entry": 50000.0,  # Dummy price
                "target": 51000.0,
                "stop": 49000.0,
                "regime": "heartbeat",
                "confidence": 0.5,  # Medium strength for heartbeat
                "reason": "Periodic heartbeat",
                "strategy": "ARES",
                "trace_id": f"hb_{current_time}",
                "timestamp": current_time,
                "expires_at": current_time + self.candidate_ttl,
                "source": "heartbeat"
            }
            
            # Append to candidates file
            append_ndjson_nobom(CANDIDATES, candidate)
            self.logger.debug(f"Heartbeat candidate emitted: {candidate['trace_id']}")
            
        except Exception as e:
            self.logger.error(f"Emit heartbeat candidate error: {e}")
    
    def _generate_ares_signals(self):
        """Generate actual ARES trading signals"""
        try:
            # Import ARES here to avoid circular imports
            from optimizer.ares import ARES

            # Initialize ARES
            ares = ARES()
            
            # Get active symbols
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            
            for symbol in symbols:
                try:
                    # Generate signal for symbol
                    signal = ares.select(symbol)
                    
                    if signal:
                        # Convert ARES signal to candidate
                        candidate = {
                            "symbol": to_public_symbol(symbol),
                            "side": signal.action.lower(),
                            "entry": float(signal.px),
                            "target": float(signal.tp),
                            "stop": float(signal.sl),
                            "regime": signal.regime,
                            "confidence": float(signal.conf),
                            "reason": signal.reason,
                            "strategy": signal.strategy,
                            "trace_id": f"ares_{now_epoch_s()}_{symbol.lower()}",
                            "timestamp": now_epoch_s(),
                            "expires_at": now_epoch_s() + self.candidate_ttl,
                            "source": "ares_engine"
                        }
                        
                        # Append to candidates file
                        append_ndjson_nobom(CANDIDATES, candidate)
                        
                        # Show notification
                        self._show_notification(symbol, signal.action, signal.px, signal.conf)
                        
                        self.logger.info(f"ARES signal generated: {symbol} {signal.action} @{signal.px} (conf={signal.conf:.2f})")
                        
                        # Rate limiting
                        self.candidate_times.append(time.time())
                        
                        # Only generate one signal per cycle to avoid spam
                        break
                    else:
                        # No signal generated, check if we should emit default signal
                        test_allow_default = os.getenv("TEST_ALLOW_DEFAULT_SIGNAL", "false").lower() == "true"
                        if test_allow_default:
                            # Emit minimal default candidate
                            default_candidate = {
                                "symbol": to_public_symbol(symbol),
                                "side": "buy",
                                "entry": 50000.0,
                                "target": 51000.0,
                                "stop": 49000.0,
                                "regime": "default",
                                "confidence": 0.3,
                                "reason": "Default signal (no real signal generated)",
                                "strategy": "ARES",
                                "trace_id": f"default_{now_epoch_s()}_{symbol.lower()}",
                                "timestamp": now_epoch_s(),
                                "expires_at": now_epoch_s() + self.candidate_ttl,
                                "source": "ares_engine"
                            }
                            
                            append_ndjson_nobom(CANDIDATES, default_candidate)
                            self.logger.info(f"Default signal generated: {symbol} BUY @50000.0 (conf=0.30)")
                            self.candidate_times.append(time.time())
                            break
                        
                except Exception as e:
                    self.logger.error(f"ARES signal generation error for {symbol}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"ARES signal generation error: {e}")
            
    def emit_candidate(self, 
                      symbol: str,
                      side: str,
                      entry: float,
                      target: float,
                      stop: float,
                      regime: str = "unknown",
                      confidence: float = 0.5,
                      reason: str = "",
                      strategy: str = "ARES",
                      trace_id: str = None) -> bool:
        """
        Emit a trading candidate
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: "buy" or "sell"
            entry: Entry price
            target: Target price
            stop: Stop loss price
            regime: Market regime
            confidence: Signal confidence (0-1)
            reason: Signal reason
            strategy: Strategy name
            trace_id: Unique trace ID
            
        Returns:
            True if candidate was emitted successfully
        """
        try:
            # Rate limiting check
            if not self._check_rate_limit():
                self.logger.warning("Rate limit exceeded, skipping candidate")
                return False
                
            # Validate inputs
            if not self._validate_candidate(symbol, side, entry, target, stop, confidence):
                return False
                
            # Generate trace ID if not provided
            if not trace_id:
                trace_id = f"ares_{now_epoch_s()}_{uuid.uuid4().hex[:8]}"
                
            # Create candidate data
            current_time = now_epoch_s()
            candidate = {
                "symbol": to_public_symbol(symbol),
                "side": side.lower(),
                "entry": float(entry),
                "target": float(target),
                "stop": float(stop),
                "regime": regime,
                "confidence": float(confidence),
                "reason": reason,
                "strategy": strategy,
                "trace_id": trace_id,
                "timestamp": current_time,
                "expires_at": current_time + self.candidate_ttl
            }
            
            # Timestamps already added above
            
            # Append to candidates file
            append_ndjson_nobom(CANDIDATES, candidate)
            
            # Update rate limiting
            self.candidate_times.append(time.time())
            
            # Show desktop notification
            self._show_notification(symbol, side, entry, confidence)
            
            self.logger.info(f"Candidate emitted: {symbol} {side} @{entry} (conf={confidence:.2f})")
            return True
            
        except Exception as e:
            self.logger.error(f"Emit candidate error: {e}")
            return False
            
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        current_time = now_epoch_s()
        
        # Check candidates per minute
        recent_candidates = [
            t for t in self.candidate_times 
            if current_time - t < 60
        ]
        
        return len(recent_candidates) < self.max_candidates_per_minute
        
    def _show_notification(self, symbol: str, side: str, entry: float, confidence: float):
        """Show desktop notification for signal"""
        if not self.notification_enabled:
            return
            
        try:
            # Format notification
            side_emoji = "🟢" if side.lower() == "buy" else "🔴"
            side_text = "매수" if side.lower() == "buy" else "매도"
            
            title = f"{side_emoji} ARES {side_text} 신호"
            message = f"{symbol} @ ${entry:,.2f}\n신뢰도: {confidence*100:.0f}%"
            
            # Show notification
            notification.notify(
                title=title,
                message=message,
                timeout=10,
                app_icon=None
            )
        except Exception as e:
            self.logger.debug(f"Notification error: {e}")
    
    def _validate_candidate(self, symbol: str, side: str, entry: float, 
                           target: float, stop: float, confidence: float) -> bool:
        """Validate candidate data"""
        try:
            # Symbol validation
            if not symbol or not isinstance(symbol, str):
                self.logger.error("Invalid symbol")
                return False
                
            # Side validation
            if side.lower() not in ['buy', 'sell']:
                self.logger.error(f"Invalid side: {side}")
                return False
                
            # Price validation
            if not all(isinstance(p, (int, float)) and p > 0 for p in [entry, target, stop]):
                self.logger.error("Invalid prices")
                return False
                
            # Confidence validation
            if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
                self.logger.error(f"Invalid confidence: {confidence}")
                return False
                
            # Logic validation
            if side.lower() == 'buy':
                if target <= entry or stop >= entry:
                    self.logger.error("Invalid buy logic: target <= entry or stop >= entry")
                    return False
            else:  # sell
                if target >= entry or stop <= entry:
                    self.logger.error("Invalid sell logic: target >= entry or stop <= entry")
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            return False
            
    def get_recent_candidates(self, max_candidates: int = 10) -> List[Dict[str, Any]]:
        """Get recent candidates"""
        try:
            from shared.io.jsonio import read_ndjson_lines
            
            if not CANDIDATES.exists():
                return []
                
            lines = read_ndjson_lines(CANDIDATES, max_candidates)
            current_time = now_epoch_s()
            
            # Filter out expired candidates
            valid_candidates = []
            for line in lines:
                expires_at = line.get('expires_at', 0)
                if expires_at > current_time:
                    valid_candidates.append(line)
                    
            return valid_candidates
            
        except Exception as e:
            self.logger.error(f"Get recent candidates error: {e}")
            return []
            
    def get_candidate_count(self) -> int:
        """Get current candidate count"""
        try:
            from shared.io.jsonio import read_ndjson_lines
            
            if not CANDIDATES.exists():
                return 0
                
            lines = read_ndjson_lines(CANDIDATES)
            current_time = now_epoch_s()
            
            # Count valid candidates
            valid_count = 0
            for line in lines:
                expires_at = line.get('expires_at', 0)
                if expires_at > current_time:
                    valid_count += 1
                    
            return valid_count
            
        except Exception as e:
            self.logger.error(f"Get candidate count error: {e}")
            return 0
            
    def inject_test_candidate(self, symbol: str = "BTCUSDT") -> bool:
        """Inject a test candidate for E2E testing"""
        try:
            # Get current price (mock)
            current_price = 50000.0  # Mock price
            
            # Generate test candidate
            return self.emit_candidate(
                symbol=symbol,
                side="buy",
                entry=current_price * 0.999,  # Slightly below current price
                target=current_price * 1.01,   # 1% target
                stop=current_price * 0.98,     # 2% stop
                regime="bull",
                confidence=0.7,
                reason="E2E test candidate",
                strategy="TEST",
                trace_id=f"test_{int(time.time())}"
            )
            
        except Exception as e:
            self.logger.error(f"Inject test candidate error: {e}")
            return False


# Global instance
_ares_service = None


def get_ares_service() -> ARESService:
    """Get global ARES service instance"""
    global _ares_service
    if _ares_service is None:
        _ares_service = ARESService()
    return _ares_service


def start_ares_service():
    """Start the global ARES service"""
    get_ares_service().start()


def stop_ares_service():
    """Stop the global ARES service"""
    global _ares_service
    if _ares_service:
        _ares_service.stop()
        _ares_service = None


def emit_candidate(symbol: str, side: str, entry: float, target: float, 
                  stop: float, **kwargs) -> bool:
    """Emit a candidate using the global service"""
    return get_ares_service().emit_candidate(
        symbol=symbol, side=side, entry=entry, target=target, stop=stop, **kwargs
    )


def main():
    """Main entry point for ARES service"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info("ENTRYPOINT_OK module=guard.optimizer.ares_service")
    
    service = ARESService()
    service.start()
    
    try:
        # Keep running indefinitely
        while True:
            time.sleep(60)  # Sleep for 1 minute intervals
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    finally:
        service.stop()


# Export main function
__all__ = ["main"]


if __name__ == "__main__":
    main()
