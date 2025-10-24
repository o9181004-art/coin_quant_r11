#!/usr/bin/env python3
"""
이벤트 기반 파일 변경 감지 시스템
주기적 자동 새로고침을 대체하여 실제 파일 변경이 있을 때만 UI 업데이트
"""

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from shared.path_registry import PathRegistry, get_absolute_path


@dataclass
class FileSignature:
    """파일 시그니처 정보"""
    abs_path: str
    mtime_ns: int
    size: int
    
    def to_hash(self) -> str:
        """시그니처를 해시로 변환"""
        content = f"{self.abs_path}|{self.mtime_ns}|{self.size}"
        return hashlib.md5(content.encode()).hexdigest()[:8]


class EventWatcher:
    """이벤트 기반 파일 변경 감지기 (Singleton)"""
    
    _instance = None
    _initialized = False
    _last_log_time = 0.0  # Throttle duplicate logs
    
    def __new__(cls):
        """Singleton pattern - only one instance per process"""
        if cls._instance is None:
            cls._instance = super(EventWatcher, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Skip re-initialization if already initialized
        if EventWatcher._initialized:
            # Throttle log: print at most once every 30s
            current_time = time.time()
            if current_time - EventWatcher._last_log_time >= 30.0:
                print("[EventWatcher] Already active – skipped re-initialization")
                EventWatcher._last_log_time = current_time
            return
        
        self.registry = PathRegistry.current()
        self.watched_files: Dict[str, str] = {}  # path -> expected hash
        self.last_signatures: Dict[str, FileSignature] = {}
        self.running = False
        self.watcher_thread: Optional[threading.Thread] = None
        
        # 설정값
        self.poll_interval = float(os.getenv("UI_EVENT_POLL_MS", "600")) / 1000.0
        self.debounce_delay = float(os.getenv("UI_RERUN_DEBOUNCE_MS", "1200")) / 1000.0
        self.max_reruns_per_min = int(os.getenv("UI_MAX_RERUNS_PER_MIN", "10"))
        
        # 상태 관리
        self.last_change_time = 0.0
        self.last_rerun_time = 0.0
        self.rerun_count = 0
        self.rerun_window_start = time.time()
        
        # 콜백
        self.on_change_callback = None
        
        EventWatcher._initialized = True
        print(f"[EventWatcher] Initialized - poll_interval={self.poll_interval}s, debounce={self.debounce_delay}s")
    
    def add_watch_file(self, relative_path: str, description: str = "") -> bool:
        """감시할 파일 추가"""
        try:
            # 상대 경로를 절대 경로로 변환
            from pathlib import Path

            from shared.path_registry import PathRegistry
            registry = PathRegistry.current()
            abs_path = str(registry.repo_root / relative_path)
            self.watched_files[abs_path] = description
            
            # 초기 시그니처 설정
            if os.path.exists(abs_path):
                sig = self._get_file_signature(abs_path)
                self.last_signatures[abs_path] = sig
                print(f"[EventWatcher] 감시 파일 추가: {relative_path} -> {sig.to_hash()}")
            else:
                print(f"[EventWatcher] 파일이 존재하지 않음: {relative_path}")
                
            return True
        except Exception as e:
            print(f"[EventWatcher] 파일 감시 추가 실패 {relative_path}: {e}")
            return False
    
    def set_change_callback(self, callback):
        """변경 감지 콜백 설정"""
        self.on_change_callback = callback
    
    def start(self):
        """감시 시작"""
        if self.running:
            # Throttle log: print at most once every 30s
            current_time = time.time()
            if current_time - EventWatcher._last_log_time >= 30.0:
                print("[EventWatcher] Already running – skipped start")
                EventWatcher._last_log_time = current_time
            return
            
        self.running = True
        self.watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.watcher_thread.start()
        print(f"[EventWatcher] Started watching {len(self.watched_files)} files")
    
    def stop(self):
        """감시 중지"""
        self.running = False
        if self.watcher_thread:
            self.watcher_thread.join(timeout=1.0)
        print("[EventWatcher] 파일 감시 중지")
    
    def _get_file_signature(self, abs_path: str) -> FileSignature:
        """파일 시그니처 계산"""
        try:
            stat = os.stat(abs_path)
            return FileSignature(
                abs_path=abs_path,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size
            )
        except (OSError, FileNotFoundError):
            # 파일이 없거나 접근 불가능한 경우 빈 시그니처
            return FileSignature(abs_path=abs_path, mtime_ns=0, size=0)
    
    def _compute_combined_hash(self) -> str:
        """모든 감시 파일의 결합 해시 계산"""
        signatures = []
        for abs_path in self.watched_files.keys():
            sig = self.last_signatures.get(abs_path)
            if sig:
                signatures.append(sig.to_hash())
            else:
                signatures.append("missing")
        
        combined = "|".join(signatures)
        return hashlib.md5(combined.encode()).hexdigest()[:12]
    
    def _check_rate_limit(self) -> bool:
        """속도 제한 확인"""
        now = time.time()
        
        # 1분 윈도우 초기화
        if now - self.rerun_window_start >= 60:
            self.rerun_count = 0
            self.rerun_window_start = now
        
        # 속도 제한 확인
        if self.rerun_count >= self.max_reruns_per_min:
            return False
            
        return True
    
    def _watch_loop(self):
        """파일 감시 메인 루프"""
        last_hash = ""
        last_debounce_check = 0.0
        
        while self.running:
            try:
                current_time = time.time()
                has_changes = False
                
                # 모든 감시 파일의 시그니처 확인
                for abs_path, description in self.watched_files.items():
                    current_sig = self._get_file_signature(abs_path)
                    last_sig = self.last_signatures.get(abs_path)
                    
                    if not last_sig or current_sig.mtime_ns != last_sig.mtime_ns or current_sig.size != last_sig.size:
                        has_changes = True
                        self.last_signatures[abs_path] = current_sig
                        
                        if description:
                            print(f"[EventWatcher] 변경 감지: {description} -> {current_sig.to_hash()}")
                
                # 변경이 감지된 경우
                if has_changes:
                    current_hash = self._compute_combined_hash()
                    
                    # 해시가 실제로 변경되었는지 확인
                    if current_hash != last_hash:
                        self.last_change_time = current_time
                        last_hash = current_hash
                        print(f"[EventWatcher] 시그니처 해시 변경: {current_hash}")
                
                # 디바운스 확인
                if has_changes and self.last_change_time > 0:
                    time_since_change = current_time - self.last_change_time
                    time_since_last_rerun = current_time - last_debounce_check
                    
                    # 디바운스 지연 시간이 지났고 속도 제한을 통과한 경우
                    if (time_since_change >= self.debounce_delay and 
                        time_since_last_rerun >= self.debounce_delay and
                        self._check_rate_limit()):
                        
                        if self.on_change_callback:
                            try:
                                self.on_change_callback()
                                last_debounce_check = current_time
                                self.last_rerun_time = current_time
                                self.rerun_count += 1
                                
                                print(f"[EventWatcher] UI 업데이트 트리거 - rerun_count={self.rerun_count}")
                            except Exception as e:
                                print(f"[EventWatcher] 콜백 실행 오류: {e}")
                
                time.sleep(self.poll_interval)
                
            except Exception as e:
                print(f"[EventWatcher] 감시 루프 오류: {e}")
                time.sleep(1.0)
    
    def get_status(self) -> Dict:
        """현재 상태 반환"""
        return {
            "running": self.running,
            "watched_files": len(self.watched_files),
            "combined_hash": self._compute_combined_hash(),
            "last_change_age": time.time() - self.last_change_time if self.last_change_time > 0 else None,
            "rerun_count": self.rerun_count,
            "poll_interval": self.poll_interval,
            "debounce_delay": self.debounce_delay
        }


# 전역 인스턴스
_watcher_instance: Optional[EventWatcher] = None


def get_event_watcher() -> EventWatcher:
    """이벤트 와처 싱글톤 인스턴스 반환"""
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = EventWatcher()
    return _watcher_instance


def initialize_event_watcher() -> EventWatcher:
    """이벤트 와처 초기화 및 감시 파일 설정"""
    watcher = get_event_watcher()
    
    # 기본 감시 파일들 추가
    watcher.add_watch_file("shared_data/ares/candidates.ndjson", "ARES 신호")
    watcher.add_watch_file("shared_data/state_bus.json", "시스템 상태")
    watcher.add_watch_file("shared_data/health/positions.json", "포지션 스냅샷")
    watcher.add_watch_file("shared_data/account_snapshot.json", "계좌 스냅샷")
    watcher.add_watch_file("shared_data/health/trader.json", "트레이더 상태")
    watcher.add_watch_file("shared_data/health/ares.json", "ARES 상태")
    
    print(f"[EventWatcher] 초기화 완료 - {len(watcher.watched_files)}개 파일 감시")
    return watcher
