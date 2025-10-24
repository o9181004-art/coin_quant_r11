#!/usr/bin/env python3
"""
Health SSOT (Single Source of Truth)
완전무결 헬스체크 시스템의 중앙 집계 및 원자적 기록

확정된 가정:
- Timeframe: 1m only (5m/15m은 ARES 내부 downsampling)
- Ledger: trades.jsonl = SSOT, 주기적 exchange API 대사
- Position Snapshot: qty, avg_price, realized_pnl, unrealized_pnl 포함
- Daily PnL: 00:00 KST 초기화 (rolling 24h 아님)
- Gap Backfill: Binance REST klines 필수 (no missing bars)
- Auto-Heal: 필수 서비스 (continuous playbook execution)
- UI: 5s polling (pull-based)
- Testnet: WS=mainnet, orders=testnet API
"""

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class CheckResult:
    """개별 체크 결과"""
    ok: bool
    reason: str = ""
    timestamp: float = 0.0
    
    # 추가 컨텍스트
    value: Optional[float] = None  # 측정값 (age, count, pct 등)
    threshold: Optional[float] = None  # 임계값
    artifacts: List[str] = None  # 관련 파일/아티팩트
    
    def __post_init__(self):
        if self.artifacts is None:
            self.artifacts = []
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class ComponentHealth:
    """컴포넌트 건강성"""
    status: str  # "OK" | "WARN" | "FAIL"
    checks: Dict[str, CheckResult]
    metrics: Dict[str, float]
    artifacts: Dict[str, str]
    remediation: Dict[str, str]  # recommended, priority, eta_sec
    
    @property
    def is_healthy(self) -> bool:
        return self.status == "OK"


@dataclass
class PipelineIntegrity:
    """파이프라인 무결성"""
    end_to_end_ok: bool
    feeder_to_ares_ok: bool
    ares_to_trader_ok: bool
    trader_to_fills_ok: bool
    fills_to_pnl_ok: bool
    broken_link: Optional[str] = None


@dataclass
class HealthSSOT:
    """Health Single Source of Truth"""
    version: str = "1.0"
    timestamp: float = 0.0
    
    overall_status: str = "UNKNOWN"  # OK, WARN, FAIL, DEGRADED, FAILSAFE
    safe_to_trade: bool = False
    mode: str = "NORMAL"  # NORMAL, DEGRADED, POSITION_GUARD, FAILSAFE
    
    # 컴포넌트별 상태
    feeder: Optional[ComponentHealth] = None
    trader: Optional[ComponentHealth] = None
    auto_heal: Optional[ComponentHealth] = None
    
    # 파이프라인 무결성
    pipeline: Optional[PipelineIntegrity] = None
    
    # 복구 상태
    last_playbook_run: Dict[str, any] = None  # {playbook_id, timestamp, result}
    circuit_breaker: Dict[str, any] = None  # {active, until, reason}
    
    # Writer 메트릭
    writer_metrics: Dict[str, any] = None  # {last_write_ts, bytes_written, stall_sec}
    
    # 진행 중인 플레이북
    playbook_in_progress: Dict[str, any] = None  # {id, step, total_steps, started_at}
    
    # 메타
    next_check_at: float = 0.0
    ttl_sec: int = 60
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if self.next_check_at == 0.0:
            self.next_check_at = self.timestamp + self.ttl_sec
        if self.last_playbook_run is None:
            self.last_playbook_run = {}
        if self.circuit_breaker is None:
            self.circuit_breaker = {"active": False, "until": 0, "reason": ""}
        if self.writer_metrics is None:
            self.writer_metrics = {}
        if self.playbook_in_progress is None:
            self.playbook_in_progress = {}


