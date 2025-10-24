#!/usr/bin/env python3
"""
Auto-Heal FSM (Fail-Safe)
Production-grade auto-healing with quarantine mode and global breakers
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .centralized_path_registry import get_path_registry
from .robust_health_reader import get_robust_health_reader


class ServiceState(Enum):
    """서비스 상태"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    QUARANTINED = "quarantined"
    RECOVERING = "recovering"


class HealAction(Enum):
    """치료 액션"""
    RESTART = "restart"
    QUARANTINE = "quarantine"
    GLOBAL_BREAK = "global_break"
    MONITOR = "monitor"
    NO_ACTION = "no_action"


@dataclass
class ServiceHealth:
    """서비스 헬스 정보"""
    name: str
    state: ServiceState
    age: Optional[float]
    threshold: float
    consecutive_failures: int
    last_restart: float
    quarantine_until: Optional[float] = None
    restart_count: int = 0


@dataclass
class HealDecision:
    """치료 결정"""
    service: str
    action: HealAction
    reason: str
    confidence: float
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class GlobalBreaker:
    """글로벌 차단기"""
    active: bool
    reason: str
    triggered_at: float
    daily_pnl_loss: float = 0.0
    balance_shortfall: float = 0.0
    ws_failure_count: int = 0


class AutoHealFSM:
    """Auto-Heal FSM (Fail-Safe)"""
    
    def __init__(self, repo_root: Path):
        self.logger = logging.getLogger(__name__)
        self.repo_root = repo_root
        self.path_registry = get_path_registry(repo_root)
        self.health_reader = get_robust_health_reader()
        
        # FSM 상태
        self.services: Dict[str, ServiceHealth] = {}
        self.global_breaker = GlobalBreaker(
            active=False,
            reason="",
            triggered_at=0.0
        )
        
        # 설정
        self.max_restart_attempts = 3
        self.quarantine_duration = 300  # 5분
        self.global_breaker_thresholds = {
            "daily_pnl_loss": -1000.0,  # -$1000
            "balance_shortfall": -500.0,  # -$500
            "ws_failure_count": 10  # 10회 연속 실패
        }
        
        # 통계
        self.stats = {
            "restarts_last_hour": 0,
            "quarantines": 0,
            "global_breaks": 0,
            "health_score": 100.0
        }
        
        # 시작 시간
        self.start_time = time.time()
        self.last_restart_hour = int(time.time() // 3600)
        
        # 로그 디렉토리
        self.log_dir = self.repo_root / "logs" / "auto_heal"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("AutoHealFSM initialized")
    
    def assess_health(self) -> Dict[str, ServiceHealth]:
        """전체 서비스 헬스 평가"""
        try:
            # 헬스 상태 조회
            health_status = self.health_reader.get_all_health_status(self.path_registry)
            
            # 서비스별 헬스 정보 생성
            services = {}
            
            # Feeder (ws_stream_databus)
            feeder_age = health_status.get("ws_stream_databus", {}).get("age")
            services["feeder"] = ServiceHealth(
                name="feeder",
                state=self._determine_service_state(feeder_age, 30),
                age=feeder_age,
                threshold=30,
                consecutive_failures=self.services.get("feeder", ServiceHealth("feeder", ServiceState.HEALTHY, 0, 30, 0, 0)).consecutive_failures,
                last_restart=self.services.get("feeder", ServiceHealth("feeder", ServiceState.HEALTHY, 0, 30, 0, 0)).last_restart,
                quarantine_until=self.services.get("feeder", ServiceHealth("feeder", ServiceState.HEALTHY, 0, 30, 0, 0)).quarantine_until,
                restart_count=self.services.get("feeder", ServiceHealth("feeder", ServiceState.HEALTHY, 0, 30, 0, 0)).restart_count
            )
            
            # ARES (ares_signal_flow)
            ares_age = health_status.get("ares", {}).get("age")
            services["ares"] = ServiceHealth(
                name="ares",
                state=self._determine_service_state(ares_age, 75),
                age=ares_age,
                threshold=75,
                consecutive_failures=self.services.get("ares", ServiceHealth("ares", ServiceState.HEALTHY, 0, 75, 0, 0)).consecutive_failures,
                last_restart=self.services.get("ares", ServiceHealth("ares", ServiceState.HEALTHY, 0, 75, 0, 0)).last_restart,
                quarantine_until=self.services.get("ares", ServiceHealth("ares", ServiceState.HEALTHY, 0, 75, 0, 0)).quarantine_until,
                restart_count=self.services.get("ares", ServiceHealth("ares", ServiceState.HEALTHY, 0, 75, 0, 0)).restart_count
            )
            
            # Trader (trader_readiness)
            trader_age = health_status.get("trader", {}).get("age")
            services["trader"] = ServiceHealth(
                name="trader",
                state=self._determine_service_state(trader_age, 300),
                age=trader_age,
                threshold=300,
                consecutive_failures=self.services.get("trader", ServiceHealth("trader", ServiceState.HEALTHY, 0, 300, 0, 0)).consecutive_failures,
                last_restart=self.services.get("trader", ServiceHealth("trader", ServiceState.HEALTHY, 0, 300, 0, 0)).last_restart,
                quarantine_until=self.services.get("trader", ServiceHealth("trader", ServiceState.HEALTHY, 0, 300, 0, 0)).quarantine_until,
                restart_count=self.services.get("trader", ServiceHealth("trader", ServiceState.HEALTHY, 0, 300, 0, 0)).restart_count
            )
            
            # Positions (positions_snapshot)
            positions_age = health_status.get("positions", {}).get("age")
            services["positions"] = ServiceHealth(
                name="positions",
                state=self._determine_service_state(positions_age, 60),
                age=positions_age,
                threshold=60,
                consecutive_failures=self.services.get("positions", ServiceHealth("positions", ServiceState.HEALTHY, 0, 60, 0, 0)).consecutive_failures,
                last_restart=self.services.get("positions", ServiceHealth("positions", ServiceState.HEALTHY, 0, 60, 0, 0)).last_restart,
                quarantine_until=self.services.get("positions", ServiceHealth("positions", ServiceState.HEALTHY, 0, 60, 0, 0)).quarantine_until,
                restart_count=self.services.get("positions", ServiceHealth("positions", ServiceState.HEALTHY, 0, 60, 0, 0)).restart_count
            )
            
            self.services = services
            return services
            
        except Exception as e:
            self.logger.error(f"Health assessment failed: {e}")
            return {}
    
    def make_heal_decisions(self) -> List[HealDecision]:
        """치료 결정 생성"""
        decisions = []
        
        try:
            # 글로벌 차단기 체크
            if self._check_global_breakers():
                decision = HealDecision(
                    service="system",
                    action=HealAction.GLOBAL_BREAK,
                    reason=self.global_breaker.reason,
                    confidence=1.0,
                    timestamp=time.time(),
                    metadata={"breaker": asdict(self.global_breaker)}
                )
                decisions.append(decision)
                return decisions
            
            # 서비스별 치료 결정
            for service_name, service_health in self.services.items():
                decision = self._make_service_heal_decision(service_name, service_health)
                if decision:
                    decisions.append(decision)
            
            return decisions
            
        except Exception as e:
            self.logger.error(f"Heal decision making failed: {e}")
            return []
    
    def execute_heal_actions(self, decisions: List[HealDecision]) -> Dict[str, bool]:
        """치료 액션 실행"""
        results = {}
        
        try:
            for decision in decisions:
                service = decision.service
                action = decision.action
                
                if action == HealAction.RESTART:
                    success = self._restart_service(service)
                    results[service] = success
                    
                    if success:
                        self._update_service_after_restart(service)
                        self.stats["restarts_last_hour"] += 1
                    else:
                        self._increment_failure_count(service)
                
                elif action == HealAction.QUARANTINE:
                    self._quarantine_service(service, decision.reason)
                    results[service] = True
                    self.stats["quarantines"] += 1
                
                elif action == HealAction.GLOBAL_BREAK:
                    self._trigger_global_break(decision.reason)
                    results[service] = True
                    self.stats["global_breaks"] += 1
                
                elif action == HealAction.MONITOR:
                    results[service] = True
                
                # 결정 로그 기록
                self._log_heal_decision(decision, results.get(service, False))
            
            # 통계 업데이트
            self._update_stats()
            
            return results
            
        except Exception as e:
            self.logger.error(f"Heal action execution failed: {e}")
            return {}
    
    def _determine_service_state(self, age: Optional[float], threshold: float) -> ServiceState:
        """서비스 상태 결정"""
        if age is None:
            return ServiceState.FAILED
        
        if age <= threshold:
            return ServiceState.HEALTHY
        elif age <= threshold * 2:
            return ServiceState.DEGRADED
        else:
            return ServiceState.FAILED
    
    def _make_service_heal_decision(self, service_name: str, service_health: ServiceHealth) -> Optional[HealDecision]:
        """서비스별 치료 결정"""
        current_time = time.time()
        
        # 격리 중인 서비스 체크
        if service_health.quarantine_until and current_time < service_health.quarantine_until:
            return HealDecision(
                service=service_name,
                action=HealAction.MONITOR,
                reason=f"Service in quarantine until {time.strftime('%H:%M:%S', time.localtime(service_health.quarantine_until))}",
                confidence=1.0,
                timestamp=current_time,
                metadata={"quarantine_until": service_health.quarantine_until}
            )
        
        # 상태별 치료 결정
        if service_health.state == ServiceState.HEALTHY:
            return None  # 치료 불필요
        
        elif service_health.state == ServiceState.DEGRADED:
            # 성능 저하 - 모니터링
            return HealDecision(
                service=service_name,
                action=HealAction.MONITOR,
                reason=f"Service degraded (age: {service_health.age:.1f}s > {service_health.threshold}s)",
                confidence=0.7,
                timestamp=current_time,
                metadata={"age": service_health.age, "threshold": service_health.threshold}
            )
        
        elif service_health.state == ServiceState.FAILED:
            # 실패 - 재시작 또는 격리
            if service_health.consecutive_failures < self.max_restart_attempts:
                return HealDecision(
                    service=service_name,
                    action=HealAction.RESTART,
                    reason=f"Service failed (age: {service_health.age:.1f}s > {service_health.threshold}s), attempt {service_health.consecutive_failures + 1}",
                    confidence=0.8,
                    timestamp=current_time,
                    metadata={"age": service_health.age, "threshold": service_health.threshold, "attempt": service_health.consecutive_failures + 1}
                )
            else:
                return HealDecision(
                    service=service_name,
                    action=HealAction.QUARANTINE,
                    reason=f"Service failed {service_health.consecutive_failures} times, entering quarantine",
                    confidence=0.9,
                    timestamp=current_time,
                    metadata={"consecutive_failures": service_health.consecutive_failures}
                )
        
        return None
    
    def _check_global_breakers(self) -> bool:
        """글로벌 차단기 체크"""
        try:
            # 일일 PnL 손실 체크
            daily_pnl = self._get_daily_pnl()
            if daily_pnl < self.global_breaker_thresholds["daily_pnl_loss"]:
                self.global_breaker.active = True
                self.global_breaker.reason = f"Daily PnL loss: ${daily_pnl:.2f}"
                self.global_breaker.daily_pnl_loss = daily_pnl
                return True
            
            # 잔고 부족 체크
            balance_shortfall = self._get_balance_shortfall()
            if balance_shortfall < self.global_breaker_thresholds["balance_shortfall"]:
                self.global_breaker.active = True
                self.global_breaker.reason = f"Balance shortfall: ${balance_shortfall:.2f}"
                self.global_breaker.balance_shortfall = balance_shortfall
                return True
            
            # WebSocket 연속 실패 체크
            ws_failures = self._get_ws_failure_count()
            if ws_failures >= self.global_breaker_thresholds["ws_failure_count"]:
                self.global_breaker.active = True
                self.global_breaker.reason = f"WebSocket failures: {ws_failures}"
                self.global_breaker.ws_failure_count = ws_failures
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Global breaker check failed: {e}")
            return False
    
    def _restart_service(self, service_name: str) -> bool:
        """서비스 재시작"""
        try:
            # 서비스별 재시작 로직
            if service_name == "feeder":
                return self._restart_feeder()
            elif service_name == "ares":
                return self._restart_ares()
            elif service_name == "trader":
                return self._restart_trader()
            elif service_name == "positions":
                return self._restart_positions()
            else:
                self.logger.warning(f"Unknown service: {service_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Service restart failed: {e}")
            return False
    
    def _restart_feeder(self) -> bool:
        """Feeder 재시작"""
        try:
            import subprocess
            import sys

            # Feeder 프로세스 중지
            result = subprocess.run([
                sys.executable, "-m", "shared.service_orchestrator", "--stop"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to stop feeder: {result.stderr}")
                return False
            
            # 잠시 대기
            time.sleep(5)
            
            # Feeder 재시작
            result = subprocess.run([
                sys.executable, "-m", "shared.service_orchestrator", "--start"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to start feeder: {result.stderr}")
                return False
            
            self.logger.info("Feeder restarted successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Feeder restart failed: {e}")
            return False
    
    def _restart_ares(self) -> bool:
        """ARES 재시작"""
        try:
            import subprocess
            import sys

            # ARES 프로세스 중지
            result = subprocess.run([
                sys.executable, "-m", "shared.ares_heartbeat_writer", "--stop"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to stop ARES: {result.stderr}")
                return False
            
            # 잠시 대기
            time.sleep(5)
            
            # ARES 재시작
            result = subprocess.run([
                sys.executable, "-m", "shared.ares_heartbeat_writer", "--start"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to start ARES: {result.stderr}")
                return False
            
            self.logger.info("ARES restarted successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"ARES restart failed: {e}")
            return False
    
    def _restart_trader(self) -> bool:
        """Trader 재시작"""
        try:
            import subprocess
            import sys

            # Trader 프로세스 중지
            result = subprocess.run([
                sys.executable, "-m", "services.trader_service", "--stop"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to stop trader: {result.stderr}")
                return False
            
            # 잠시 대기
            time.sleep(5)
            
            # Trader 재시작
            result = subprocess.run([
                sys.executable, "-m", "services.trader_service", "--start"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to start trader: {result.stderr}")
                return False
            
            self.logger.info("Trader restarted successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Trader restart failed: {e}")
            return False
    
    def _restart_positions(self) -> bool:
        """Positions 재시작 (HealthEmitter)"""
        try:
            import subprocess
            import sys

            # HealthEmitter 중지
            result = subprocess.run([
                sys.executable, "-m", "shared.health_emitter_launcher", "--stop"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to stop HealthEmitter: {result.stderr}")
                return False
            
            # 잠시 대기
            time.sleep(5)
            
            # HealthEmitter 재시작
            result = subprocess.run([
                sys.executable, "-m", "shared.health_emitter_launcher", "--start"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to start HealthEmitter: {result.stderr}")
                return False
            
            self.logger.info("HealthEmitter restarted successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"HealthEmitter restart failed: {e}")
            return False
    
    def _quarantine_service(self, service_name: str, reason: str):
        """서비스 격리"""
        current_time = time.time()
        quarantine_until = current_time + self.quarantine_duration
        
        if service_name in self.services:
            self.services[service_name].quarantine_until = quarantine_until
            self.services[service_name].state = ServiceState.QUARANTINED
        
        self.logger.warning(f"Service {service_name} quarantined until {time.strftime('%H:%M:%S', time.localtime(quarantine_until))}: {reason}")
    
    def _trigger_global_break(self, reason: str):
        """글로벌 차단 트리거"""
        current_time = time.time()
        
        self.global_breaker.active = True
        self.global_breaker.reason = reason
        self.global_breaker.triggered_at = current_time
        
        # STOP.TXT 파일 생성
        try:
            stop_file = self.repo_root / "STOP.TXT"
            with open(stop_file, 'w') as f:
                f.write(f"Global breaker triggered at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Reason: {reason}\n")
                f.write("All new orders are blocked\n")
                f.write("Manual intervention required\n")
            
            self.logger.critical(f"Global breaker triggered: {reason}")
            
            # 텔레그램 알림 (선택적)
            self._send_telegram_alert(reason)
            
        except Exception as e:
            self.logger.error(f"Failed to create STOP.TXT: {e}")
    
    def _update_service_after_restart(self, service_name: str):
        """재시작 후 서비스 상태 업데이트"""
        current_time = time.time()
        
        if service_name in self.services:
            self.services[service_name].last_restart = current_time
            self.services[service_name].consecutive_failures = 0
            self.services[service_name].quarantine_until = None
            self.services[service_name].restart_count += 1
            self.services[service_name].state = ServiceState.RECOVERING
    
    def _increment_failure_count(self, service_name: str):
        """실패 횟수 증가"""
        if service_name in self.services:
            self.services[service_name].consecutive_failures += 1
    
    def _update_stats(self):
        """통계 업데이트"""
        current_hour = int(time.time() // 3600)
        
        # 시간이 바뀌면 재시작 카운트 리셋
        if current_hour != self.last_restart_hour:
            self.stats["restarts_last_hour"] = 0
            self.last_restart_hour = current_hour
        
        # 헬스 스코어 계산
        healthy_services = sum(1 for s in self.services.values() if s.state == ServiceState.HEALTHY)
        total_services = len(self.services)
        
        if total_services > 0:
            self.stats["health_score"] = (healthy_services / total_services) * 100
        else:
            self.stats["health_score"] = 0.0
    
    def _get_daily_pnl(self) -> float:
        """일일 PnL 조회"""
        try:
            # PnL 파일에서 일일 손익 조회
            pnl_file = self.path_registry.get("pnl_rollup")
            if pnl_file and pnl_file.exists():
                with open(pnl_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 오늘의 PnL 합계
                today = time.strftime('%Y-%m-%d')
                daily_pnl = 0.0
                
                for entry in data.get("trades", []):
                    if entry.get("date") == today:
                        daily_pnl += entry.get("realized_pnl_usdt", 0.0)
                
                return daily_pnl
            
            return 0.0
            
        except Exception as e:
            self.logger.error(f"Failed to get daily PnL: {e}")
            return 0.0
    
    def _get_balance_shortfall(self) -> float:
        """잔고 부족 조회"""
        try:
            # 잔고 파일에서 부족분 조회
            balance_file = self.path_registry.get("trader_balances")
            if balance_file and balance_file.exists():
                with open(balance_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # USDT 잔고 확인
                usdt_balance = data.get("USDT", {}).get("free", 0.0)
                if usdt_balance < 0:
                    return usdt_balance
                
                return 0.0
            
            return 0.0
            
        except Exception as e:
            self.logger.error(f"Failed to get balance shortfall: {e}")
            return 0.0
    
    def _get_ws_failure_count(self) -> int:
        """WebSocket 실패 횟수 조회"""
        try:
            # WebSocket 로그에서 실패 횟수 조회
            ws_log_file = self.log_dir / "websocket_failures.json"
            if ws_log_file.exists():
                with open(ws_log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                return data.get("consecutive_failures", 0)
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Failed to get WS failure count: {e}")
            return 0
    
    def _send_telegram_alert(self, reason: str):
        """텔레그램 알림 전송"""
        try:
            # 텔레그램 봇 설정
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            
            if not bot_token or not chat_id:
                self.logger.warning("Telegram credentials not configured")
                return
            
            import requests
            
            message = f"🚨 Global Breaker Triggered\n\nReason: {reason}\nTime: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\nManual intervention required."
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                self.logger.info("Telegram alert sent successfully")
            else:
                self.logger.error(f"Failed to send Telegram alert: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Telegram alert failed: {e}")
    
    def _log_heal_decision(self, decision: HealDecision, success: bool):
        """치료 결정 로그 기록"""
        try:
            log_entry = {
                "timestamp": decision.timestamp,
                "service": decision.service,
                "action": decision.action.value,
                "reason": decision.reason,
                "confidence": decision.confidence,
                "success": success,
                "metadata": decision.metadata
            }
            
            log_file = self.log_dir / "heal_decisions.jsonl"
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            
        except Exception as e:
            self.logger.error(f"Failed to log heal decision: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        return {
            **self.stats,
            "uptime_seconds": int(time.time() - self.start_time),
            "global_breaker_active": self.global_breaker.active,
            "global_breaker_reason": self.global_breaker.reason,
            "services_count": len(self.services),
            "healthy_services": sum(1 for s in self.services.values() if s.state == ServiceState.HEALTHY),
            "quarantined_services": sum(1 for s in self.services.values() if s.state == ServiceState.QUARANTINED)
        }


def get_auto_heal_fsm(repo_root: Path) -> AutoHealFSM:
    """AutoHealFSM 인스턴스 획득"""
    return AutoHealFSM(repo_root)
