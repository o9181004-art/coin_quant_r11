#!/usr/bin/env python3
"""
이벤트 기반 UI 새로고침 시스템
파일 와처와 연동하여 최소한의 UI 업데이트 수행
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Set

import streamlit as st

from .file_watcher import FileChangeEvent, TelemetryData, get_global_watcher


@dataclass
class RefreshState:
    """새로고침 상태"""
    last_refresh: float = 0.0
    pending_refresh: bool = False
    refresh_count: int = 0
    last_telemetry_update: float = 0.0


class EventDrivenRefresh:
    """이벤트 기반 새로고침 관리자"""
    
    def __init__(self, 
                 min_refresh_interval: float = 0.3,  # 최소 새로고침 간격 (300ms)
                 max_refresh_interval: float = 5.0,  # 최대 새로고침 간격 (5초)
                 telemetry_update_interval: float = 1.0):  # 텔레메트리 업데이트 간격
        
        self.min_refresh_interval = min_refresh_interval
        self.max_refresh_interval = max_refresh_interval
        self.telemetry_update_interval = telemetry_update_interval
        
        self.logger = logging.getLogger(__name__)
        self.state = RefreshState()
        
        # 파일 와처
        self.watcher = get_global_watcher()
        
        # 콜백 등록
        self._register_callbacks()
        
        # 세션 상태 초기화
        self._init_session_state()
    
    def _init_session_state(self):
        """세션 상태 초기화"""
        if 'event_driven_refresh' not in st.session_state:
            st.session_state.event_driven_refresh = {
                'enabled': True,
                'last_file_change': 0.0,
                'pending_changes': set(),
                'telemetry_data': None,
                'stale_threshold': 15.0,  # 15초 stale threshold
                'heartbeat_threshold': 20.0,  # 20초 heartbeat threshold
            }
    
    def _register_callbacks(self):
        """파일 와처 콜백 등록"""
        # databus_snapshot.json 변경 시
        self.watcher.add_callback('modified', self._on_snapshot_change)
        self.watcher.add_callback('moved', self._on_snapshot_change)
        
        # health.json 변경 시
        self.watcher.add_callback('modified', self._on_health_change)
        self.watcher.add_callback('moved', self._on_health_change)
        
        # 일반 파일 변경 시
        self.watcher.add_callback('*', self._on_any_change)
    
    def _on_snapshot_change(self, event: FileChangeEvent):
        """databus_snapshot.json 변경 처리"""
        if 'databus_snapshot.json' in event.path:
            self.logger.debug(f"Snapshot change detected: {event.path}")
            self._schedule_refresh('snapshot', event.timestamp)
    
    def _on_health_change(self, event: FileChangeEvent):
        """health.json 변경 처리"""
        if 'health.json' in event.path:
            self.logger.debug(f"Health change detected: {event.path}")
            self._schedule_refresh('health', event.timestamp)
    
    def _on_any_change(self, event: FileChangeEvent):
        """일반 파일 변경 처리"""
        # shared_data 내의 다른 파일들
        if 'shared_data' in event.normalized_path:
            self.logger.debug(f"Shared data change: {event.path}")
            self._schedule_refresh('data', event.timestamp)
    
    def _schedule_refresh(self, change_type: str, timestamp: float):
        """새로고침 스케줄링"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        if not st.session_state.event_driven_refresh['enabled']:
            return
        
        # 중복 변경 방지
        current_time = time.time()
        if current_time - self.state.last_refresh < self.min_refresh_interval:
            self.state.pending_refresh = True
            return
        
        # 새로고침 실행
        self._execute_refresh(change_type, timestamp)
    
    def _execute_refresh(self, change_type: str, timestamp: float):
        """새로고침 실행"""
        current_time = time.time()
        
        # 최소 간격 확인
        if current_time - self.state.last_refresh < self.min_refresh_interval:
            return
        
        # 최대 간격 확인 (폴백)
        if current_time - self.state.last_refresh > self.max_refresh_interval:
            self.logger.warning("Max refresh interval exceeded, forcing refresh")
        
        # 새로고침 실행
        self.state.last_refresh = current_time
        self.state.refresh_count += 1
        self.state.pending_refresh = False
        
        # 세션 상태 업데이트
        st.session_state.event_driven_refresh['last_file_change'] = timestamp
        
        # 선택적 캐시 무효화
        self._invalidate_cache(change_type)
        
        # UI 새로고침
        st.rerun()
        
        self.logger.debug(f"Refresh executed: {change_type} (count: {self.state.refresh_count})")
    
    def _invalidate_cache(self, change_type: str):
        """선택적 캐시 무효화"""
        if change_type == 'snapshot':
            # 데이터 관련 캐시만 무효화
            try:
                # 특정 캐시 키만 무효화 (전체 무효화 대신)
                if hasattr(st.cache_data, 'clear'):
                    # 스트림릿 캐시 무효화는 전체만 가능하므로 조건부 실행
                    pass
            except Exception as e:
                self.logger.error(f"Cache invalidation error: {e}")
        
        elif change_type == 'health':
            # 헬스 관련 캐시만 무효화
            pass
        
        elif change_type == 'data':
            # 일반 데이터 캐시 무효화
            pass
    
    def check_and_refresh(self):
        """새로고침 필요 여부 확인 및 실행"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        if not st.session_state.event_driven_refresh['enabled']:
            return
        
        current_time = time.time()
        
        # 대기 중인 새로고침 확인
        if self.state.pending_refresh:
            if current_time - self.state.last_refresh >= self.min_refresh_interval:
                self._execute_refresh('pending', current_time)
        
        # 텔레메트리 업데이트
        if current_time - self.state.last_telemetry_update >= self.telemetry_update_interval:
            self._update_telemetry()
            self.state.last_telemetry_update = current_time
    
    def _update_telemetry(self):
        """텔레메트리 데이터 업데이트"""
        try:
            telemetry = self.watcher.get_telemetry()
            st.session_state.event_driven_refresh['telemetry_data'] = telemetry
            
            # Stale/Heartbeat 경고 확인
            self._check_stale_warnings(telemetry)
            
        except Exception as e:
            self.logger.error(f"Telemetry update error: {e}")
    
    def _check_stale_warnings(self, telemetry: TelemetryData):
        """Stale/Heartbeat 경고 확인"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        stale_threshold = st.session_state.event_driven_refresh['stale_threshold']
        heartbeat_threshold = st.session_state.event_driven_refresh['heartbeat_threshold']
        
        # Stale 데이터 경고
        if telemetry.snapshot_age_sec > stale_threshold:
            self.logger.warning(f"Stale data detected: {telemetry.snapshot_age_sec:.1f}s > {stale_threshold}s")
        
        # Heartbeat 지연 경고
        if telemetry.feeder_lag_sec > heartbeat_threshold:
            self.logger.warning(f"Feeder lag detected: {telemetry.feeder_lag_sec:.1f}s > {heartbeat_threshold}s")
    
    def get_telemetry_display(self) -> str:
        """텔레메트리 표시 문자열 반환"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        telemetry = st.session_state.event_driven_refresh.get('telemetry_data')
        if not telemetry:
            return "Telemetry: Loading..."
        
        # 상태 표시
        status_icon = "🟢"
        if telemetry.snapshot_age_sec > 15:
            status_icon = "🟡"
        if telemetry.snapshot_age_sec > 30:
            status_icon = "🔴"
        
        return (f"{status_icon} Last snapshot: {telemetry.last_snapshot_time} · "
                f"Age: {telemetry.snapshot_age_sec:.1f}s · "
                f"Active symbols: {telemetry.symbols_active}/{telemetry.symbols_expected} · "
                f"Feeder lag: {telemetry.feeder_lag_sec:.1f}s")
    
    def enable(self):
        """이벤트 기반 새로고침 활성화"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        st.session_state.event_driven_refresh['enabled'] = True
        self.logger.info("Event-driven refresh enabled")
    
    def disable(self):
        """이벤트 기반 새로고침 비활성화"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        st.session_state.event_driven_refresh['enabled'] = False
        self.logger.info("Event-driven refresh disabled")
    
    def is_enabled(self) -> bool:
        """이벤트 기반 새로고침 활성화 여부"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        return st.session_state.event_driven_refresh['enabled']
    
    def get_stats(self) -> Dict:
        """새로고침 통계 반환"""
        # 세션 상태 초기화 확인
        self._init_session_state()
        return {
            'refresh_count': self.state.refresh_count,
            'last_refresh': self.state.last_refresh,
            'pending_refresh': self.state.pending_refresh,
            'enabled': self.is_enabled(),
            'telemetry': st.session_state.event_driven_refresh.get('telemetry_data')
        }


# 전역 인스턴스
_global_refresh: Optional[EventDrivenRefresh] = None


def get_global_refresh() -> EventDrivenRefresh:
    """전역 새로고침 관리자 반환"""
    global _global_refresh
    if _global_refresh is None:
        _global_refresh = EventDrivenRefresh()
    return _global_refresh


def render_telemetry_footer():
    """텔레메트리 푸터 렌더링"""
    refresh_manager = get_global_refresh()
    
    # 새로고침 확인
    refresh_manager.check_and_refresh()
    
    # 텔레메트리 표시
    telemetry_text = refresh_manager.get_telemetry_display()
    
    # 푸터 스타일
    st.markdown(
        f"""
        <div style="
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: #0e1117;
            border-top: 1px solid #262730;
            padding: 8px 16px;
            font-size: 12px;
            color: #808495;
            z-index: 1000;
        ">
            {telemetry_text}
        </div>
        """,
        unsafe_allow_html=True
    )


# render_refresh_controls 함수 제거됨 (사용되지 않는 중복 버튼)
    
