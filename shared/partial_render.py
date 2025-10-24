#!/usr/bin/env python3
"""
부분 렌더링 시스템
변경된 섹션만 렌더링하여 성능 최적화
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import streamlit as st

from shared.event_watcher import FileSignature


@dataclass
class SectionKey:
    """섹션 렌더링 키"""
    name: str
    hash_value: str
    
    def __str__(self) -> str:
        return f"{self.name}:{self.hash_value[:8]}"


class PartialRenderManager:
    """부분 렌더링 관리자"""
    
    def __init__(self):
        # 섹션별 마지막 키 저장
        if "section_keys" not in st.session_state:
            st.session_state.section_keys = {}
        
        # 렌더링 통계
        if "render_stats" not in st.session_state:
            st.session_state.render_stats = {}
    
    def get_section_key(self, section_name: str, *signatures: FileSignature) -> SectionKey:
        """섹션 키 생성"""
        hash_input = f"{section_name}|"
        for sig in signatures:
            hash_input += f"{sig.abs_path}|{sig.mtime_ns}|{sig.size}|"
        
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        return SectionKey(name=section_name, hash_value=hash_value)
    
    def should_render_section(self, section_name: str, current_key: SectionKey) -> bool:
        """섹션이 렌더링되어야 하는지 확인"""
        # Initialize section_keys if not exists
        if "section_keys" not in st.session_state:
            st.session_state.section_keys = {}
        
        last_key = st.session_state.get("section_keys", {}).get(section_name)
        
        if last_key is None or str(last_key) != str(current_key):
            # 키가 변경되었거나 처음 렌더링
            # Safe initialization of section_keys
            section_keys = st.session_state.get("section_keys", {})
            section_keys[section_name] = current_key
            st.session_state["section_keys"] = section_keys
            
            # 통계 업데이트
            render_stats = st.session_state.get("render_stats", {})
            if section_name not in render_stats:
                render_stats[section_name] = {"renders": 0, "skips": 0}
            render_stats[section_name]["renders"] += 1
            st.session_state["render_stats"] = render_stats
            
            return True
        else:
            # 키가 동일하므로 스킵
            render_stats = st.session_state.get("render_stats", {})
            if section_name not in render_stats:
                render_stats[section_name] = {"renders": 0, "skips": 0}
            render_stats[section_name]["skips"] += 1
            st.session_state["render_stats"] = render_stats
            
            return False
    
    def render_section(self, section_name: str, current_key: SectionKey, 
                      render_func: Callable, *args, **kwargs) -> Any:
        """섹션 렌더링 (조건부)"""
        if self.should_render_section(section_name, current_key):
            return render_func(*args, **kwargs)
        else:
            # 스킵된 경우 빈 컨테이너 반환
            return st.empty()
    
    def get_render_stats(self) -> Dict[str, Dict[str, int]]:
        """렌더링 통계 반환"""
        return st.session_state.render_stats.copy()
    
    def reset_stats(self):
        """통계 초기화"""
        st.session_state.render_stats = {}


# 전역 인스턴스
_render_manager: Optional[PartialRenderManager] = None


def get_render_manager() -> PartialRenderManager:
    """렌더링 관리자 싱글톤 반환"""
    global _render_manager
    if _render_manager is None:
        _render_manager = PartialRenderManager()
    return _render_manager


def render_with_cache(section_name: str, signatures: list, render_func: Callable, *args, **kwargs):
    """캐시 기반 조건부 렌더링"""
    manager = get_render_manager()
    section_key = manager.get_section_key(section_name, *signatures)
    
    return manager.render_section(section_name, section_key, render_func, *args, **kwargs)


def create_section_container(section_name: str) -> st.container:
    """섹션별 안정적인 컨테이너 생성"""
    # 안정적인 키로 컨테이너 생성
    container_key = f"container_{section_name}"
    return st.container()


def render_placeholder(section_name: str, last_age: Optional[float] = None):
    """가벼운 플레이스홀더 렌더링 (탭이 비활성화된 경우)"""
    placeholder = st.empty()
    
    with placeholder.container():
        if last_age is not None:
            st.info(f"📊 {section_name} (마지막 업데이트: {last_age:.1f}초 전)")
        else:
            st.info(f"📊 {section_name} (데이터 로딩 중...)")
    
    return placeholder


def get_file_signature_for_path(relative_path: str) -> FileSignature:
    """파일 경로에 대한 시그니처 생성"""
    from pathlib import Path

    from shared.event_watcher import EventWatcher
    from shared.path_registry import PathRegistry
    
    registry = PathRegistry.current()
    watcher = EventWatcher()
    
    # 상대 경로를 절대 경로로 변환
    abs_path = str(registry.repo_root / relative_path)
    return watcher._get_file_signature(abs_path)