class HealthSSOTManager:
    """SSOT 관리자 - 원자적 읽기/쓰기"""
    
    def __init__(self, ssot_path: str = "shared_data/health_ssot.json"):
        from shared.path_resolver import get_path_resolver
        self.path_resolver = get_path_resolver()
        self.ssot_path = self.path_resolver.resolve(ssot_path)
        self.ssot_path.parent.mkdir(parents=True, exist_ok=True)
    
    def read(self) -> Optional[HealthSSOT]:
        """SSOT 읽기 (체크섬 검증)"""
        try:
            if not self.ssot_path.exists():
                return None
            
            with open(self.ssot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 체크섬 검증
            stored_checksum = data.pop("_checksum", None)
            if stored_checksum:
                calculated = self._calculate_checksum(data)
                if calculated != stored_checksum:
                    # 체크섬 불일치 - 이전 백업 사용
                    return self._read_backup()
            
            # 딕셔너리를 HealthSSOT로 변환
            return self._dict_to_ssot(data)
            
        except Exception as e:
            print(f"[SSOT] 읽기 실패: {e}")
            return self._read_backup()
    
    def write(self, ssot: HealthSSOT):
        """SSOT 쓰기 (원자적, 체크섬 포함)"""
        try:
            # dataclass를 dict로 변환
            data = self._ssot_to_dict(ssot)
            
            # 체크섬 계산
            data["_checksum"] = self._calculate_checksum(data)
            data["_write_start_ts"] = time.time()
            
            # 임시 파일에 쓰기
            tmp_path = self.ssot_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            # 이전 버전 백업
            if self.ssot_path.exists():
                backup_path = self.ssot_path.with_suffix(".prev")
                shutil.copy(self.ssot_path, backup_path)
            
            # 원자적 교체
            tmp_path.replace(self.ssot_path)
            
        except Exception as e:
            print(f"[SSOT] 쓰기 실패: {e}")
            raise
    
    def _calculate_checksum(self, data: dict) -> str:
        """데이터 체크섬 계산"""
        # _write_start_ts, _checksum 제외하고 계산
        clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
        json_str = json.dumps(clean_data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(json_str.encode()).hexdigest()
    
    def _read_backup(self) -> Optional[HealthSSOT]:
        """백업에서 읽기"""
        try:
            backup_path = self.ssot_path.with_suffix(".prev")
            if backup_path.exists():
                with open(backup_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return self._dict_to_ssot(data)
        except:
            pass
        return None
    
    def _ssot_to_dict(self, ssot: HealthSSOT) -> dict:
        """HealthSSOT를 dict로 변환"""
        data = {
            "version": ssot.version,
            "timestamp": ssot.timestamp,
            "overall_status": ssot.overall_status,
            "safe_to_trade": ssot.safe_to_trade,
            "mode": ssot.mode,
            "last_playbook_run": ssot.last_playbook_run,
            "circuit_breaker": ssot.circuit_breaker,
            "writer_metrics": ssot.writer_metrics,
            "playbook_in_progress": ssot.playbook_in_progress,
            "next_check_at": ssot.next_check_at,
            "ttl_sec": ssot.ttl_sec
        }
        
        # ComponentHealth 변환
        if ssot.feeder:
            data["feeder"] = {
                "status": ssot.feeder.status,
                "checks": {k: asdict(v) for k, v in ssot.feeder.checks.items()},
                "metrics": ssot.feeder.metrics,
                "artifacts": ssot.feeder.artifacts,
                "remediation": ssot.feeder.remediation
            }
        
        if ssot.trader:
            data["trader"] = {
                "status": ssot.trader.status,
                "checks": {k: asdict(v) for k, v in ssot.trader.checks.items()},
                "metrics": ssot.trader.metrics,
                "artifacts": ssot.trader.artifacts,
                "remediation": ssot.trader.remediation
            }
        
        if ssot.auto_heal:
            data["auto_heal"] = {
                "status": ssot.auto_heal.status,
                "checks": {k: asdict(v) for k, v in ssot.auto_heal.checks.items()},
                "metrics": ssot.auto_heal.metrics,
                "artifacts": {},
                "remediation": {"recommended": "none"}
            }
        
        # PipelineIntegrity 변환
        if ssot.pipeline:
            data["pipeline"] = asdict(ssot.pipeline)
        
        return data
    
    def _dict_to_ssot(self, data: dict) -> HealthSSOT:
        """dict를 HealthSSOT로 변환"""
        # CheckResult 복원 helper
        def restore_check(check_data: dict) -> CheckResult:
            return CheckResult(
                ok=check_data.get("ok", False),
                reason=check_data.get("reason", ""),
                timestamp=check_data.get("timestamp", 0.0),
                value=check_data.get("value"),
                threshold=check_data.get("threshold"),
                artifacts=check_data.get("artifacts", [])
            )
        
        # ComponentHealth 복원
        def restore_component(comp_data: dict) -> ComponentHealth:
            return ComponentHealth(
                status=comp_data.get("status", "UNKNOWN"),
                checks={k: restore_check(v) for k, v in comp_data.get("checks", {}).items()},
                metrics=comp_data.get("metrics", {}),
                artifacts=comp_data.get("artifacts", {}),
                remediation=comp_data.get("remediation", {})
            )
        
        # PipelineIntegrity 복원
        pipeline_data = data.get("pipeline", {})
        pipeline = PipelineIntegrity(
            end_to_end_ok=pipeline_data.get("end_to_end_ok", False),
            feeder_to_ares_ok=pipeline_data.get("feeder_to_ares_ok", False),
            ares_to_trader_ok=pipeline_data.get("ares_to_trader_ok", False),
            trader_to_fills_ok=pipeline_data.get("trader_to_fills_ok", False),
            fills_to_pnl_ok=pipeline_data.get("fills_to_pnl_ok", False),
            broken_link=pipeline_data.get("broken_link")
        ) if pipeline_data else None
        
        return HealthSSOT(
            version=data.get("version", "1.0"),
            timestamp=data.get("timestamp", time.time()),
            overall_status=data.get("overall_status", "UNKNOWN"),
            safe_to_trade=data.get("safe_to_trade", False),
            mode=data.get("mode", "NORMAL"),
            feeder=restore_component(data["feeder"]) if "feeder" in data else None,
            trader=restore_component(data["trader"]) if "trader" in data else None,
            auto_heal=restore_component(data["auto_heal"]) if "auto_heal" in data else None,
            pipeline=pipeline,
            last_playbook_run=data.get("last_playbook_run", {}),
            circuit_breaker=data.get("circuit_breaker", {"active": False, "until": 0, "reason": ""}),
            writer_metrics=data.get("writer_metrics", {}),
            playbook_in_progress=data.get("playbook_in_progress", {}),
            next_check_at=data.get("next_check_at", time.time() + 60),
            ttl_sec=data.get("ttl_sec", 60)
        )


# 전역 SSOT 매니저
_ssot_manager = None


def get_ssot_manager() -> HealthSSOTManager:
    """전역 SSOT 매니저 반환"""
    global _ssot_manager
    if _ssot_manager is None:
        _ssot_manager = HealthSSOTManager()
    return _ssot_manager


def load_health_ssot() -> Optional[HealthSSOT]:
    """SSOT 로드 (편의 함수)"""
    return get_ssot_manager().read()


def save_health_ssot(ssot: HealthSSOT):
    """SSOT 저장 (편의 함수)"""
    get_ssot_manager().write(ssot)
