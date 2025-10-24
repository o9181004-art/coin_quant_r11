#!/usr/bin/env python3
"""
Health & Paths Debug Panel
Provides detailed debugging information for health probes
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from .centralized_path_registry import get_path_registry
from .health_v2 import get_health_v2_summary
from .robust_health_reader import get_robust_health_reader


class HealthDebugPanel:
    """헬스 디버그 패널"""
    
    def __init__(self):
        self.path_registry = get_path_registry()
        self.cache_key = "health_debug_cache"
        self.last_refresh_key = "health_debug_last_refresh"
    
    def render(self):
        """디버그 패널 렌더링"""
        with st.expander("🔍 Health & Paths Debug", expanded=False):
            self._render_global_info()
            st.markdown("---")
            self._render_health_probes()
            st.markdown("---")
            self._render_path_info()
            st.markdown("---")
            self._render_cache_control()
    
    def _render_global_info(self):
        """전역 정보 렌더링"""
        st.subheader("🌐 Global Info")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**RESOLVED_REPO_ROOT:**")
            st.code(str(self.path_registry.get('repo_root')))
            
            st.write("**Python Executable:**")
            st.code(str(Path(sys.executable).resolve()))
        
        with col2:
            st.write("**Streamlit PID:**")
            st.code(str(os.getpid()))
            
            st.write("**Streamlit Port:**")
            # 포트 정보는 UI 가드에서 가져올 수 있음
            st.code("8502")  # 기본값
    
    def _render_health_probes(self):
        """헬스 프로브 정보 렌더링"""
        st.subheader("🏥 Health Probes")
        
        # 헬스 프로브 정의
        probes = [
            ("ws_stream_databus", "WebSocket Stream", 60),
            ("positions_snapshot", "Positions Snapshot", 60),
            ("ares_signal_flow", "ARES Signal Flow", 75),
            ("trader_readiness", "Trader Readiness", 300),
            ("env_drift", "Environment Drift", 300),
            ("integration_contracts", "Integration Contracts", 90),
        ]
        
        for probe_name, display_name, threshold in probes:
            with st.expander(f"{display_name} ({probe_name})", expanded=False):
                self._render_probe_details(probe_name, threshold)
    
    def _render_probe_details(self, probe_name: str, threshold: int):
        """개별 프로브 상세 정보"""
        # 파일 경로 매핑
        file_mapping = {
            "ws_stream_databus": "state_bus",
            "positions_snapshot": "health_positions",
            "ares_signal_flow": "health_ares",
            "trader_readiness": "health_trader",
            "env_drift": "ssot_env",
            "integration_contracts": "candidates_ndjson",
        }
        
        file_key = file_mapping.get(probe_name)
        if not file_key:
            st.error(f"Unknown probe: {probe_name}")
            return
        
        path_info = self.path_registry.get_path_info(file_key)
        
        # 강화된 헬스 리더 사용 (ws_stream_databus 제외)
        if probe_name != "ws_stream_databus":
            health_reader = get_robust_health_reader()
            health_status = health_reader.get_all_health_status(self.path_registry)
            
            # 프로브별 헬스 데이터 매핑
            health_mapping = {
                "positions_snapshot": health_status.get("positions"),
                "ares_signal_flow": health_status.get("ares"),
                "trader_readiness": health_status.get("trader"),
                "env_drift": health_status.get("env"),
                "integration_contracts": health_status.get("integration"),
            }
            
            health_data = health_mapping.get(probe_name)
            
            if health_data:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**File Path:**")
                    st.code(path_info['path'])
                    
                    st.write("**File Exists:**")
                    if path_info['exists']:
                        st.success("✅ Yes")
                    else:
                        st.error("❌ No")
                
                with col2:
                    if health_data["age"] is not None:
                        st.write(f"**Age:** {health_data['age']:.1f}s")
                        st.write(f"**Threshold:** {health_data['threshold']}s")
                        st.write(f"**Raw TS:** {health_data['raw_ts']}")
                        st.write(f"**Parsed TS:** {health_data['parsed_ts']}")
                        st.write(f"**Status:** {health_data['status']}")
                        
                        # PASS/FAIL 표시
                        if health_data["pass"]:
                            st.success(f"✅ PASS (≤ {health_data['threshold']}s)")
                        else:
                            st.error(f"❌ FAIL (> {health_data['threshold']}s)")
                        
                        if health_data.get("error"):
                            st.error(f"**Error:** {health_data['error']}")
                    else:
                        st.error(f"❌ {health_data['status']}")
                        if health_data.get("error"):
                            st.error(f"**Error:** {health_data['error']}")
                
                # JSON 내용 미리보기
                if path_info['exists']:
                    try:
                        with open(path_info['path'], 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        if path_info['path'].suffix == '.json':
                            data = json.loads(content)
                            st.json(data)
                        else:
                            st.text_area("Content", content, height=200)
                            
                    except Exception as e:
                        st.error(f"Failed to read file: {e}")
                
                return
        
        # 기존 방식 (ws_stream_databus)
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**File Path:**")
            st.code(path_info['path'])
            
            st.write("**File Exists:**")
            if path_info['exists']:
                st.success("✅ Yes")
            else:
                st.error("❌ No")
        
        with col2:
            if path_info['exists']:
                st.write("**Last Modified:**")
                st.write(f"Human: {path_info.get('mtime_human', 'Unknown')}")
                st.write(f"Epoch: {path_info.get('mtime', 'Unknown')}")
                
                # Age 계산
                if 'mtime' in path_info:
                    age = time.time() - path_info['mtime']
                    st.write(f"**Age:** {age:.1f}s")
                    
                    # Threshold 비교
                    if age <= threshold:
                        st.success(f"✅ PASS (≤ {threshold}s)")
                    else:
                        st.error(f"❌ FAIL (> {threshold}s)")
                else:
                    st.warning("⚠️ Cannot calculate age")
            else:
                st.error("❌ File not found")
        
        # 파일 내용 미리보기
        if path_info['exists'] and path_info['is_file']:
            try:
                with open(path_info['path'], 'r', encoding='utf-8') as f:
                    content = f.read()
                
                st.write("**File Content Preview:**")
                if len(content) > 500:
                    st.code(content[:500] + "...")
                else:
                    st.code(content)
                    
                # JSON 파싱 시도
                try:
                    data = json.loads(content)
                    st.write("**JSON Keys:**")
                    st.write(list(data.keys()) if isinstance(data, dict) else "Not a dict")
                except json.JSONDecodeError:
                    st.write("**Content Type:** Not valid JSON")
                    
            except Exception as e:
                st.error(f"Error reading file: {e}")
    
    def _render_path_info(self):
        """경로 정보 렌더링"""
        st.subheader("📁 Path Registry")
        
        all_paths = self.path_registry.get_all_paths()
        
        for key, path in all_paths.items():
            exists = "✅" if path.exists() else "❌"
            st.write(f"{exists} **{key}:** `{path}`")
    
    def _render_cache_control(self):
        """캐시 제어"""
        st.subheader("🔄 Cache Control")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Reload Health", key="reload_health"):
                # 캐시 무효화
                if self.cache_key in st.session_state:
                    del st.session_state[self.cache_key]
                if self.last_refresh_key in st.session_state:
                    del st.session_state[self.last_refresh_key]
                
                st.session_state[self.last_refresh_key] = time.time()
                st.success("Health cache cleared!")
                st.rerun()
        
        with col2:
            if st.button("🧪 Run Writer Self-Test (30s)", key="self_test"):
                # 자체 테스트 실행
                import subprocess
                import sys
                from pathlib import Path
                
                project_root = Path(__file__).parent.parent.parent
                test_script = project_root / "shared" / "test_writers.py"
                
                try:
                    # 백그라운드에서 테스트 실행
                    subprocess.Popen([
                        sys.executable, str(test_script), "30"
                    ], cwd=str(project_root))
                    
                    st.success("🧪 Self-test started! Monitor ages in the probes above.")
                    st.info("Test writers will update all health files every 10s for 30s")
                    
                except Exception as e:
                    st.error(f"Failed to start self-test: {e}")
        
        with col3:
            if self.last_refresh_key in st.session_state:
                last_refresh = st.session_state[self.last_refresh_key]
                st.write(f"**Last Refresh:** {time.strftime('%H:%M:%S', time.localtime(last_refresh))}")
            else:
                st.write("**Last Refresh:** Never")
        
        # HealthEmitter 컨트롤
        st.markdown("---")
        st.subheader("🏥 HealthEmitter Control")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🏥 Start HealthEmitter", key="start_health_emitter"):
                # HealthEmitter 시작
                import subprocess
                import sys
                from pathlib import Path
                
                project_root = Path(__file__).parent.parent.parent
                launcher_script = project_root / "shared" / "health_emitter_launcher.py"
                
                try:
                    # 백그라운드에서 HealthEmitter 실행
                    subprocess.Popen([
                        sys.executable, "-m", "shared.health_emitter_launcher", "--start"
                    ], cwd=str(project_root))
                    
                    st.success("🏥 HealthEmitter started!")
                    st.info("HealthEmitter will keep all health files fresh")
                    
                except Exception as e:
                    st.error(f"Failed to start HealthEmitter: {e}")
        
        with col2:
            if st.button("🛑 Stop HealthEmitter", key="stop_health_emitter"):
                # HealthEmitter 중지
                import subprocess
                import sys
                from pathlib import Path
                
                project_root = Path(__file__).parent.parent.parent
                
                try:
                    # HealthEmitter 중지
                    result = subprocess.run([
                        sys.executable, "-m", "shared.health_emitter_launcher", "--stop"
                    ], cwd=str(project_root), capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        st.success("🛑 HealthEmitter stopped!")
                    else:
                        st.error(f"Failed to stop HealthEmitter: {result.stderr}")
                        
                except Exception as e:
                    st.error(f"Failed to stop HealthEmitter: {e}")
        
        # HealthEmitter 상태 표시
        try:
            import subprocess
            import sys
            from pathlib import Path
            
            project_root = Path(__file__).parent.parent.parent
            
            # 상태 조회
            result = subprocess.run([
                sys.executable, "-m", "shared.health_emitter_launcher", "--status"
            ], cwd=str(project_root), capture_output=True, text=True)
            
            if result.returncode == 0:
                if "🟢" in result.stdout:
                    st.success("🟢 HealthEmitter is running")
                else:
                    st.info("⚪ HealthEmitter not running")
            else:
                st.info("⚪ HealthEmitter status unknown")
                
        except Exception:
            st.info("⚪ HealthEmitter status unknown")


def render_health_debug_panel():
    """헬스 디버그 패널 렌더링 함수"""
    panel = HealthDebugPanel()
    panel.render()
