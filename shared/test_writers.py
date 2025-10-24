#!/usr/bin/env python3
"""
Test Writers for Self-Test
Lightweight test writers that update all health targets
"""

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List

from .centralized_path_registry import get_path_registry
from .heartbeat_writer import get_heartbeat_writer


class TestWriter:
    """테스트 라이터"""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.path_registry = get_path_registry(repo_root)
        self.running = False
        self.threads: List[threading.Thread] = []
        
        # 테스트 라이터들
        self.writers = {
            "positions": self._write_positions,
            "ares": self._write_ares,
            "trader": self._write_trader,
            "feeder": self._write_feeder,
            "ssot": self._write_ssot,
            "candidates": self._write_candidates
        }
    
    def start_test_writers(self, duration: int = 30) -> bool:
        """테스트 라이터 시작"""
        if self.running:
            return False
        
        self.running = True
        print(f"🧪 Starting test writers for {duration} seconds...")
        
        # 각 라이터를 별도 스레드에서 실행
        for name, writer_func in self.writers.items():
            thread = threading.Thread(
                target=self._run_writer,
                args=(name, writer_func, duration),
                daemon=True
            )
            thread.start()
            self.threads.append(thread)
        
        return True
    
    def stop_test_writers(self):
        """테스트 라이터 중지"""
        if not self.running:
            return
        
        self.running = False
        print("🛑 Stopping test writers...")
        
        # 모든 스레드 종료 대기
        for thread in self.threads:
            thread.join(timeout=5)
        
        self.threads.clear()
        print("✅ Test writers stopped")
    
    def _run_writer(self, name: str, writer_func, duration: int):
        """라이터 실행"""
        start_time = time.time()
        
        while self.running and (time.time() - start_time) < duration:
            try:
                writer_func()
                time.sleep(10)  # 10초마다 업데이트
            except Exception as e:
                print(f"❌ Test writer {name} error: {e}")
                break
    
    def _write_positions(self):
        """포지션 테스트 데이터 작성"""
        writer = get_heartbeat_writer("positions", self.repo_root)
        
        # 테스트 포지션 데이터
        test_positions = [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "size": 0.001,
                "entry_price": 67000.0,
                "unrealized_pnl": 12.5
            }
        ]
        
        success = writer.write_positions_snapshot(test_positions)
        if success:
            print(f"✅ Positions test data written")
    
    def _write_ares(self):
        """ARES 테스트 데이터 작성"""
        writer = get_heartbeat_writer("ares", self.repo_root)
        
        # 테스트 ARES 데이터
        ares_data = {
            "last_signal_update": int(time.time()),
            "is_real_signal": False,
            "signal_count": 0,
            "candidates_count": 0,
            "test_mode": True
        }
        
        success = writer.write_heartbeat(ares_data)
        if success:
            print(f"✅ ARES test data written")
    
    def _write_trader(self):
        """트레이더 테스트 데이터 작성"""
        writer = get_heartbeat_writer("trader", self.repo_root)
        
        # 테스트 트레이더 데이터
        trader_data = {
            "last_rest_ok_ts": int(time.time()),
            "exchange_info_loaded": True,
            "balances": {
                "fresh_ts": int(time.time())
            },
            "circuit_breaker": {
                "active": False,
                "since": 0
            },
            "test_mode": True
        }
        
        success = writer.write_heartbeat(trader_data)
        if success:
            print(f"✅ Trader test data written")
    
    def _write_feeder(self):
        """피더 테스트 데이터 작성"""
        writer = get_heartbeat_writer("feeder", self.repo_root)
        
        # 테스트 피더 데이터
        feeder_data = {
            "prices_data": {
                "symbols": ["btcusdt", "ethusdt", "solusdt"],
                "symbol_count": 3
            },
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "symbol_count": 3,
            "last_price_update": int(time.time()),
            "test_mode": True
        }
        
        success = writer.write_heartbeat(feeder_data)
        if success:
            print(f"✅ Feeder test data written")
    
    def _write_ssot(self):
        """SSOT 테스트 데이터 작성"""
        writer = get_heartbeat_writer("feeder", self.repo_root)  # SSOT는 feeder가 작성
        
        # 테스트 SSOT 데이터
        ssot_data = {
            "mode": "TESTNET",
            "base_url": "https://testnet.binance.vision",
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "git_hash": "test123",
            "env_hash": "test_hash",
            "writer": "feeder",
            "test_mode": True
        }
        
        success = writer.write_ssot_env(ssot_data)
        if success:
            print(f"✅ SSOT test data written")
    
    def _write_candidates(self):
        """candidates.ndjson 테스트 데이터 작성"""
        writer = get_heartbeat_writer("ares", self.repo_root)
        
        # 테스트 candidates 데이터
        test_candidates = [
            {
                "symbol": "BTCUSDT",
                "signal": "BUY",
                "strength": 0.75,
                "timestamp": int(time.time())
            }
        ]
        
        success = writer.write_candidates_ndjson(test_candidates, is_real_signal=False)
        if success:
            print(f"✅ Candidates test data written")


def run_self_test(repo_root: Path, duration: int = 30) -> bool:
    """자체 테스트 실행"""
    test_writer = TestWriter(repo_root)
    
    try:
        # 테스트 라이터 시작
        if not test_writer.start_test_writers(duration):
            print("❌ Failed to start test writers")
            return False
        
        print(f"🧪 Test writers running for {duration} seconds...")
        print("📊 Monitor the Debug panel to see ages falling to < 5s")
        
        # 지정된 시간 대기
        time.sleep(duration)
        
        # 테스트 라이터 중지
        test_writer.stop_test_writers()
        
        print("✅ Self-test completed")
        return True
        
    except Exception as e:
        print(f"❌ Self-test failed: {e}")
        test_writer.stop_test_writers()
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        duration = int(sys.argv[1])
    else:
        duration = 30
    
    project_root = Path(__file__).parent.parent
    success = run_self_test(project_root, duration)
    sys.exit(0 if success else 1)
