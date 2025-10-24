#!/usr/bin/env python3
"""
Auto-Heal & Process Supervision - 자동 복구 및 프로세스 감독
"""

import json
import logging
import os
import psutil
import signal
import subprocess
import time
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from collections import deque

from shared.guardrails import get_guardrails
from shared.state_bus import get_state_bus, update_service_heartbeat

# Risk mode integration
try:
    from guard.risk.risk_mode_manager import get_risk_mode_manager, AutoHealEvent
    RISK_MODE_AVAILABLE = True
except ImportError:
    RISK_MODE_AVAILABLE = False


class ServiceStatus(Enum):
    """서비스 상태"""
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    CRASHED = "CRASHED"
    UNKNOWN = "UNKNOWN"


class ServiceType(Enum):
    """서비스 타입"""
    FEEDER = "feeder"
    ARES = "ares"
    TRADER = "trader"
    UI = "ui"


@dataclass
class ServiceConfig:
    """서비스 설정"""
    name: str
    service_type: ServiceType
    command: List[str]
    working_dir: str
    pid_file: str
    lock_file: str
    
    # 모니터링 설정
    heartbeat_timeout: float = 30.0  # 하트비트 타임아웃 (초)
    restart_cooldown: float = 60.0  # 재시작 쿨다운 (초)
    max_restarts: int = 5  # 최대 재시작 횟수
    restart_window: float = 300.0  # 재시작 윈도우 (초)
    
    # 프로세스 설정
    auto_start: bool = True
    auto_restart: bool = True
    graceful_shutdown: bool = True
    shutdown_timeout: float = 30.0  # 종료 타임아웃 (초)


@dataclass
class ServiceStatus:
    """서비스 상태 정보"""
    name: str
    status: ServiceStatus
    pid: Optional[int] = None
    start_time: float = 0.0
    last_heartbeat: float = 0.0
    restart_count: int = 0
    last_restart: float = 0.0
    last_error: str = ""
    
    # 통계
    total_uptime: float = 0.0
    total_restarts: int = 0
    crash_count: int = 0


