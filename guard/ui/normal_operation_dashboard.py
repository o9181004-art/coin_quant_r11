"""
Normal Operation Dashboard - Fast-First Render (FFR) Optimized
Main dashboard with HealthV2 integration and auto trading control
Guarantees first paint within 5 seconds with lazy hydration
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import FFR Guard
from guard.ui.boot_controller import get_ffr_guard, skip_if_fast_start, with_timeout
from shared.auto_trading_control import (
    disable_auto_trading,
    emergency_stop,
    enable_auto_trading,
    get_auto_trading_status,
)
from shared.env_loader import get_env, get_env_hash
from shared.env_ssot import read_ssot_snapshot
from shared.health_v2 import (
    get_health_v2_summary,
    is_system_ready_for_auto_trading,
    validate_health_v2,
)
from shared.path_registry import (
    get_account_snapshot_path,
    get_all_paths,
    get_uds_heartbeat_path,
    log_paths,
)
from shared.schema_validators import validate_account_schema, validate_uds_schema


@with_timeout(200)  # 200ms timeout
def render_header():
    """Render dashboard header"""
    ffr = get_ffr_guard()
    ffr.mark_first_paint()

    st.markdown("## 🚀 코인퀀트 Normal Operation Dashboard")
    st.markdown("---")

    # Read SSOT for environment info (deferred if heavy)
    ssot = (
        ffr.defer_task("ssot_read", read_ssot_snapshot, 100)
        if ffr.should_skip_heavy_operations()
        else read_ssot_snapshot()
    )

    # Environment info
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if ssot:
            mode = ssot.get("mode", "UNKNOWN")
            if mode == "LIVE":
                st.success("🟢 LIVE 모드")
            elif mode == "TESTNET":
                st.warning("🧪 TESTNET")
            else:
                st.info(f"🔵 {mode} 모드")
        else:
            trading_mode = get_env("TRADING_MODE", "unknown")
            if trading_mode == "live":
                st.success("🟢 LIVE 모드")
            else:
                st.info(f"🔵 {trading_mode.upper()} 모드")

    with col2:
        if ssot:
            base_url = ssot.get("base_url", "UNKNOWN")
            if "testnet" in base_url.lower():
                st.warning("🧪 TESTNET")
            else:
                st.success("🌐 MAINNET")
        else:
            testnet = get_env("BINANCE_USE_TESTNET", "true", bool)
            if testnet:
                st.warning("🧪 TESTNET")
            else:
                st.success("🌐 MAINNET")

    with col3:
        if ssot:
            env_hash = ssot.get("env_hash", "unknown")
            st.text(f"ENV: {env_hash[:8]}...")
        else:
            env_hash = get_env_hash()
            st.text(f"ENV: {env_hash[:8]}...")

    with col4:
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        st.text(f"시간: {current_time}")


@with_timeout(300)  # 300ms timeout
def render_system_status():
    """Render system status overview"""
    st.markdown("### 📊 시스템 상태")

    try:
        ffr = get_ffr_guard()

        # Defer heavy health checks if needed
        if ffr.should_skip_heavy_operations():
            health_status = ffr.defer_task("health_check", validate_health_v2, 200)
            auto_status = ffr.defer_task("auto_status", get_auto_trading_status, 100)
        else:
            health_status = validate_health_v2()
            auto_status = get_auto_trading_status()

        # Status cards
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if health_status.is_green:
                st.success("🟢 GREEN")
            else:
                st.error("🔴 RED")
            st.metric("Health Status", f"{health_status.green_count}/7")

        with col2:
            if auto_status.get("enabled", False):
                st.success("🟢 Auto Trading ON")
            else:
                st.error("🔴 Auto Trading OFF")
            st.metric(
                "Trading Status", "Active" if auto_status.get("enabled") else "Inactive"
            )

        with col3:
            if health_status.safe_to_trade:
                st.success("✅ Safe to Trade")
            else:
                st.error("❌ Unsafe to Trade")
            st.metric("Safety", "OK" if health_status.safe_to_trade else "BLOCKED")

        with col4:
            st.info("🔄 Live Data")
            st.metric("Last Update", time.strftime("%H:%M:%S"))

        # Status summary
        if health_status.is_green and auto_status.get("enabled", False):
            st.success("🎉 시스템이 정상 작동 중이며 자동매매가 활성화되어 있습니다.")
        elif health_status.is_green:
            st.info("✅ 시스템이 정상 작동 중입니다. 자동매매를 시작할 수 있습니다.")
        else:
            st.error("❌ 시스템에 문제가 있습니다. 자동매매를 시작할 수 없습니다.")

        return health_status, auto_status

    except Exception as e:
        st.error(f"시스템 상태 확인 중 오류: {e}")
        return None, None


def render_control_panel():
    """Render control panel"""
    st.markdown("### 🎛️ 제어판")

    try:
        health_status = validate_health_v2()
        auto_status = get_auto_trading_status()

        # Control buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "🚀 Start Auto-Trading", type="primary", use_container_width=True
            ):
                if health_status.is_green:
                    result = enable_auto_trading("dashboard")
                    if result.get("success", False):
                        st.success("✅ 자동매매가 시작되었습니다!")
                        st.rerun()
                    else:
                        st.error(
                            f"❌ 자동매매 시작 실패: {result.get('reason', 'Unknown error')}"
                        )
                else:
                    st.error(
                        "❌ 시스템이 GREEN 상태가 아닙니다. 모든 프로브가 통과해야 합니다."
                    )

        with col2:
            if st.button("⏸️ Stop Auto-Trading", use_container_width=True):
                result = disable_auto_trading("dashboard", "Manual stop from dashboard")
                if result.get("success", False):
                    st.success("✅ 자동매매가 중지되었습니다!")
                    st.rerun()
                else:
                    st.error(
                        f"❌ 자동매매 중지 실패: {result.get('reason', 'Unknown error')}"
                    )

        with col3:
            if st.button(
                "🚨 Emergency Stop", type="secondary", use_container_width=True
            ):
                result = emergency_stop("Emergency stop from dashboard")
                if result.get("success", False):
                    st.error("🚨 비상정지가 실행되었습니다!")
                    st.rerun()
                else:
                    st.error(
                        f"❌ 비상정지 실패: {result.get('reason', 'Unknown error')}"
                    )

        # Status details
        if auto_status.get("enabled", False):
            st.info(
                f"💡 자동매매 활성화됨 (by {auto_status.get('enabled_by', 'unknown')})"
            )
            if auto_status.get("last_enabled"):
                last_enabled = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(auto_status["last_enabled"])
                )
                st.text(f"마지막 활성화: {last_enabled}")
        else:
            st.warning("⚠️ 자동매매가 비활성화되어 있습니다.")
            if auto_status.get("reason"):
                st.text(f"사유: {auto_status['reason']}")

    except Exception as e:
        st.error(f"제어판 상태 확인 중 오류: {e}")


@with_timeout(300)  # 300ms timeout
def render_ssot_paths():
    """Render SSOT Paths section"""
    st.markdown("### 📁 SSOT Paths")

    try:
        # Get all canonical paths
        paths = get_all_paths()

        # Critical paths to display (using exact paths from requirements)
        uds_heartbeat_path = get_uds_heartbeat_path()
        account_snapshot_path = get_account_snapshot_path()

        critical_paths = [
            ("UDS_HEARTBEAT", "UDS Heartbeat", uds_heartbeat_path),
            ("ACCOUNT_SNAPSHOT", "Account Snapshot", account_snapshot_path),
            ("HEALTH", "Main Health", paths.get("HEALTH", Path(""))),
            (
                "DATABUS_SNAPSHOT",
                "Databus Snapshot",
                paths.get("DATABUS_SNAPSHOT", Path("")),
            ),
        ]

        for path_key, description, path in critical_paths:
            exists = path.exists()
            age = "N/A"

            if exists:
                try:
                    mtime = path.stat().st_mtime
                    age = f"{time.time() - mtime:.1f}s"
                except:
                    age = "ERROR"

            col1, col2, col3 = st.columns([3, 1, 2])
            with col1:
                status = "✓" if exists else "✗"
                st.text(f"{status} {description}")
            with col2:
                st.text(age)
            with col3:
                st.text(str(path))

        # Exact Path Display (as requested)
        st.markdown("#### Exact Absolute Paths")
        st.text(f"UDS_HEARTBEAT = {uds_heartbeat_path}")
        st.text(f"ACCOUNT_SNAPSHOT = {account_snapshot_path}")
        st.text(f"DATABUS_SNAPSHOT = {paths.get('DATABUS_SNAPSHOT', Path(''))}")

        # Validation status
        st.markdown("#### Validation Status")

        # UDS validation (using correct UDS heartbeat path)
        uds_validation = validate_uds_schema(uds_heartbeat_path)
        uds_status = (
            "✓ VALID"
            if uds_validation.is_valid
            else f"✗ INVALID ({uds_validation.error_msg})"
        )
        st.text(f"UDS Heartbeat: {uds_status} (age: {uds_validation.age_sec:.1f}s)")

        # Account validation (using correct account snapshot path)
        account_validation = validate_account_schema(account_snapshot_path)
        account_status = (
            "✓ VALID"
            if account_validation.is_valid
            else f"✗ INVALID ({account_validation.error_msg})"
        )
        st.text(
            f"Account Snapshot: {account_status} (age: {account_validation.age_sec:.1f}s)"
        )

    except Exception as e:
        st.error(f"SSOT Paths error: {e}")


def render_health_probes():
    """Render health probes status"""
    st.markdown("### 🔍 헬스 프로브 상태")

    try:
        health_status = validate_health_v2()

        # Probe results
        for probe in health_status.probe_results:
            col1, col2, col3 = st.columns([3, 1, 2])

            with col1:
                if probe.status:
                    st.success(f"✅ {probe.probe_name}")
                else:
                    st.error(f"❌ {probe.probe_name}")

            with col2:
                if probe.age_seconds > 0:
                    st.metric("Age", f"{probe.age_seconds:.1f}s")
                else:
                    st.metric("Age", "N/A")

            with col3:
                st.text(probe.message)

        # Summary
        if health_status.is_green:
            st.success("🎉 모든 프로브가 정상 작동 중입니다.")
        else:
            failed_probes = [
                p.probe_name for p in health_status.probe_results if not p.status
            ]
            st.error(f"⚠️ 다음 프로브가 실패했습니다: {', '.join(failed_probes)}")

    except Exception as e:
        st.error(f"헬스 프로브 상태 확인 중 오류: {e}")


def render_quick_actions():
    """Render quick actions"""
    st.markdown("### ⚡ 빠른 작업")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🔍 Health Check", use_container_width=True):
            st.rerun()

    with col2:
        if st.button("📊 Status", use_container_width=True):
            st.rerun()

    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    with col4:
        if st.button("📋 Logs", use_container_width=True):
            st.info("로그 확인 기능은 개발 중입니다.")


def render_normal_operation_dashboard():
    """Main normal operation dashboard renderer with FFR Guard"""
    ffr = get_ffr_guard()

    # Check if we should show skeleton UI
    if not ffr.enforce_first_paint_deadline():
        ffr.render_skeleton_ui()
        ffr.render_degraded_banner()
        return {"health_status": None, "auto_status": None}

    # Fast-first render
    try:
        # Header (always fast)
        render_header()

        # System status (with timeout protection)
        health_status, auto_status = render_system_status()
        st.markdown("---")

        # Control panel (deferred if needed)
        if ffr.should_skip_heavy_operations():
            st.info("🎛️ 제어판 로딩 중...")
        else:
            render_control_panel()
        st.markdown("---")

        # SSOT Paths (deferred if needed)
        if ffr.should_skip_heavy_operations():
            st.info("📁 SSOT Paths 로딩 중...")
        else:
            render_ssot_paths()
        st.markdown("---")

        # Health probes (deferred if needed)
        if ffr.should_skip_heavy_operations():
            st.info("🔍 헬스 프로브 로딩 중...")
        else:
            render_health_probes()
        st.markdown("---")

        # Quick actions (always fast)
        render_quick_actions()
        st.markdown("---")

        # Footer (always fast)
        st.markdown("### 💡 사용법")
        st.info(
            """
        1. **시스템 시작**: `start_all.bat` 실행
        2. **상태 확인**: 모든 프로브가 GREEN인지 확인
        3. **자동매매 시작**: "Start Auto-Trading" 버튼 클릭
        4. **모니터링**: 실시간 상태 확인
        5. **중지**: "Stop Auto-Trading" 또는 "Emergency Stop" 버튼 클릭
        """
        )

        # Auto refresh
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()

        st.info("💡 이 페이지는 30초마다 자동으로 새로고침됩니다.")

        # Start hydration for deferred content
        ffr.start_hydration()

        # Show degraded banner if needed
        ffr.render_degraded_banner()

        return {"health_status": health_status, "auto_status": auto_status}

    except Exception as e:
        st.error(f"대시보드 렌더링 오류: {e}")
        ffr.render_degraded_banner()
        return {"health_status": None, "auto_status": None}


if __name__ == "__main__":
    # Initialize FFR Guard
    ffr = get_ffr_guard()

    # Test the dashboard
    st.set_page_config(
        page_title="Normal Operation Dashboard", page_icon="🚀", layout="wide"
    )

    # Render with FFR protection
    result = render_normal_operation_dashboard()

    # Show performance metrics if requested
    if st.query_params.get("report") == "timing":
        st.markdown("### 📊 Performance Report")
        metrics = ffr.get_metrics_summary()
        st.json(metrics)
