#!/usr/bin/env python3
"""
Single-Root Orchestrator
Production-grade, unattended trading runtime with strict start-order gating
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

# Load environment variables
load_dotenv("config.env")


class SingleRootOrchestrator:
    """단일 루트 오케스트레이터 - 엄격한 시작 순서 및 readiness 체크"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.repo_root = Path(__file__).parent.parent.absolute()
        self.runtime_dir = self.repo_root / ".runtime"
        self.runtime_dir.mkdir(exist_ok=True)
        
        # 서비스 시작 순서 (엄격한 의존성)
        self.service_order = ["feeder", "ares", "trader", "auto_heal"]
        
        # UI 임계값 (반드시 준수)
        self.ui_thresholds = {
            "ws_stream_databus": 30,      # Feeder
            "positions_snapshot": 60,     # Positions
            "ares_signal_flow": 75,       # ARES
            "trader_readiness": 300,      # Trader
            "env_drift": 300,             # Environment
            "integration_contracts": 90   # Integration
        }
        
        # 서비스별 readiness 체크 매핑
        self.service_health_mapping = {
            "feeder": "ws_stream_databus",
            "ares": "ares_signal_flow", 
            "trader": "trader_readiness"
        }
        
        # 헬스 파일 경로 (절대 경로만 사용)
        self.health_files = {
            "feeder": self.repo_root / "shared_data" / "health" / "feeder.json",
            "ares": self.repo_root / "shared_data" / "health" / "ares.json",
            "trader": self.repo_root / "shared_data" / "health" / "trader.json",
            "positions": self.repo_root / "shared_data" / "health" / "positions.json",
            "env": self.repo_root / "shared_data" / "ssot" / "env.json",
            "integration": self.repo_root / "shared_data" / "candidates.ndjson"
        }
        
        # PID 파일 경로
        self.pid_files = {
            service: self.runtime_dir / f"{service}.pid"
            for service in self.service_order
        }
        
        # 환경 변수
        self.python_exe = self.repo_root / "venv_fixed" / "Scripts" / "python.exe"
        self.restart_cooldown = min(int(os.getenv("RESTART_COOLDOWN_SECS", "120")), 120)  # 최대 120초
        
        # Git hash 및 시작 정보
        self.git_hash = self._get_git_hash()
        self.start_time = time.time()
        
        # 시작 로그
        self._log_startup_info()
    
    def _get_git_hash(self) -> str:
        """Git hash 획득"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return "unknown"
    
    def _log_startup_info(self):
        """시작 정보 로깅"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 SINGLE-ROOT ORCHESTRATOR STARTUP")
        self.logger.info(f"ROOT={self.repo_root}")
        self.logger.info(f"VENV_PY={self.python_exe}")
        self.logger.info(f"GIT_HASH={self.git_hash}")
        self.logger.info(f"PID={os.getpid()}")
        self.logger.info(f"COOLDOWN={self.restart_cooldown}s")
        self.logger.info("=" * 60)
        
    def start_services(self, force: bool = False):
        """서비스들을 엄격한 순서대로 시작 (GREEN 상태에서만)"""
        self.logger.info("🚀 SINGLE-ROOT ORCHESTRATOR: 서비스 시작")
        
        started_services = []
        
        for service in self.service_order:
            try:
                # 기존 프로세스 확인
                if not force and self._is_service_running(service):
                    self.logger.info(f"✅ {service} 이미 실행 중")
                    started_services.append(service)
                    continue
                
                # 엄격한 의존성 체크 (GREEN 상태에서만 시작)
                if not self._check_dependencies_strict(service, started_services):
                    self.logger.error(f"❌ {service} 의존성 체크 실패 - 시작 중단")
                    break
                
                # 서비스 시작
                if self._start_service(service):
                    self.logger.info(f"✅ {service} 시작 성공")
                    started_services.append(service)
                    
                    # Readiness 체크 (임계값 내에서 GREEN 확인)
                    if self._wait_for_readiness_strict(service):
                        self.logger.info(f"✅ {service} readiness 체크 통과 (GREEN)")
                    else:
                        self.logger.warning(f"⚠️ {service} readiness 체크 실패 - 계속 진행")
                else:
                    self.logger.error(f"❌ {service} 시작 실패")
                    break
                    
            except Exception as e:
                self.logger.error(f"❌ {service} 시작 중 오류: {e}")
                break
        
        self.logger.info(f"🎯 시작 완료: {started_services}")
        return started_services
    
    def stop_services(self, services: Optional[List[str]] = None):
        """서비스들 중지"""
        if services is None:
            services = list(reversed(self.service_order))  # 역순으로 중지
        
        self.logger.info(f"🛑 서비스 중지: {services}")
        
        for service in services:
            try:
                if self._stop_service(service):
                    self.logger.info(f"✅ {service} 중지 성공")
                else:
                    self.logger.warning(f"⚠️ {service} 중지 실패 또는 이미 중지됨")
            except Exception as e:
                self.logger.error(f"❌ {service} 중지 중 오류: {e}")
    
    def restart_services(self, services: Optional[List[str]] = None):
        """서비스들 재시작"""
        if services is None:
            services = self.service_order
        
        self.logger.info(f"🔄 서비스 재시작: {services}")
        
        # 중지
        self.stop_services(services)
        
        # 쿨다운 대기
        self.logger.info(f"⏳ 쿨다운 대기: {self.restart_cooldown}초")
        time.sleep(self.restart_cooldown)
        
        # 시작
        self.start_services(force=True)
    
    def _is_service_running(self, service: str) -> bool:
        """서비스가 실행 중인지 확인"""
        pid_file = self.pid_files[service]
        
        if not pid_file.exists():
            return False
        
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # 프로세스 존재 확인
            import psutil
            return psutil.pid_exists(pid)
        except:
            return False
    
    def _check_dependencies_strict(self, service: str, started_services: List[str]) -> bool:
        """엄격한 서비스 의존성 체크 (GREEN 상태에서만 시작)"""
        if service == "feeder":
            return True  # Feeder는 의존성 없음
        
        elif service == "ares":
            # Feeder가 시작되어 있고 GREEN 상태
            if "feeder" not in started_services:
                self._log_skip_start(service, "feeder", "not_started", 0, 30)
                return False
            
            # Feeder 헬스 체크 (ws_stream_databus ≤ 30s)
            feeder_age = self._get_health_age("ws_stream_databus")
            if feeder_age is None or feeder_age > 30:
                self._log_skip_start(service, "feeder", "stale", feeder_age, 30)
                return False
            
            return True
        
        elif service == "trader":
            # Feeder와 ARES가 시작되어 있고 GREEN 상태
            if "feeder" not in started_services:
                self._log_skip_start(service, "feeder", "not_started", 0, 30)
                return False
            
            if "ares" not in started_services:
                self._log_skip_start(service, "ares", "not_started", 0, 75)
                return False
            
            # Feeder 헬스 체크 (ws_stream_databus ≤ 30s)
            feeder_age = self._get_health_age("ws_stream_databus")
            if feeder_age is None or feeder_age > 30:
                self._log_skip_start(service, "feeder", "stale", feeder_age, 30)
                return False
            
            # ARES 헬스 체크 (ares_signal_flow ≤ 75s)
            ares_age = self._get_health_age("ares_signal_flow")
            if ares_age is None or ares_age > 75:
                self._log_skip_start(service, "ares", "stale", ares_age, 75)
                return False
            
            return True
        
        elif service == "auto_heal":
            # 모든 핵심 서비스가 시작되어 있고 GREEN 상태
            if "feeder" not in started_services or "ares" not in started_services or "trader" not in started_services:
                self._log_skip_start(service, "core_services", "not_started", 0, 0)
                return False
            
            return True
        
        return True
    
    def _log_skip_start(self, service: str, dep: str, reason: str, dep_age: Optional[float], threshold: int):
        """SKIP_START 로그 출력"""
        next_retry = datetime.now(timezone.utc).timestamp() + self.restart_cooldown
        next_retry_iso = datetime.fromtimestamp(next_retry, timezone.utc).isoformat()
        
        self.logger.warning(
            f"SKIP_START service={service} dep={dep} dep_age={dep_age:.1f}s threshold={threshold}s "
            f"reason={reason} next_retry={next_retry_iso}"
        )
    
    def _start_service(self, service: str) -> bool:
        """서비스 시작"""
        try:
            # 기존 프로세스 중지
            if self._is_service_running(service):
                self._stop_service(service)
                time.sleep(2)
            
            # 서비스별 시작 명령
            if service == "feeder":
                cmd = [str(self.python_exe), "-m", "guard.feeder"]
            elif service == "ares":
                cmd = [str(self.python_exe), "-m", "guard.optimizer"]
            elif service == "trader":
                cmd = [str(self.python_exe), "-m", "guard.trader"]
            else:
                self.logger.error(f"알 수 없는 서비스: {service}")
                return False
            
            # 백그라운드에서 시작
            process = subprocess.Popen(
                cmd,
                cwd=str(self.repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # PID 파일 저장
            pid_file = self.pid_files[service]
            with open(pid_file, 'w') as f:
                f.write(str(process.pid))
            
            self.logger.info(f"📝 {service} PID 저장: {process.pid}")
            return True
            
        except Exception as e:
            self.logger.error(f"서비스 시작 실패: {e}")
            return False
    
    def _stop_service(self, service: str) -> bool:
        """서비스 중지"""
        try:
            pid_file = self.pid_files[service]
            
            if not pid_file.exists():
                return True  # 이미 중지됨
            
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # 프로세스 중지
            import psutil
            try:
                process = psutil.Process(pid)
                process.terminate()
                process.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass  # 이미 종료됨
            except psutil.TimeoutExpired:
                process.kill()  # 강제 종료
            
            # PID 파일 삭제
            pid_file.unlink(missing_ok=True)
            return True
            
        except Exception as e:
            self.logger.error(f"서비스 중지 실패: {e}")
            return False
    
    def _wait_for_readiness_strict(self, service: str, timeout: int = 60) -> bool:
        """엄격한 서비스 readiness 대기 (UI 임계값 준수)"""
        health_key = self.service_health_mapping.get(service)
        if not health_key:
            return True  # auto_heal 등은 별도 체크 없음
        
        threshold = self.ui_thresholds.get(health_key, 300)
        
        self.logger.info(f"⏳ {service} readiness 대기 (임계값: {threshold}s, 타임아웃: {timeout}s)")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            age = self._get_health_age(health_key)
            if age is not None and age <= threshold:
                self.logger.info(f"✅ {service} GREEN 상태 확인 (age: {age:.1f}s ≤ {threshold}s)")
                return True
            
            time.sleep(5)  # 5초마다 체크
        
        self.logger.warning(f"⚠️ {service} readiness 타임아웃 (age: {age:.1f}s > {threshold}s)")
        return False
    
    def _get_health_age(self, health_key: str) -> Optional[float]:
        """헬스 파일 age 조회 (정규화된 타임스탬프)"""
        if health_key == "ws_stream_databus":
            # Feeder databus snapshot 체크
            databus_file = self.repo_root / "shared_data" / "databus_snapshot.json"
            if not databus_file.exists():
                return None
            
            try:
                with open(databus_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                timestamp = data.get('timestamp', 0)
                if timestamp > 1e12:  # milliseconds
                    timestamp = timestamp / 1000
                
                return time.time() - timestamp
            except:
                return None
        
        elif health_key == "ares_signal_flow":
            # ARES health 파일 체크
            ares_file = self.health_files.get("ares")
            if not ares_file or not ares_file.exists():
                return None
            
            try:
                with open(ares_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # last_signal_update 우선
                timestamp = data.get("data", {}).get("last_signal_update") or data.get("timestamp", 0)
                if timestamp > 1e12:  # milliseconds
                    timestamp = timestamp / 1000
                
                return time.time() - timestamp
            except:
                return None
        
        elif health_key == "trader_readiness":
            # Trader health 파일 체크
            trader_file = self.health_files.get("trader")
            if not trader_file or not trader_file.exists():
                return None
            
            try:
                with open(trader_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 가장 최신 타임스탬프 선택
                candidates = []
                if "data" in data and "heartbeat_ts" in data["data"]:
                    candidates.append(data["data"]["heartbeat_ts"])
                if "data" in data and "balances" in data["data"]:
                    balances = data["data"]["balances"]
                    if "updated_ts" in balances:
                        candidates.append(balances["updated_ts"])
                    elif "fresh_ts" in balances:
                        candidates.append(balances["fresh_ts"])
                if "timestamp" in data:
                    candidates.append(data["timestamp"])
                
                if not candidates:
                    return None
                
                # 가장 최신 타임스탬프 선택
                best_ts = max(candidates)
                if best_ts > 1e12:  # milliseconds
                    best_ts = best_ts / 1000
                
                return time.time() - best_ts
            except:
                return None
        
        return None
    
    def get_service_status(self) -> Dict[str, Dict]:
        """서비스 상태 조회 (UI 임계값 기준)"""
        status = {}
        
        for service in self.service_order:
            is_running = self._is_service_running(service)
            health_key = self.service_health_mapping.get(service)
            health_age = None
            threshold = None
            
            if health_key:
                health_age = self._get_health_age(health_key)
                threshold = self.ui_thresholds.get(health_key, 300)
            
            status[service] = {
                "running": is_running,
                "health_key": health_key,
                "health_age": health_age,
                "threshold": threshold,
                "green": health_age is not None and health_age <= (threshold or 300)
            }
        
        return status


def main():
    """메인 진입점"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Single-Root Orchestrator")
    parser.add_argument("--start", action="store_true", help="서비스 시작")
    parser.add_argument("--stop", action="store_true", help="서비스 중지")
    parser.add_argument("--restart", action="store_true", help="서비스 재시작")
    parser.add_argument("--status", action="store_true", help="서비스 상태 조회")
    parser.add_argument("--force", action="store_true", help="강제 시작")
    
    args = parser.parse_args()
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    orchestrator = SingleRootOrchestrator()
    
    if args.start:
        orchestrator.start_services(force=args.force)
    elif args.stop:
        orchestrator.stop_services()
    elif args.restart:
        orchestrator.restart_services()
    elif args.status:
        status = orchestrator.get_service_status()
        print(json.dumps(status, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