class ProcessSupervisor:
    """프로세스 감독자"""
    
    def __init__(self, config_path: str = "config/policy.yaml"):
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        
        # 가드레일 및 상태 버스
        self.guardrails = get_guardrails()
        self.state_bus = get_state_bus()
        self.config = self.guardrails.get_config()
        
        # 서비스 설정
        self.services: Dict[str, ServiceConfig] = {}
        self.service_status: Dict[str, ServiceStatus] = {}
        
        # 락
        self._lock = threading.RLock()
        
        # 통계
        self._stats = {
            "services_monitored": 0,
            "total_restarts": 0,
            "total_crashes": 0,
            "failsafe_activations": 0,
            "last_restart_time": 0.0,
        }
        
        # 모니터링 스레드
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running = False
        
        # 자동 복구 스레드
        self._healer_thread: Optional[threading.Thread] = None
        self._healer_running = False
        
        # 초기화
        self._initialize_services()
    
    def _initialize_services(self):
        """서비스 초기화"""
        try:
            # Feeder 서비스
            self.services["feeder"] = ServiceConfig(
                name="feeder",
                service_type=ServiceType.FEEDER,
                command=["python", "-m", "feeder.main"],
                working_dir=".",
                pid_file="shared_data/feeder.pid",
                lock_file="shared_data/feeder.lock",
                heartbeat_timeout=20.0,
                restart_cooldown=30.0,
                max_restarts=3,
            )
            
            # ARES 서비스
            self.services["ares"] = ServiceConfig(
                name="ares",
                service_type=ServiceType.ARES,
                command=["python", "-m", "optimizer.enhanced_ares"],
                working_dir=".",
                pid_file="shared_data/ares.pid",
                lock_file="shared_data/ares.lock",
                heartbeat_timeout=30.0,
                restart_cooldown=60.0,
                max_restarts=5,
            )
            
            # Trader 서비스
            self.services["trader"] = ServiceConfig(
                name="trader",
                service_type=ServiceType.TRADER,
                command=["python", "-m", "trader.enhanced_order_router"],
                working_dir=".",
                pid_file="shared_data/trader.pid",
                lock_file="shared_data/trader.lock",
                heartbeat_timeout=30.0,
                restart_cooldown=60.0,
                max_restarts=5,
            )
            
            # UI 서비스
            self.services["ui"] = ServiceConfig(
                name="ui",
                service_type=ServiceType.UI,
                command=["streamlit", "run", "app.py"],
                working_dir=".",
                pid_file="shared_data/ui.pid",
                lock_file="shared_data/ui.lock",
                heartbeat_timeout=60.0,
                restart_cooldown=120.0,
                max_restarts=3,
            )
            
            # 서비스 상태 초기화
            for service_name in self.services:
                self.service_status[service_name] = ServiceStatus(
                    name=service_name,
                    status=ServiceStatus.UNKNOWN
                )
            
            self._stats["services_monitored"] = len(self.services)
            self.logger.info(f"Initialized {len(self.services)} services")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize services: {e}")
    
    def start(self):
        """프로세스 감독자 시작"""
        try:
            # 모니터링 스레드 시작
            self._monitor_running = True
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()
            
            # 자동 복구 스레드 시작
            self._healer_running = True
            self._healer_thread = threading.Thread(target=self._healer_loop, daemon=True)
            self._healer_thread.start()
            
            self.logger.info("Process Supervisor started")
            
        except Exception as e:
            self.logger.error(f"Failed to start Process Supervisor: {e}")
    
    def stop(self):
        """프로세스 감독자 중지"""
        try:
            self._monitor_running = False
            self._healer_running = False
            
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5.0)
            
            if self._healer_thread:
                self._healer_thread.join(timeout=5.0)
            
            # 모든 서비스 정상 종료
            self._shutdown_all_services()
            
            self.logger.info("Process Supervisor stopped")
            
        except Exception as e:
            self.logger.error(f"Failed to stop Process Supervisor: {e}")
    
    def _monitor_loop(self):
        """모니터링 루프"""
        while self._monitor_running:
            try:
                current_time = time.time()
                
                # 각 서비스 상태 확인
                for service_name, service_config in self.services.items():
                    self._check_service_status(service_name, service_config)
                
                # 상태 버스에 업데이트
                self._update_state_bus()
                
                # 10초마다 모니터링
                time.sleep(10.0)
                
            except Exception as e:
                self.logger.error(f"Process monitor error: {e}")
                time.sleep(10.0)
    
    def _healer_loop(self):
        """자동 복구 루프"""
        while self._healer_running:
            try:
                current_time = time.time()
                
                # 각 서비스 복구 확인
                for service_name, service_config in self.services.items():
                    if service_config.auto_restart:
                        self._check_service_health(service_name, service_config)
                
                # 30초마다 복구 시도
                time.sleep(30.0)
                
            except Exception as e:
                self.logger.error(f"Process healer error: {e}")
                time.sleep(30.0)
    
    def _publish_critical_event(self, event_type: str, count: int, window_sec: float, details: Dict[str, Any]):
        """Publish critical event to risk mode manager"""
        try:
            if not RISK_MODE_AVAILABLE:
                return

            risk_manager = get_risk_mode_manager()

            event = AutoHealEvent(
                event_type=event_type,
                timestamp=time.time(),
                count=count,
                window_sec=window_sec,
                details=details
            )

            risk_manager.on_auto_heal_event(event)
            self.logger.info(f"Published critical event to risk manager: {event_type}")

        except Exception as e:
            self.logger.error(f"Failed to publish critical event: {e}")

    def _check_service_status(self, service_name: str, service_config: ServiceConfig):
        """서비스 상태 확인"""
        try:
            current_time = time.time()
            status = self.service_status[service_name]

            # PID 파일 확인
            pid_file = Path(service_config.pid_file)
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    if psutil.pid_exists(pid):
                        # 프로세스가 실행 중
                        if status.status != ServiceStatus.RUNNING:
                            status.status = ServiceStatus.RUNNING
                            status.pid = pid
                            status.start_time = current_time
                            self.logger.info(f"Service {service_name} is running (PID: {pid})")
                    else:
                        # 프로세스가 종료됨
                        if status.status == ServiceStatus.RUNNING:
                            status.status = ServiceStatus.CRASHED
                            status.crash_count += 1
                            self.logger.warning(f"Service {service_name} crashed (PID: {pid})")

                            # Publish critical event if crash count is high
                            if status.crash_count >= 3:
                                self._publish_critical_event(
                                    "order_failure",
                                    status.crash_count,
                                    900,  # 15 minutes
                                    {"service": service_name, "pid": pid}
                                )
                except (ValueError, FileNotFoundError):
                    # PID 파일이 없거나 잘못된 형식
                    if status.status == ServiceStatus.RUNNING:
                        status.status = ServiceStatus.STOPPED
                        self.logger.warning(f"Service {service_name} stopped unexpectedly")
            else:
                # PID 파일이 없음
                if status.status == ServiceStatus.RUNNING:
                    status.status = ServiceStatus.STOPPED
                    self.logger.warning(f"Service {service_name} stopped (no PID file)")
            
            # 하트비트 확인
            heartbeat = self.state_bus.get_service_heartbeat(service_name)
            if heartbeat:
                status.last_heartbeat = heartbeat.get('ts', 0)
                
                # 하트비트 타임아웃 확인
                if current_time - status.last_heartbeat > service_config.heartbeat_timeout:
                    if status.status == ServiceStatus.RUNNING:
                        status.status = ServiceStatus.CRASHED
                        status.last_error = f"Heartbeat timeout ({service_config.heartbeat_timeout}s)"
                        self.logger.warning(f"Service {service_name} heartbeat timeout")
            
        except Exception as e:
            self.logger.error(f"Failed to check service status for {service_name}: {e}")
    
    def _check_service_health(self, service_name: str, service_config: ServiceConfig):
        """서비스 건강 상태 확인 및 복구"""
        try:
            current_time = time.time()
            status = self.service_status[service_name]
            
            # 서비스가 중지되었거나 크래시된 경우
            if status.status in [ServiceStatus.STOPPED, ServiceStatus.CRASHED]:
                # 재시작 쿨다운 확인
                if current_time - status.last_restart < service_config.restart_cooldown:
                    return
                
                # 최대 재시작 횟수 확인
                if status.restart_count >= service_config.max_restarts:
                    self.logger.error(f"Service {service_name} exceeded max restarts ({service_config.max_restarts})")
                    self._enter_failsafe_mode(service_name)
                    return
                
                # 서비스 재시작
                if self._restart_service(service_name, service_config):
                    status.restart_count += 1
                    status.total_restarts += 1
                    status.last_restart = current_time
                    self._stats["total_restarts"] += 1
                    self._stats["last_restart_time"] = current_time
                    
                    self.logger.info(f"Service {service_name} restarted (attempt {status.restart_count})")
                else:
                    self.logger.error(f"Failed to restart service {service_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to check service health for {service_name}: {e}")
    
    def _restart_service(self, service_name: str, service_config: ServiceConfig) -> bool:
        """서비스 재시작"""
        try:
            # 기존 프로세스 정리
            self._cleanup_service(service_name, service_config)
            
            # 서비스 시작
            return self._start_service(service_name, service_config)
            
        except Exception as e:
            self.logger.error(f"Failed to restart service {service_name}: {e}")
            return False
    
    def _start_service(self, service_name: str, service_config: ServiceConfig) -> bool:
        """서비스 시작"""
        try:
            # 작업 디렉토리 확인
            working_dir = Path(service_config.working_dir)
            if not working_dir.exists():
                self.logger.error(f"Working directory not found: {working_dir}")
                return False
            
            # 서비스 시작
            process = subprocess.Popen(
                service_config.command,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            # PID 파일 생성
            pid_file = Path(service_config.pid_file)
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(process.pid))
            
            # 상태 업데이트
            status = self.service_status[service_name]
            status.status = ServiceStatus.RUNNING
            status.pid = process.pid
            status.start_time = time.time()
            
            self.logger.info(f"Service {service_name} started (PID: {process.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start service {service_name}: {e}")
            return False
    
    def _stop_service(self, service_name: str, service_config: ServiceConfig) -> bool:
        """서비스 중지"""
        try:
            status = self.service_status[service_name]
            
            if status.pid and psutil.pid_exists(status.pid):
                # 프로세스 종료
                if service_config.graceful_shutdown:
                    # 우아한 종료 시도
                    try:
                        os.kill(status.pid, signal.SIGTERM)
                        time.sleep(service_config.shutdown_timeout)
                        
                        # 여전히 실행 중이면 강제 종료
                        if psutil.pid_exists(status.pid):
                            os.kill(status.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # 프로세스가 이미 종료됨
                else:
                    # 강제 종료
                    try:
                        os.kill(status.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # 프로세스가 이미 종료됨
            
            # 상태 업데이트
            status.status = ServiceStatus.STOPPED
            status.pid = None
            
            # 정리
            self._cleanup_service(service_name, service_config)
            
            self.logger.info(f"Service {service_name} stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop service {service_name}: {e}")
            return False
    
    def _cleanup_service(self, service_name: str, service_config: ServiceConfig):
        """서비스 정리"""
        try:
            # PID 파일 삭제
            pid_file = Path(service_config.pid_file)
            if pid_file.exists():
                pid_file.unlink()
            
            # 락 파일 삭제
            lock_file = Path(service_config.lock_file)
            if lock_file.exists():
                lock_file.unlink()
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup service {service_name}: {e}")
    
    def _enter_failsafe_mode(self, service_name: str):
        """페일세이프 모드 진입"""
        try:
            self._stats["failsafe_activations"] += 1
            
            # STOP.TXT 마커 생성
            stop_file = Path("STOP.TXT")
            stop_file.write_text(f"Failsafe mode activated for service: {service_name}\n"
                               f"Timestamp: {time.time()}\n"
                               f"Reason: Exceeded max restarts\n")
            
            # 모든 서비스 중지
            self._shutdown_all_services()
            
            self.logger.error(f"FAILSAFE MODE ACTIVATED for service {service_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to enter failsafe mode: {e}")
    
    def _shutdown_all_services(self):
        """모든 서비스 종료"""
        try:
            for service_name, service_config in self.services.items():
                if self.service_status[service_name].status == ServiceStatus.RUNNING:
                    self._stop_service(service_name, service_config)
            
        except Exception as e:
            self.logger.error(f"Failed to shutdown all services: {e}")
    
    def _update_state_bus(self):
        """상태 버스 업데이트"""
        try:
            # 서비스 상태 업데이트
            service_heartbeats = {}
            for service_name, status in self.service_status.items():
                service_heartbeats[service_name] = {
                    "status": status.status.value,
                    "pid": status.pid,
                    "last_heartbeat": status.last_heartbeat,
                    "restart_count": status.restart_count,
                    "uptime": time.time() - status.start_time if status.start_time > 0 else 0,
                }
            
            # 상태 버스에 업데이트
            self.state_bus.update_service_heartbeats(service_heartbeats)
            
        except Exception as e:
            self.logger.error(f"Failed to update state bus: {e}")
    
    def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        """서비스 상태 반환"""
        return self.service_status.get(service_name)
    
    def get_all_service_status(self) -> Dict[str, ServiceStatus]:
        """모든 서비스 상태 반환"""
        return self.service_status.copy()
    
    def restart_service(self, service_name: str) -> bool:
        """서비스 수동 재시작"""
        try:
            if service_name not in self.services:
                self.logger.error(f"Unknown service: {service_name}")
                return False
            
            service_config = self.services[service_name]
            return self._restart_service(service_name, service_config)
            
        except Exception as e:
            self.logger.error(f"Failed to restart service {service_name}: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """서비스 수동 중지"""
        try:
            if service_name not in self.services:
                self.logger.error(f"Unknown service: {service_name}")
                return False
            
            service_config = self.services[service_name]
            return self._stop_service(service_name, service_config)
            
        except Exception as e:
            self.logger.error(f"Failed to stop service {service_name}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        stats = self._stats.copy()
        stats["services"] = {}
        
        for service_name, status in self.service_status.items():
            stats["services"][service_name] = {
                "status": status.status.value,
                "restart_count": status.restart_count,
                "crash_count": status.crash_count,
                "uptime": time.time() - status.start_time if status.start_time > 0 else 0,
            }
        
        return stats


# 전역 인스턴스
_global_process_supervisor: Optional[ProcessSupervisor] = None


def get_process_supervisor() -> ProcessSupervisor:
    """전역 프로세스 감독자 반환"""
    global _global_process_supervisor
    if _global_process_supervisor is None:
        _global_process_supervisor = ProcessSupervisor()
        _global_process_supervisor.start()
    return _global_process_supervisor


def restart_service(service_name: str) -> bool:
    """서비스 재시작"""
    return get_process_supervisor().restart_service(service_name)


def stop_service(service_name: str) -> bool:
    """서비스 중지"""
    return get_process_supervisor().stop_service(service_name)


def get_service_status(service_name: str) -> Optional[ServiceStatus]:
    """서비스 상태 반환"""
    return get_process_supervisor().get_service_status(service_name)


def get_all_service_status() -> Dict[str, ServiceStatus]:
    """모든 서비스 상태 반환"""
    return get_process_supervisor().get_all_service_status()


def get_supervisor_stats() -> Dict[str, Any]:
    """감독자 통계 반환"""
    return get_process_supervisor().get_stats()
