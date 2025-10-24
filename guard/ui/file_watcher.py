#!/usr/bin/env python3
"""
실시간 파일 와처 - UI 반응형 업데이트
디렉토리 범위 모니터링, Windows 경로 정규화, 원자적 이동 이벤트 처리
SSOT Path Resolver 통합 (절대 경로 사용)
"""

import json
import logging
import os
import queue
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from typing import Callable, Dict, List, Optional, Set

# SSOT Path Resolver import
try:
    from shared.ssot_path_resolver import (get_databus_snapshot_path,
                                           get_health_dir, get_health_path,
                                           get_shared_data_dir,
                                           log_resolved_paths)
    SSOT_AVAILABLE = True
except ImportError:
    SSOT_AVAILABLE = False

try:
    from watchdog.events import (FileCreatedEvent, FileModifiedEvent,
                                 FileMovedEvent, FileSystemEventHandler)
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object
    FileMovedEvent = object
    FileModifiedEvent = object
    FileCreatedEvent = object


@dataclass
class FileChangeEvent:
    """파일 변경 이벤트"""
    path: str
    event_type: str  # 'modified', 'moved', 'created'
    timestamp: float
    normalized_path: str


@dataclass
class TelemetryData:
    """텔레메트리 데이터"""
    last_snapshot_time: str
    snapshot_age_sec: float
    symbols_active: int
    symbols_expected: int
    feeder_lag_sec: float
    last_update: float


class PathNormalizer:
    """Windows 경로 정규화 유틸리티"""
    
    @staticmethod
    def normalize_path(path: str) -> str:
        """경로 정규화: \\? prefix 제거, case-folding, resolve"""
        try:
            # \\? prefix 제거
            if path.startswith('\\\\?\\'):
                path = path[4:]
            
            # Path 객체로 변환하여 resolve
            path_obj = Path(path)
            resolved = path_obj.resolve()
            
            # case-folding 적용
            normalized = str(resolved).lower()
            
            return normalized
        except Exception:
            # 정규화 실패 시 원본 경로 반환
            return str(path).lower()
    
    @staticmethod
    def is_shared_data_path(path: str) -> bool:
        """shared_data 경로인지 확인"""
        normalized = PathNormalizer.normalize_path(path)
        return 'shared_data' in normalized
    
    @staticmethod
    def is_logs_path(path: str) -> bool:
        """logs 경로인지 확인"""
        normalized = PathNormalizer.normalize_path(path)
        return 'logs' in normalized


