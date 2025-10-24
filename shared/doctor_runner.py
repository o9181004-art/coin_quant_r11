#!/usr/bin/env python3
"""
Doctor Runner - Read-only sequential lightweight system checker
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.atomic_io import (append_ndjson_atomic, read_json_atomic,
                              write_json_atomic)
from shared.environment_guardrails import (check_service_pid_lock,
                                           get_repo_paths)


class DoctorRunner:
    """Doctor Runner - 읽기 전용 시스템 진단"""
    
    def __init__(self):
        self.paths = get_repo_paths()
        self.run_id = str(uuid.uuid4())[:8]
        self.start_time = time.time()
        self.steps = []
        self.progress_file = self.paths["shared_data"] / "doctor" / f"run_{self.run_id}.ndjson"
        self.summary_file = self.paths["shared_data"] / "doctor" / "summary.json"
        self.lock_file = self.paths["shared_data"] / "doctor" / "doctor.lock"
        self.reports_dir = self.paths["shared_data_reports"]
        
        # 디렉토리 생성
        (self.paths["shared_data"] / "doctor").mkdir(parents=True, exist_ok=True)
        (self.paths["shared_data"] / "ops" / "done").mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def run(self, mode: str = "quick") -> bool:
        """Doctor 실행"""
        try:
            # 1. 락 파일 생성 (fail fast if exists)
            if self._create_lock():
                return False
            
            # 2. 진행 상황 파일 초기화
            self._write_progress({
                "step": "start",
                "status": "running",
                "msg_ko": "Doctor 진단을 시작합니다...",
                "pct": 0,
                "timestamp": time.time()
            })
            
            # 3. 순차적 체크 실행
            success = self._run_sequential_checks(mode)
            
            # 4. 결과 요약 생성
            self._generate_summary()
            
            # 5. 마크다운 보고서 생성
            self._generate_markdown_report()
            
            # 6. 완료 처리
            self._cleanup()
            
            return success
            
        except Exception as e:
            self._write_progress({
                "step": "error",
                "status": "fail",
                "msg_ko": f"Doctor 실행 중 오류: {str(e)}",
                "timestamp": time.time()
            })
            self._cleanup()
            return False
    
    def _create_lock(self) -> bool:
        """락 파일 생성 (이미 존재하면 실패)"""
        if self.lock_file.exists():
            print(f"❌ Doctor가 이미 실행 중입니다: {self.lock_file}")
            return True
        
        try:
            lock_data = {
                "run_id": self.run_id,
                "started_at": time.time(),
                "pid": os.getpid()
            }
            write_json_atomic(self.lock_file, lock_data)
            return False
        except Exception as e:
            print(f"❌ 락 파일 생성 실패: {e}")
            return True
    
    def _write_progress(self, data: Dict[str, Any]):
        """진행 상황 기록"""
        data["run_id"] = self.run_id
        append_ndjson_atomic(self.progress_file, data)
    
    def _run_sequential_checks(self, mode: str) -> bool:
        """순차적 체크 실행"""
        checks = [
            ("env_parity", self._check_environment_parity),
            ("duplicate_instances", self._check_duplicate_instances),
            ("health_snapshot", self._check_health_snapshot),
            ("feeder", self._check_feeder),
            ("uds", self._check_uds),
            ("ares", self._check_ares),
            ("trader_guardrails", self._check_trader_guardrails),
            ("account_snapshot", self._check_account_snapshot),
            ("autoheal", self._check_autoheal),
            ("resources", self._check_resources)
        ]
        
        total_steps = len(checks)
        all_passed = True
        
        for i, (step_name, check_func) in enumerate(checks):
            pct = int((i / total_steps) * 100)
            
            # running 상태 기록
            self._write_progress({
                "step": step_name,
                "status": "running",
                "msg_ko": self._get_step_message(step_name),
                "pct": pct,
                "timestamp": time.time()
            })
            
            # 체크 실행
            try:
                success, details = check_func()
                status = "pass" if success else "fail"
                
                if not success:
                    all_passed = False
                
                # 결과 기록
                result = {
                    "step": step_name,
                    "status": status,
                    "pct": pct,
                    "timestamp": time.time()
                }
                
                if details:
                    result.update(details)
                
                self._write_progress(result)
                self.steps.append(result)
                
                # 50-100ms 간격
                time.sleep(0.075)
                
            except Exception as e:
                # 오류 처리
                self._write_progress({
                    "step": step_name,
                    "status": "fail",
                    "reason": str(e),
                    "pct": pct,
                    "timestamp": time.time()
                })
                all_passed = False
                self.steps.append({
                    "step": step_name,
                    "status": "fail",
                    "reason": str(e),
                    "pct": pct
                })
        
        return all_passed
    
    def _get_step_message(self, step_name: str) -> str:
        """단계별 한국어 메시지"""
        messages = {
            "env_parity": "환경 설정 및 디렉토리 점검 중...",
            "duplicate_instances": "중복 프로세스 확인 중...",
            "health_snapshot": "헬스 스냅샷 분석 중...",
            "feeder": "시세 수집/스냅샷 쓰기 점검...",
            "uds": "사용자 데이터 스트림 상태 확인...",
            "ares": "ARES 엔진 신호 검증 중...",
            "trader_guardrails": "트레이더 가드레일 점검...",
            "account_snapshot": "계좌 스냅샷 유효성 검사...",
            "autoheal": "자동 복구 시스템 상태 확인...",
            "resources": "시스템 리소스 모니터링..."
        }
        return messages.get(step_name, f"{step_name} 점검 중...")
    
    def _check_environment_parity(self) -> Tuple[bool, Dict[str, Any]]:
        """환경 패리티 체크"""
        try:
            # repo root 확인
            expected_root = self.paths["repo_root"]
            current_root = Path.cwd().absolute()
            
            if current_root != expected_root:
                return False, {
                    "reason": f"Wrong working directory: {current_root} != {expected_root}",
                    "hint_ko": "프로젝트 루트에서 실행하세요."
                }
            
            # venv 경로 확인
            venv_python = self.paths["venv_python"]
            if not venv_python.exists():
                return False, {
                    "reason": f"Virtual environment not found: {venv_python}",
                    "hint_ko": "가상환경을 생성하거나 활성화하세요."
                }
            
            # 필수 디렉토리 확인
            required_dirs = ["shared_data", "logs", "shared_data/pids"]
            missing_dirs = []
            
            for dir_name in required_dirs:
                dir_path = self.paths.get(dir_name.replace("/", "_"), Path(dir_name))
                if not dir_path.exists() or not os.access(dir_path, os.W_OK):
                    missing_dirs.append(str(dir_path))
            
            if missing_dirs:
                return False, {
                    "reason": f"Missing or unwritable directories: {missing_dirs}",
                    "hint_ko": "필수 디렉토리를 생성하고 쓰기 권한을 확인하세요."
                }
            
            return True, {"metric": {"repo_root": str(expected_root), "venv": str(venv_python)}}
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "환경 설정을 확인하세요."}
    
    def _check_duplicate_instances(self) -> Tuple[bool, Dict[str, Any]]:
        """중복 인스턴스 체크"""
        try:
            services = ["feeder", "trader", "ares", "uds", "autoheal"]
            duplicates = []
            running_services = []
            
            for service in services:
                is_running, pid = check_service_pid_lock(service)
                if is_running:
                    running_services.append(service)
                    
                    # 실제 프로세스 확인
                    try:
                        process = psutil.Process(pid)
                        cmdline = " ".join(process.cmdline())
                        if service not in cmdline:
                            duplicates.append(f"{service}: PID {pid} not matching")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # 스테일 PID 파일
                        duplicates.append(f"{service}: stale PID {pid}")
            
            if duplicates:
                return False, {
                    "reason": f"Duplicate or stale processes: {duplicates}",
                    "hint_ko": "중복 프로세스를 정리하고 다시 시작하세요.",
                    "metric": {"duplicates": len(duplicates), "running": len(running_services)}
                }
            
            return True, {"metric": {"running_services": running_services, "total": len(services)}}
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "프로세스 상태를 확인하세요."}
    
    def _check_health_snapshot(self) -> Tuple[bool, Dict[str, Any]]:
        """헬스 스냅샷 체크"""
        try:
            health_file = self.paths["shared_data"] / "health.json"
            
            if not health_file.exists():
                return False, {
                    "reason": "health.json not found",
                    "hint_ko": "헬스 파일이 생성되지 않았습니다."
                }
            
            # 파일 나이 확인
            file_age = time.time() - health_file.stat().st_mtime
            if file_age > 15:
                return False, {
                    "reason": f"health.json age {file_age:.1f}s > 15s",
                    "hint_ko": "헬스 파일이 오래되었습니다. 서비스를 확인하세요."
                }
            
            # JSON 파싱 확인
            health_data = read_json_atomic(health_file, {})
            if not health_data:
                return False, {
                    "reason": "health.json parse failed",
                    "hint_ko": "헬스 파일 형식을 확인하세요."
                }
            
            return True, {"metric": {"file_age_sec": file_age, "components": len(health_data)}}
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "헬스 파일을 확인하세요."}
    
    def _check_feeder(self) -> Tuple[bool, Dict[str, Any]]:
        """Feeder 체크"""
        try:
            # 스냅샷 파일 확인
            snapshot_files = [
                self.paths["shared_data"] / "state_bus.json",
                self.paths["shared_data"] / "databus_snapshot.json"
            ]
            
            snapshot_age = float('inf')
            snapshot_file = None
            
            for file_path in snapshot_files:
                if file_path.exists():
                    age = time.time() - file_path.stat().st_mtime
                    if age < snapshot_age:
                        snapshot_age = age
                        snapshot_file = file_path.name
            
            if snapshot_age > 5:
                return False, {
                    "reason": f"snapshot age {snapshot_age:.1f}s > 5s",
                    "hint_ko": "Feeder 서비스를 재시작하세요.",
                    "metric": {"snapshot_age_sec": snapshot_age}
                }
            
            # 로그 파일 확인 (최근 120줄)
            log_files = [
                self.paths["logs"] / "feeder.log",
                self.paths["shared_data"] / "logs" / "feeder.log"
            ]
            
            win_errors = []
            for log_file in log_files:
                if log_file.exists():
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            recent_lines = lines[-120:] if len(lines) > 120 else lines
                            
                            for line in recent_lines:
                                if "WinError 183" in line or "WinError 32" in line:
                                    win_errors.append(line.strip())
                    except Exception:
                        pass
            
            if win_errors:
                return False, {
                    "reason": f"WinError found in logs: {len(win_errors)} instances",
                    "hint_ko": "파일 락 오류가 발생했습니다. 시스템을 재시작하세요.",
                    "metric": {"win_errors": len(win_errors)}
                }
            
            return True, {
                "metric": {
                    "snapshot_age_sec": snapshot_age,
                    "snapshot_file": snapshot_file,
                    "win_errors": 0
                }
            }
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "Feeder 서비스를 확인하세요."}
    
    def _check_uds(self) -> Tuple[bool, Dict[str, Any]]:
        """UDS 체크"""
        try:
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            uds_health = health_data.get("uds", {})
            
            if not uds_health:
                return False, {
                    "reason": "UDS health data not found",
                    "hint_ko": "UDS 서비스를 시작하세요."
                }
            
            heartbeat_age = uds_health.get("heartbeat_age_sec", 999)
            state = uds_health.get("state", "UNKNOWN")
            
            if heartbeat_age > 50:
                return False, {
                    "reason": f"heartbeat_age_sec={heartbeat_age} > 50",
                    "hint_ko": "UDS 재시작이 필요합니다.",
                    "metric": {"heartbeat_age_sec": heartbeat_age, "state": state}
                }
            
            if state != "CONNECTED":
                return False, {
                    "reason": f"UDS state={state} != CONNECTED",
                    "hint_ko": "UDS 연결 상태를 확인하세요.",
                    "metric": {"heartbeat_age_sec": heartbeat_age, "state": state}
                }
            
            return True, {"metric": {"heartbeat_age_sec": heartbeat_age, "state": state}}
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "UDS 서비스를 확인하세요."}
    
    def _check_ares(self) -> Tuple[bool, Dict[str, Any]]:
        """ARES 체크"""
        try:
            # fallback 플래그 확인
            allow_default = os.getenv("TEST_ALLOW_DEFAULT_SIGNAL", "false").lower() == "true"
            
            if allow_default:
                return True, {"metric": {"fallback_allowed": True, "signals": "default allowed"}}
            
            # 신호 파일 확인
            signals_file = self.paths["shared_data"] / "signals" / "ares_signals.json"
            if not signals_file.exists():
                return False, {
                    "reason": "ARES signals file not found",
                    "hint_ko": "ARES 엔진을 시작하세요."
                }
            
            # 파일 나이 확인 (10분)
            file_age = time.time() - signals_file.stat().st_mtime
            if file_age > 600:
                return False, {
                    "reason": f"signals file age {file_age:.1f}s > 600s",
                    "hint_ko": "ARES 엔진이 멈춘 것 같습니다.",
                    "metric": {"file_age_sec": file_age}
                }
            
            # 실제 신호 확인
            signals_data = read_json_atomic(signals_file, {})
            real_signals = 0
            
            for symbol, signal_data in signals_data.items():
                if isinstance(signal_data, dict):
                    confidence = signal_data.get("confidence", 0)
                    if confidence > 50:  # 50% 이상 신뢰도
                        real_signals += 1
            
            if real_signals == 0:
                return False, {
                    "reason": "No real signals found",
                    "hint_ko": "ARES가 실제 신호를 생성하지 못하고 있습니다.",
                    "metric": {"real_signals": 0, "total_signals": len(signals_data)}
                }
            
            return True, {
                "metric": {
                    "real_signals": real_signals,
                    "total_signals": len(signals_data),
                    "file_age_sec": file_age
                }
            }
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "ARES 엔진을 확인하세요."}
    
    def _check_trader_guardrails(self) -> Tuple[bool, Dict[str, Any]]:
        """Trader 가드레일 체크"""
        try:
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            trader_health = health_data.get("trader", {})
            
            if not trader_health:
                return False, {
                    "reason": "Trader health data not found",
                    "hint_ko": "Trader 서비스를 시작하세요."
                }
            
            issues = []
            
            # UDS age 확인
            uds_age = trader_health.get("uds_age", 999)
            if uds_age > 60:
                issues.append(f"uds_age={uds_age} > 60")
            
            # Filters state 확인
            filters_state = trader_health.get("filters", "STALE")
            if filters_state != "FRESH":
                issues.append(f"filters_state={filters_state} != FRESH")
            
            # Circuit breaker 확인
            circuit_file = self.paths["shared_data"] / "circuit_breaker.json"
            if circuit_file.exists():
                circuit_data = read_json_atomic(circuit_file, {})
                if circuit_data.get("active", False):
                    issues.append("circuit_breaker=ON")
            
            # Account snapshot age 확인
            account_file = self.paths["shared_data"] / "account_snapshot.json"
            if account_file.exists():
                account_age = time.time() - account_file.stat().st_mtime
                if account_age > 180:
                    issues.append(f"account_snapshot_age={account_age:.1f}s > 180s")
            
            # Health file recency 확인
            health_age = trader_health.get("last_update", 0)
            if health_age > 0:
                age = time.time() - health_age
                if age > 15:
                    issues.append(f"health_age={age:.1f}s > 15s")
            
            if issues:
                return False, {
                    "reason": f"Guardrail violations: {issues}",
                    "hint_ko": "Trader 가드레일을 확인하고 필요한 조치를 취하세요.",
                    "metric": {"violations": len(issues), "details": issues}
                }
            
            return True, {"metric": {"violations": 0, "status": "all_clear"}}
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "Trader 서비스를 확인하세요."}
    
    def _check_account_snapshot(self) -> Tuple[bool, Dict[str, Any]]:
        """계좌 스냅샷 체크"""
        try:
            account_file = self.paths["shared_data"] / "account_snapshot.json"
            
            if not account_file.exists():
                return False, {
                    "reason": "account_snapshot.json not found",
                    "hint_ko": "계좌 스냅샷 서비스를 시작하세요."
                }
            
            # 파일 나이 확인
            file_age = time.time() - account_file.stat().st_mtime
            if file_age > 180:
                return False, {
                    "reason": f"account_snapshot age {file_age:.1f}s > 180s",
                    "hint_ko": "계좌 스냅샷 서비스를 확인하세요.",
                    "metric": {"file_age_sec": file_age}
                }
            
            # JSON 파싱 및 필수 필드 확인
            account_data = read_json_atomic(account_file, {})
            if not account_data:
                return False, {
                    "reason": "account_snapshot.json parse failed",
                    "hint_ko": "계좌 스냅샷 파일 형식을 확인하세요."
                }
            
            # equity/free 필드 확인
            has_equity = "equity" in account_data or any("equity" in str(key).lower() for key in account_data.keys())
            has_free = "free" in account_data or any("free" in str(key).lower() for key in account_data.keys())
            
            if not (has_equity or has_free):
                return False, {
                    "reason": "equity/free fields not found in account snapshot",
                    "hint_ko": "계좌 정보가 올바르게 수집되지 않았습니다.",
                    "metric": {"file_age_sec": file_age, "fields": list(account_data.keys())}
                }
            
            return True, {
                "metric": {
                    "file_age_sec": file_age,
                    "has_equity": has_equity,
                    "has_free": has_free,
                    "fields": list(account_data.keys())
                }
            }
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "계좌 스냅샷을 확인하세요."}
    
    def _check_autoheal(self) -> Tuple[bool, Dict[str, Any]]:
        """Auto-Heal 체크"""
        try:
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            autoheal_health = health_data.get("autoheal", {})
            
            if not autoheal_health:
                return False, {
                    "reason": "Auto-Heal health data not found",
                    "hint_ko": "Auto-Heal 서비스를 시작하세요."
                }
            
            # 컴포넌트 등록 확인
            if "component" not in autoheal_health:
                return False, {
                    "reason": "Auto-Heal component not registered",
                    "hint_ko": "Auto-Heal이 시스템에 등록되지 않았습니다."
                }
            
            # heartbeat 확인
            heartbeat_age = autoheal_health.get("last_update", 0)
            if heartbeat_age > 0:
                age = time.time() - heartbeat_age
                if age > 30:
                    return False, {
                        "reason": f"Auto-Heal heartbeat age {age:.1f}s > 30s",
                        "hint_ko": "Auto-Heal 서비스를 확인하세요.",
                        "metric": {"heartbeat_age_sec": age}
                    }
            
            # watching list 확인
            watching = autoheal_health.get("watching", [])
            expected_services = ["feeder", "trader", "ares", "uds"]
            missing_watches = [svc for svc in expected_services if svc not in watching]
            
            if missing_watches:
                return False, {
                    "reason": f"Missing watched services: {missing_watches}",
                    "hint_ko": "Auto-Heal이 모든 서비스를 모니터링하지 못하고 있습니다.",
                    "metric": {"watching": watching, "missing": missing_watches}
                }
            
            return True, {
                "metric": {
                    "heartbeat_age_sec": age if heartbeat_age > 0 else 0,
                    "watching_services": watching,
                    "total_watched": len(watching)
                }
            }
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "Auto-Heal 서비스를 확인하세요."}
    
    def _check_resources(self) -> Tuple[bool, Dict[str, Any]]:
        """리소스 체크"""
        try:
            # 메모리 사용률
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # 디스크 여유공간
            disk_usage = psutil.disk_usage(str(self.paths["repo_root"]))
            free_gb = disk_usage.free / (1024**3)
            
            # 핸들 수 (간단한 추정)
            try:
                process = psutil.Process()
                handle_count = process.num_handles() if hasattr(process, 'num_handles') else 0
            except:
                handle_count = 0
            
            warnings = []
            
            if memory_percent > 90:
                warnings.append(f"memory={memory_percent:.1f}%")
            
            if free_gb < 1.0:
                warnings.append(f"disk_free={free_gb:.1f}GB")
            
            if handle_count > 1000:
                warnings.append(f"handles={handle_count}")
            
            if warnings:
                return False, {
                    "reason": f"Resource warnings: {warnings}",
                    "hint_ko": "시스템 리소스가 부족합니다. 정리가 필요합니다.",
                    "metric": {
                        "memory_percent": memory_percent,
                        "disk_free_gb": free_gb,
                        "handle_count": handle_count
                    }
                }
            
            return True, {
                "metric": {
                    "memory_percent": memory_percent,
                    "disk_free_gb": free_gb,
                    "handle_count": handle_count
                }
            }
            
        except Exception as e:
            return False, {"reason": str(e), "hint_ko": "시스템 리소스를 확인하세요."}
    
    def _generate_summary(self):
        """요약 생성"""
        try:
            failed_steps = [step for step in self.steps if step.get("status") == "fail"]
            passed_steps = [step for step in self.steps if step.get("status") == "pass"]
            
            # 주요 원인 분석
            top_causes = []
            for step in failed_steps:
                reason = step.get("reason", "Unknown")
                top_causes.append({
                    "step": step.get("step"),
                    "reason": reason,
                    "hint_ko": step.get("hint_ko", "상세 정보를 확인하세요.")
                })
            
            # 다음 액션
            next_actions = []
            if failed_steps:
                next_actions.append("실패한 서비스들을 재시작하세요.")
                next_actions.append("로그 파일을 확인하여 오류 원인을 파악하세요.")
                next_actions.append("시스템 리소스 상태를 점검하세요.")
            else:
                next_actions.append("모든 시스템이 정상 작동 중입니다.")
                next_actions.append("정기적인 모니터링을 계속하세요.")
                next_actions.append("로그 로테이션을 확인하세요.")
            
            summary = {
                "run_id": self.run_id,
                "timestamp": time.time(),
                "duration_sec": time.time() - self.start_time,
                "overall_status": "pass" if not failed_steps else "fail",
                "steps": self.steps,
                "summary": {
                    "total_steps": len(self.steps),
                    "passed": len(passed_steps),
                    "failed": len(failed_steps)
                },
                "top_causes": top_causes,
                "next_actions_ko": next_actions
            }
            
            write_json_atomic(self.summary_file, summary)
            
        except Exception as e:
            print(f"Summary generation failed: {e}")
    
    def _generate_markdown_report(self):
        """마크다운 보고서 생성 - Canonical path with atomic write"""
        import logging
        logger = logging.getLogger(__name__)

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Canonical paths: latest.md and timestamped backup
            canonical_dir = self.reports_dir / "stack_doctor"
            canonical_dir.mkdir(parents=True, exist_ok=True)

            latest_report = canonical_dir / "latest.md"
            timestamped_report = self.reports_dir / f"stack_doctor_{timestamp}.md"

            failed_steps = [step for step in self.steps if step.get("status") == "fail"]
            passed_steps = [step for step in self.steps if step.get("status") == "pass"]

            # 결론 3줄
            if not failed_steps:
                conclusion = [
                    "✅ 모든 시스템이 정상 작동 중입니다.",
                    "🎯 자동매매 시스템이 안전하게 운영될 준비가 되어 있습니다.",
                    "📊 정기적인 모니터링을 계속하세요."
                ]
            else:
                conclusion = [
                    f"❌ {len(failed_steps)}개 항목에서 문제가 발견되었습니다.",
                    "🚨 자동매매를 시작하기 전에 문제를 해결해야 합니다.",
                    "🔧 아래 권장 조치를 따라 시스템을 복구하세요."
                ]

            # 신호등 표
            status_emoji = "🟢" if not failed_steps else "🔴"
            overall_status = "정상" if not failed_steps else "문제 발견"

            # 근거 (각 항목 TTL/실측값)
            evidence = []
            for step in self.steps:
                step_name = step.get("step", "unknown")
                status = step.get("status", "unknown")
                reason = step.get("reason", "")
                metric = step.get("metric", {})
                hint = step.get("hint_ko", "")

                status_icon = "✅" if status == "pass" else "❌" if status == "fail" else "⏳"
                evidence.append(f"- {status_icon} **{step_name}**: {reason or 'OK'}")
                if metric:
                    metric_str = ", ".join([f"{k}={v}" for k, v in metric.items()])
                    evidence.append(f"  - 측정값: {metric_str}")
                if hint:
                    evidence.append(f"  - 💡 {hint}")

            # 바로 할 일 3개
            actions = []
            if failed_steps:
                # 실패한 항목별 액션
                for step in failed_steps[:3]:  # 최대 3개
                    step_name = step.get("step", "")
                    hint = step.get("hint_ko", "상세 확인 필요")
                    actions.append(f"1. **{step_name}**: {hint}")
            else:
                actions = [
                    "1. **모니터링**: 시스템 상태를 지속적으로 관찰하세요.",
                    "2. **로그 관리**: 로그 파일 로테이션을 확인하세요.",
                    "3. **백업**: 정기적인 설정 파일 백업을 수행하세요."
                ]

            # 보고서 작성 (ensure non-empty even on "no issues")
            report_content = f"""# Stack Doctor Report - {timestamp}

