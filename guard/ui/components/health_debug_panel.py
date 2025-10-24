#!/usr/bin/env python3
"""
Health Debug Panel
Health 파일 경로, mtime, age, status 표시
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

# SSOT Path Resolver import
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from shared.ssot_path_resolver import (get_component_health_path,
                                           get_databus_snapshot_path,
                                           get_health_dir, get_health_path)
    SSOT_AVAILABLE = True
except ImportError:
    SSOT_AVAILABLE = False


class HealthDebugPanel:
    """Health Debug Panel 렌더러"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # SSOT 경로
        if SSOT_AVAILABLE:
            self.health_file = get_health_path()
            self.health_dir = get_health_dir()
            self.databus_file = get_databus_snapshot_path()
            self.components = ["feeder", "trader", "uds", "ares", "autoheal"]
        else:
            self.logger.warning("SSOT Path Resolver not available")
            self.health_file = None
            self.health_dir = None
            self.databus_file = None
            self.components = []
    
    def _get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """
        파일 정보 조회
        
        Returns:
            {
                "exists": bool,
                "mtime": float,
                "mtime_iso": str,
                "age_sec": float,
                "size_bytes": int
            }
        """
        try:
            if not file_path or not file_path.exists():
                return {
                    "exists": False,
                    "mtime": 0,
                    "mtime_iso": "N/A",
                    "age_sec": float('inf'),
                    "size_bytes": 0
                }
            
            mtime = file_path.stat().st_mtime
            age_sec = time.time() - mtime
            mtime_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            size_bytes = file_path.stat().st_size
            
            return {
                "exists": True,
                "mtime": mtime,
                "mtime_iso": mtime_iso,
                "age_sec": age_sec,
                "size_bytes": size_bytes
            }
        except Exception as e:
            self.logger.error(f"Failed to get file info for {file_path}: {e}")
            return {
                "exists": False,
                "mtime": 0,
                "mtime_iso": "ERROR",
                "age_sec": float('inf'),
                "size_bytes": 0
            }
    
    def _parse_health_file(self, file_path: Path) -> Optional[Dict]:
        """Health 파일 파싱"""
        try:
            if not file_path or not file_path.exists():
                return None
            
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to parse {file_path}: {e}")
            return None
    
    def _get_status_icon(self, age_sec: float, exists: bool) -> str:
        """상태 아이콘 반환"""
        if not exists:
            return "⚫"  # Missing
        elif age_sec > 30:
            return "🔴"  # Stale (> 30s)
        elif age_sec > 15:
            return "🟡"  # Warning (> 15s)
        else:
            return "🟢"  # Fresh (< 15s)
    
    def render_compact(self):
        """Compact Health Debug Panel (상단 배지)"""
        if not SSOT_AVAILABLE or not self.health_file:
            st.warning("⚠️ SSOT Path Resolver not available")
            return
        
        # 통합 health.json 정보
        info = self._get_file_info(self.health_file)
        status_icon = self._get_status_icon(info["age_sec"], info["exists"])
        
        # Compact badge
        st.markdown(
            f"""
            <div style="
                background-color: #262730;
                border: 1px solid #404050;
                border-radius: 4px;
                padding: 6px 12px;
                margin-bottom: 8px;
                font-size: 11px;
                color: #808495;
            ">
                {status_icon} <strong>Health Source:</strong> 
                <code style="font-size: 10px;">{self.health_file}</code> · 
                Last Modified: <strong>{info["mtime_iso"]}</strong> · 
                Age: <strong>{info["age_sec"]:.1f}s</strong>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    def render_full(self):
        """Full Health Debug Panel (확장형)"""
        if not SSOT_AVAILABLE:
            st.error("❌ SSOT Path Resolver not available")
            return
        
        st.markdown("#### 🔍 Health Debug Panel")
        st.markdown("---")
        
        # 1. Aggregated health.json
        st.markdown("**📊 Aggregated Health File**")
        info = self._get_file_info(self.health_file)
        status_icon = self._get_status_icon(info["age_sec"], info["exists"])
        
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        with col1:
            st.text(f"{status_icon} {self.health_file}")
        with col2:
            st.text(f"Modified: {info['mtime_iso']}")
        with col3:
            st.text(f"Age: {info['age_sec']:.1f}s")
        with col4:
            st.text(f"{info['size_bytes']} bytes")
        
        # Health 파일 파싱 결과
        if info["exists"]:
            health_data = self._parse_health_file(self.health_file)
            if health_data:
                global_status = health_data.get("global_status", "UNKNOWN")
                status_color = {
                    "GREEN": "🟢",
                    "YELLOW": "🟡",
                    "RED": "🔴",
                    "UNKNOWN": "⚪"
                }.get(global_status, "⚪")
                
                st.markdown(f"**Global Status:** {status_color} {global_status}")
                
                # 컴포넌트 상태 요약
                components_data = health_data.get("components", {})
                if components_data:
                    st.markdown("**Component Summary:**")
                    for comp, comp_data in components_data.items():
                        comp_status = comp_data.get("status", "UNKNOWN")
                        comp_age = comp_data.get("age_sec", float('inf'))
                        comp_icon = self._get_status_icon(comp_age, comp_status != "MISSING")
                        st.text(f"  {comp_icon} {comp:12s} = {comp_status:10s} (age: {comp_age:.1f}s)")
        
        st.markdown("---")
        
        # 2. Per-component health files
        st.markdown("**📂 Per-Component Health Files**")
        
        for component in self.components:
            comp_path = get_component_health_path(component)
            info = self._get_file_info(comp_path)
            status_icon = self._get_status_icon(info["age_sec"], info["exists"])
            
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            with col1:
                st.text(f"{status_icon} {comp_path.name}")
            with col2:
                st.text(f"{info['mtime_iso']}")
            with col3:
                st.text(f"{info['age_sec']:.1f}s")
            with col4:
                st.text(f"{info['size_bytes']} bytes" if info["exists"] else "N/A")
        
        st.markdown("---")
        
        # 3. DataBus snapshot
        st.markdown("**🔄 DataBus Snapshot**")
        info = self._get_file_info(self.databus_file)
        status_icon = self._get_status_icon(info["age_sec"], info["exists"])
        
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        with col1:
            st.text(f"{status_icon} {self.databus_file}")
        with col2:
            st.text(f"{info['mtime_iso']}")
        with col3:
            st.text(f"{info['age_sec']:.1f}s")
        with col4:
            st.text(f"{info['size_bytes']} bytes" if info["exists"] else "N/A")
        
        st.markdown("---")
        
        # 4. Periodic log (30s 주기로 로그 출력)
        current_time = time.time()
        if not hasattr(st.session_state, "_last_health_log_time"):
            st.session_state._last_health_log_time = 0
        
        if current_time - st.session_state._last_health_log_time >= 30:
            self._log_health_status()
            st.session_state._last_health_log_time = current_time
    
    def _log_health_status(self):
        """Health 상태 로그 (30초마다)"""
        try:
            info = self._get_file_info(self.health_file)
            
            # 파일 파싱
            health_data = self._parse_health_file(self.health_file)
            global_status = "UNKNOWN"
            if health_data:
                global_status = health_data.get("global_status", "UNKNOWN")
            
            # 한 줄 로그
            self.logger.info(
                f"[HealthUI] reading from {self.health_file}, "
                f"mtime={info['mtime_iso']}, age={info['age_sec']:.1f}s, global={global_status}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log health status: {e}")


# 전역 인스턴스
_health_debug_panel: Optional[HealthDebugPanel] = None


def get_health_debug_panel() -> HealthDebugPanel:
    """전역 Health Debug Panel 인스턴스 반환"""
    global _health_debug_panel
    if _health_debug_panel is None:
        _health_debug_panel = HealthDebugPanel()
    return _health_debug_panel


def render_health_debug_compact():
    """Compact Health Debug Panel 렌더링"""
    panel = get_health_debug_panel()
    panel.render_compact()


def render_health_debug_full():
    """Full Health Debug Panel 렌더링"""
    panel = get_health_debug_panel()
    panel.render_full()