class FileChangeHandler(FileSystemEventHandler):
    """파일 변경 이벤트 핸들러"""
    
    def __init__(self, event_queue: queue.Queue, debounce_ms: int = 300):
        self.event_queue = event_queue
        self.debounce_ms = debounce_ms  # 300ms 디바운싱
        self.last_events: Dict[str, float] = {}
        self.logger = logging.getLogger(__name__)
        
        # 허용할 파일 패턴 (dir-allowlist + file-denylist)
        self.allowed_patterns = {
            'databus_snapshot.json',
            'health.json',  # 통합 health 파일
            'feeder.json',  # health/ 서브 디렉토리
            'trader.json',
            'uds.json',
            'ares.json',
            'autoheal.json',
            'universe_cache.json',
            'coin_watchlist.json',
            'feeder.log'
        }
        
        # 무시할 파일 패턴
        self.ignored_patterns = {
            '.tmp', '.bak', '.old', '.log.1', '.log.2',  # 임시/백업 파일
            'history_', 'archive_',  # 대용량 히스토리 파일
        }
    
    def _should_process_event(self, path: str) -> bool:
        """이벤트 처리 여부 결정"""
        normalized_path = PathNormalizer.normalize_path(path)
        
        # shared_data 또는 logs 경로인지 확인
        if not (PathNormalizer.is_shared_data_path(path) or PathNormalizer.is_logs_path(path)):
            return False
        
        # 파일명 추출
        filename = Path(path).name.lower()
        
        # 허용된 패턴 확인
        if filename in self.allowed_patterns:
            return True
        
        # 무시할 패턴 확인
        for pattern in self.ignored_patterns:
            if pattern in filename:
                return False
        
        # 기본적으로 shared_data/**는 허용
        if PathNormalizer.is_shared_data_path(path):
            return True
            
        return False
    
    def _debounce_event(self, path: str) -> bool:
        """이벤트 디바운스 처리"""
        current_time = time.time() * 1000  # ms
        last_time = self.last_events.get(path, 0)
        
        if current_time - last_time < self.debounce_ms:
            return False  # 디바운스됨
        
        self.last_events[path] = current_time
        return True
    
    def _queue_event(self, path: str, event_type: str):
        """이벤트를 큐에 추가"""
        if not self._should_process_event(path):
            self.logger.debug(f"Ignoring changed path: {path}")
            return
        
        if not self._debounce_event(path):
            return  # 디바운스됨
        
        event = FileChangeEvent(
            path=path,
            event_type=event_type,
            timestamp=time.time(),
            normalized_path=PathNormalizer.normalize_path(path)
        )
        
        try:
            self.event_queue.put_nowait(event)
            self.logger.debug(f"Queued event: {event_type} {path}")
        except queue.Full:
            self.logger.warning(f"Event queue full, dropping event: {path}")
    
    def on_modified(self, event):
        """파일 수정 이벤트"""
        if not event.is_directory:
            self._queue_event(event.src_path, 'modified')
    
    def on_moved(self, event):
        """파일 이동/이름변경 이벤트 (원자적 이동 처리)"""
        if not event.is_directory:
            # *.tmp → *.json 원자적 이동 감지
            if event.dest_path.endswith('.json') and event.src_path.endswith('.tmp'):
                self._queue_event(event.dest_path, 'moved')
            else:
                self._queue_event(event.dest_path, 'moved')
    
    def on_created(self, event):
        """파일 생성 이벤트"""
        if not event.is_directory:
            self._queue_event(event.src_path, 'created')


