#!/usr/bin/env python3
"""
Auditable Signal Manager - Immutable records and idempotency
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import threading
from collections import deque

from shared.guardrails import get_guardrails
from shared.state_bus import get_state_bus


@dataclass
class ImmutableSignalRecord:
    """불변 신호 기록"""
    # 신호 식별
    signal_id: str
    symbol: str
    side: str
    strategy_id: str
    
    # 신뢰도 정보
    base_conf: float
    cost_bps: float
    net_conf: float
    
    # 가격 및 크기
    price: float
    size_usdt: float
    
    # 무결성 정보
    inputs_hash: str
    signal_hash: str
    
    # 시간 정보
    generated_at: float
    expires_at: float
    
    # 메타데이터
    reason: str
    metadata: Dict[str, Any]
    
    # 감사 추적
    created_by: str
    version: int


@dataclass
class OrderIntentRecord:
    """주문 의도 기록"""
    # 주문 식별
    client_order_id: str
    signal_id: str
    
    # 주문 정보
    symbol: str
    side: str
    quantity: float
    price: float
    
    # 상태 추적
    status: str
    created_at: float
    updated_at: float
    
    # 재시도 정보
    retry_count: int
    max_retries: int
    
    # 오류 정보
    last_error: str
    
    # 메타데이터
    metadata: Dict[str, Any]


class AuditableSignalManager:
    """감사 가능한 신호 관리자"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.guardrails = get_guardrails()
        self.config = self.guardrails.get_config()
        self.state_bus = get_state_bus()
        
        # 디렉토리 설정
        self.signals_dir = Path("shared_data/signals_outbox")
        self.orders_dir = Path("shared_data/order_intents")
        self.audit_dir = Path("shared_data/audit_logs")
        
        # 디렉토리 생성
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        self.orders_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        
        # 중복 제거를 위한 롤링 윈도우
        self._signal_window: deque = deque(maxlen=1000)
        self._order_window: deque = deque(maxlen=1000)
        self._dedup_keys: Set[str] = set()
        
        # 락
        self._lock = threading.RLock()
        
        # 통계
        self._stats = {
            "signals_recorded": 0,
            "orders_recorded": 0,
            "duplicates_filtered": 0,
            "expired_records": 0,
            "audit_entries": 0,
        }
    
    def record_signal(
        self,
        symbol: str,
        side: str,
        base_conf: float,
        cost_bps: float,
        net_conf: float,
        strategy_id: str,
        price: float,
        size_usdt: float,
        inputs_hash: str,
        reason: str = "",
        metadata: Dict[str, Any] = None
    ) -> Optional[ImmutableSignalRecord]:
        """신호 기록 (불변)"""
        try:
            current_time = time.time()
            
            # 신호 ID 생성 (멱등성)
            signal_id = self._generate_signal_id(
                symbol, side, base_conf, cost_bps, net_conf, strategy_id, inputs_hash
            )
            
            # 중복 확인
            if self._is_duplicate_signal(signal_id):
                self._stats["duplicates_filtered"] += 1
                self.logger.debug(f"Duplicate signal filtered: {signal_id}")
                return None
            
            # 신호 해시 생성
            signal_hash = self._generate_signal_hash(
                symbol, side, base_conf, cost_bps, net_conf, strategy_id, price, size_usdt
            )
            
            # 불변 신호 기록 생성
            record = ImmutableSignalRecord(
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                strategy_id=strategy_id,
                base_conf=base_conf,
                cost_bps=cost_bps,
                net_conf=net_conf,
                price=price,
                size_usdt=size_usdt,
                inputs_hash=inputs_hash,
                signal_hash=signal_hash,
                generated_at=current_time,
                expires_at=current_time + 300,  # 5분 후 만료
                reason=reason,
                metadata=metadata or {},
                created_by="ARES_FIXED",
                version=1
            )
            
            # 파일에 저장
            if self._save_signal_record(record):
                # 롤링 윈도우에 추가
                with self._lock:
                    self._signal_window.append({
                        'signal_id': signal_id,
                        'generated_at': current_time,
                        'expires_at': record.expires_at
                    })
                    self._dedup_keys.add(signal_id)
                
                self._stats["signals_recorded"] += 1
                self._audit_log("SIGNAL_RECORDED", record)
                
                return record
            
            return None
            
        except Exception as e:
            self.logger.error(f"Signal recording failed: {e}")
            return None
    
    def record_order_intent(
        self,
        signal_record: ImmutableSignalRecord,
        quantity: float,
        order_price: float
    ) -> Optional[OrderIntentRecord]:
        """주문 의도 기록"""
        try:
            current_time = time.time()
            
            # 클라이언트 주문 ID 생성 (멱등성)
            client_order_id = self._generate_client_order_id(signal_record, quantity, order_price)
            
            # 주문 의도 기록 생성
            order_record = OrderIntentRecord(
                client_order_id=client_order_id,
                signal_id=signal_record.signal_id,
                symbol=signal_record.symbol,
                side=signal_record.side,
                quantity=quantity,
                price=order_price,
                status="INTENT",
                created_at=current_time,
                updated_at=current_time,
                retry_count=0,
                max_retries=3,
                last_error="",
                metadata={
                    'signal_hash': signal_record.signal_hash,
                    'base_conf': signal_record.base_conf,
                    'cost_bps': signal_record.cost_bps,
                    'net_conf': signal_record.net_conf,
                }
            )
            
            # 파일에 저장
            if self._save_order_record(order_record):
                # 롤링 윈도우에 추가
                with self._lock:
                    self._order_window.append({
                        'client_order_id': client_order_id,
                        'signal_id': signal_record.signal_id,
                        'created_at': current_time
                    })
                
                self._stats["orders_recorded"] += 1
                self._audit_log("ORDER_INTENT_RECORDED", order_record)
                
                return order_record
            
            return None
            
        except Exception as e:
            self.logger.error(f"Order intent recording failed: {e}")
            return None
    
    def update_order_status(
        self,
        client_order_id: str,
        status: str,
        error: str = "",
        metadata: Dict[str, Any] = None
    ) -> bool:
        """주문 상태 업데이트"""
        try:
            # 주문 기록 로드
            order_record = self._load_order_record(client_order_id)
            if not order_record:
                self.logger.warning(f"Order record not found: {client_order_id}")
                return False
            
            # 상태 업데이트
            order_record.status = status
            order_record.updated_at = time.time()
            order_record.last_error = error
            
            if metadata:
                order_record.metadata.update(metadata)
            
            # 파일에 저장
            if self._save_order_record(order_record):
                self._audit_log("ORDER_STATUS_UPDATED", order_record)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Order status update failed: {e}")
            return False
    
    def _generate_signal_id(
        self,
        symbol: str,
        side: str,
        base_conf: float,
        cost_bps: float,
        net_conf: float,
        strategy_id: str,
        inputs_hash: str
    ) -> str:
        """신호 ID 생성 (멱등성)"""
        try:
            # 멱등성을 위한 해시 데이터
            hash_data = {
                'symbol': symbol,
                'side': side,
                'base_conf': round(base_conf, 4),
                'cost_bps': round(cost_bps, 1),
                'net_conf': round(net_conf, 4),
                'strategy_id': strategy_id,
                'inputs_hash': inputs_hash,
                'timestamp': int(time.time() / 60) * 60  # 1분 단위로 반올림
            }
            
            hash_string = json.dumps(hash_data, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()[:16]
            
        except Exception as e:
            self.logger.error(f"Signal ID generation failed: {e}")
            return f"SIG_{int(time.time())}"
    
    def _generate_signal_hash(
        self,
        symbol: str,
        side: str,
        base_conf: float,
        cost_bps: float,
        net_conf: float,
        strategy_id: str,
        price: float,
        size_usdt: float
    ) -> str:
        """신호 해시 생성"""
        try:
            hash_data = {
                'symbol': symbol,
                'side': side,
                'base_conf': base_conf,
                'cost_bps': cost_bps,
                'net_conf': net_conf,
                'strategy_id': strategy_id,
                'price': price,
                'size_usdt': size_usdt,
            }
            
            hash_string = json.dumps(hash_data, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
            
        except Exception as e:
            self.logger.error(f"Signal hash generation failed: {e}")
            return ""
    
    def _generate_client_order_id(
        self,
        signal_record: ImmutableSignalRecord,
        quantity: float,
        order_price: float
    ) -> str:
        """클라이언트 주문 ID 생성 (멱등성)"""
        try:
            hash_data = {
                'signal_id': signal_record.signal_id,
                'symbol': signal_record.symbol,
                'side': signal_record.side,
                'quantity': round(quantity, 8),
                'price': round(order_price, 8),
                'timestamp': int(time.time() / 60) * 60  # 1분 단위로 반올림
            }
            
            hash_string = json.dumps(hash_data, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()[:16]
            
        except Exception as e:
            self.logger.error(f"Client order ID generation failed: {e}")
            return f"ORD_{int(time.time())}"
    
    def _is_duplicate_signal(self, signal_id: str) -> bool:
        """중복 신호 확인"""
        try:
            with self._lock:
                return signal_id in self._dedup_keys
                
        except Exception as e:
            self.logger.error(f"Duplicate signal check failed: {e}")
            return False
    
    def _save_signal_record(self, record: ImmutableSignalRecord) -> bool:
        """신호 기록 저장"""
        try:
            signal_file = self.signals_dir / f"{record.signal_id}.json"
            
            record_dict = asdict(record)
            with open(signal_file, 'w', encoding='utf-8') as f:
                json.dump(record_dict, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Signal record save failed: {e}")
            return False
    
    def _save_order_record(self, record: OrderIntentRecord) -> bool:
        """주문 기록 저장"""
        try:
            order_file = self.orders_dir / f"{record.client_order_id}.json"
            
            record_dict = asdict(record)
            with open(order_file, 'w', encoding='utf-8') as f:
                json.dump(record_dict, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Order record save failed: {e}")
            return False
    
    def _load_order_record(self, client_order_id: str) -> Optional[OrderIntentRecord]:
        """주문 기록 로드"""
        try:
            order_file = self.orders_dir / f"{client_order_id}.json"
            
            if not order_file.exists():
                return None
            
            with open(order_file, 'r', encoding='utf-8') as f:
                record_dict = json.load(f)
            
            return OrderIntentRecord(**record_dict)
            
        except Exception as e:
            self.logger.error(f"Order record load failed: {e}")
            return None
    
    def _audit_log(self, action: str, record: Any):
        """감사 로그 기록"""
        try:
            current_time = time.time()
            
            audit_entry = {
                'timestamp': current_time,
                'action': action,
                'record_type': type(record).__name__,
                'record_id': getattr(record, 'signal_id', getattr(record, 'client_order_id', 'unknown')),
                'details': asdict(record) if hasattr(record, '__dict__') else str(record)
            }
            
            # 감사 로그 파일에 저장
            audit_file = self.audit_dir / f"audit_{int(current_time // 86400)}.json"  # 일별 파일
            
            # 기존 로그 로드
            audit_logs = []
            if audit_file.exists():
                with open(audit_file, 'r', encoding='utf-8') as f:
                    audit_logs = json.load(f)
            
            # 새 로그 추가
            audit_logs.append(audit_entry)
            
            # 파일 저장
            with open(audit_file, 'w', encoding='utf-8') as f:
                json.dump(audit_logs, f, indent=2, ensure_ascii=False)
            
            self._stats["audit_entries"] += 1
            
        except Exception as e:
            self.logger.error(f"Audit log failed: {e}")
    
    def cleanup_expired_records(self):
        """만료된 기록 정리"""
        try:
            current_time = time.time()
            
            # 만료된 신호 기록 정리
            with self._lock:
                expired_signals = []
                for item in self._signal_window:
                    if item['expires_at'] > 0 and item['expires_at'] < current_time:
                        expired_signals.append(item)
                
                for item in expired_signals:
                    self._signal_window.remove(item)
                    self._dedup_keys.discard(item['signal_id'])
                    self._stats["expired_records"] += 1
            
            if expired_signals:
                self.logger.info(f"Cleaned up {len(expired_signals)} expired signal records")
            
        except Exception as e:
            self.logger.error(f"Expired records cleanup failed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self._stats.copy()
    
    def get_recent_signals(self, limit: int = 100) -> List[ImmutableSignalRecord]:
        """최근 신호 기록 반환"""
        try:
            signals = []
            
            # 신호 파일 목록 가져오기
            signal_files = sorted(self.signals_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
            
            for signal_file in signal_files[:limit]:
                try:
                    with open(signal_file, 'r', encoding='utf-8') as f:
                        record_dict = json.load(f)
                    
                    signal = ImmutableSignalRecord(**record_dict)
                    signals.append(signal)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load signal file {signal_file}: {e}")
                    continue
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Recent signals retrieval failed: {e}")
            return []
    
    def get_recent_orders(self, limit: int = 100) -> List[OrderIntentRecord]:
        """최근 주문 기록 반환"""
        try:
            orders = []
            
            # 주문 파일 목록 가져오기
            order_files = sorted(self.orders_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
            
            for order_file in order_files[:limit]:
                try:
                    with open(order_file, 'r', encoding='utf-8') as f:
                        record_dict = json.load(f)
                    
                    order = OrderIntentRecord(**record_dict)
                    orders.append(order)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load order file {order_file}: {e}")
                    continue
            
            return orders
            
        except Exception as e:
            self.logger.error(f"Recent orders retrieval failed: {e}")
            return []


# 전역 인스턴스
_global_auditable_manager: Optional[AuditableSignalManager] = None


def get_auditable_manager() -> AuditableSignalManager:
    """전역 감사 가능한 관리자 반환"""
    global _global_auditable_manager
    if _global_auditable_manager is None:
        _global_auditable_manager = AuditableSignalManager()
    return _global_auditable_manager


def record_signal(
    symbol: str,
    side: str,
    base_conf: float,
    cost_bps: float,
    net_conf: float,
    strategy_id: str,
    price: float,
    size_usdt: float,
    inputs_hash: str,
    reason: str = "",
    metadata: Dict[str, Any] = None
) -> Optional[ImmutableSignalRecord]:
    """신호 기록"""
    return get_auditable_manager().record_signal(
        symbol, side, base_conf, cost_bps, net_conf, strategy_id,
        price, size_usdt, inputs_hash, reason, metadata
    )


def record_order_intent(
    signal_record: ImmutableSignalRecord,
    quantity: float,
    order_price: float
) -> Optional[OrderIntentRecord]:
    """주문 의도 기록"""
    return get_auditable_manager().record_order_intent(signal_record, quantity, order_price)


def update_order_status(
    client_order_id: str,
    status: str,
    error: str = "",
    metadata: Dict[str, Any] = None
) -> bool:
    """주문 상태 업데이트"""
    return get_auditable_manager().update_order_status(client_order_id, status, error, metadata)
