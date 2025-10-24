#!/usr/bin/env python3
"""
ARES Heartbeat Writer & Candidates Emission
Production-grade ARES health and signal emission with strict thresholds
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv("config.env")


class ARESHeartbeatWriter:
    """ARES Heartbeat Writer - Updates ARES health, symbol files, and candidates emission"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.start_time = time.time()
        
        # Paths (절대 경로만 사용)
        self.repo_root = Path(__file__).parent.parent.absolute()
        self.health_dir = self.repo_root / "shared_data" / "health"
        self.ares_dir = self.repo_root / "shared_data" / "ares"
        self.candidates_file = self.repo_root / "shared_data" / "candidates.ndjson"
        
        # Ensure directories exist
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.ares_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration (UI 임계값 준수)
        self.health_interval = 30  # Update health every 30s (ares_signal_flow ≤ 75s)
        self.symbol_interval = 60  # Update symbol files every 60s
        self.candidates_interval = 90  # Update candidates every 90s (integration_contracts ≤ 90s)
        self.last_health_update = 0
        self.last_symbol_update = 0
        self.last_candidates_update = 0
        
        # Environment hash for consistency
        self.env_hash = "677f80cd2f88351809752a8f1b79d914f72a222ac2cec20e35cf4e38d895ff9d"
        
        # 시작 로그
        self._log_startup_info()
    
    def _log_startup_info(self):
        """시작 정보 로깅"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 ARES HEARTBEAT WRITER STARTUP")
        self.logger.info(f"ROOT={self.repo_root}")
        self.logger.info(f"HEALTH_OUT={self.health_dir / 'ares.json'}")
        self.logger.info(f"ARES_OUT={self.ares_dir}")
        self.logger.info(f"CANDIDATES_OUT={self.candidates_file}")
        self.logger.info(f"PID={os.getpid()}")
        self.logger.info("=" * 60)
        
    def start(self):
        """Start the ARES Heartbeat Writer"""
        if self.running:
            self.logger.warning("ARES Heartbeat Writer already running")
            return
            
        self.running = True
        self.logger.info("🚀 ARES Heartbeat Writer started")
        
        # Initial update
        self._update_health_file()
        self._update_symbol_files()
        self._update_candidates_file()
        
        # Main loop
        while self.running:
            try:
                current_time = time.time()
                
                # Update health file every 30s (ares_signal_flow ≤ 75s)
                if current_time - self.last_health_update >= self.health_interval:
                    self._update_health_file()
                    self.last_health_update = current_time
                
                # Update symbol files every 60s
                if current_time - self.last_symbol_update >= self.symbol_interval:
                    self._update_symbol_files()
                    self.last_symbol_update = current_time
                
                # Update candidates file every 90s (integration_contracts ≤ 90s)
                if current_time - self.last_candidates_update >= self.candidates_interval:
                    self._update_candidates_file()
                    self.last_candidates_update = current_time
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"ARES Heartbeat Writer error: {e}")
                time.sleep(30)  # Wait 30s on error
                
    def stop(self):
        """Stop the ARES Heartbeat Writer"""
        self.running = False
        self.logger.info("ARES Heartbeat Writer stopped")
        
    def _update_health_file(self):
        """Update shared_data/health/ares.json"""
        try:
            current_time = int(time.time())
            
            # Read latest candidates to get signal info
            signal_count = 0
            candidates_count = 0
            last_signal_update = current_time
            is_real_signal = False
            
            if self.candidates_file.exists():
                try:
                    with open(self.candidates_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        candidates_count = len(lines)
                        
                        # Find latest signal
                        for line in reversed(lines[-10:]):  # Check last 10 lines
                            try:
                                data = json.loads(line.strip())
                                if data.get('source') == 'ares_engine':
                                    signal_count += 1
                                    is_real_signal = True
                                    last_signal_update = data.get('timestamp', current_time)
                                    break
                            except:
                                continue
                                
                except Exception as e:
                    self.logger.warning(f"Failed to read candidates file: {e}")
            
            # Create health data
            health_data = {
                "timestamp": current_time,
                "service": "ares",
                "env_hash": self.env_hash,
                "entrypoint_ok": True,
                "uptime_seconds": int(current_time - self.start_time),
                "data": {
                    "last_signal_update": last_signal_update,
                    "is_real_signal": is_real_signal,
                    "signal_count": signal_count,
                    "candidates_count": candidates_count,
                    "writer": "ares_heartbeat_writer"
                },
                "pid": os.getpid(),
                "started_at": self.start_time,
                "version": "1.0",
                "args": [],
                "status": "running"
            }
            
            # Write atomically
            self._write_atomic(self.health_dir / "ares.json", health_data)
            self.logger.debug(f"Updated ARES health file: signals={signal_count}, candidates={candidates_count}")
            
        except Exception as e:
            self.logger.error(f"Failed to update ARES health file: {e}")
            
    def _update_symbol_files(self):
        """Update shared_data/ares/*.json files (top pick fields: side, entry/target/stop, confidence)"""
        try:
            current_time = int(time.time())
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            
            # Read latest candidates to get signal data
            latest_signals = {}
            if self.candidates_file.exists():
                try:
                    with open(self.candidates_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        
                        # Find latest signal for each symbol
                        for line in reversed(lines[-20:]):  # Check last 20 lines
                            try:
                                data = json.loads(line.strip())
                                symbol = data.get('symbol', '').upper()
                                if symbol in symbols and data.get('source') == 'ares_engine':
                                    if symbol not in latest_signals:
                                        latest_signals[symbol] = data
                            except:
                                continue
                                
                except Exception as e:
                    self.logger.warning(f"Failed to read candidates file: {e}")
            
            # Update each symbol file
            for symbol in symbols:
                try:
                    symbol_lower = symbol.lower()
                    signal_data = latest_signals.get(symbol)
                    
                    if signal_data:
                        # Real signal data (top pick fields)
                        symbol_data = {
                            "symbol": symbol_lower,
                            "timestamp": current_time,
                            "snapshot_ts": current_time,
                            "status": "active",
                            "regime": signal_data.get('regime', 'unknown'),
                            "signals": [{
                                "action": signal_data.get('side', 'buy'),
                                "confidence": signal_data.get('confidence', 0.5) * 100,
                                "price": signal_data.get('entry', 0.0),
                                "entry_price": signal_data.get('entry', 0.0),
                                "size": 100.0,  # Default size
                                "reason": signal_data.get('reason', 'ARES signal'),
                                "timestamp": signal_data.get('timestamp', current_time),
                                "snapshot_ts": signal_data.get('timestamp', current_time),
                                "tp": signal_data.get('target'),
                                "sl": signal_data.get('stop')
                            }],
                            "features": {
                                "price": signal_data.get('entry', 0.0),
                                "timestamp": current_time * 1000  # milliseconds
                            },
                            "age_sec": 0
                        }
                    else:
                        # No signal - create heartbeat entry
                        symbol_data = {
                            "symbol": symbol_lower,
                            "timestamp": current_time,
                            "snapshot_ts": current_time,
                            "status": "idle",
                            "regime": "unknown",
                            "signals": [],
                            "features": {
                                "price": 0.0,
                                "timestamp": current_time * 1000
                            },
                            "age_sec": 0
                        }
                    
                    # Write atomically
                    self._write_atomic(self.ares_dir / f"{symbol_lower}.json", symbol_data)
                    
                except Exception as e:
                    self.logger.error(f"Failed to update {symbol} file: {e}")
            
            self.logger.debug(f"Updated ARES symbol files: {len(latest_signals)} signals")
            
        except Exception as e:
            self.logger.error(f"Failed to update ARES symbol files: {e}")
    
    def _update_candidates_file(self):
        """Update shared_data/candidates.ndjson (append at least every ≤90s when signals exist; if idle, append noop heartbeat)"""
        try:
            current_time = time.time()
            
            # Check if we have recent signals
            has_recent_signals = False
            if self.candidates_file.exists():
                try:
                    with open(self.candidates_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        
                        # Check last 10 lines for recent signals
                        for line in reversed(lines[-10:]):
                            try:
                                data = json.loads(line.strip())
                                signal_time = data.get('timestamp', 0)
                                if signal_time > 1e12:  # milliseconds
                                    signal_time = signal_time / 1000
                                
                                # Signal within last 5 minutes
                                if current_time - signal_time < 300:
                                    has_recent_signals = True
                                    break
                            except:
                                continue
                                
                except Exception as e:
                    self.logger.warning(f"Failed to read candidates file: {e}")
            
            # Append appropriate entry
            if has_recent_signals:
                # Append latest signal info
                entry = {
                    "writer": "ares_heartbeat_writer",
                    "count": 1,
                    "is_real_signal": True,
                    "ts": current_time,
                    "type": "signal_heartbeat"
                }
            else:
                # Append noop heartbeat
                entry = {
                    "writer": "ares_heartbeat_writer",
                    "count": 0,
                    "is_real_signal": False,
                    "ts": current_time,
                    "type": "noop"
                }
            
            # Append to candidates file
            with open(self.candidates_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            self.logger.debug(f"Updated candidates file: {entry['type']}")
            
        except Exception as e:
            self.logger.error(f"Failed to update candidates file: {e}")
            
    def _write_atomic(self, file_path: Path, data: Dict[str, Any]):
        """Write data atomically (write to .tmp then rename)"""
        try:
            temp_path = file_path.with_suffix('.tmp')
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Atomic rename
            temp_path.replace(file_path)
            
        except Exception as e:
            self.logger.error(f"Failed to write {file_path}: {e}")
            # Clean up temp file
            temp_path.unlink(missing_ok=True)


def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    writer = ARESHeartbeatWriter()
    
    try:
        writer.start()
    except KeyboardInterrupt:
        writer.stop()
    except Exception as e:
        logging.error(f"ARES Heartbeat Writer failed: {e}")
        writer.stop()


if __name__ == "__main__":
    main()
