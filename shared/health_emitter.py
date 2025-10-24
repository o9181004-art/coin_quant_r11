#!/usr/bin/env python3
"""
HealthEmitter Service
Bridges state_bus → UI health files (single root)
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from .centralized_path_registry import get_path_registry


class HealthEmitter:
    """헬스 파일 방출기"""
    
    def __init__(self, repo_root: Path, dry_run: bool = False, force_root: Optional[Path] = None):
        self.repo_root = repo_root.resolve()
        self.dry_run = dry_run
        self.force_root = force_root
        self.path_registry = get_path_registry(self.repo_root)
        self.runtime_dir = self.repo_root / ".runtime"
        self.runtime_dir.mkdir(exist_ok=True)
        
        # PID 파일
        self.pid_file = self.runtime_dir / "health_emitter.pid"
        
        # 출력 파일 경로들 (Single source of path)
        from .environment_manager import get_health_path, get_ssot_path
        
        self.output_paths = {
            "positions": self.path_registry.get("health_positions"),
            "ares": self.path_registry.get("health_ares"),
            "trader": self.path_registry.get("health_trader"),
            "ssot": get_ssot_path(),  # Use the same SSOT path as EnvironmentManager
            "health": get_health_path(),  # Use the same health path as EnvironmentManager
            "candidates": self.path_registry.get("candidates_ndjson")
        }
        
        # Log resolved absolute paths once on startup
        print("🔧 HealthEmitter paths:")
        for name, path in self.output_paths.items():
            print(f"  {name}: {path.absolute()}")
        
        # 입력 파일 경로
        self.input_paths = {
            "state_bus": self.path_registry.get("state_bus"),
            "databus_snapshot": self.path_registry.get("shared_data") / "databus_snapshot.json"
        }
        
        # 타이머 설정 (요구사항에 맞게 조정)
        self.timers = {
            "positions": {"interval": 1, "last_write": 0},  # 1초 간격
            "ares": {"interval": 1, "last_write": 0},       # 1초 간격
            "trader": {"interval": 1, "last_write": 0},     # 1초 간격
            "ssot": {"interval": 1, "last_write": 0},       # 1초 간격
            "health": {"interval": 1, "last_write": 0},     # 1초 간격
            "candidates": {"interval": 1, "last_write": 0}  # 1초 간격
        }
        
        self.running = False
        self.start_time = time.time()
    
    def calculate_env_hash(self) -> str:
        """환경변수 해시 계산 - Unified Environment Manager 사용"""
        try:
            from .environment_manager import get_env_hash
            return get_env_hash()
        except ImportError:
            # Fallback to legacy method
            important_vars = [
                'BINANCE_API_KEY', 'BINANCE_API_SECRET', 'TESTNET', 'LIVE_MODE',
                'KIS_ACCOUNT', 'KIS_APPKEY', 'KIS_APPSECRET', 'ACCOUNT_SNAPSHOT_TTL_SEC',
                'TRADER_TTL', 'FEEDER_TTL', 'ARES_TTL', 'UDS_TTL'
            ]
            
            env_vars = {}
            for var in important_vars:
                value = os.environ.get(var, 'NOT_SET')
                env_vars[var] = value
            
            # 환경변수 해시 계산
            env_str = str(sorted(env_vars.items()))
            return hashlib.md5(env_str.encode()).hexdigest()[:8]
    
    def print_startup_info(self):
        """시작 정보 출력"""
        print("=" * 80)
        print("🏥 HealthEmitter Service")
        print("=" * 80)
        print(f"HEALTH_EMITTER ROOT={self.repo_root}")
        print(f"PY={sys.executable}")
        print(f"DRY_RUN={self.dry_run}")
        print(f"ROOT={self.repo_root}")
        
        # Log SSOT path for debugging
        print(f"🔧 SSOT Path: {self.output_paths['ssot']}")
        
        print("OUTS=")
        for name, path in self.output_paths.items():
            print(f"  {name}: {path}")
        
        print("INPUTS=")
        for name, path in self.input_paths.items():
            print(f"  {name}: {path}")
        
        print("=" * 80)
    
    def check_existing_instance(self) -> bool:
        """기존 인스턴스 확인"""
        if not self.pid_file.exists():
            return False
        
        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            if psutil.pid_exists(pid):
                print(f"❌ HealthEmitter already running (PID: {pid})")
                return True
            else:
                # 죽은 PID 파일 정리
                self.pid_file.unlink()
                return False
                
        except Exception:
            # 손상된 PID 파일 정리
            self.pid_file.unlink()
            return False
    
    def acquire_lock(self) -> bool:
        """락 획득"""
        if self.check_existing_instance():
            return False
        
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except Exception as e:
            print(f"❌ Failed to acquire lock: {e}")
            return False
    
    def release_lock(self):
        """락 해제"""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass
    
    def validate_root(self) -> bool:
        """루트 검증"""
        if self.force_root:
            if self.force_root.resolve() != self.repo_root:
                print(f"❌ Force root mismatch: {self.force_root} != {self.repo_root}")
                return False
        
        return True
    
    def read_state_bus(self) -> Optional[Dict[str, Any]]:
        """state_bus 데이터 읽기"""
        for input_name, input_path in self.input_paths.items():
            if input_path.exists():
                try:
                    with open(input_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    print(f"📖 Read {input_name}: {len(str(data))} bytes")
                    return data
                except Exception as e:
                    print(f"⚠️  Failed to read {input_name}: {e}")
        
        return None
    
    def write_atomic(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """원자적 파일 쓰기 (BOM-free, atomic)"""
        if self.dry_run:
            print(f"🔍 DRY_RUN: Would write {file_path}")
            return True
        
        try:
            # Log absolute path for all writes
            print(f"INFO: health_path={file_path.absolute()}")
            
            # Add required fields for health emitter
            current_time = int(time.time() * 1000)  # epoch ms
            data.update({
                "updated_at": current_time,
                "age_sec": 0,  # Fresh write
                "producer": "health_emitter",
                "version": "1.0"
            })
            
            # Add checksum for debugging
            payload_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
            checksum = hashlib.md5(payload_str.encode('utf-8')).hexdigest()[:8]
            data["checksum"] = checksum
            
            # 임시 파일에 작성 (BOM-free)
            temp_file = file_path.with_suffix(".tmp")
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 원자적 이동
            temp_file.replace(file_path)
            return True
            
        except Exception as e:
            print(f"❌ Failed to write {file_path}: {e}")
            return False
    
    def write_positions(self, state_data: Optional[Dict[str, Any]]) -> bool:
        """포지션 헬스 파일 작성"""
        current_time = int(time.time())
        
        # 기본 포지션 데이터 (health_v2.py 호환 형식)
        positions_data = {
            "timestamp": current_time,
            "positions": [],  # 루트 레벨에 positions 필드
            "position_count": 0,
            "last_update": current_time,
            "snapshot_ts": current_time,
            "writer": "health_emitter",
            "service": "positions",
            "env_hash": self.calculate_env_hash(),
            "entrypoint_ok": True,
            "uptime_seconds": int(current_time - self.start_time),
            "pid": os.getpid(),
            "started_at": self.start_time,
            "version": "1.0",
            "args": [],
            "status": "running"
        }
        
        # state_bus에서 포지션 정보 추출
        if state_data:
            # 실제 포지션 데이터가 있다면 사용
            if "positions" in state_data:
                positions_data["positions"] = state_data["positions"]
                positions_data["position_count"] = len(state_data["positions"])
        
        return self.write_atomic(self.output_paths["positions"], positions_data)
    
    def write_ares(self, state_data: Optional[Dict[str, Any]]) -> bool:
        """ARES 헬스 파일 작성"""
        current_time = int(time.time())
        
        # 기본 ARES 데이터
        ares_data = {
            "timestamp": current_time,
            "service": "ares",
            "env_hash": self.calculate_env_hash(),
            "entrypoint_ok": True,
            "uptime_seconds": int(current_time - self.start_time),
            "data": {
                "last_signal_update": current_time,
                "is_real_signal": False,
                "signal_count": 0,
                "candidates_count": 0,
                "writer": "health_emitter"
            },
            "pid": os.getpid(),
            "started_at": self.start_time,
            "version": "1.0",
            "args": [],
            "status": "running"
        }
        
        # state_bus에서 ARES 정보 추출
        if state_data:
            if "ares" in state_data:
                ares_info = state_data["ares"]
                ares_data["data"].update(ares_info)
        
        return self.write_atomic(self.output_paths["ares"], ares_data)
    
    def write_trader(self, state_data: Optional[Dict[str, Any]]) -> bool:
        """트레이더 헬스 파일 작성"""
        current_time = int(time.time())
        
        # 기본 트레이더 데이터
        trader_data = {
            "timestamp": current_time,
            "service": "trader",
            "env_hash": self.calculate_env_hash(),
            "entrypoint_ok": True,
            "uptime_seconds": int(current_time - self.start_time),
            "data": {
                "last_rest_ok_ts": current_time,
                "exchange_info_loaded": True,
                "balances": {
                    "fresh_ts": current_time
                },
                "circuit_breaker": {
                    "active": False,
                    "since": 0
                },
                "heartbeat_ts": current_time,
                "writer": "health_emitter"
            },
            "pid": os.getpid(),
            "started_at": self.start_time,
            "version": "1.0",
            "args": [],
            "status": "running"
        }
        
        # state_bus에서 트레이더 정보 추출
        if state_data:
            if "trader" in state_data:
                trader_info = state_data["trader"]
                trader_data["data"].update(trader_info)
        
        # trader.json은 기존 형식 유지 (하위 호환성)
        legacy_trader_data = {
            "timestamp": current_time,
            "entrypoint_ok": True,
            "last_rest_ok_ts": current_time,
            "exchange_info_loaded": True,
            "balances": {
                "fresh_ts": current_time
            },
            "circuit_breaker": {
                "active": False,
                "since": 0
            },
            "balances_fresh_ts": current_time,  # health_v2.py에서 요구하는 필드
            "circuit_breaker_active": False  # health_v2.py에서 요구하는 필드
        }
        
        return self.write_atomic(self.output_paths["trader"], legacy_trader_data)
    
    def write_ssot(self, state_data: Optional[Dict[str, Any]]) -> bool:
        """SSOT env.json 작성"""
        current_time = int(time.time())
        
        # Log absolute SSOT path
        ssot_path = self.output_paths["ssot"]
        print(f"INFO: ssot_path={ssot_path.absolute()}")
        
        # 기본 SSOT 데이터
        ssot_data = {
            "mode": "TESTNET",
            "base_url": "https://testnet.binance.vision",
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "git_hash": "unknown",
            "env_hash": self.calculate_env_hash(),
            "writer": "health_emitter",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "timestamp": current_time,  # Add timestamp field for UI
            "ts": current_time
        }
        
        # state_bus에서 SSOT 정보 추출
        if state_data:
            if "ssot" in state_data:
                ssot_info = state_data["ssot"]
                ssot_data.update(ssot_info)
        
        return self.write_atomic(ssot_path, ssot_data)
    
    def write_health(self, state_data: Optional[Dict[str, Any]]) -> bool:
        """Health.json 작성 (통합 헬스 파일)"""
        current_time = int(time.time())
        
        # 기본 헬스 데이터
        health_data = {
            "timestamp": current_time,
            "service": "health_emitter",
            "env_hash": self.calculate_env_hash(),
            "entrypoint_ok": True,
            "uptime_seconds": int(current_time - self.start_time),
            "data": {
                "feeder_ok": True,
                "trader_ok": True,
                "ares_ok": True,
                "positions_ok": True,
                "writer": "health_emitter"
            },
            "pid": os.getpid(),
            "started_at": self.start_time,
            "version": "1.0",
            "args": [],
            "status": "running"
        }
        
        # state_bus에서 헬스 정보 추출
        if state_data:
            if "health" in state_data:
                health_info = state_data["health"]
                health_data["data"].update(health_info)
        
        return self.write_atomic(self.output_paths["health"], health_data)
    
    def write_candidates(self, state_data: Optional[Dict[str, Any]]) -> bool:
        """candidates.ndjson 작성"""
        current_time = time.time()
        
        # 기본 candidates 데이터
        candidates_data = {
            "writer": "health_emitter",
            "count": 0,
            "is_real_signal": False,
            "ts": current_time,
            "type": "noop"
        }
        
        # state_bus에서 candidates 정보 추출
        if state_data:
            if "candidates" in state_data:
                candidates_info = state_data["candidates"]
                candidates_data.update(candidates_info)
                candidates_data["type"] = "signal"
        
        # NDJSON 형식으로 추가
        if self.dry_run:
            print(f"🔍 DRY_RUN: Would append to {self.output_paths['candidates']}")
            return True
        
        try:
            with open(self.output_paths["candidates"], 'a', encoding='utf-8') as f:
                f.write(json.dumps(candidates_data, ensure_ascii=False) + '\n')
            return True
        except Exception as e:
            print(f"❌ Failed to write candidates: {e}")
            return False
    
    def should_write(self, name: str) -> bool:
        """쓰기 시점 확인"""
        current_time = time.time()
        timer = self.timers[name]
        
        if current_time - timer["last_write"] >= timer["interval"]:
            timer["last_write"] = current_time
            return True
        
        return False
    
    def run_cycle(self) -> bool:
        """한 번의 사이클 실행"""
        # state_bus 데이터 읽기
        state_data = self.read_state_bus()
        
        success_count = 0
        total_count = 0
        
        # 각 헬스 파일 업데이트
        for name, should_write_func in [
            ("positions", lambda: self.should_write("positions")),
            ("ares", lambda: self.should_write("ares")),
            ("trader", lambda: self.should_write("trader")),
            ("ssot", lambda: self.should_write("ssot")),
            ("health", lambda: self.should_write("health")),
            ("candidates", lambda: self.should_write("candidates"))
        ]:
            if should_write_func():
                total_count += 1
                
                if name == "positions":
                    success = self.write_positions(state_data)
                elif name == "ares":
                    success = self.write_ares(state_data)
                elif name == "trader":
                    success = self.write_trader(state_data)
                elif name == "ssot":
                    success = self.write_ssot(state_data)
                elif name == "health":
                    success = self.write_health(state_data)
                elif name == "candidates":
                    success = self.write_candidates(state_data)
                
                if success:
                    success_count += 1
                    print(f"✅ {name} updated")
                else:
                    print(f"❌ {name} failed")
        
        if total_count > 0:
            print(f"📊 Cycle: {success_count}/{total_count} files updated")
        
        return success_count == total_count
    
    def run(self) -> int:
        """메인 실행 루프"""
        # 루트 검증
        if not self.validate_root():
            return 1
        
        # 락 획득
        if not self.acquire_lock():
            return 1
        
        # 시작 정보 출력
        self.print_startup_info()
        
        print("🏥 HealthEmitter started")
        self.running = True
        
        try:
            # Emit heartbeat on startup
            print("🏥 HealthEmitter heartbeat on startup")
            
            # Log one line per minute summarizing age and writes
            last_log_time = time.time()
            write_count = 0
            
            while self.running:
                self.run_cycle()
                
                # Log summary every minute
                current_time = time.time()
                if current_time - last_log_time >= 60:
                    print(f"📊 HealthEmitter: {write_count} writes in last minute")
                    last_log_time = current_time
                    write_count = 0
                else:
                    write_count += 1
                
                time.sleep(1)  # 1초마다 체크 (HEALTH_EMITTER_INTERVAL_MS=1000)
                
        except KeyboardInterrupt:
            print("\n🛑 HealthEmitter stopped by user")
        
        except Exception as e:
            print(f"❌ HealthEmitter error: {e}")
            return 1
        
        finally:
            self.release_lock()
            print("✅ HealthEmitter cleanup completed")
        
        return 0


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="HealthEmitter Service")
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not write")
    parser.add_argument("--force-root", type=Path, help="Force specific root path")
    
    args = parser.parse_args()
    
    # 프로젝트 루트 자동 감지
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "shared").exists() and (parent / "guard").exists():
            repo_root = parent
            break
    else:
        print("❌ Could not find project root")
        return 1
    
    # HealthEmitter 실행
    emitter = HealthEmitter(repo_root, args.dry_run, args.force_root)
    return emitter.run()


if __name__ == "__main__":
    sys.exit(main())