class RealTimeFileWatcher:
    """
    실시간 파일 와처 (SSOT Path Resolver 통합)
    절대 경로 사용 및 health/*.json 파일들 감시
    """
    
    def __init__(self, 
                 shared_data_dir: Optional[str] = None,
                 logs_dir: Optional[str] = None,
                 debounce_ms: int = 300,
                 max_queue_size: int = 1000):
        
        # SSOT Path Resolver 사용 (절대 경로)
        if SSOT_AVAILABLE and shared_data_dir is None:
            self.shared_data_dir = get_shared_data_dir()
            self.health_dir = get_health_dir()
            self.health_file = get_health_path()
            self.databus_file = get_databus_snapshot_path()
            self.logger = logging.getLogger(__name__)
            self.logger.info("Using SSOT Path Resolver for absolute paths")
            log_resolved_paths()
        else:
            # Fallback to relative paths
            self.shared_data_dir = Path(shared_data_dir or "shared_data")
            self.health_dir = self.shared_data_dir / "health"
            self.health_file = self.shared_data_dir / "health.json"
            self.databus_file = self.shared_data_dir / "databus_snapshot.json"
            self.logger = logging.getLogger(__name__)
            self.logger.warning("SSOT Path Resolver not available, using relative paths")
        
        self.logs_dir = Path(logs_dir) if logs_dir else Path("logs")
        self.debounce_ms = debounce_ms
        self.max_queue_size = max_queue_size
        
        self.observer: Optional[Observer] = None
        self.event_queue = queue.Queue(maxsize=max_queue_size)
        self.handler: Optional[FileChangeHandler] = None
        
        self.running = False
        self.stop_event = Event()
        self.watcher_thread: Optional[Thread] = None
        
        # 콜백 함수들
        self.callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        # 텔레메트리 데이터
        self.telemetry = TelemetryData(
            last_snapshot_time="",
            snapshot_age_sec=0.0,
            symbols_active=0,
            symbols_expected=0,
            feeder_lag_sec=0.0,
            last_update=0.0
        )
        
        # 첫 계산 시드를 위한 상태
        self.first_tick_seeded: Set[str] = set()
        self.last_snapshot_data: Optional[Dict] = None
    
    def add_callback(self, event_type: str, callback: Callable[[FileChangeEvent], None]):
        """이벤트 콜백 추가"""
        self.callbacks[event_type].append(callback)
        self.logger.info(f"Added callback for {event_type}: {callback.__name__}")
    
    def remove_callback(self, event_type: str, callback: Callable):
        """이벤트 콜백 제거"""
        if callback in self.callbacks[event_type]:
            self.callbacks[event_type].remove(callback)
            self.logger.info(f"Removed callback for {event_type}: {callback.__name__}")
    
    def _ensure_directories(self):
        """디렉토리 존재 확인 및 생성"""
        self.shared_data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def _start_observer(self):
        """Observer 시작 (SSOT 절대 경로 사용)"""
        if not WATCHDOG_AVAILABLE:
            self.logger.error("Watchdog library not available")
            return False
        
        try:
            self.observer = Observer()
            self.handler = FileChangeHandler(self.event_queue, self.debounce_ms)
            
            # 디렉토리 모니터링 시작 (절대 경로)
            self.observer.schedule(self.handler, str(self.shared_data_dir), recursive=True)
            self.observer.schedule(self.handler, str(self.logs_dir), recursive=True)
            
            # health 서브 디렉토리 명시적으로 감시
            if self.health_dir.exists():
                self.observer.schedule(self.handler, str(self.health_dir), recursive=False)
                self.logger.info(f"Watching health dir: {self.health_dir}")
            
            self.observer.start()
            self.logger.info(f"Started watching (absolute paths):")
            self.logger.info(f"  - {self.shared_data_dir}")
            self.logger.info(f"  - {self.health_dir}")
            self.logger.info(f"  - {self.logs_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start observer: {e}")
            return False
    
    def _process_events(self):
        """이벤트 처리 루프"""
        while not self.stop_event.is_set():
            try:
                # 이벤트 대기 (타임아웃 1초)
                event = self.event_queue.get(timeout=1.0)
                
                # 이벤트 타입별 콜백 실행
                for callback in self.callbacks.get(event.event_type, []):
                    try:
                        callback(event)
                    except Exception as e:
                        self.logger.error(f"Callback error for {event.event_type}: {e}")
                
                # 모든 이벤트에 대한 일반 콜백
                for callback in self.callbacks.get('*', []):
                    try:
                        callback(event)
                    except Exception as e:
                        self.logger.error(f"General callback error: {e}")
                
                self.event_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Event processing error: {e}")
    
    def _update_telemetry(self):
        """텔레메트리 데이터 업데이트"""
        try:
            # health.json 읽기
            health_file = self.shared_data_dir / "health.json"
            if health_file.exists():
                with open(health_file, 'r', encoding='utf-8') as f:
                    health_data = json.load(f)
                
                current_time = time.time()
                heartbeat_ts = health_data.get('heartbeat', {}).get('ts', 0)
                
                self.telemetry.feeder_lag_sec = current_time - heartbeat_ts
                self.telemetry.symbols_active = health_data.get('symbols', {}).get('active', 0)
                self.telemetry.symbols_expected = health_data.get('symbols', {}).get('expected', 0)
            
            # databus_snapshot.json 읽기
            snapshot_file = self.shared_data_dir / "databus_snapshot.json"
            if snapshot_file.exists():
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    snapshot_data = json.load(f)
                
                current_time = time.time()
                snapshot_ts = snapshot_data.get('timestamp', 0)
                
                self.telemetry.snapshot_age_sec = current_time - snapshot_ts
                self.telemetry.last_snapshot_time = time.strftime('%H:%M:%S', time.localtime(snapshot_ts))
                self.telemetry.last_update = current_time
                
                # 첫 계산 시드를 위한 데이터 저장
                self.last_snapshot_data = snapshot_data
                
        except Exception as e:
            self.logger.error(f"Telemetry update error: {e}")
    
    def start(self):
        """와처 시작"""
        if self.running:
            self.logger.warning("File watcher already running")
            return
        
        self.logger.info("Starting real-time file watcher...")
        
        # 디렉토리 확인
        self._ensure_directories()
        
        # Observer 시작
        if not self._start_observer():
            return False
        
        # 이벤트 처리 스레드 시작
        self.running = True
        self.stop_event.clear()
        self.watcher_thread = Thread(target=self._process_events, daemon=True)
        
        # Streamlit 컨텍스트 추가
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            add_script_run_ctx(self.watcher_thread)
        except ImportError:
            pass  # Streamlit이 없으면 무시
        
        self.watcher_thread.start()
        
        self.logger.info("File watcher started successfully")
        return True
    
    def stop(self):
        """와처 중지"""
        if not self.running:
            return
        
        self.logger.info("Stopping file watcher...")
        
        self.running = False
        self.stop_event.set()
        
        # Observer 중지
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        # 이벤트 처리 스레드 중지
        if self.watcher_thread:
            self.watcher_thread.join(timeout=5.0)
        
        self.logger.info("File watcher stopped")
    
    def get_telemetry(self) -> TelemetryData:
        """텔레메트리 데이터 반환"""
        self._update_telemetry()
        return self.telemetry
    
    def seed_first_tick(self, symbol: str) -> bool:
        """첫 틱 시드 (2-tick 지연 방지)"""
        if symbol in self.first_tick_seeded:
            return False
        
        if not self.last_snapshot_data:
            return False
        
        try:
            # 심볼 데이터 확인
            ohlcv_data = self.last_snapshot_data.get('ohlcv_1m', {})
            if symbol not in ohlcv_data:
                return False
            
            # 타임스탬프 일관성 확인
            current_time = time.time()
            snapshot_ts = self.last_snapshot_data.get('timestamp', 0)
            
            # 5분 이내 데이터만 사용
            if current_time - snapshot_ts > 300:
                return False
            
            # 시드 완료
            self.first_tick_seeded.add(symbol)
            self.logger.info(f"Seeded first tick for {symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"First tick seed error for {symbol}: {e}")
            return False
    
    def validate_integrity(self, data: Dict) -> bool:
        """데이터 무결성 검증"""
        try:
            # JSON 파싱 확인
            if not isinstance(data, dict):
                return False
            
            # 필수 키 확인
            required_keys = ['timestamp', 'meta', 'ohlcv_1m']
            for key in required_keys:
                if key not in data:
                    self.logger.warning(f"Missing required key: {key}")
                    return False
            
            # 타임스탬프 진행 확인
            current_ts = data.get('timestamp', 0)
            if hasattr(self, '_last_timestamp'):
                if current_ts <= self._last_timestamp:
                    self.logger.warning(f"Timestamp not progressing: {current_ts} <= {self._last_timestamp}")
                    return False
            
            self._last_timestamp = current_ts
            
            # 심볼 수 확인
            ohlcv_data = data.get('ohlcv_1m', {})
            symbol_count = len(ohlcv_data)
            
            # watchlist와 비교 (대략적)
            if symbol_count < 5:  # 최소 심볼 수
                self.logger.warning(f"Too few symbols: {symbol_count}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Integrity validation error: {e}")
            return False


# 전역 와처 인스턴스
_global_watcher: Optional[RealTimeFileWatcher] = None


def get_global_watcher() -> RealTimeFileWatcher:
    """전역 와처 인스턴스 반환"""
    global _global_watcher
    if _global_watcher is None:
        _global_watcher = RealTimeFileWatcher()
    return _global_watcher


def start_global_watcher() -> bool:
    """전역 와처 시작"""
    watcher = get_global_watcher()
    return watcher.start()


def stop_global_watcher():
    """전역 와처 중지"""
    global _global_watcher
    if _global_watcher:
        _global_watcher.stop()
        _global_watcher = None
