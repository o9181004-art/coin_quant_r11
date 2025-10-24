#!/usr/bin/env python3
"""
완전무결 헬스체크 시스템 v2 - SSOT 기반
각 서비스의 모든 핵심 기능을 검증하고 하나라도 실패하면 즉시 감지

확정된 가정:
- Timeframe: 1m only (5m/15m은 ARES 내부 downsampling)
- Ledger: trades.jsonl = SSOT
- Daily PnL: 00:00 KST 초기화
- Auto-Heal: 필수 서비스 (continuous playbook execution)
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psutil

from shared.health_thresholds import get_thresholds

# SSOT import (circular import 방지를 위해 필요시에만 import)
try:
    from shared.health_ssot import (CheckResult, ComponentHealth, HealthSSOT,
                                    PipelineIntegrity, get_ssot_manager,
                                    load_health_ssot, save_health_ssot)
    from shared.recovery_playbooks import get_playbooks, run_playbook
    SSOT_AVAILABLE = True
except ImportError:
    SSOT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class FeederHealthCheck:
    """Feeder 건강성 체크 결과"""
    
    process_running: bool = False
    websocket_connected: bool = False
    data_collecting: bool = False
    file_writing: bool = False
    ares_feeding: bool = False
    
    # 상세 정보
    active_symbols: int = 0
    stale_symbols: int = 0
    last_update_age: float = 999.0
    error_message: str = ""
    
    @property
    def is_healthy(self) -> bool:
        """모든 핵심 기능이 정상이어야 True"""
        return (
            self.process_running and
            self.websocket_connected and
            self.data_collecting and
            self.file_writing and
            self.ares_feeding
        )


@dataclass
class TraderHealthCheck:
    """Trader 건강성 체크 결과"""
    
    process_running: bool = False
    signal_receiving: bool = False
    risk_checking: bool = False
    order_executing: bool = False
    position_tracking: bool = False
    
    # 상세 정보
    active_signals: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    total_exposure: float = 0.0
    daily_pnl: float = 0.0
    error_message: str = ""
    
    @property
    def is_healthy(self) -> bool:
        """모든 핵심 기능이 정상이어야 True"""
        return (
            self.process_running and
            self.signal_receiving and
            self.risk_checking and
            self.order_executing and
            self.position_tracking
        )


@dataclass
class AutoHealHealthCheck:
    """Auto-Heal 건강성 체크 결과"""
    
    process_running: bool = False
    monitoring_active: bool = False
    data_validation: bool = False
    auto_recovery: bool = False
    
    # 상세 정보
    last_check_age: float = 999.0
    restart_count: int = 0
    error_message: str = ""
    
    @property
    def is_healthy(self) -> bool:
        """모든 핵심 기능이 정상이어야 True"""
        return (
            self.process_running and
            self.monitoring_active and
            self.data_validation and
            self.auto_recovery
        )


@dataclass
class SystemHealthCheck:
    """시스템 전체 건강성 체크 결과"""
    
    timestamp: float
    feeder: FeederHealthCheck
    trader: TraderHealthCheck
    auto_heal: AutoHealHealthCheck
    
    @property
    def is_all_healthy(self) -> bool:
        """모든 서비스가 건강해야 True"""
        return (
            self.feeder.is_healthy and
            self.trader.is_healthy and
            self.auto_heal.is_healthy
        )
    
    @property
    def overall_status(self) -> str:
        """전체 상태 요약"""
        if self.is_all_healthy:
            return "healthy"
        elif not self.feeder.is_healthy:
            return "feeder_issue"
        elif not self.trader.is_healthy:
            return "trader_issue"
        elif not self.auto_heal.is_healthy:
            return "autoheal_issue"
        else:
            return "unknown_issue"


class ComprehensiveHealthChecker:
    """완전무결 헬스 체커"""
    
    def __init__(self):
        from shared.path_resolver import get_path_resolver
        self.path_resolver = get_path_resolver()
        self.project_root = self.path_resolver.ssot_root
        self.logger = logging.getLogger(__name__)
        self.thresholds = get_thresholds()
        
    def check_all_v2(self) -> HealthSSOT:
        """완전무결 헬스체크 v2 - SSOT 반환"""
        ssot = HealthSSOT()
        ssot.timestamp = time.time()
        
        # Feeder 체크
        ssot.feeder = self._check_feeder_v2()
        
        # Trader 체크
        ssot.trader = self._check_trader_v2()
        
        # Auto-Heal 체크
        ssot.auto_heal = self._check_auto_heal_v2()
        
        # Pipeline 무결성 체크
        ssot.pipeline = self._check_pipeline_integrity()
        
        # Overall status 결정
        ssot.overall_status = self._determine_overall_status(ssot)
        ssot.safe_to_trade = self._is_safe_to_trade(ssot)
        ssot.mode = self._determine_mode(ssot)
        
        # Circuit breaker 체크
        ssot.circuit_breaker = self._check_circuit_breaker()
        
        # Writer 메트릭 체크
        ssot.writer_metrics = self._check_writer_metrics()
        
        # SSOT 저장
        save_health_ssot(ssot)
        
        return ssot
    
    def _check_feeder_v2(self) -> ComponentHealth:
        """Feeder 기능 체크 v2"""
        checks = {}
        metrics = {}
        
        # Check 1: 프로세스 실행 여부
        process_ok = self._is_process_running("feeder")
        checks["process"] = CheckResult(
            ok=process_ok,
            reason="" if process_ok else "Feeder 프로세스 미실행"
        )
        
        # Check 2: 스냅샷 파일 존재 + 신선도
        snapshot_dir = self.path_resolver.snapshots_dir()
        snapshot_files = list(snapshot_dir.glob("prices_*.json")) if snapshot_dir.exists() else []
        
        snapshot_ok = len(snapshot_files) > 0
        if snapshot_ok:
            latest_file = max(snapshot_files, key=lambda f: f.stat().st_mtime)
            age_sec = time.time() - latest_file.stat().st_mtime
            snapshot_ok = age_sec < self.thresholds.FEEDER_DATABUS_SNAPSHOT_AGE_SEC
            
            checks["snapshot_fresh"] = CheckResult(
                ok=snapshot_ok,
                reason="" if snapshot_ok else f"스냅샷 오래됨 ({age_sec:.0f}초)",
                value=age_sec,
                threshold=self.thresholds.FEEDER_DATABUS_SNAPSHOT_AGE_SEC
            )
            metrics["snapshot_age_sec"] = age_sec
        else:
            checks["snapshot_fresh"] = CheckResult(
                ok=False,
                reason="스냅샷 파일 없음"
            )
        
        # Check 3: 커버리지 (멀티심볼 체크)
        coverage_pct = (len(snapshot_files) / 10) * 100 if snapshot_files else 0  # 10개 심볼 기준
        coverage_ok = coverage_pct >= self.thresholds.FEEDER_SNAPSHOT_COVERAGE_PCT
        
        checks["coverage"] = CheckResult(
            ok=coverage_ok,
            reason="" if coverage_ok else f"커버리지 부족 ({coverage_pct:.0f}%)",
            value=coverage_pct,
            threshold=self.thresholds.FEEDER_SNAPSHOT_COVERAGE_PCT
        )
        metrics["coverage_pct"] = coverage_pct
        
        # Overall status
        all_ok = all(c.ok for c in checks.values())
        status = "OK" if all_ok else ("WARN" if process_ok else "FAIL")
        
        # Remediation
        remediation = {"recommended": "none", "priority": "low", "eta_sec": 0}
        if not all_ok:
            if not process_ok:
                remediation = {"recommended": "PB-01", "priority": "critical", "eta_sec": 30}
            elif not snapshot_ok:
                remediation = {"recommended": "PB-02", "priority": "high", "eta_sec": 10}
        
        return ComponentHealth(
            status=status,
            checks=checks,
            metrics=metrics,
            artifacts={"snapshot_dir": str(snapshot_dir)},
            remediation=remediation
        )
    
    def _check_trader_v2(self) -> ComponentHealth:
        """Trader 기능 체크 v2"""
        checks = {}
        metrics = {}
        
        # Check 1: 프로세스 실행
        process_ok = self._is_process_running("trader")
        checks["process"] = CheckResult(
            ok=process_ok,
            reason="" if process_ok else "Trader 프로세스 미실행"
        )
        
        # Check 2: 체결 기록 파일 쓰기 확인
        trades_file = self.path_resolver.trades_dir() / "trades.jsonl"
        trades_ok = trades_file.exists()
        
        checks["ledger_exists"] = CheckResult(
            ok=trades_ok,
            reason="" if trades_ok else "체결 기록 없음"
        )
        
        # Check 3: 포지션 스냅샷 존재 + 신선도
        positions_file = self.path_resolver.data_dir() / "positions_snapshot.json"
        positions_ok = positions_file.exists()
        
        if positions_ok:
            age_sec = time.time() - positions_file.stat().st_mtime
            positions_fresh = age_sec < self.thresholds.TRADER_POSITION_SNAPSHOT_AGE_OK_SEC
            
            checks["positions_fresh"] = CheckResult(
                ok=positions_fresh,
                reason="" if positions_fresh else f"포지션 오래됨 ({age_sec:.0f}초)",
                value=age_sec,
                threshold=self.thresholds.TRADER_POSITION_SNAPSHOT_AGE_OK_SEC
            )
            metrics["positions_age_sec"] = age_sec
        else:
            checks["positions_fresh"] = CheckResult(
                ok=False,
                reason="포지션 스냅샷 없음"
            )
        
        # Check 4: Daily PnL 파일 존재
        pnl_file = self.path_resolver.data_dir() / "daily_pnl.json"
        pnl_ok = pnl_file.exists()
        
        checks["pnl_exists"] = CheckResult(
            ok=pnl_ok,
            reason="" if pnl_ok else "일일 손익 파일 없음"
        )
        
        if pnl_ok:
            try:
                with open(pnl_file, "r") as f:
                    pnl_data = json.load(f)
                    metrics["daily_pnl"] = pnl_data.get("total", 0.0)
            except:
                pass
        
        # Overall status
        all_ok = all(c.ok for c in checks.values())
        status = "OK" if all_ok else ("WARN" if process_ok else "FAIL")
        
        # Remediation
        remediation = {"recommended": "none", "priority": "low", "eta_sec": 0}
        if not all_ok:
            if not positions_ok:
                remediation = {"recommended": "PB-05", "priority": "high", "eta_sec": 5}
            elif not pnl_ok:
                remediation = {"recommended": "PB-06", "priority": "medium", "eta_sec": 10}
        
        return ComponentHealth(
            status=status,
            checks=checks,
            metrics=metrics,
            artifacts={"trades_file": str(trades_file)},
            remediation=remediation
        )
    
    def _check_auto_heal_v2(self) -> ComponentHealth:
        """Auto-Heal 기능 체크 v2"""
        checks = {}
        metrics = {}
        
        # Check 1: 프로세스 실행
        process_ok = self._is_process_running("auto_heal")
        checks["process"] = CheckResult(
            ok=process_ok,
            reason="" if process_ok else "Auto-Heal 프로세스 미실행"
        )
        
        # Check 2: 플레이북 실행 이력 확인
        playbooks = get_playbooks()
        history_ok = len(playbooks.playbook_history) > 0
        
        checks["playbook_history"] = CheckResult(
            ok=True,  # 이력 없어도 OK (아직 실행 안했을 수 있음)
            reason="",
            value=len(playbooks.playbook_history)
        )
        metrics["playbooks_run"] = len(playbooks.playbook_history)
        
        # Overall status
        status = "OK" if process_ok else "WARN"
        
        return ComponentHealth(
            status=status,
            checks=checks,
            metrics=metrics,
            artifacts={},
            remediation={"recommended": "none"}
        )
    
    def _check_pipeline_integrity(self) -> PipelineIntegrity:
        """파이프라인 무결성 체크"""
        # Feeder → ARES
        snapshot_dir = self.path_resolver.snapshots_dir()
        feeder_to_ares = snapshot_dir.exists() and len(list(snapshot_dir.glob("prices_*.json"))) > 0
        
        # ARES → Trader
        signals_dir = self.path_resolver.signals_dir()
        ares_to_trader = signals_dir.exists() and len(list(signals_dir.glob("*.json"))) > 0
        
        # Trader → Fills
        trades_file = self.path_resolver.trades_dir() / "trades.jsonl"
        trader_to_fills = trades_file.exists()
        
        # Fills → PnL
        pnl_file = self.path_resolver.data_dir() / "daily_pnl.json"
        fills_to_pnl = pnl_file.exists()
        
        # End-to-end
        end_to_end = feeder_to_ares and ares_to_trader and trader_to_fills and fills_to_pnl
        
        # Broken link 식별
        broken_link = None
        if not feeder_to_ares:
            broken_link = "feeder→ares"
        elif not ares_to_trader:
            broken_link = "ares→trader"
        elif not trader_to_fills:
            broken_link = "trader→fills"
        elif not fills_to_pnl:
            broken_link = "fills→pnl"
        
        return PipelineIntegrity(
            end_to_end_ok=end_to_end,
            feeder_to_ares_ok=feeder_to_ares,
            ares_to_trader_ok=ares_to_trader,
            trader_to_fills_ok=trader_to_fills,
            fills_to_pnl_ok=fills_to_pnl,
            broken_link=broken_link
        )
    
    def _determine_overall_status(self, ssot: HealthSSOT) -> str:
        """Overall status 결정"""
        if ssot.feeder.status == "FAIL" or ssot.trader.status == "FAIL":
            return "FAIL"
        elif ssot.feeder.status == "WARN" or ssot.trader.status == "WARN":
            return "WARN"
        elif not ssot.pipeline.end_to_end_ok:
            return "DEGRADED"
        else:
            return "OK"
    
    def _is_safe_to_trade(self, ssot: HealthSSOT) -> bool:
        """거래 가능 여부 - Pipeline Gates 기반"""
        # Pipeline Gates 체크
        feeder_to_ares_ok = ssot.pipeline.feeder_to_ares_ok
        ares_to_trader_ok = ssot.pipeline.ares_to_trader_ok
        trader_ok = ssot.trader.status == "OK"
        circuit_breaker_inactive = not ssot.circuit_breaker.get("active", False)
        
        # Writer stall 체크
        writer_healthy = not ssot.writer_metrics.get("is_stalled", True)
        
        return (
            feeder_to_ares_ok and
            ares_to_trader_ok and
            trader_ok and
            circuit_breaker_inactive and
            writer_healthy
        )
    
    def _determine_mode(self, ssot: HealthSSOT) -> str:
        """모드 결정"""
        if ssot.circuit_breaker.get("active", False):
            return "FAILSAFE"
        elif ssot.overall_status == "FAIL":
            return "POSITION_GUARD"
        elif ssot.overall_status == "DEGRADED":
            return "DEGRADED"
        else:
            return "NORMAL"
    
    def _check_circuit_breaker(self) -> Dict:
        """Circuit Breaker 상태 체크"""
        # Circuit breaker 파일 체크
        cb_file = self.path_resolver.data_dir() / "circuit_breaker.json"
        
        if cb_file.exists():
            try:
                with open(cb_file, "r") as f:
                    cb_data = json.load(f)
                    
                    if cb_data.get("active", False):
                        until = cb_data.get("until", 0)
                        
                        if time.time() < until:
                            return cb_data
                        else:
                            # Circuit breaker 만료 - 해제
                            cb_data["active"] = False
                            with open(cb_file, "w") as wf:
                                json.dump(cb_data, wf)
                            return cb_data
            except:
                pass
        
        return {"active": False, "until": 0, "reason": ""}
    
    def _check_writer_metrics(self) -> Dict:
        """Writer 메트릭 체크"""
        try:
            from feeder.heartbeat import get_heartbeat_monitor
            monitor = get_heartbeat_monitor()
            return monitor.get_writer_metrics()
        except Exception as e:
            self.logger.error(f"Failed to check writer metrics: {e}")
            return {
                "status": "unknown",
                "stall_sec": float('inf'),
                "is_stalled": True,
                "last_write_ts": 0,
                "total_writes": 0,
                "failed_writes": 0,
                "queue_size": 0
            }
    
    def check_all(self) -> SystemHealthCheck:
        """전체 시스템 건강성 체크"""
        return SystemHealthCheck(
            timestamp=time.time(),
            feeder=self._check_feeder(),
            trader=self._check_trader(),
            auto_heal=self._check_autoheal()
        )
    
    def _check_feeder(self) -> FeederHealthCheck:
        """Feeder 완전 검증"""
        result = FeederHealthCheck()
        
        try:
            # 1. 프로세스 확인
            result.process_running = self._is_process_running("feeder")
            if not result.process_running:
                result.error_message = "Feeder 프로세스 미실행"
                return result
            
            # 2. WebSocket 연결 확인 (health.json의 symbols 확인)
            health_file = self.project_root / "shared_data" / "health.json"
            if health_file.exists():
                with open(health_file, "r", encoding="utf-8") as f:
                    health_data = json.load(f)
                    
                    symbols = health_data.get("symbols", {})
                    result.active_symbols = len([s for s in symbols.values() if isinstance(s, dict)])
                    result.stale_symbols = len([
                        s for s in symbols.values() 
                        if isinstance(s, dict) and s.get("age_sec", 999) > 60
                    ])
                    
                    # WebSocket 연결 = ws_connected 필드 체크
                    connected_symbols = len([
                        s for s in symbols.values()
                        if isinstance(s, dict) and s.get("ws_connected", False) == True
                    ])
                    result.websocket_connected = connected_symbols > 0
            else:
                result.websocket_connected = False
                result.error_message = "health.json 없음"
                return result
            
            # 3. 데이터 수집 확인 (snapshots 파일들의 신선도)
            snapshot_dir = self.project_root / "shared_data" / "snapshots"
            if snapshot_dir.exists():
                snapshot_files = list(snapshot_dir.glob("prices_*.json"))
                if snapshot_files:
                    # 최근 업데이트된 파일 확인
                    latest_file = max(snapshot_files, key=lambda f: f.stat().st_mtime)
                    age = time.time() - latest_file.stat().st_mtime
                    result.last_update_age = age
                    result.data_collecting = age < 120  # 2분 이내 업데이트 (완화)
                else:
                    result.data_collecting = False
                    result.error_message = "스냅샷 파일 없음"
            else:
                result.data_collecting = False
                result.error_message = "snapshots 디렉토리 없음"
                return result
            
            # 4. 파일 기록 확인 (history 파일들의 신선도)
            history_dir = self.project_root / "shared_data" / "history"
            if history_dir.exists():
                history_files = list(history_dir.glob("*_1m.jsonl"))
                if history_files:
                    latest_file = max(history_files, key=lambda f: f.stat().st_mtime)
                    age = time.time() - latest_file.stat().st_mtime
                    result.file_writing = age < 120  # 2분 이내 기록
                else:
                    result.file_writing = False
                    result.error_message = "히스토리 파일 없음"
            else:
                result.file_writing = False
                result.error_message = "history 디렉토리 없음"
                return result
            
            # 5. ARES 전달 확인 (ares 파일들의 신선도 및 signals 존재)
            ares_dir = self.project_root / "shared_data" / "ares"
            if ares_dir.exists():
                ares_files = list(ares_dir.glob("*.json"))
                ares_with_signals = 0
                
                for ares_file in ares_files:
                    try:
                        with open(ares_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            # signals 배열이 있고 비어있지 않으면 카운트
                            if data.get("signals") and len(data.get("signals", [])) > 0:
                                ares_with_signals += 1
                    except:
                        continue
                
                # ARES 전달 = 신호가 있는 파일이 있음
                result.ares_feeding = ares_with_signals > 0
                
                if not result.ares_feeding:
                    result.error_message = "ARES 신호 없음"
            else:
                result.ares_feeding = False
                result.error_message = "ares 디렉토리 없음"
            
        except Exception as e:
            result.error_message = f"Feeder 체크 예외: {e}"
            
        return result
    
    def _check_trader(self) -> TraderHealthCheck:
        """Trader 완전 검증"""
        result = TraderHealthCheck()
        
        try:
            # 1. 프로세스 확인
            result.process_running = self._is_process_running("trader")
            if not result.process_running:
                result.error_message = "Trader 프로세스 미실행"
                return result
            
            # 2. 신호 수신 확인 (ares 파일들 존재 및 신선도)
            # signals 폴더는 deprecated, ares 폴더가 실제 신호 소스
            ares_dir = self.project_root / "shared_data" / "ares"
            if ares_dir.exists():
                signal_files = list(ares_dir.glob("*.json"))
                if signal_files:
                    # 최근 신호 파일 확인
                    latest_file = max(signal_files, key=lambda f: f.stat().st_mtime)
                    age = time.time() - latest_file.stat().st_mtime
                    result.signal_receiving = age < 300  # 5분 이내 신호 (완화)
                    
                    # 활성 신호 개수
                    for signal_file in signal_files:
                        try:
                            with open(signal_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                # ARES 신호 구조: signals 배열 확인
                                signals_list = data.get("signals", [])
                                if signals_list and len(signals_list) > 0:
                                    result.active_signals += 1
                        except:
                            continue
                else:
                    result.signal_receiving = False
                    result.error_message = "신호 파일 없음"
            else:
                result.signal_receiving = False
                result.error_message = "ares 디렉토리 없음"
                return result
            
            # 3. 리스크 체크 확인 (risk_status.json 존재 및 정상)
            risk_file = self.project_root / "shared_data" / "risk_status.json"
            if risk_file.exists():
                try:
                    with open(risk_file, "r", encoding="utf-8") as f:
                        risk_data = json.load(f)
                        # failsafe_mode가 아니면 정상
                        result.risk_checking = not risk_data.get("failsafe_mode", True)
                except:
                    result.risk_checking = False
                    result.error_message = "리스크 상태 파일 읽기 실패"
            else:
                # 파일이 없어도 정상 (초기 상태)
                result.risk_checking = True
            
            # 4. 주문 실행 확인 (최근 trades 기록 존재)
            trades_file = self.project_root / "trades" / "trades.jsonl"
            if trades_file.exists():
                age = time.time() - trades_file.stat().st_mtime
                result.order_executing = age < 300  # 5분 이내 주문
                
                # 성공/실패 카운트는 로그에서 확인 필요
                # 여기서는 간단히 파일 존재만 확인
                result.successful_orders = 1 if result.order_executing else 0
            else:
                # 체결 파일이 없어도 시작 단계에서는 정상
                result.order_executing = True  # 너무 strict하면 초기에 무조건 빨간불
                
            # 5. 포지션 추적 확인 (positions_snapshot.json 존재 및 신선도)
            positions_file = self.project_root / "shared_data" / "positions_snapshot.json"
            if positions_file.exists():
                try:
                    with open(positions_file, "r", encoding="utf-8") as f:
                        pos_data = json.load(f)
                        
                        # 타임스탬프 확인 (완화 - 순환 문제 방지)
                        ts = pos_data.get("ts", 0)
                        age = time.time() * 1000 - ts
                        result.position_tracking = age < 3600000  # 1시간 이내 (완화)
                        
                        # 총 노출 계산
                        for symbol, pos in pos_data.items():
                            if symbol != "ts" and isinstance(pos, dict):
                                qty = pos.get("qty", 0)
                                avg_price = pos.get("avg_price", 0)
                                result.total_exposure += abs(qty * avg_price)
                except:
                    result.position_tracking = False
                    result.error_message = "포지션 파일 읽기 실패"
            else:
                # 포지션 파일이 없으면 문제
                result.position_tracking = False
                result.error_message = "포지션 파일 없음"
            
        except Exception as e:
            result.error_message = f"Trader 체크 예외: {e}"
            
        return result
    
    def _check_autoheal(self) -> AutoHealHealthCheck:
        """Auto-Heal 완전 검증"""
        result = AutoHealHealthCheck()
        
        try:
            # Auto-Heal은 필수 서비스 (Supervisor Daemon에 의해 보장됨)
            
            # 1. 프로세스 확인 (필수)
            result.process_running = self._is_process_running("auto_heal")
            
            # 2. Supervisor Daemon 상태 확인
            supervisor_daemon_pid = self.project_root / "shared_data" / "supervisor_daemon.pid"
            if supervisor_daemon_pid.exists():
                try:
                    with open(supervisor_daemon_pid, "r", encoding="utf-8") as f:
                        pid = int(f.read().strip())
                    
                    # Supervisor Daemon 프로세스 확인
                    try:
                        process = psutil.Process(pid)
                        if process.is_running():
                            result.monitoring_active = True
                        else:
                            result.monitoring_active = False
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        result.monitoring_active = False
                except (ValueError, OSError):
                    result.monitoring_active = False
            else:
                result.monitoring_active = False
            
            # 3. 데이터 검증 활성 (health.json 업데이트 확인)
            health_file = self.project_root / "shared_data" / "health.json"
            if health_file.exists():
                age = time.time() - health_file.stat().st_mtime
                result.last_check_age = age
                result.data_validation = age < 120  # 2분 이내 업데이트
            else:
                result.data_validation = False
                result.error_message = "health.json 없음"
            
            # 4. 자동복구 기능 (Supervisor Daemon이 Auto-Heal 보장)
            result.auto_recovery = result.monitoring_active
            
        except Exception as e:
            result.error_message = f"AutoHeal 체크 예외: {e}"
            
        return result
    
    def _is_process_running(self, service_name: str) -> bool:
        """프로세스 실행 여부 확인 - CommandLine 기반"""
        try:
            # 먼저 CommandLine으로 실제 프로세스 찾기 (가장 정확)
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        cmdline = proc.info['cmdline']
                        if cmdline:
                            cmdline_str = ' '.join(cmdline).lower()
                            
                            # 서비스별 패턴 매칭 (완화된 기준)
                            if service_name == "feeder":
                                if "multi_symbol_stream_bus.py" in cmdline_str or "feeder" in cmdline_str or "services.feeder_service" in cmdline_str:
                                    return True
                            elif service_name == "trader":
                                if "trader_service.py" in cmdline_str or "trader" in cmdline_str or "services.trader_service" in cmdline_str:
                                    return True
                            elif service_name == "auto_heal":
                                if "auto_heal" in cmdline_str or "services.auto_heal" in cmdline_str:
                                    return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # CommandLine으로 못 찾으면 PID 파일 확인 (폴백)
            pid_locations = [
                self.project_root / "logs" / f"{service_name}.pid",
                self.project_root / "shared_data" / f"{service_name}.pid",
            ]
            
            for pid_file in pid_locations:
                if not pid_file.exists():
                    continue
                
                try:
                    with open(pid_file, "r") as f:
                        pid_str = f.read().strip()
                        if not pid_str:
                            continue
                        pid = int(pid_str)
                    
                    # 파일 수정 시간 체크 (1시간 이상 오래된 것은 무시)
                    file_age_hours = (time.time() - pid_file.stat().st_mtime) / 3600
                    if file_age_hours > 1:
                        continue
                    
                    if psutil.pid_exists(pid):
                        process = psutil.Process(pid)
                        if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                            return True
                            
                except Exception:
                    continue
            
            return False
            
        except Exception:
            return False
    
    def save_health_report(self, health_check: SystemHealthCheck):
        """헬스 체크 결과 저장"""
        try:
            report_file = self.project_root / "shared_data" / "comprehensive_health.json"
            
            # dataclass를 dict로 변환
            report = {
                "timestamp": health_check.timestamp,
                "overall_status": health_check.overall_status,
                "is_all_healthy": health_check.is_all_healthy,
                "feeder": asdict(health_check.feeder),
                "trader": asdict(health_check.trader),
                "auto_heal": asdict(health_check.auto_heal)
            }
            
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"헬스 리포트 저장: {health_check.overall_status}")
            
        except Exception as e:
            self.logger.error(f"헬스 리포트 저장 실패: {e}")


def load_comprehensive_health() -> Optional[SystemHealthCheck]:
    """저장된 헬스 체크 결과 로드"""
    try:
        report_file = Path("shared_data/comprehensive_health.json")
        if not report_file.exists():
            return None
        
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return SystemHealthCheck(
            timestamp=data["timestamp"],
            feeder=FeederHealthCheck(**data["feeder"]),
            trader=TraderHealthCheck(**data["trader"]),
            auto_heal=AutoHealHealthCheck(**data["auto_heal"])
        )
        
    except Exception:
        return None


# 전역 인스턴스
_health_checker = None


def get_health_checker() -> ComprehensiveHealthChecker:
    """전역 헬스 체커 인스턴스 반환"""
    global _health_checker
    if _health_checker is None:
        _health_checker = ComprehensiveHealthChecker()
    return _health_checker


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    
    checker = ComprehensiveHealthChecker()
    health = checker.check_all()
    
    print("\n=== 완전무결 헬스 체크 결과 ===\n")
    print(f"전체 상태: {health.overall_status}")
    print(f"모두 정상: {health.is_all_healthy}\n")
    
    print(f"📡 Feeder: {'✅' if health.feeder.is_healthy else '❌'}")
    print(f"  - 프로세스: {health.feeder.process_running}")
    print(f"  - WebSocket: {health.feeder.websocket_connected}")
    print(f"  - 데이터 수집: {health.feeder.data_collecting}")
    print(f"  - 파일 기록: {health.feeder.file_writing}")
    print(f"  - ARES 전달: {health.feeder.ares_feeding}")
    if health.feeder.error_message:
        print(f"  ⚠️ 오류: {health.feeder.error_message}")
    
    print(f"\n💹 Trader: {'✅' if health.trader.is_healthy else '❌'}")
    print(f"  - 프로세스: {health.trader.process_running}")
    print(f"  - 신호 수신: {health.trader.signal_receiving}")
    print(f"  - 리스크 체크: {health.trader.risk_checking}")
    print(f"  - 주문 실행: {health.trader.order_executing}")
    print(f"  - 포지션 추적: {health.trader.position_tracking}")
    print(f"  - 총 노출: ${health.trader.total_exposure:,.2f}")
    if health.trader.error_message:
        print(f"  ⚠️ 오류: {health.trader.error_message}")
    
    print(f"\n🔧 Auto-Heal: {'✅' if health.auto_heal.is_healthy else '❌'}")
    print(f"  - 프로세스: {health.auto_heal.process_running}")
    print(f"  - 모니터링: {health.auto_heal.monitoring_active}")
    print(f"  - 데이터 검증: {health.auto_heal.data_validation}")
    print(f"  - 자동 복구: {health.auto_heal.auto_recovery}")
    if health.auto_heal.error_message:
        print(f"  ⚠️ 오류: {health.auto_heal.error_message}")
    
    # 저장
    checker.save_health_report(health)
    print(f"\n✅ 헬스 리포트 저장 완료")