## 🎯 결론
{chr(10).join(conclusion)}

## 🚦 전체 상태
| 항목 | 상태 | 세부사항 |
|------|------|----------|
| **전체 시스템** | {status_emoji} {overall_status} | {len(passed_steps)}/{len(self.steps)} 항목 통과 |
| **실행 시간** | ⏱️ | {time.time() - self.start_time:.1f}초 |
| **진단 ID** | 🔍 | {self.run_id} |

## 📊 상세 근거
{chr(10).join(evidence)}

## 🔧 바로 할 일
{chr(10).join(actions)}

---
*생성 시간: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*Doctor Runner v1.0*
"""

            # Atomic write to both locations (UTF-8, no BOM)
            from shared.atomic_io import write_text_atomic

            # Write to canonical latest.md
            success_latest = write_text_atomic(latest_report, report_content, encoding='utf-8')
            if success_latest:
                logger.info(f"report_writer: wrote canonical report to {latest_report}")

            # Write to timestamped backup
            success_timestamped = write_text_atomic(timestamped_report, report_content, encoding='utf-8')
            if success_timestamped:
                logger.info(f"report_writer: wrote timestamped report to {timestamped_report}")

        except Exception as e:
            print(f"Markdown report generation failed: {e}")
    
    def _cleanup(self):
        """정리 작업"""
        try:
            # 락 파일 제거
            if self.lock_file.exists():
                self.lock_file.unlink()
            
            # 명령어 파일을 done으로 이동
            trigger_file = self.paths["shared_data"] / "ops" / "doctor.run"
            if trigger_file.exists():
                done_file = self.paths["shared_data"] / "ops" / "done" / f"doctor_{self.run_id}.json"
                trigger_file.rename(done_file)
            
        except Exception as e:
            print(f"Cleanup failed: {e}")


def run_doctor():
    """Doctor 실행 (외부에서 호출)"""
    trigger_file = Path("shared_data/ops/doctor.run")
    
    if not trigger_file.exists():
        return False
    
    try:
        # 트리거 파일 읽기
        trigger_data = read_json_atomic(trigger_file, {})
        mode = trigger_data.get("mode", "quick")
        
        # Doctor 실행
        runner = DoctorRunner()
        success = runner.run(mode)
        
        return success
        
    except Exception as e:
        print(f"Doctor execution failed: {e}")
        return False


if __name__ == "__main__":
    # 직접 실행 시 테스트
    print("🔍 Doctor Runner - 독립 실행")
    
    # 테스트용 트리거 파일 생성
    test_trigger = Path("shared_data/ops/doctor.run")
    test_trigger.parent.mkdir(parents=True, exist_ok=True)
    
    write_json_atomic(test_trigger, {"mode": "quick"})
    
    success = run_doctor()
    
    if success:
        print("\n🎉 Doctor 진단 완료 - 모든 항목 통과!")
    else:
        print("\n❌ Doctor 진단 완료 - 일부 항목 실패")
