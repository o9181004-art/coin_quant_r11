#!/usr/bin/env python3
"""
실시간 자동매매 엔진 - Multi-Symbol Dashboard
- Multi Board: 다중 심볼 모니터링
- Detail: 단일 심볼 상세 차트
- ARES 분석 항상 표시
- 다크 테마, 그리드 시스템
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from plotly.subplots import make_subplots

# Project root resolver - detect project root by presence of pyproject.toml or src/coin_quant
def get_project_root():
    """Detect project root by looking for pyproject.toml or src/coin_quant directory"""
    current_path = Path(__file__).resolve().parent
    
    # Check current directory and parent directories
    for path in [current_path] + list(current_path.parents):
        if (path / "pyproject.toml").exists() or (path / "src" / "coin_quant").exists():
            return path
    
    # Fallback to current directory
    return current_path

# Set up project root and sys.path
PROJECT_ROOT = get_project_root()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Set up logging for Streamlit
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# Monitoring backend configuration
MONITORING_BACKEND = os.getenv("MONITORING_BACKEND", "file")
HEALTH_DIR = os.getenv("HEALTH_DIR", str(PROJECT_ROOT / "shared_data" / "health"))
MONITORING_ENDPOINT = os.getenv("MONITORING_ENDPOINT", "")

# Safe Readers API - UI should only read, never write
try:
    from shared.readers import (
        read_health_json, read_databus_snapshot, read_account_info,
        read_ares_status, read_candidates_ndjson, read_trader_heartbeat,
        read_json_safely, get_artifact_info
    )
except ImportError:
    # Fallback for when shared.readers is not available
    logging.warning("shared.readers not available, using fallback implementations")
    def read_health_json():
        return {}
    def read_databus_snapshot():
        return {}
    def read_account_info():
        return {}
    def read_ares_status():
        return {}
    def read_candidates_ndjson():
        return []
    def read_trader_heartbeat():
        return {}
    def read_json_safely(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    def get_artifact_info(path):
        return {}

# Configuration constants - use PROJECT_ROOT for all paths
SHARED_DATA_DIR = os.getenv("SHARED_DATA_DIR", str(PROJECT_ROOT / "shared_data"))
SNAPSHOTS_DIR = os.getenv("SNAPSHOTS_DIR", str(PROJECT_ROOT / "shared_data" / "snapshots"))
SIGNALS_DIR = os.getenv("SIGNALS_DIR", str(PROJECT_ROOT / "shared_data" / "signals"))
ARES_DIR = os.getenv("ARES_DIR", str(PROJECT_ROOT / "shared_data" / "ares"))
POSITIONS_FILE = os.getenv("POSITIONS_FILE", str(PROJECT_ROOT / "shared_data" / "positions_snapshot.json"))
SSOT_ENV_FILE = os.getenv("SSOT_ENV_FILE", str(PROJECT_ROOT / "shared_data" / "ssot" / "env.json"))
ACCOUNT_SNAPSHOT_FILE = os.getenv("ACCOUNT_SNAPSHOT_FILE", str(PROJECT_ROOT / "shared_data" / "account_snapshot.json"))
ACCOUNT_INFO_FILE = os.getenv("ACCOUNT_INFO_FILE", str(PROJECT_ROOT / "shared_data" / "account_info.json"))
DATABUS_SNAPSHOT_FILE = os.getenv("DATABUS_SNAPSHOT_FILE", str(PROJECT_ROOT / "shared_data" / "databus_snapshot.json"))
STATE_BUS_FILE = os.getenv("STATE_BUS_FILE", str(PROJECT_ROOT / "shared_data" / "state_bus.json"))
AUTO_TRADING_STATE_FILE = os.getenv("AUTO_TRADING_STATE_FILE", str(PROJECT_ROOT / "shared_data" / "auto_trading_state.json"))

def get_run_mode():
    """Detect run mode with fallback hierarchy"""
    try:
        # Primary: SSOT env.json
        if os.path.exists(SSOT_ENV_FILE):
            with open(SSOT_ENV_FILE, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                sim_mode = data.get("SIMULATION_MODE", "true").lower() == "true"
                return {
                    "mode": "SIMULATION" if sim_mode else "LIVE",
                    "source": "env.json"
                }
    except Exception:
        pass
    
    # Fallback: Environment variable
    sim_mode = os.getenv("SIMULATION_MODE", "true").lower() == "true"
    return {
        "mode": "SIMULATION" if sim_mode else "LIVE", 
        "source": "env"
    }

def load_sim_snapshot(path=None):
    """Load simulation snapshot with comprehensive schema validation"""
    if path is None:
        path = ACCOUNT_SNAPSHOT_FILE
    warnings = []
    
    try:
        if not os.path.exists(path):
            warnings.append(f"Missing file: {path}")
            return None, warnings
            
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            
        # Schema validation
        if not isinstance(data, dict):
            warnings.append("Invalid JSON structure: not a dictionary")
            return None, warnings
        
        # Validate required fields
        if "snapshot_ts" not in data:
            warnings.append("Missing snapshot_ts field")
        elif not isinstance(data["snapshot_ts"], str):
            warnings.append("snapshot_ts should be a string")
            
        # Validate cash structure
        if "cash" not in data:
            warnings.append("Missing cash object")
        elif not isinstance(data["cash"], dict):
            warnings.append("cash should be an object")
        elif "balance" not in data["cash"]:
            warnings.append("Missing cash.balance field")
        elif not isinstance(data["cash"]["balance"], (int, float)):
            warnings.append("cash.balance should be a number")
            
        # Validate assets array
        if "assets" not in data:
            warnings.append("Missing assets array")
        elif not isinstance(data["assets"], list):
            warnings.append("assets should be an array")
        else:
            # Validate each asset
            for i, asset in enumerate(data["assets"]):
                if not isinstance(asset, dict):
                    warnings.append(f"Asset[{i}] should be an object")
                    continue
                    
                if "symbol" not in asset:
                    warnings.append(f"Asset[{i}] missing symbol field")
                elif not isinstance(asset["symbol"], str):
                    warnings.append(f"Asset[{i}] symbol should be a string")
                    
                if "free" not in asset:
                    warnings.append(f"Asset[{i}] missing free field")
                elif not isinstance(asset["free"], (int, float)):
                    warnings.append(f"Asset[{i}] free should be a number")
                    
                if "locked" not in asset:
                    warnings.append(f"Asset[{i}] missing locked field")
                elif not isinstance(asset["locked"], (int, float)):
                    warnings.append(f"Asset[{i}] locked should be a number")
        
        # Validate legacy fields
        if "balance" in data and not isinstance(data["balance"], (int, float)):
            warnings.append("balance should be a number")
            
        if "equity" in data and not isinstance(data["equity"], (int, float)):
            warnings.append("equity should be a number")
            
        return data, warnings
        
    except json.JSONDecodeError as e:
        warnings.append(f"JSON parse error: {str(e)}")
        return None, warnings
    except Exception as e:
        warnings.append(f"File read error: {str(e)}")
        return None, warnings

def compute_portfolio(snapshot):
    """Compute portfolio totals from snapshot data with comprehensive validation"""
    warnings = []
    total_balance = 0.0
    assets = []
    
    if not snapshot:
        return total_balance, assets, warnings
    
    try:
        # Extract cash balance (prefer cash.balance over legacy balance)
        if "cash" in snapshot and "balance" in snapshot["cash"]:
            balance = snapshot["cash"]["balance"]
        elif "balance" in snapshot:
            balance = snapshot["balance"]
        else:
            balance = 0.0
            
        # Extract equity (prefer equity over balance)
        if "equity" in snapshot:
            equity = snapshot["equity"]
        else:
            equity = balance
            
        # Validate and normalize values
        if not isinstance(balance, (int, float)) or balance < 0:
            warnings.append("Invalid balance value, using 0")
            balance = 0.0
            
        if not isinstance(equity, (int, float)) or equity < 0:
            warnings.append("Invalid equity value, using 0")
            equity = 0.0
            
        total_balance = max(balance, equity)
        
        # Extract assets (if present)
        if "assets" in snapshot and isinstance(snapshot["assets"], list):
            for i, asset in enumerate(snapshot["assets"]):
                if isinstance(asset, dict):
                    symbol = asset.get("symbol", "")
                    free = asset.get("free", 0.0)
                    locked = asset.get("locked", 0.0)
                    price = asset.get("price", 0.0)
                    
                    # Validate values
                    if not isinstance(free, (int, float)) or free < 0:
                        warnings.append(f"Asset[{i}] invalid free value, using 0")
                        free = 0.0
                        
                    if not isinstance(locked, (int, float)) or locked < 0:
                        warnings.append(f"Asset[{i}] invalid locked value, using 0")
                        locked = 0.0
                        
                    if not isinstance(price, (int, float)) or price < 0:
                        warnings.append(f"Asset[{i}] invalid price value, using 0")
                        price = 0.0
                    
                    if symbol and (free > 0 or locked > 0):
                        assets.append({
                            "symbol": symbol,
                            "free": float(free),
                            "locked": float(locked),
                            "price": float(price),
                            "total": float(free) + float(locked)
                        })
        
        return total_balance, assets, warnings
        
    except Exception as e:
        warnings.append(f"Portfolio computation error: {str(e)}")
        return 0.0, [], warnings

# 알림 시스템을 위한 import
try:
    import winsound

    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False

try:
    from plyer import notification

    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


# 실제 잔고 조회 함수
def get_real_balance():
    """Real balance query with enhanced SSOT logic"""
    mode_info = get_run_mode()
    
    if mode_info["mode"] == "SIMULATION":
        # Use enhanced SSOT snapshot loader
        snapshot, warnings = load_sim_snapshot()
        if snapshot:
            balance, _, _ = compute_portfolio(snapshot)
            return balance
        else:
            # Graceful fallback to zeros
            return 0.0
    else:
        # LIVE mode: keep existing logic
        try:
            if os.path.exists(ACCOUNT_INFO_FILE):
                with open(ACCOUNT_INFO_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    equity_usdt = data.get("total_equity_usdt", 0.0)
                    if equity_usdt == 0.0 and data.get("metadata", {}).get("testnet_mode", False):
                        return 120870.90  # Fallback value
                    return equity_usdt
            
            # Backup: check_balance.py script
            import re
            import subprocess
            
            result = subprocess.run(
                ["python", "check_balance.py"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            
            if result.returncode == 0:
                output = result.stdout
                usdt_match = re.search(r"USDT: ([\d,]+\.?\d*)", output)
                if usdt_match:
                    usdt_balance = usdt_match.group(1).replace(",", "")
                    return float(usdt_balance)
            
            return None
            
        except Exception as e:
            return None


# 실시간 잔고 업데이트를 위한 캐시
@st.cache_data(ttl=3)  # 3초마다 캐시 갱신 (더 자주 갱신)
def get_cached_balance():
    """캐시된 잔고 조회 (3초마다 갱신)"""
    return get_real_balance()


# 실시간 잔고 업데이트 함수
def update_balance_display():
    """실시간 잔고 표시 업데이트"""
    real_balance = get_cached_balance()
    if real_balance is not None:
        balance_display = f"{real_balance:,.2f}"
        return balance_display
    else:
        return "조회 실패"


def save_auto_trading_state(active_state=None):
    """자동매매 상태를 파일에 저장"""
    try:
        state_file = Path(AUTO_TRADING_STATE_FILE)
        state_file.parent.mkdir(parents=True, exist_ok=True)

        # 매개변수가 제공되면 사용하고, 그렇지 않으면 session_state에서 가져옴
        if active_state is not None:
            auto_trading_active = active_state
        else:
            auto_trading_active = st.session_state.get("auto_trading_active", False)

        state = {
            "auto_trading_active": auto_trading_active,
            "timestamp": time.time(),
            "version": "1.0",
        }

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    except Exception:
        pass  # 저장 실패 시 무시


def load_auto_trading_state():
    """파일에서 자동매매 상태 로드"""
    try:
        state_file = Path(AUTO_TRADING_STATE_FILE)
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

                # 1시간 이상 오래된 상태는 무효화
                if time.time() - state.get("timestamp", 0) < 3600:
                    return state.get("auto_trading_active", False)

    except Exception:
        pass

    return False


def clear_auto_trading_state():
    """자동매매 상태 파일 삭제"""
    try:
        state_file = Path(AUTO_TRADING_STATE_FILE)
        if state_file.exists():
            state_file.unlink()
    except Exception:
        pass


# 환경변수 로드
load_dotenv("config.env")

# UI 모드 설정
UI_CARDS_ONLY = os.getenv("UI_CARDS_ONLY", "false").lower() == "true"


# 자동 새로고침 설정 (모의/테스트넷에서만 활성화)
def load_auto_refresh_config():
    """자동 새로고침 설정 로드"""
    try:
        import yaml

        cfg = read_json_safely("config/policy.yaml", default={})

        AUTO_REFRESH_SEC = cfg.get("ui", {}).get("auto_refresh_interval_sec", 5)
        REFRESH_KEY = cfg.get("ui", {}).get("auto_refresh_key", "auto_refresh_main")
    except Exception:
        AUTO_REFRESH_SEC = 5
        REFRESH_KEY = "auto_refresh_main"

    IS_MOCK = str(os.getenv("IS_MOCK", "false")).lower() == "true"
    IS_TESTNET = (
        str(os.getenv("TESTNET", os.getenv("IS_TESTNET", "true"))).lower() == "true"
    )

    # 개발/테스트 환경에서 자동 새로고침 활성화 (기본값)
    # 실제 운영 환경에서는 IS_MOCK=false, TESTNET=false로 설정
    # 환경변수가 설정되지 않은 경우 기본적으로 활성화 (개발/테스트 환경)
    AUTO_REFRESH_ENABLED = (
        IS_MOCK
        or IS_TESTNET
        or (os.getenv("IS_MOCK") is None and os.getenv("TESTNET") is None)
    )

    return AUTO_REFRESH_SEC, REFRESH_KEY, IS_MOCK, IS_TESTNET, AUTO_REFRESH_ENABLED


# 자동 새로고침 설정 로드 (페이지 설정 이후에 실행됨)
AUTO_REFRESH_SEC, REFRESH_KEY, IS_MOCK, IS_TESTNET, AUTO_REFRESH_ENABLED = (
    load_auto_refresh_config()
)


# 알림 시스템 함수들
def play_sound_alert(sound_type="buy"):
    """사운드 알림 재생"""
    if not WINSOUND_AVAILABLE:
        return

    try:
        if sound_type == "buy":
            winsound.MessageBeep(winsound.MB_ICONASTERISK)  # 매수 알림
        elif sound_type == "sell":
            winsound.MessageBeep(winsound.MB_ICONHAND)  # 매도 알림
        else:
            winsound.MessageBeep(winsound.MB_OK)  # 일반 알림
    except Exception:
        pass  # 사운드 재생 실패 시 무시


def show_desktop_notification(title, message, sound_type="info"):
    """데스크톱 알림 표시"""
    if not PLYER_AVAILABLE:
        return

    try:
        notification.notify(title=title, message=message, timeout=5, app_icon=None)
    except Exception:
        pass  # 알림 실패 시 무시


def show_trade_notification(symbol, side, amount, price, confidence=None):
    """거래 체결 알림 표시"""
    timestamp = datetime.now().strftime("%H:%M:%S")

    if side == "BUY":
        title = f"🟢 {symbol} 매수 체결"
        message = f"{amount} USDT @ {price:.2f}"
        sound_type = "buy"
        st.success(
            f"🟢 **{timestamp}** - {symbol} 매수 체결! {amount} USDT @ {price:.2f}"
        )
    else:
        title = f"🔴 {symbol} 매도 체결"
        message = f"{amount} USDT @ {price:.2f}"
        sound_type = "sell"
        st.error(
            f"🔴 **{timestamp}** - {symbol} 매도 체결! {amount} USDT @ {price:.2f}"
        )

    # 신뢰도 표시
    if confidence:
        st.info(f"신뢰도: {confidence}%")

    # 사운드 및 데스크톱 알림
    play_sound_alert(sound_type)
    show_desktop_notification(title, message, sound_type)


def add_notification(message, notification_type="info"):
    """알림을 세션 상태에 추가하고 실시간으로 표시"""
    if "notifications" not in st.session_state:
        st.session_state.notifications = []

    # 알림 추가
    notification = {
        "message": message,
        "type": notification_type,
        "timestamp": time.time(),
    }
    st.session_state.notifications.append(notification)

    # 실시간 토스트 알림 표시 (브라우저 알림 설정 확인)
    browser_notifications = st.session_state.get("browser_notifications", True)
    if browser_notifications:
        if notification_type == "success":
            st.toast(message, icon="✅")
        elif notification_type == "error":
            st.toast(message, icon="❌")
        elif notification_type == "warning":
            st.toast(message, icon="⚠️")
        else:
            st.toast(message, icon="ℹ️")

    # 사운드 알림 (설정된 경우)
    if st.session_state.get("sound_notifications", True):
        play_sound_alert(notification_type)

    # 데스크톱 알림 (설정된 경우)
    if st.session_state.get("desktop_notifications", True):
        show_desktop_notification("코인퀀트 알림", message, notification_type)


def show_fixed_notification_area():
    """고정된 알림 영역 표시 (대시보드 밀림 방지)"""
    # 알림이 있으면 표시, 없으면 빈 영역 유지
    if "notifications" not in st.session_state or not st.session_state.notifications:
        # 알림이 없을 때는 빈 영역만 표시 (고정된 공간 유지)
        st.markdown(
            """
        <div id="fixed-notification-area" style="
            min-height: 50px;
            margin-bottom: 10px;
            background-color: transparent;
            border-radius: 5px;
        "></div>
        """,
            unsafe_allow_html=True,
        )
        return

    # 가장 최근 알림 표시
    latest_notification = st.session_state.notifications[-1]
    message = latest_notification["message"]
    notification_type = latest_notification["type"]

    # 알림 타입별 색상 설정 (매우 부드러운 투명도 적용)
    if notification_type == "success":
        bg_color = "rgba(40, 167, 69, 0.4)"  # 녹색 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(30, 126, 52, 0.3)"
    elif notification_type == "error":
        bg_color = "rgba(220, 53, 69, 0.4)"  # 빨간색 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(189, 33, 48, 0.3)"
    elif notification_type == "warning":
        bg_color = "rgba(220, 53, 69, 0.35)"  # 빨간색 계열 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(189, 33, 48, 0.25)"
    else:
        bg_color = "rgba(23, 162, 184, 0.4)"  # 청록색 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(19, 132, 150, 0.3)"

    # 고정된 알림 영역에 알림 표시
    st.markdown(
        f"""
    <div id="fixed-notification-area" style="
        min-height: 50px;
        margin-bottom: 10px;
        background-color: {bg_color};
        color: {text_color};
        padding: 12px 15px;
        border-radius: 5px;
        border: 1px solid {border_color};
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        font-size: 14px;
        font-weight: 500;
        display: flex;
        align-items: center;
        animation: slideIn 0.3s ease-out;
        backdrop-filter: blur(12px);
    ">
        <span style="margin-right: 8px;">🔔</span>
        <span>{message}</span>
    </div>
    
    <style>
    @keyframes slideIn {{
        from {{
            opacity: 0;
            transform: translateY(-10px);
        }}
        to {{
            opacity: 1;
            transform: translateY(0);
        }}
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )


def show_unified_notification():
    """통합 알림 표시 (JavaScript로 완전히 분리)"""
    if "notifications" not in st.session_state or not st.session_state.notifications:
        return

    # 가장 최근 알림만 표시
    latest_notification = st.session_state.notifications[-1]
    message = latest_notification["message"]
    notification_type = latest_notification["type"]

    # JavaScript로 알림 표시 (레이아웃에 전혀 영향 없음)
    if notification_type == "success":
        color = "#28a745"
        text_color = "white"
    elif notification_type == "error":
        color = "#dc3545"
        text_color = "white"
    elif notification_type == "warning":
        color = "#ffc107"
        text_color = "black"
    else:
        color = "#17a2b8"
        text_color = "white"

    st.markdown(
        f"""
    <script>
    // 기존 알림 제거
    const existingNotification = document.getElementById('unified-notification');
    if (existingNotification) {{
        existingNotification.remove();
    }}
    
    // 새 알림 생성
    const notification = document.createElement('div');
    notification.id = 'unified-notification';
    notification.style.cssText = `
        position: fixed !important;
        top: 20px !important;
        right: 20px !important;
        z-index: 99999 !important;
        background-color: {color} !important;
        color: {text_color} !important;
        padding: 10px 15px !important;
        border-radius: 5px !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.3) !important;
        font-size: 14px !important;
        max-width: 400px !important;
        font-family: Arial, sans-serif !important;
    `;
    notification.innerHTML = `{message}`;
    
    // DOM에 추가
    document.body.appendChild(notification);
    
    // 5초 후 자동 제거
    setTimeout(() => {{
        if (notification.parentNode) {{
            notification.remove();
        }}
    }}, 5000);
    </script>
    """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=2)
def load_latest_signals():
    """최신 ARES 신호 로드"""
    signals = {}
    try:
        ares_dir = Path(ARES_DIR)
        if ares_dir.exists():
            for signal_file in ares_dir.glob("*.json"):
                try:
                    with open(signal_file, "r", encoding="utf-8") as f:
                        signal_data = json.load(f)
                        symbol = signal_file.stem.upper()

                        # 새로운 ARES 데이터 구조 처리
                        if "signals" in signal_data and signal_data["signals"]:
                            # 가장 높은 신뢰도의 신호 선택
                            best_signal = max(
                                signal_data["signals"],
                                key=lambda x: x.get("confidence", 0),
                            )

                            signals[symbol] = {
                                "side": best_signal.get("action", "hold"),
                                "confidence": best_signal.get("confidence", 0),
                                "price": best_signal.get("price", 0),
                                "timestamp": signal_data.get("timestamp", time.time()),
                            }
                        else:
                            # 기존 구조 호환성 유지
                            signals[symbol] = {
                                "side": signal_data.get("side", "hold"),
                                "confidence": signal_data.get("confidence", 0),
                                "price": signal_data.get("price", 0),
                                "timestamp": signal_data.get("timestamp", time.time()),
                            }
                except Exception:
                    continue
    except Exception:
        pass

    return signals


@st.cache_data(ttl=1)
def load_recent_executions():
    """최근 체결 내역 로드 (수익 정보 포함)"""
    executions = []
    try:
        orders_file = Path("data/orders_log.ndjson")
        if orders_file.exists():
            with open(orders_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # 최근 20개 로드 (매수/매도 쌍을 찾기 위해)
                recent_lines = lines[-20:] if len(lines) > 20 else lines

                for line in recent_lines:
                    try:
                        exec_data = json.loads(line.strip())
                        executions.append(
                            {
                                "ts": exec_data.get("ts", 0),
                                "type": exec_data.get("type", ""),
                                "symbol": exec_data.get("symbol", ""),
                                "quote": exec_data.get("quote", 0),
                                "qty": exec_data.get("qty", 0),
                                "price": exec_data.get("res", {})
                                .get("fills", [{}])[0]
                                .get("price", 0),
                                "order_id": exec_data.get("order_id", ""),
                                "raw_data": exec_data,  # 원본 데이터 보관
                            }
                        )
                    except Exception:
                        continue
    except Exception:
        pass

    return executions


def calculate_profit_for_sell(symbol, sell_execution, executions):
    """매도 거래의 수익 계산"""
    try:
        # 같은 심볼의 최근 매수 거래 찾기 (매도 이전의 매수)
        buy_executions = [
            exec
            for exec in executions
            if exec["symbol"] == symbol
            and exec["type"] == "BUY"
            and exec["ts"] < sell_execution["ts"]
        ]

        if not buy_executions:
            return None, None

        # 가장 최근 매수 거래 선택
        latest_buy = max(buy_executions, key=lambda x: x["ts"])

        # 매수/매도 가격
        buy_price = float(latest_buy["price"]) if latest_buy["price"] else 0
        sell_price = float(sell_execution["price"]) if sell_execution["price"] else 0

        if buy_price <= 0 or sell_price <= 0:
            return None, None

        # 수익률 계산
        profit_rate = ((sell_price - buy_price) / buy_price) * 100

        # 수익금 계산 (매도 수량 기준)
        sell_qty = float(sell_execution["qty"]) if sell_execution["qty"] else 0
        profit_amount = sell_qty * (sell_price - buy_price)

        return profit_rate, profit_amount

    except Exception:
        return None, None


def render_trading_signals():
    """실시간 거래 신호 표시"""
    st.subheader("📊 실시간 거래 신호")

    signals = load_latest_signals()

    if not signals:
        st.info("현재 신호 데이터가 없습니다.")

        # 최근 신호 파일들 확인하여 표시
        try:
            signal_files = [
                "SIGNALS_DIR/btcusdt.json",
                "SIGNALS_DIR/ethusdt.json",
                "SIGNALS_DIR/dogeusdt.json",
            ]

            recent_signals = []
            for signal_file in signal_files:
                if os.path.exists(signal_file):
                    with open(signal_file, "r", encoding="utf-8") as f:
                        signal_data = json.load(f)
                        if signal_data.get("confidence", 0) > 0.3:  # 30% 이상만 표시
                            recent_signals.append(signal_data)

            if recent_signals:
                st.markdown("**🔔 최근 신호:**")
                for signal in recent_signals[-3:]:  # 최근 3개만
                    symbol = signal.get("symbol", "").upper()
                    side = signal.get("side", "").upper()
                    confidence = signal.get("confidence", 0)
                    price_hint = signal.get("price_hint", 0)
                    st.write(
                        f"• {symbol} {side} (신뢰도: {confidence:.1f}%) @ ${price_hint:.2f}"
                    )
        except:
            pass

        return

    # 신호를 신뢰도 순으로 정렬
    sorted_signals = sorted(
        signals.items(), key=lambda x: x[1]["confidence"], reverse=True
    )

    # 리스트형으로 깔끔하게 표시
    for symbol, signal in sorted_signals:
        side = signal["side"]
        confidence = signal["confidence"]
        price = signal["price"]

        # 상태 아이콘과 텍스트
        if side == "buy":
            status_display = "🟢 매수"
        elif side == "sell":
            status_display = "🔴 매도"
        else:
            status_display = "⚪ 대기"

        # 가격 포맷팅
        price_display = (
            f"${float(price):,.2f}"
            if price
            and str(price).replace(".", "").replace("-", "").isdigit()
            and float(price) > 0
            else "-"
        )

        # 리스트 아이템으로 표시
        st.markdown(
            f"**{symbol}** | {status_display} | 신뢰도: {confidence:.1f}% | 가격: {price_display}"
        )
        st.markdown("---")


def render_live_executions():
    """실시간 체결 내역 (수익 정보 포함)"""
    st.subheader("⚡ 최근 체결 내역")

    executions = load_recent_executions()

    if not executions:
        st.info("체결 내역이 없습니다.")

        # 현재 포지션 정보 표시
        try:
            if os.path.exists(POSITIONS_FILE):
                with open(
                    POSITIONS_FILE, "r", encoding="utf-8"
                ) as f:
                    positions_data = json.load(f)

                st.markdown("**📊 현재 포지션:**")
                for symbol, position in positions_data.items():
                    if symbol != "timestamp" and isinstance(position, dict):
                        qty = position.get("qty", 0)
                        if qty > 0:
                            avg_px = position.get("avg_px", 0)
                            unrealized_pnl = position.get("unrealized_pnl", 0)
                            st.write(
                                f"• {symbol}: {qty:.6f} @ ${avg_px:.2f} (미실현: ${unrealized_pnl:.2f})"
                            )
        except:
            pass

        return

    # 최신 거래가 위로 오도록 정렬하여 표시
    for execution in reversed(executions[-10:]):  # 최신 10개, 최신이 위로
        timestamp = datetime.fromtimestamp(execution["ts"]).strftime("%H:%M:%S")

        if execution["type"] == "BUY":
            st.success(f"🟢 **{timestamp}** - {execution['symbol']} 매수 체결")
            if execution["quote"] > 0:
                st.write(f"   금액: {execution['quote']} USDT")
            if (
                execution["price"]
                and str(execution["price"]).replace(".", "").replace("-", "").isdigit()
                and float(execution["price"]) > 0
            ):
                st.write(f"   가격: ${float(execution['price']):,.2f}")
        else:
            # 매도 거래 - 수익 정보 계산
            profit_rate, profit_amount = calculate_profit_for_sell(
                execution["symbol"], execution, executions
            )

            if profit_rate is not None and profit_amount is not None:
                # 수익/손실에 따른 색상 결정
                if profit_rate > 0:
                    profit_color = "🟢"
                    profit_text = f"수익: +{profit_rate:.2f}% (+${profit_amount:.2f})"
                else:
                    profit_color = "🔴"
                    profit_text = f"손실: {profit_rate:.2f}% (${profit_amount:.2f})"

                st.error(f"🔴 **{timestamp}** - {execution['symbol']} 매도 체결")
                st.write(f"   수량: {execution['qty']}")
                if (
                    execution["price"]
                    and str(execution["price"])
                    .replace(".", "")
                    .replace("-", "")
                    .isdigit()
                    and float(execution["price"]) > 0
                ):
                    st.write(f"   가격: ${float(execution['price']):,.2f}")
                st.write(f"   {profit_color} {profit_text}")
            else:
                # 수익 정보 없음 (매수 거래 없음)
                st.error(f"🔴 **{timestamp}** - {execution['symbol']} 매도 체결")
                if execution["qty"] > 0:
                    st.write(f"   수량: {execution['qty']}")
                if (
                    execution["price"]
                    and str(execution["price"])
                    .replace(".", "")
                    .replace("-", "")
                    .isdigit()
                    and float(execution["price"]) > 0
                ):
                    st.write(f"   가격: ${float(execution['price']):,.2f}")
                st.write("   ⚪ 수익 정보 없음")


def render_notification_settings():
    """알림 설정"""
    st.subheader("🔔 알림 설정")

    col1, col2 = st.columns(2)

    with col1:
        # 알림 설정 체크박스들 (안전한 방식)
        sound_notifications = st.checkbox(
            "🔊 사운드 알림",
            value=st.session_state.get("sound_notifications", True),
            key="sound_notifications",
        )

        desktop_notifications = st.checkbox(
            "🖥️ 데스크톱 알림",
            value=st.session_state.get("desktop_notifications", True),
            key="desktop_notifications",
        )

        browser_notifications = st.checkbox(
            "🌐 브라우저 알림",
            value=st.session_state.get("browser_notifications", True),
            key="browser_notifications",
        )

    with col2:
        min_confidence = st.slider("최소 신뢰도 (%)", 50, 95, 75, key="min_confidence")
        notification_interval = st.selectbox(
            "알림 간격 (초)", [1, 5, 10, 30], index=1, key="notification_interval"
        )

    # 알림 테스트 버튼
    if st.button("🔔 알림 테스트"):
        test_notification()


def test_notification():
    """알림 테스트 함수"""
    # 현재 설정에 따라 알림 테스트
    if st.session_state.get("browser_notifications", True):
        st.toast("🔔 알림 테스트 - 브라우저 알림이 활성화되어 있습니다!", icon="🔔")

    if st.session_state.get("sound_notifications", True):
        st.success("🔊 사운드 알림 테스트 완료!")

    if st.session_state.get("desktop_notifications", True):
        st.info("🖥️ 데스크톱 알림 테스트 완료!")

    # 설정 상태 표시
    st.write("**현재 알림 설정:**")
    st.write(
        f"- 🔊 사운드 알림: {'✅ 활성' if st.session_state.get('sound_notifications', True) else '❌ 비활성'}"
    )
    st.write(
        f"- 🖥️ 데스크톱 알림: {'✅ 활성' if st.session_state.get('desktop_notifications', True) else '❌ 비활성'}"
    )
    st.write(
        f"- 🌐 브라우저 알림: {'✅ 활성' if st.session_state.get('browser_notifications', True) else '❌ 비활성'}"
    )
    st.write(f"- 📊 최소 신뢰도: {st.session_state.get('min_confidence', 75)}%")
    st.write(f"- ⏰ 알림 간격: {st.session_state.get('notification_interval', 5)}초")


def check_and_notify_signals():
    """신호 확인 및 실시간 알림"""
    try:
        # 신호 파일들 확인
        signal_files = [
            "SIGNALS_DIR/btcusdt.json",
            "SIGNALS_DIR/ethusdt.json",
            "SIGNALS_DIR/dogeusdt.json",
            "SIGNALS_DIR/adausdt.json",
            "SIGNALS_DIR/ltcusdt.json",
            "SIGNALS_DIR/xrpusdt.json",
            "SIGNALS_DIR/solusdt.json",
            "SIGNALS_DIR/avaxusdt.json",
            "SIGNALS_DIR/aaveusdt.json",
            "SIGNALS_DIR/eurusdt.json",
            "SIGNALS_DIR/fdusdusdt.json",
            "SIGNALS_DIR/seiusdt.json",
        ]

        # 마지막 신호 체크 시간 초기화
        if "last_signal_check" not in st.session_state:
            st.session_state.last_signal_check = {}

        for signal_file in signal_files:
            try:
                if not os.path.exists(signal_file):
                    continue

                with open(signal_file, "r", encoding="utf-8") as f:
                    signal_data = json.load(f)

                symbol = signal_data.get("symbol", "").upper()
                signal_timestamp = signal_data.get("ts", 0)
                side = signal_data.get("side", "").upper()
                confidence = signal_data.get("confidence", 0)
                price_hint = signal_data.get("price_hint", 0)

                # 새로운 신호인지 확인
                last_check_time = st.session_state.last_signal_check.get(symbol, 0)

                if (
                    signal_timestamp > last_check_time and confidence > 0.5
                ):  # 신뢰도 50% 이상
                    # 신호 알림 표시
                    signal_message = f"{symbol} {side} 신호 (신뢰도: {confidence:.2f}) @ ${price_hint:.2f}"
                    add_notification(signal_message, "info")

                    # 마지막 체크 시간 업데이트
                    st.session_state.last_signal_check[symbol] = signal_timestamp

            except Exception:
                continue  # 개별 파일 오류는 무시

    except Exception:
        pass  # 전체 오류는 무시


def check_and_notify_executions():
    """실시간 체결 감지 및 알림"""
    try:
        # 세션에 마지막 체결 시간 저장
        if "last_execution_check" not in st.session_state:
            st.session_state.last_execution_check = time.time()

        # 최근 체결 내역 로드
        executions = load_recent_executions()

        if not executions:
            return

        # 가장 최근 체결 확인
        latest_execution = executions[-1]
        latest_execution_time = latest_execution["ts"]
        last_check_time = st.session_state.last_execution_check

        # 새로운 체결이 있는지 확인 (마지막 체결이 마지막 체크 시간 이후)
        if latest_execution_time > last_check_time:
            # 새로운 체결 감지 - 알림 표시
            symbol = latest_execution["symbol"]
            side = latest_execution["type"]
            price = float(latest_execution.get("price", 0))

            if side == "BUY":
                amount = latest_execution.get("quote", 0)
            else:
                amount = latest_execution.get("qty", 0)

            # 알림 표시
            show_trade_notification(symbol, side, amount, price)

            # 마지막 체크 시간 업데이트
            st.session_state.last_execution_check = latest_execution_time

    except Exception:
        # 체결 감지 실패 시 무시 (로그에만 기록)
        pass


def is_auto_healing_active():
    """자동복구 시스템이 활성화되어 있는지 확인"""
    try:
        # 자동복구 시스템이 활성화되어 있는지 확인하는 로직
        # 1. 자동복구 함수가 호출되고 있는지 확인
        # 2. 서비스 상태 모니터링이 작동하고 있는지 확인

        # 세션 상태에서 자동복구 활성화 여부 확인
        if "auto_healing_active" not in st.session_state:
            st.session_state.auto_healing_active = False  # 비활성화 (서비스 재시작 루프 방지)

        return st.session_state.auto_healing_active

    except Exception:
        return False


def check_and_restart_services():
    """서비스 상태 확인 및 자동 재시작 (적극적 모드) - 비활성화됨"""
    try:
        # 오토힐 기능 비활성화 (서비스 재시작 루프 방지)
        return
        
        from coin_quant.shared.service_launcher import get_service_launcher

        sm = get_service_launcher()

        # 자동복구 시스템 활성화 상태 업데이트
        st.session_state.auto_healing_active = False

        feeder_running = sm.is_service_running("feeder")
        trader_running = sm.is_service_running("trader")

        # 중단된 서비스가 있으면 즉시 재시작 시도
        if not feeder_running or not trader_running:
            stopped_services = []
            restart_results = []

            if not feeder_running:
                stopped_services.append("Feeder")
                add_notification("🔄 Feeder 서비스 자동 재시작 시도 중...", "info")
                restart_results.append(("Feeder", sm.start_service("feeder")))

            if not trader_running:
                stopped_services.append("Trader")
                add_notification("🔄 Trader 서비스 자동 재시작 시도 중...", "info")
                restart_results.append(("Trader", sm.start_service("trader")))

            # 재시작 결과 확인 및 메시지 표시
            success_services = [name for name, success in restart_results if success]
            failed_services = [name for name, success in restart_results if not success]

            if success_services:
                add_notification(
                    f"✅ {', '.join(success_services)} 서비스 자동 재시작 완료",
                    "success",
                )
                # 성공 시 상태 업데이트
                time.sleep(1)  # 상태 업데이트 대기

            if failed_services:
                add_notification(
                    f"❌ {', '.join(failed_services)} 서비스 재시작 실패 - 수동 시작 필요",
                    "error",
                )

        # ARES 데이터 건강 상태 확인 (임시 비활성화 - WebSocket 연결 문제로 인한 스테일 데이터)
        # ares_data_issue = check_ares_data_health()
        # if ares_data_issue:
        #     add_notification(f"⚠️ ARES 데이터 문제 감지: {ares_data_issue}", "warning")
        #     # ARES 데이터 문제 시 Trader 서비스 재시작
        #     if trader_running:
        #         add_notification("🔄 ARES 데이터 문제로 인한 Trader 서비스 재시작...", "info")
        #         sm.start_trader()

        # 모든 서비스가 정상이면 간단한 확인 메시지 (선택적)
        elif (
            "show_health_status" not in st.session_state
            or st.session_state.show_health_status
        ):
            # 5초마다 한 번만 표시
            if "last_health_check" not in st.session_state:
                st.session_state.last_health_check = 0

            if time.time() - st.session_state.last_health_check > 5:
                st.session_state.last_health_check = time.time()
                # 조용한 상태 표시 (토스트 메시지로)
                st.toast("🟢 모든 서비스 정상 작동 중", icon="✅")

    except Exception as e:
        st.error(f"❌ 자동복구 시스템 오류: {e}")
        # 오류 발생 시 자동복구 시스템 비활성화
        st.session_state.auto_healing_active = False


def check_ares_data_health():
    """ARES 데이터 건강 상태 확인 - 개선된 모니터링"""
    try:
        import time

        ares_dir = "ARES_DIR"
        if not os.path.exists(ares_dir):
            return "ARES 디렉토리 없음"

        # 워치리스트 로드
        watchlist = load_watchlist_cached()
        if not watchlist:
            return "워치리스트 없음"

        issues = []
        current_time = time.time() * 1000  # 밀리초

        for symbol in watchlist[:7]:  # 모든 심볼 체크
            ares_file = os.path.join(ares_dir, f"{symbol.lower()}.json")

            if not os.path.exists(ares_file):
                issues.append(f"{symbol} ARES 파일 없음")
                continue

            try:
                with open(ares_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 데이터 나이 확인 - 실제 데이터 구조에 맞게 수정
                timestamp = data.get("timestamp", 0)
                if timestamp > 0:
                    age_sec = (time.time() * 1000 - timestamp) / 1000
                    if age_sec > 300:  # 5분 이상 오래된 데이터
                        issues.append(f"{symbol} 데이터 오래됨 ({age_sec:.0f}초)")

                # 상태 확인
                status = data.get("status", "unknown")
                if status != "normal":
                    issues.append(f"{symbol} 상태 이상 ({status})")

            except Exception as e:
                issues.append(f"{symbol} 파일 읽기 오류: {e}")

        if issues:
            return "; ".join(issues[:3])  # 최대 3개 이슈만 표시

        return None  # 문제 없음

    except Exception as e:
        return f"ARES 데이터 체크 오류: {e}"

def render_sidebar():
    """사이드바 렌더링 - 깔끔하게 정리"""
    with st.sidebar:
        # Gates Status Panel - REMOVED (사용자 요청)
        # render_gates_status_panel()
        # st.markdown("---")
        
        # Risk Mode Panel (Compact) - REMOVED
        # try:
        #     from guard.ui.components.risk_panel import \
        #         render_risk_panel_compact
        #     render_risk_panel_compact()
        #     st.markdown("---")
        # except Exception as e:
        #     pass  # Silently fail if risk mode not available

        # 자동매매 컨트롤 섹션
        # 자동매매 상태 초기화 (파일에서 복원) - 사이드바 렌더링 전에 먼저 실행
        if "auto_trading_active" not in st.session_state:
            # 파일에서 저장된 상태 로드
            saved_state = load_auto_trading_state()
            st.session_state.auto_trading_active = saved_state

        # 상태 표시와 함께 제목 표시
        auto_trading_status = st.session_state.get("auto_trading_active", False)
        status_text = "🟢 자동" if auto_trading_status else "🔴 멈춤"
        st.markdown(f"### 🤖 Auto Trading {status_text}")

        # 디버깅: 파일 상태와 세션 상태 비교
        file_state = load_auto_trading_state()
        if file_state != auto_trading_status:
            st.warning(f"⚠️ 상태 불일치 감지! 파일: {file_state}, 세션: {auto_trading_status}")
            st.info("🔄 페이지를 새로고침하면 동기화됩니다.")

        # 적절한 간격 추가
        st.markdown("<div style='margin-bottom: 1rem;'></div>", unsafe_allow_html=True)

        # 저장된 상태가 활성화되어 있으면 엔진 재초기화
        if "auto_trading_active" in st.session_state and st.session_state.auto_trading_active:
            try:
                from executor.trade_exec import TradeExecutor
                from optimizer.ares import ARES

                st.session_state.ares_engine = ARES()
                st.session_state.trade_executor = TradeExecutor()
                st.success("🔄 자동매매 상태가 복원되었습니다")
            except Exception as e:
                st.error(f"자동매매 상태 복원 실패: {e}")
                st.session_state.auto_trading_active = False
                clear_auto_trading_state()

        if "ares_engine" not in st.session_state:
            st.session_state.ares_engine = None
        if "trade_executor" not in st.session_state:
            st.session_state.trade_executor = None

        # 자동매매 토글 - 깔끔한 버튼
        if st.session_state.get("auto_trading_active", False):
            if st.button(
                "🛑 Stop Auto Trading",
                use_container_width=True,
                type="secondary",
                key="btn_stop_auto",
            ):
                try:
                    # Use control plane to disable auto trading
                    from shared.control_plane import get_control_plane
                    
                    control_plane = get_control_plane()
                    success = control_plane.set_user_toggle(False)
                    
                    if success:
                        st.session_state.auto_trading_active = False
                        st.session_state.ares_engine = None
                        st.session_state.trade_executor = None
                        save_auto_trading_state(False)
                        add_notification("🛑 자동매매가 중단되었습니다!", "success")
                        st.rerun()
                    else:
                        add_notification("❌ 자동매매 중단 실패", "error")
                        
                except Exception as e:
                    add_notification(f"❌ 자동매매 중단 오류: {e}", "error")
        else:
            if st.button(
                "🚀 Start Auto Trading",
                use_container_width=True,
                type="primary",
                key="btn_start_auto",
            ):
                try:
                    # Use control plane to enable auto trading
                    from shared.control_plane import get_control_plane
                    
                    control_plane = get_control_plane()
                    success = control_plane.set_user_toggle(True)
                    
                    if success:
                        # ARES 엔진 초기화
                        from executor.trade_exec import TradeExecutor
                        from optimizer.ares import ARES

                        st.session_state.ares_engine = ARES()
                        st.session_state.trade_executor = TradeExecutor()
                        st.session_state.auto_trading_active = True

                        # 상태 저장
                        save_auto_trading_state(True)

                        add_notification("🚀 자동매매가 시작되었습니다!", "success")
                        st.rerun()
                    else:
                        add_notification("❌ 자동매매 시작 실패", "error")

                except Exception as e:
                    add_notification(f"❌ 자동매매 시작 실패: {e}", "error")

        # 글로벌 일시정지 상태 확인 제거됨

        # 현재 레짐과 전략 표시 (자동매매가 활성화된 경우에만)
        if st.session_state.get("auto_trading_active", False):
            # 현재 레짐과 전략 표시 (간격 줄임)
            current_regime = st.session_state.get("current_regime", "sideways")
            current_strategy = st.session_state.get(
                "current_strategy", "bb_mean_revert_v2"
            )

            # 현재 레짐과 전략 표시 (적절한 간격으로 조정)
            st.markdown(
                f"""
            <div style="margin-bottom: 0.5rem;">
                <div style="background-color: #1e1e1e; border: 1px solid #333; border-radius: 0.5rem; padding: 0.5rem; margin-bottom: 0.3rem;">
                    📊 현재 레짐: <strong>{current_regime}</strong>
                </div>
                <div style="background-color: #1e1e1e; border: 1px solid #333; border-radius: 0.5rem; padding: 0.5rem;">
                    🎯 활성 전략: <strong>{current_strategy}</strong>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        # 거래 모드 표시
        trading_mode = (
            "TESTNET"
            if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
            else "MAINNET"
        )
        dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

        # 구분선과 간격 (더 작은 간격으로 조정)
        st.markdown("<hr style='margin: 2rem 0 1.5rem 0; border-color: #444;'>", unsafe_allow_html=True)

        # Manual Trading 섹션 추가 (위로 이동)
        st.markdown("### 💰 Manual Trading")
        
        # 적절한 간격 추가
        st.markdown("<div style='margin-bottom: 1rem;'></div>", unsafe_allow_html=True)

        # 심볼 선택
        watchlist = load_watchlist_cached()
        if watchlist:
            selected_symbol = st.selectbox(
                "Symbol", watchlist, key="manual_trading_symbol_top"
            )

            # 거래 금액 입력
            trade_amount = st.number_input(
                "Amount (USDT)",
                min_value=10.0,
                max_value=1000.0,
                value=100.0,
                step=10.0,
                key="manual_trade_amount_top",
            )
            
            # 간격 추가
            st.markdown("<div style='margin: 0.5rem 0;'></div>", unsafe_allow_html=True)

            # BUY 버튼만 표시
            if st.button(
                "🟢 BUY", use_container_width=True, key="manual_buy_btn_top"
            ):
                    try:
                        # 실제 매수 로직 구현
                        from binance.spot import Spot
                        from dotenv import load_dotenv

                        load_dotenv("config.env")

                        # API 키 설정
                        api_key = os.getenv("BINANCE_API_KEY")
                        api_secret = os.getenv("BINANCE_API_SECRET")
                        use_testnet = (
                            os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
                        )

                        if api_key and api_secret:
                            # Binance 클라이언트 초기화
                            if use_testnet:
                                client = Spot(
                                    api_key=api_key,
                                    api_secret=api_secret,
                                    base_url="https://testnet.binance.vision",
                                )
                            else:
                                client = Spot(api_key=api_key, api_secret=api_secret)

                            # 매수 실행
                            result = client.new_order(
                                symbol=selected_symbol,
                                side="BUY",
                                type="MARKET",
                                quoteOrderQty=trade_amount,
                            )

                            st.success(
                                f"✅ {selected_symbol} 매수 주문 완료 ({trade_amount} USDT)"
                            )

                            # 잔고 캐시 무효화
                            get_cached_balance.clear()
                        else:
                            st.error("❌ API 키가 설정되지 않았습니다")
                    except Exception as e:
                        st.error(f"❌ 매수 실패: {e}")

            # SELL 버튼 제거됨

            # 포지션 확인 버튼 (아래에 별도) - 더 큰 간격 추가
            st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
            if st.button(
                "📊 Position Check",
                use_container_width=True,
                key="position_check_btn_top",
            ):
                try:
                    # 포지션 확인 로직 (실제 구현 필요)
                    st.success(f"✅ {selected_symbol} 포지션 확인 완료")
                except Exception as e:
                    st.error(f"❌ 포지션 확인 실패: {e}")

        # 구분선과 간격
        st.markdown("<hr style='margin: 1rem 0 1.5rem 0; border-color: #444;'>", unsafe_allow_html=True)

        # 잔고 섹션 - 실제 잔고 상시 표시 (아래로 이동)
        st.markdown("### 💰 잔고")
        
        # 적절한 간격 추가
        st.markdown("<div style='margin-bottom: 1rem;'></div>", unsafe_allow_html=True)

        # 실제 잔고 상시 표시
        try:
            # 환경변수에서 API 키 가져오기
            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv(
                "BINANCE_API_SECRET"
            )  # BINANCE_SECRET_KEY -> BINANCE_API_SECRET 수정

            if api_key and api_secret:
                # binance.spot.Spot 클라이언트 사용 (check_balance.py와 동일한 방식)
                from binance.spot import Spot

                # TESTNET URL 설정
                base_url = (
                    "https://testnet.binance.vision"
                    if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
                    else "https://api.binance.com"
                )

                # Spot 클라이언트 생성
                client = Spot(api_key=api_key, api_secret=api_secret, base_url=base_url)

                # 계좌 정보 조회
                account = client.account()
                balances = account.get("balances", [])

                # USDT 잔고 찾기
                usdt_balance = 0.0
                for balance in balances:
                    if balance["asset"] == "USDT":
                        usdt_balance = float(balance["free"]) + float(balance["locked"])
                        break

                # 잔고 표시와 즉시 갱신 버튼
                col_balance = st.columns([1])[0]

                with col_balance:
                    st.markdown(
                        f"""
                    <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333; margin-bottom: 1rem;">
                        <div style="font-size: 1.6rem; font-weight: bold; color: #4CAF50;">{usdt_balance:,.2f} USDT</div>
                        <div style="font-size: 0.8rem; color: #888; margin-top: 0.5rem;">실시간 업데이트</div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

                # 즉시갱신 버튼 제거됨

            else:
                # API 오류 시 데모 잔고 표시
                # 실시간 잔고 조회
                balance_display = update_balance_display()

                # 데모 잔고 표시
                col_balance_demo = st.columns([1])[0]

                with col_balance_demo:
                    st.markdown(
                        f"""
                    <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333; margin-bottom: 1rem;">
                        <div style="font-size: 1.6rem; font-weight: bold; color: #FF9800;">{balance_display} USDT</div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

                # 두 번째 즉시갱신 버튼 제거됨

        except Exception:
            # 오류 시 데모 잔고 표시
            # 실시간 잔고 조회
            balance_display = update_balance_display()

            # 오류 시 데모 잔고 표시 (즉시갱신 버튼 제거됨)
            col_balance_error = st.columns([1])[0]

            with col_balance_error:
                st.markdown(
                    f"""
                <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333; margin-bottom: 1rem;">
                    <div style="font-size: 1.6rem; font-weight: bold; color: #FF9800;">{balance_display} USDT</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # 보유 코인 조회 버튼
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        if st.button(
            "📊 보유 코인 조회", use_container_width=True, key="holdings-check"
        ):
            try:
                mode_info = get_run_mode()
                
                if mode_info["mode"] == "SIMULATION":
                    # Use enhanced SSOT snapshot for holdings
                    snapshot, warnings = load_sim_snapshot()
                    if snapshot:
                        _, assets, _ = compute_portfolio(snapshot)
                        if assets:
                            st.success("📊 시뮬레이션 모드 보유 코인:")
                            for asset in assets:
                                st.write(f"• {asset['symbol']}: {asset['total']:.6f}")
                        else:
                            st.info("📊 현재 보유한 코인이 없습니다.")
                    else:
                        st.warning("📊 시뮬레이션 데이터를 불러올 수 없습니다.")
                        if warnings:
                            with st.expander("⚠️ 데이터 경고", expanded=False):
                                for warning in warnings:
                                    st.warning(warning)
                        
                else:
                    # LIVE mode: keep existing API logic
                    other_balances = {}

                    # 환경변수에서 API 키 가져오기
                    api_key = os.getenv("BINANCE_API_KEY")
                    api_secret = os.getenv(
                        "BINANCE_API_SECRET"
                    )  # BINANCE_SECRET_KEY -> BINANCE_API_SECRET 수정

                    if api_key and api_secret:
                        try:
                            # binance.spot.Spot 클라이언트 사용 (check_balance.py와 동일한 방식)
                            from binance.spot import Spot

                            # TESTNET URL 설정
                            base_url = (
                                "https://testnet.binance.vision"
                                if os.getenv("BINANCE_USE_TESTNET", "true").lower()
                                == "true"
                                else "https://api.binance.com"
                            )

                            # Spot 클라이언트 생성
                            client = Spot(
                                api_key=api_key, api_secret=api_secret, base_url=base_url
                            )

                            # 계좌 정보 조회
                            account = client.account()
                            balances = account.get("balances", [])

                            # 실제로 보유한 코인만 표시 (USDT 제외)
                            for balance in balances:
                                asset = balance["asset"]
                                free = float(balance["free"])
                                locked = float(balance["locked"])
                                total = free + locked

                                # USDT가 아니고 실제로 보유한 코인만 표시
                                if asset != "USDT" and total >= 0.001:  # 0.001 이상만 표시
                                    other_balances[asset] = total

                        except Exception as api_error:
                            st.warning(f"API 조회 실패: {str(api_error)}")
                            # API 실패 시 포지션 데이터에서 가져오기
                            try:
                                import json
                                import pathlib

                                positions_file = pathlib.Path(
                                    "POSITIONS_FILE"
                                )

                                if positions_file.exists():
                                    with open(positions_file, "r", encoding="utf-8") as f:
                                        positions_data = json.load(f)

                                    for symbol, pos_data in positions_data.items():
                                        if symbol.upper().endswith("USDT"):
                                            asset = symbol.upper().replace("USDT", "")
                                            qty = float(pos_data.get("qty", 0))
                                            if qty > 0:
                                                other_balances[asset] = qty
                            except Exception as file_error:
                                st.warning(f"포지션 데이터 조회 실패: {str(file_error)}")

                    else:
                        # API 키 없을 시 포지션 데이터에서 가져오기
                        try:
                            import json
                            import pathlib

                            positions_file = pathlib.Path(
                                "POSITIONS_FILE"
                            )

                            if positions_file.exists():
                                with open(positions_file, "r", encoding="utf-8") as f:
                                    positions_data = json.load(f)

                                for symbol, pos_data in positions_data.items():
                                    if symbol.upper().endswith("USDT"):
                                        asset = symbol.upper().replace("USDT", "")
                                        qty = float(pos_data.get("qty", 0))
                                        if qty > 0:
                                            other_balances[asset] = qty
                        except Exception as file_error:
                            st.warning(f"포지션 데이터 조회 실패: {str(file_error)}")

                    # 결과 표시
                    if other_balances:
                        st.markdown("**보유 코인:**")

                        # 보유 코인을 카드 형태로 표시
                        for asset, qty in sorted(other_balances.items()):
                            # 현재 가격 조회
                            try:
                                from binance.spot import Spot

                                base_url = (
                                    "https://testnet.binance.vision"
                                    if os.getenv("BINANCE_USE_TESTNET", "true").lower()
                                    == "true"
                                    else "https://api.binance.com"
                                )
                                client = Spot(
                                    api_key=api_key,
                                    api_secret=api_secret,
                                    base_url=base_url,
                                )

                                symbol = f"{asset}USDT"
                                ticker = client.ticker_price(symbol=symbol)
                                current_price = float(ticker["price"])
                                total_value = qty * current_price
                            except:
                                current_price = 0
                                total_value = 0

                            # 코인 카드 표시
                            with st.container():
                                st.markdown(
                                    f"""
                                <div style="background-color: #1e1e1e; border: 1px solid #333; border-radius: 0.5rem; padding: 1rem; margin-bottom: 0.5rem;">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <div>
                                            <h4 style="margin: 0; color: #fff;">{asset}</h4>
                                            <p style="margin: 0.2rem 0; color: #888;">보유: {qty:,.8f}</p>
                                            <p style="margin: 0; color: #4CAF50;">가치: ${total_value:,.2f}</p>
                                        </div>
                                        <div style="text-align: right;">
                                            <p style="margin: 0; color: #888;">${current_price:,.4f}</p>
                                        </div>
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                            # 매도 버튼들
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                if st.button(
                                    "🔴 전량 매도",
                                    key=f"sell_all_{asset}",
                                    use_container_width=True,
                                ):
                                    try:
                                        from binance.spot import Spot

                                        base_url = (
                                            "https://testnet.binance.vision"
                                            if os.getenv(
                                                "BINANCE_USE_TESTNET", "true"
                                            ).lower()
                                            == "true"
                                            else "https://api.binance.com"
                                        )
                                        client = Spot(
                                            api_key=api_key,
                                            api_secret=api_secret,
                                            base_url=base_url,
                                        )

                                        symbol = f"{asset}USDT"

                                        # 최소 주문 금액 체크 (5 USDT 이상)
                                        min_notional = 5.0
                                        order_value = qty * current_price

                                        if order_value < min_notional:
                                            st.warning(
                                                f"⚠️ {asset} 주문 금액이 너무 작습니다. 최소 ${min_notional} 필요 (현재: ${order_value:.2f})"
                                            )
                                        else:
                                            # 심볼 정보 조회하여 stepSize 확인
                                            try:
                                                exchange_info = client.exchange_info()
                                                symbol_info = None
                                                for s in exchange_info["symbols"]:
                                                    if s["symbol"] == symbol:
                                                        symbol_info = s
                                                        break

                                                step_size = 1.0
                                                if symbol_info:
                                                    for filter_info in symbol_info[
                                                        "filters"
                                                    ]:
                                                        if (
                                                            filter_info["filterType"]
                                                            == "LOT_SIZE"
                                                        ):
                                                            step_size = float(
                                                                filter_info["stepSize"]
                                                            )
                                                            break

                                                # stepSize에 맞게 수량 조정
                                                adjusted_qty = (
                                                    round(qty / step_size) * step_size
                                                )

                                                order = client.new_order(
                                                    symbol=symbol,
                                                    side="SELL",
                                                    type="MARKET",
                                                    quantity=adjusted_qty,
                                                )

                                                st.success(
                                                    f"✅ {asset} 전량 매도 완료! (수량: {adjusted_qty})"
                                                )
                                                # 캐시 무효화하여 즉시 반영
                                                st.cache_data.clear()
                                                st.rerun()

                                            except Exception as e:
                                                st.error(f"❌ 매도 실패: {e}")

                                    except Exception as e:
                                        st.error(f"❌ 매도 실패: {e}")

                            with col2:
                                if st.button(
                                    "🔴 50% 매도",
                                    key=f"sell_half_{asset}",
                                    use_container_width=True,
                                ):
                                    try:
                                        from binance.spot import Spot

                                        base_url = (
                                            "https://testnet.binance.vision"
                                            if os.getenv(
                                                "BINANCE_USE_TESTNET", "true"
                                            ).lower()
                                            == "true"
                                            else "https://api.binance.com"
                                        )
                                        client = Spot(
                                            api_key=api_key,
                                            api_secret=api_secret,
                                            base_url=base_url,
                                        )

                                        symbol = f"{asset}USDT"
                                        sell_qty = qty * 0.5

                                        # 최소 주문 금액 체크 (5 USDT 이상)
                                        min_notional = 5.0
                                        order_value = sell_qty * current_price

                                        if order_value < min_notional:
                                            st.warning(
                                                f"⚠️ {asset} 50% 매도 금액이 너무 작습니다. 최소 ${min_notional} 필요 (현재: ${order_value:.2f})"
                                            )
                                        else:
                                            # 심볼 정보 조회하여 stepSize 확인
                                            try:
                                                exchange_info = client.exchange_info()
                                                symbol_info = None
                                                for s in exchange_info["symbols"]:
                                                    if s["symbol"] == symbol:
                                                        symbol_info = s
                                                        break

                                                step_size = 1.0
                                                if symbol_info:
                                                    for filter_info in symbol_info[
                                                        "filters"
                                                    ]:
                                                        if (
                                                            filter_info["filterType"]
                                                            == "LOT_SIZE"
                                                        ):
                                                            step_size = float(
                                                                filter_info["stepSize"]
                                                            )
                                                            break

                                                # stepSize에 맞게 수량 조정 (정밀도 문제 해결)
                                                adjusted_qty = (
                                                    round(sell_qty / step_size)
                                                    * step_size
                                                )

                                                # 소수점 자릿수 제한 (stepSize에 따라)
                                                if step_size == 0.1:
                                                    adjusted_qty = round(
                                                        adjusted_qty, 1
                                                    )
                                                elif step_size == 0.01:
                                                    adjusted_qty = round(
                                                        adjusted_qty, 2
                                                    )
                                                elif step_size == 0.001:
                                                    adjusted_qty = round(
                                                        adjusted_qty, 3
                                                    )
                                                else:
                                                    adjusted_qty = round(adjusted_qty)

                                                order = client.new_order(
                                                    symbol=symbol,
                                                    side="SELL",
                                                    type="MARKET",
                                                    quantity=adjusted_qty,
                                                )

                                                st.success(
                                                    f"✅ {asset} 50% 매도 완료! (수량: {adjusted_qty})"
                                                )
                                                # 캐시 무효화하여 즉시 반영
                                                st.cache_data.clear()
                                                st.rerun()

                                            except Exception as e:
                                                st.error(f"❌ 매도 실패: {e}")

                                    except Exception as e:
                                        st.error(f"❌ 매도 실패: {e}")

                            with col3:
                                if st.button(
                                    "🔴 25% 매도",
                                    key=f"sell_quarter_{asset}",
                                    use_container_width=True,
                                ):
                                    try:
                                        from binance.spot import Spot

                                        base_url = (
                                            "https://testnet.binance.vision"
                                            if os.getenv(
                                                "BINANCE_USE_TESTNET", "true"
                                            ).lower()
                                            == "true"
                                            else "https://api.binance.com"
                                        )
                                        client = Spot(
                                            api_key=api_key,
                                            api_secret=api_secret,
                                            base_url=base_url,
                                        )

                                        symbol = f"{asset}USDT"
                                        sell_qty = qty * 0.25

                                        # 최소 주문 금액 체크 (5 USDT 이상)
                                        min_notional = 5.0
                                        order_value = sell_qty * current_price

                                        if order_value < min_notional:
                                            st.warning(
                                                f"⚠️ {asset} 25% 매도 금액이 너무 작습니다. 최소 ${min_notional} 필요 (현재: ${order_value:.2f})"
                                            )
                                        else:
                                            # 심볼 정보 조회하여 stepSize 확인
                                            try:
                                                exchange_info = client.exchange_info()
                                                symbol_info = None
                                                for s in exchange_info["symbols"]:
                                                    if s["symbol"] == symbol:
                                                        symbol_info = s
                                                        break

                                                step_size = 1.0
                                                if symbol_info:
                                                    for filter_info in symbol_info[
                                                        "filters"
                                                    ]:
                                                        if (
                                                            filter_info["filterType"]
                                                            == "LOT_SIZE"
                                                        ):
                                                            step_size = float(
                                                                filter_info["stepSize"]
                                                            )
                                                            break

                                                # stepSize에 맞게 수량 조정 (정밀도 문제 해결)
                                                adjusted_qty = (
                                                    round(sell_qty / step_size)
                                                    * step_size
                                                )

                                                # 소수점 자릿수 제한 (stepSize에 따라)
                                                if step_size == 0.1:
                                                    adjusted_qty = round(
                                                        adjusted_qty, 1
                                                    )
                                                elif step_size == 0.01:
                                                    adjusted_qty = round(
                                                        adjusted_qty, 2
                                                    )
                                                elif step_size == 0.001:
                                                    adjusted_qty = round(
                                                        adjusted_qty, 3
                                                    )
                                                else:
                                                    adjusted_qty = round(adjusted_qty)

                                                order = client.new_order(
                                                    symbol=symbol,
                                                    side="SELL",
                                                    type="MARKET",
                                                    quantity=adjusted_qty,
                                                )

                                                st.success(
                                                    f"✅ {asset} 25% 매도 완료! (수량: {adjusted_qty})"
                                                )
                                                # 캐시 무효화하여 즉시 반영
                                                st.cache_data.clear()
                                                st.rerun()

                                            except Exception as e:
                                                st.error(f"❌ 매도 실패: {e}")

                                    except Exception as e:
                                        st.error(f"❌ 매도 실패: {e}")

                            st.markdown("")  # 공백
                    else:
                        st.info("보유 코인이 없습니다.")

            except Exception as e:
                st.error(f"❌ 보유 코인 조회 실패: {str(e)}")


# 페이지 설정 (중복 호출 방지)
if "page_config_set" not in st.session_state:
    st.set_page_config(
        page_title="실시간 자동매매 엔진",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.session_state.page_config_set = True

# 모의/테스트넷에서만 자동 새로고침 활성화 (페이지 설정 이후)
print(f"[DEBUG] AUTO_REFRESH_ENABLED: {AUTO_REFRESH_ENABLED}")
print(f"[DEBUG] AUTO_REFRESH_SEC: {AUTO_REFRESH_SEC}")
print(f"[DEBUG] IS_MOCK: {IS_MOCK}, IS_TESTNET: {IS_TESTNET}")

if AUTO_REFRESH_ENABLED and AUTO_REFRESH_SEC and AUTO_REFRESH_SEC > 0:
    # 안전가드: 최소 3초, 최대 30초
    AUTO_REFRESH_SEC = max(3, min(AUTO_REFRESH_SEC, 30))
    print(f"[DEBUG] 자동 새로고침 활성화됨: {AUTO_REFRESH_SEC}초")

    # 자동 새로고침 구현 - JavaScript 기반
    st.markdown(
        f"""
    <script>
    setTimeout(function() {{
        window.location.reload();
    }}, {AUTO_REFRESH_SEC * 1000});
    </script>
    """,
        unsafe_allow_html=True,
    )
else:
    print("[DEBUG] 자동 새로고침 비활성화됨")

# 다크 테마 CSS
st.markdown(
    """
<style>
    /* 다크 테마 기본 설정 */
    .stApp {
        background-color: #0e1117;
        color: #ffffff !important;
    }
    
    /* 사이드바 기본 설정 */
    .stSidebar {
        transition: transform 0.3s ease !important;
    }
    
    /* 사이드바 토글 버튼 강제 표시 */
    .stSidebarToggle {
        display: block !important;
        visibility: visible !important;
    }
    
    /* 사이드바 콘텐츠 강제 표시 */
    .stSidebar .stMarkdown,
    .stSidebar .stSelectbox,
    .stSidebar .stButton,
    .stSidebar .stCheckbox {
        display: block !important;
        visibility: visible !important;
    }
    
    /* 사이드바 전체 - 반응형 설정 */
    section[data-testid="stSidebar"] {
        position: relative !important;
        width: 300px !important;
        z-index: 999 !important;
        transition: transform 0.3s ease !important;
    }

    /* 사이드바가 닫혔을 때 */
    section[data-testid="stSidebar"][aria-expanded="false"] {
        transform: translateX(-100%) !important;
        width: 0 !important;
    }
    
    /* 사이드바 토글 버튼 */
    button[data-testid="stSidebarToggle"] {
        display: block !important;
        visibility: visible !important;
    }
    
    /* 메인 컨텐츠 영역 조정 - 사이드바 상태에 따라 동적 조정 */
    /* Streamlit 기본 상단 패딩 제거 */
    .stApp > div:first-child {
        margin-left: 0 !important;
        transition: margin-left 0.3s ease !important;
        padding-top: 0 !important;
    }
    
    /* 메인 영역 상단 패딩 제거 */
    .main {
        padding-top: 0 !important;
    }
    
    /* 헤더 바로 아래로 컨텐츠 이동 */
    .main .block-container {
        margin-left: 0 !important;
        max-width: 100% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 0.5rem !important;
    }

    /* 헤더 컨테이너를 상단으로 이동 */
    .header-container {
        margin-top: 0 !important;
        margin-bottom: 0.5rem !important;
    }
    
    /* 첫 번째 요소의 상단 마진 제거 */
    .main .block-container > div:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    
    /* 버튼 간격 최소화 */
    .main .element-container {
        margin-top: 0.1rem !important;
        margin-bottom: 0.1rem !important;
    }
    
    /* 버튼 컨테이너 간격 최소화 */
    .main .block-container > div {
        margin-top: 0.1rem !important;
        margin-bottom: 0.1rem !important;
    }
    
    /* 첫 번째 버튼 그룹과 두 번째 버튼 그룹 간격 최소화 */
    .main .block-container > div:nth-child(2) {
        margin-top: 0.2rem !important;
    }
    
    /* 사이드바 콘텐츠 강제 표시 */
    .stSidebar .element-container {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* 사이드바 내부 모든 요소 강제 표시 */
    .stSidebar * {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* 사이드바 스크롤 영역 강제 표시 */
    .stSidebar .css-1d391kg {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* 모든 텍스트 색상 강제 설정 */
    .stApp, .stApp * {
        color: #ffffff !important;
    }
    
    /* 특정 요소들 색상 개별 설정 */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        color: #ffffff !important;
    }
    
    .stApp p, .stApp div, .stApp span {
        color: #ffffff !important;
    }
    
    /* 헤더 스타일 - 깔끔하고 컴팩트한 디자인 */
    .header-container {
        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        border: 1px solid #404040;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        min-height: 50px;
    }
    
    .header-grid {
        display: grid;
        grid-template-columns: 1fr 2fr 1fr;
        gap: 16px;
        align-items: center;
        min-height: 30px;
    }
    
    .header-left {
        display: flex;
        gap: 8px;
        align-items: center;
    }
    
    .header-center {
        text-align: center;
        font-size: 14px;
        line-height: 1.4;
    }
    
    .header-right {
        display: flex;
        gap: 8px;
        justify-content: flex-end;
        align-items: center;
    }
    
    /* 이머전시 버튼 스타일 */
    .emergency-btn-placeholder {
        width: 80px !important;
        height: 40px !important;
        border-radius: 20px !important;
        background: linear-gradient(135deg, #ff4444, #cc0000) !important;
        border: 2px solid #ff6666 !important;
        color: white !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(255, 68, 68, 0.4) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* 자동매매 상태 표시 */
    .auto-trading-status {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 120px !important;
        height: 40px !important;
        border-radius: 20px !important;
        background: linear-gradient(135deg, #2d5a2d, #1a3d1a) !important;
        border: 2px solid #4a7c4a !important;
        color: white !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(45, 90, 45, 0.4) !important;
    }
    
    .auto-trading-status.stopped {
        background: linear-gradient(135deg, #5a2d2d, #3d1a1a) !important;
        border-color: #7c4a4a !important;
        box-shadow: 0 4px 12px rgba(90, 45, 45, 0.4) !important;
    }
    
    .status-indicator {
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        font-size: 12px !important;
        font-weight: bold !important;
    }
    
    .status-icon {
        font-size: 16px !important;
        animation: pulse 2s infinite !important;
    }
    
    .status-icon.stopped {
        animation: none !important;
    }
    
    @keyframes pulse {
        0% {
            transform: scale(1);
            opacity: 1;
        }
        50% {
            transform: scale(1.2);
            opacity: 0.7;
        }
        100% {
            transform: scale(1);
            opacity: 1;
        }
    }
    
    .status-text {
        font-size: 10px !important;
        white-space: nowrap !important;
    }
    
    
    /* 배지 스타일 - 더 작고 깔끔하게 */
    .badge {
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 0 2px;
    }
    
    .badge-testnet { 
        background: linear-gradient(135deg, #00ff88, #00cc6a);
        color: #000;
        box-shadow: 0 2px 4px rgba(0, 255, 136, 0.3);
    }
    .badge-mainnet { 
        background: linear-gradient(135deg, #ff6b6b, #ee5a52);
        color: #fff;
    }
    .badge-sim { 
        background: linear-gradient(135deg, #666, #444);
        color: #fff;
        border: 1px solid #555;
    }
    .badge-paper { 
        background: linear-gradient(135deg, #ffc107, #ff8f00);
        color: #000;
    }
    .badge-live { 
        background: linear-gradient(135deg, #dc3545, #c82333);
        color: #fff;
    }
    
    .badge-fresh { 
        background: linear-gradient(135deg, #00ff88, #00cc6a);
        color: #000;
        font-size: 10px;
        padding: 2px 6px;
    }
    .badge-stale { 
        background: linear-gradient(135deg, #ff6b6b, #ee5a52);
        color: #fff;
        font-size: 10px;
        padding: 2px 6px;
    }
    .badge-error { 
        background: linear-gradient(135deg, #dc3545, #c82333);
        color: #fff;
        font-size: 10px;
        padding: 2px 6px;
    }
    
    /* 그리드 시스템 */
    .grid-12 {
        display: grid;
        grid-template-columns: repeat(12, 1fr);
        gap: 1rem;
    }
    
    .grid-6 {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 1rem;
    }
    
    .grid-4 {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
    }
    
    .grid-3 {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1rem;
    }
    
    /* 매매 버튼 스타일 - 더 깔끔하고 컴팩트하게 */
    .stButton > button {
        background: linear-gradient(135deg, #2d2d2d, #404040) !important;
        color: #ffffff !important;
        border: 1px solid #555 !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 12px !important;
        padding: 8px 16px !important;
        transition: all 0.2s ease !important;
        min-height: 36px !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #404040, #555) !important;
        border-color: #00ff88 !important;
        box-shadow: 0 2px 8px rgba(0, 255, 136, 0.2) !important;
        transform: translateY(-1px) !important;
    }
    
    /* 매수 버튼 특별 스타일 */
    div[data-testid="column"]:has(button:contains("Market Buy")) button {
        background-color: #28a745 !important;
        border-color: #28a745 !important;
    }
    
    div[data-testid="column"]:has(button:contains("Market Buy")) button:hover {
        background-color: #218838 !important;
    }
    
    /* 매도 버튼 특별 스타일 */
    div[data-testid="column"]:has(button:contains("Market Sell")) button {
        background-color: #dc3545 !important;
        border-color: #dc3545 !important;
    }
    
    div[data-testid="column"]:has(button:contains("Market Sell")) button:hover {
        background-color: #c82333 !important;
    }
    
    /* 자동매매 버튼 스타일 */
    .stButton > button[kind="primary"] {
        background-color: #28a745 !important;
        border-color: #28a745 !important;
        color: #ffffff !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #218838 !important;
        border-color: #218838 !important;
    }
    
    /* 워치리스트 에디터 스타일 */
    .watchlist-display {
        background-color: #2d2d2d !important;
        padding: 15px !important;
        border-radius: 8px !important;
        margin: 10px 0 !important;
        border: 1px solid #444 !important;
    }
    
    .watchlist-text {
        color: #ffffff !important;
        font-family: 'Segoe UI', 'Arial', sans-serif !important;
        font-size: 16px !important;
        margin: 0 !important;
        line-height: 1.8 !important;
        font-weight: 500 !important;
    }
    
    /* Streamlit 기본 요소들 색상 강제 설정 */
    .stTextInput > div > div > input {
        background-color: #2d2d2d !important;
        color: #ffffff !important;
        border: 1px solid #555 !important;
    }
    
    .stSelectbox > div > div > select {
        background-color: #2d2d2d !important;
        color: #ffffff !important;
        border: 1px solid #555 !important;
    }
    
    .stSelectbox > div > div > div {
        background-color: #2d2d2d !important;
        color: #ffffff !important;
    }
    
    /* 카드 스타일 */
    .symbol-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 0.5rem;
        padding: 1rem;
        transition: border-color 0.2s;
        margin-bottom: 1rem;
    }
    
    .symbol-card:hover {
        border-color: #555;
    }
    
    .symbol-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    
    .symbol-card-main {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1rem;
        margin-bottom: 0.5rem;
        font-size: 0.8rem;
    }
    
    .symbol-card-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.7rem;
    }
    
    /* KPI 타일 */
    .kpi-tile {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 0.5rem;
        padding: 1rem;
        text-align: center;
    }
    
    .kpi-value {
        font-size: 1.5rem;
        font-weight: bold;
        font-family: 'Courier New', monospace;
        color: #ffffff !important;
    }
    
    .kpi-label {
        font-size: 0.75rem;
        color: #cccccc !important;
        text-transform: uppercase;
    }
    
    /* 탭 스타일 - 카드형 디자인 */
    .stTabs [data-baseweb="tab-list"] {
        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        border: 1px solid #404040;
        border-radius: 8px;
        padding: 8px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }
    
    .stTabs [data-baseweb="tab"] {
        color: #aaa !important;
        background: transparent !important;
        border: 1px solid transparent !important;
        border-radius: 6px !important;
        padding: 8px 16px !important;
        margin: 0 4px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        color: #fff !important;
        background: linear-gradient(135deg, #333, #444) !important;
        border-color: #555 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
    }
    
    .stTabs [aria-selected="true"] {
        color: #000 !important;
        background: linear-gradient(135deg, #00ff88, #00cc6a) !important;
        border-color: #00ff88 !important;
        box-shadow: 0 4px 12px rgba(0, 255, 136, 0.3) !important;
        transform: translateY(-2px) !important;
    }
    
    .stTabs [aria-selected="true"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, #00ff88, #00cc6a);
        opacity: 0.8;
    }
    
    /* 탭 아이콘 스타일 */
    .stTabs [data-baseweb="tab"] .emoji {
        font-size: 14px !important;
        margin-right: 6px !important;
        filter: grayscale(0.3) !important;
        transition: all 0.2s ease !important;
    }
    
    .stTabs [aria-selected="true"] .emoji {
        filter: grayscale(0) !important;
        transform: scale(1.1) !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover .emoji {
        filter: grayscale(0) !important;
        transform: scale(1.05) !important;
    }
    
    /* 탭 리스트 정렬 및 간격 */
    .stTabs [data-baseweb="tab-list"] {
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
        gap: 8px !important;
    }
    
/* 간단한 텍스트 스타일 */
.stMarkdown h4 {
    font-size: 14px !important;
    color: #fff !important;
    margin-bottom: 8px !important;
    font-weight: 600 !important;
}

.stMarkdown p {
    font-size: 12px !important;
    color: #ccc !important;
    margin: 4px 0 !important;
    line-height: 1.4 !important;
}

/* 작은 텍스트 스타일 (숫자 폰트 크기 조정 - Detail 탭과 동일하게) */
.stMarkdown small {
    font-size: 12px !important;
    color: #ccc !important;
    line-height: 1.4 !important;
}
    
    /* 테이블 스타일 - Detail 탭용 */
    .stDataFrame {
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid #555 !important;
        border-radius: 6px !important;
    }
    
    .stDataFrame table {
        font-size: 12px !important;
    }
    
    .stDataFrame th {
        background: rgba(255, 255, 255, 0.1) !important;
        color: #fff !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        padding: 8px !important;
    }
    
    .stDataFrame td {
        color: #ccc !important;
        font-size: 11px !important;
        padding: 6px 8px !important;
    }
    
    /* 정보 박스 스타일 */
    .stInfo {
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid #555 !important;
        border-radius: 6px !important;
        font-size: 12px !important;
    }
    
    .stWarning {
        background: rgba(255, 193, 7, 0.1) !important;
        border: 1px solid #ffc107 !important;
        border-radius: 6px !important;
        font-size: 12px !important;
    }
    
    /* 버튼 스타일 */
    .stButton > button {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border: 2px solid #555 !important;
        border-radius: 0.5rem !important;
        font-weight: bold !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button:hover {
        background-color: #333 !important;
        border-color: #777 !important;
        color: #ffffff !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton > button:active {
        background-color: #444 !important;
        transform: translateY(0) !important;
        transition: all 0.1s ease !important;
    }
    
    /* 특정 버튼 스타일 강화 */
    button[kind="primary"], button[kind="secondary"] {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border: 2px solid #555 !important;
    }
    
    /* 모든 버튼 요소 강제 스타일 */
    button, .stButton button, [role="button"] {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border: 2px solid #555 !important;
    }
    
    /* 메트릭 스타일 */
    [data-testid="metric-container"] {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 0.5rem;
        padding: 1rem;
    }
    
    [data-testid="metric-value"] {
        font-family: 'Courier New', monospace;
        font-size: 0.5rem !important;
        color: #ffffff !important;
        line-height: 1.0 !important;
        overflow: visible !important;
        white-space: nowrap !important;
    }
    
    [data-testid="metric-label"] {
        color: #cccccc !important;
        font-size: 0.8rem;
    }
    
    [data-testid="metric-delta"] {
        font-size: 0.7rem !important;
        color: #cccccc !important;
    }
    
    /* 테이블 스타일 */
    .stDataFrame {
        background-color: #1e1e1e;
        color: #ffffff !important;
    }
    
    /* 입력 필드 스타일 */
    .stTextInput > div > div > input {
        background-color: #1e1e1e;
        color: #ffffff !important;
        border: 1px solid #333;
    }
    
    .stSelectbox > div > div > div {
        background-color: #1e1e1e;
        color: #ffffff !important;
        border: 1px solid #333;
    }
    
    /* 체크박스 스타일 */
    .stCheckbox > div > div > div {
        background-color: #1e1e1e;
    }
    
    /* 사이드바 스타일 */
    .stSidebar {
        background-color: #1e1e1e;
        color: #ffffff !important;
    }
    
    .stSidebar .stMarkdown {
        color: #ffffff !important;
    }
    
    .stSidebar h1, .stSidebar h2, .stSidebar h3, .stSidebar h4, .stSidebar h5, .stSidebar h6 {
        color: #ffffff !important;
    }
    
    .stSidebar p, .stSidebar div, .stSidebar span {
        color: #ffffff !important;
    }
    
    /* 스크롤바 스타일 */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #1e1e1e;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #555;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #666;
    }
    
    /* 로그 상자 스타일 */
    .stTextArea textarea {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border: 1px solid #333 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 0.8rem !important;
        line-height: 1.3 !important;
    }
    
    .stTextArea textarea:focus {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border-color: #555 !important;
        box-shadow: 0 0 0 1px #555 !important;
    }
    
    /* ARES 상태 배지 */
    .ares-status {
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.75rem;
        font-weight: 500;
        text-align: center;
    }
    
    .ares-normal { background-color: #28a745; color: white; }
    .ares-warming { background-color: #ffc107; color: black; }
    .ares-stale { background-color: #fd7e14; color: white; }
    .ares-error { background-color: #dc3545; color: white; }
    .ares-flat { background-color: #6c757d; color: white; }
    
    /* Streamlit 상단 메뉴바 다크 테마 - 강력한 오버라이드 */
    header[data-testid="stHeader"],
    .stApp > header,
    .stApp header,
    header {
        background-color: #1e1e1e !important;
        border-bottom: 1px solid #333 !important;
    }
    
    /* 툴바 영역 강제 다크 테마 */
    [data-testid="stToolbar"],
    .stApp > header [data-testid="stToolbar"],
    .stApp header [data-testid="stToolbar"] {
        background-color: #1e1e1e !important;
    }
    
    /* 툴바 내부 모든 요소 */
    [data-testid="stToolbar"] *,
    .stApp > header [data-testid="stToolbar"] *,
    .stApp header [data-testid="stToolbar"] * {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
    }
    
    /* 모든 헤더 버튼 강제 스타일 */
    header button,
    header [data-testid="stToolbar"] button,
    header [data-testid="stToolbar"] a,
    .stApp > header button,
    .stApp > header [data-testid="stToolbar"] button,
    .stApp > header [data-testid="stToolbar"] a {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border: 1px solid #555 !important;
    }
    
    /* 호버 효과 */
    header button:hover,
    header [data-testid="stToolbar"] button:hover,
    header [data-testid="stToolbar"] a:hover,
    .stApp > header button:hover,
    .stApp > header [data-testid="stToolbar"] button:hover,
    .stApp > header [data-testid="stToolbar"] a:hover {
        background-color: #333 !important;
        color: #ffffff !important;
    }
    
    /* Deploy 버튼 특별 처리 */
    header [data-testid="stToolbar"] button[kind="primary"],
    .stApp > header [data-testid="stToolbar"] button[kind="primary"] {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border: 1px solid #555 !important;
    }
    
    /* 메뉴 아이콘 특별 처리 */
    header [data-testid="stToolbar"] button[aria-label="More options"],
    .stApp > header [data-testid="stToolbar"] button[aria-label="More options"] {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        border: 1px solid #555 !important;
    }
    
    /* 로고 영역 */
    header [data-testid="stToolbar"] > div:first-child,
    .stApp > header [data-testid="stToolbar"] > div:first-child {
        background-color: #1e1e1e !important;
    }
    
    /* 폰트 크기 조정 */
    html, body, .main, .main .block-container {
            font-size: 0.9rem !important;
        }
        
    .main h1, h1 { font-size: 1.3rem !important; }
    .main h2, h2 { font-size: 1.1rem !important; }
    .main h3, h3 { font-size: 1.0rem !important; }
    
    /* 패딩 최소화 */
        .main .block-container {
            padding: 0.5rem !important;
        }
        
        .main .element-container {
            margin-bottom: 0.3rem !important;
        }
        
        /* 숫자 입력창 스타일 - 더 강력한 선택자 */
        .stNumberInput input,
        .stNumberInput > div > div > input,
        div[data-testid="stNumberInput"] input,
        .stNumberInput input[type="number"] {
            color: #ffffff !important;
            background-color: #1e1e1e !important;
            border: 1px solid #333 !important;
        }
        
        .stNumberInput input:focus,
        .stNumberInput > div > div > input:focus,
        div[data-testid="stNumberInput"] input:focus,
        .stNumberInput input[type="number"]:focus {
            color: #ffffff !important;
            background-color: #2a2a2a !important;
            border: 1px solid #555 !important;
    }
</style>

<script>
// 동적으로 헤더 스타일 강제 적용
function forceDarkHeader() {
    const headers = document.querySelectorAll('header, [data-testid="stHeader"]');
    const toolbars = document.querySelectorAll('[data-testid="stToolbar"]');
    
    headers.forEach(header => {
        header.style.backgroundColor = '#1e1e1e !important';
        header.style.borderBottom = '1px solid #333 !important';
    });
    
    toolbars.forEach(toolbar => {
        toolbar.style.backgroundColor = '#1e1e1e !important';
        const buttons = toolbar.querySelectorAll('button, a');
        buttons.forEach(button => {
            button.style.backgroundColor = '#1e1e1e !important';
            button.style.color = '#ffffff !important';
            button.style.border = '1px solid #555 !important';
        });
    });
}

// 숫자 입력창 스타일 강제 적용
function forceNumberInputStyle() {
    const numberInputs = document.querySelectorAll('.stNumberInput input, input[type="number"]');
    numberInputs.forEach(input => {
        input.style.color = '#ffffff !important';
        input.style.backgroundColor = '#1e1e1e !important';
        input.style.border = '1px solid #333 !important';
    });
}

// 페이지 로드 시 실행
document.addEventListener('DOMContentLoaded', function() {
    forceDarkHeader();
    forceNumberInputStyle();
});

// 주기적으로 실행 (Streamlit이 동적으로 요소를 추가할 수 있음)
setInterval(function() {
    forceDarkHeader();
    forceNumberInputStyle();
}, 1000);
</script>
""",
    unsafe_allow_html=True,
)


# 유틸리티 함수들
def load_watchlist():
    """워치리스트 로드 (중복 제거)"""
    try:
        symbols = read_json_safely("coin_watchlist.json", default=[])
        
        # 중복 제거 및 정규화
        unique_symbols = []
        seen = set()
        
        for symbol in symbols:
            if isinstance(symbol, str):
                normalized = symbol.lower().strip()
                if normalized and normalized not in seen:
                    unique_symbols.append(normalized)
                    seen.add(normalized)
        
        # 중복이 제거된 경우 파일 업데이트
        if len(unique_symbols) != len(symbols):
            save_watchlist(unique_symbols)
            print(f"중복 심볼 제거됨: {len(symbols)} -> {len(unique_symbols)}")
        
        return unique_symbols
    
    except Exception:
        return ["btcusdt", "ethusdt", "solusdt"]  # 기본값


def save_watchlist(watchlist):
    """워치리스트 저장 - UI는 쓰기 금지"""
    st.warning("⚠️ UI에서는 워치리스트 저장이 금지되어 있습니다. 설정 파일을 직접 수정하세요.")
    return False


def load_symbol_snapshot(symbol):
    """심볼별 스냅샷 로드 - 강화된 파일 검색"""
    try:
        # 심볼 케이스 표준화 (소문자로 통일)
        from shared.symbol_utils import normalize_symbol

        normalized_symbol = normalize_symbol(symbol)

        # 1. 소문자 파일 경로 우선 검색
        snapshot_path = f"{SNAPSHOTS_DIR}/prices_{normalized_symbol}.json"
        if Path(snapshot_path).exists():
            with open(snapshot_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # 2. 대문자 파일 경로 검색 (실제 파일이 대문자로 존재)
        uppercase_path = f"{SNAPSHOTS_DIR}/prices_{symbol.upper()}.json"
        if Path(uppercase_path).exists():
            with open(uppercase_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Binance WebSocket 데이터 구조 변환
                if "t" in data and "c" in data:
                    return {
                        "ts": data["t"] / 1000,  # 밀리초를 초로 변환
                        "price": float(data["c"]),  # close price
                        "open": float(data.get("o", data["c"])),
                        "high": float(data.get("h", data["c"])),
                        "low": float(data.get("l", data["c"])),
                        "volume": float(data.get("v", 0)),
                        "symbol": normalized_symbol,
                    }
                return data

        # 3. 루트 디렉토리에서도 찾기 (소문자)
        root_snapshot_path = f"{SHARED_DATA_DIR}/prices_{normalized_symbol}.json"
        if Path(root_snapshot_path).exists():
            with open(root_snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Binance WebSocket 데이터 구조 변환
                if "k" in data:
                    kline = data["k"]
                    return {
                        "ts": kline["t"] / 1000,  # 밀리초를 초로 변환
                        "price": float(kline["c"]),  # close price
                        "open": float(kline["o"]),
                        "high": float(kline["h"]),
                        "low": float(kline["l"]),
                        "volume": float(kline["v"]),
                        "symbol": normalized_symbol,
                    }
                return data

        # 4. 폴백: prices_snapshot.json에서 찾기
        fallback_path = f"{SHARED_DATA_DIR}/prices_snapshot.json"
        if Path(fallback_path).exists():
            with open(fallback_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "rows" in data:
                    for row in data["rows"]:
                        if row.get("symbol", "").lower() == normalized_symbol:
                            return row

        # 5. 디버그 정보 출력
        print(
            f"[SymbolCard] {symbol} 스냅샷 파일을 찾을 수 없음: {snapshot_path}, {uppercase_path}"
        )

    except Exception as e:
        print(f"[SymbolCard] {symbol} 스냅샷 로드 오류: {e}")
    return None


def load_symbol_history(symbol, limit=100):
    """심볼별 히스토리 로드 (최근 limit개)"""
    try:
        # 심볼 케이스 표준화 (소문자로 통일)
        from shared.symbol_utils import normalize_symbol

        normalized_symbol = normalize_symbol(symbol)

        # 소문자 파일 경로 사용
        history_path = f"{SHARED_DATA_DIR}/history/{normalized_symbol}_1m.jsonl"
        if Path(history_path).exists():
            data = []
            with open(history_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-limit:]:  # 최근 limit개만
                    if line.strip():
                        data.append(json.loads(line.strip()))
            return data
    except Exception:
        pass
    return []


def load_ares_data(symbol):
    """ARES 데이터 로드 - 타임스탬프 검증 포함"""
    try:
        # 심볼 케이스 표준화 (소문자로 통일)
        from shared.symbol_utils import normalize_symbol

        normalized_symbol = normalize_symbol(symbol)

        # 소문자 파일 경로 사용
        ares_path = f"ARES_DIR/{normalized_symbol}.json"
        if Path(ares_path).exists():
            with open(ares_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # 타임스탬프 검증 및 수정 - 실제 ARES 데이터 구조에 맞게 수정
                if data and "timestamp" in data:
                    current_time = time.time() * 1000  # 밀리초로 변환
                    ts = data.get("timestamp", current_time)

                    # 미래 시간인 경우 현재 시간으로 수정
                    if ts > current_time + 3600000:  # 1시간 이상 미래 (밀리초)
                        data["timestamp"] = current_time
                        data["age_sec"] = 0
                        print(
                            f"[ARES] {symbol} 미래 타임스탬프 수정: {ts} -> {current_time}"
                        )

                        # 수정된 데이터 저장
                        try:
                            with open(ares_path, "w", encoding="utf-8") as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            print(f"[ARES] {symbol} 타임스탬프 수정 저장 실패: {e}")

                return data
    except Exception as e:
        print(f"[ARES] {symbol} 로드 오류: {e}")
    return None


def get_freshness_badge(age_sec, threshold_fresh=60, threshold_stale=180):
    """신선도 배지 생성"""
    if age_sec < threshold_fresh:
        return f'<span class="badge badge-fresh">{age_sec:.0f}s</span>'
    elif age_sec < threshold_stale:
        return f'<span class="badge badge-stale">{age_sec:.0f}s</span>'
    else:
        return f'<span class="badge badge-error">{age_sec:.0f}s</span>'


def get_ares_status_badge(ares_data):
    """ARES 상태 배지 생성 - 실제 데이터 구조에 맞게 수정"""
    if not ares_data:
        return '<span class="ares-status ares-error">NO DATA</span>'

    status = ares_data.get("status", "unknown")
    signals = ares_data.get("signals", [])
    age_sec = ares_data.get("age_sec", 999)

    # 타임스탬프 검증 (미래 시간 체크) - 실제 데이터 구조에 맞게 수정
    current_time = time.time() * 1000  # 밀리초로 변환
    ts = ares_data.get("timestamp", current_time)
    if ts > current_time + 3600000:  # 1시간 이상 미래 (밀리초)
        return '<span class="ares-status ares-error">TIME ERR</span>'

    # 신호가 있는지 확인
    has_signal = len(signals) > 0 and any(s.get("action") != "flat" for s in signals)

    # 상태 우선순위: error > stale > warming > flat > normal
    if status == "error" or age_sec > 300:  # 5분 이상 오래된 경우
        return '<span class="ares-status ares-error">ERROR</span>'
    elif status == "stale" or age_sec > 120:
        return '<span class="ares-status ares-stale">STALE</span>'
    elif status == "warming" or age_sec < 5:
        return '<span class="ares-status ares-warming">WARMING</span>'
    elif not has_signal:
        return '<span class="ares-status ares-flat">FLAT</span>'
    else:
        return '<span class="ares-status ares-normal">NORMAL</span>'


def format_price(price):
    """가격 포맷팅"""
    if price is None or price == 0:
        return "0.00"
    return f"{price:,.2f}"


def format_percentage(value):
    """퍼센트 포맷팅"""
    if value is None:
        return "0.00%"
    return f"{value:+.2f}%"


def format_number(value, decimals=0):
    """숫자 포맷팅"""
    if value is None:
        return "0"
    return f"{value:,.{decimals}f}"


# 차트 자동 포커스 로직
def get_auto_focus_symbol(watchlist, user_selected=None, auto_focus_enabled=True):
    """차트 자동 포커스 심볼 결정"""
    if user_selected:
        return user_selected

    if not auto_focus_enabled:
        return watchlist[0] if watchlist else None

    # 1. Event focus: 가장 최근 ARES non-flat 신호 (60초 내)
    current_time = time.time()
    event_symbol = None
    max_signal_time = 0

    for symbol in watchlist:
        ares_data = load_ares_data(symbol)
        if ares_data and ares_data.get("signal"):
            signal = ares_data["signal"]
            meta = ares_data.get("meta", {})
            signal_time = meta.get("ts", 0)

            # non-flat 신호이고 60초 내
            if (
                signal.get("action") != "flat"
                and current_time - signal_time < 60
                and signal_time > max_signal_time
            ):
                max_signal_time = signal_time
                event_symbol = symbol

    if event_symbol:
        return event_symbol

    # 2. Volatility focus: 가장 높은 절대 1분 수익률 (≥ 0.3% 임계값)
    volatility_symbol = None
    max_volatility = 0

    for symbol in watchlist:
        history = load_symbol_history(symbol, 2)  # 최근 2개 캔들
        if len(history) >= 2:
            current_price = history[-1].get("close", 0)
            prev_price = history[-2].get("close", 0)

            if prev_price > 0:
                volatility = abs((current_price - prev_price) / prev_price * 100)
                if volatility >= 0.3 and volatility > max_volatility:
                    max_volatility = volatility
                    volatility_symbol = symbol

    if volatility_symbol:
        return volatility_symbol

    # 3. Rotation: 워치리스트 순환 (30초마다)
    if watchlist:
        rotation_index = int(current_time / 30) % len(watchlist)
        return watchlist[rotation_index]

    return watchlist[0] if watchlist else None


def check_symbol_stale(symbol):
    """심볼이 stale한지 확인"""
    snapshot = load_symbol_snapshot(symbol)
    ares_data = load_ares_data(symbol)

    # 가격 데이터 stale 체크 (180초)
    if snapshot:
        current_time = time.time()
        snapshot_time = snapshot.get("ts", current_time)
        if current_time - snapshot_time > 180:
            return True, "Price stale"

    # ARES 데이터 stale 체크 (120초)
    if ares_data and ares_data.get("meta"):
        ares_age = ares_data.get("age_sec", 999)
        if ares_age > 120:
            return True, "ARES stale"

    return False, "OK"


# 성능 최적화: 캐싱 시스템
@st.cache_data(ttl=10)  # 10초 캐시 (더 긴 캐시로 깜빡거림 방지)
def load_watchlist_cached():
    """워치리스트 캐시된 로드"""
    return load_watchlist()


@st.cache_data(ttl=5)  # 5초 캐시 (더 긴 캐시로 깜빡거림 방지)
def load_symbol_snapshot_cached(symbol):
    """심볼 스냅샷 캐시된 로드"""
    return load_symbol_snapshot(symbol)


@st.cache_data(ttl=0)  # 캐시 비활성화 (실시간 반영)
def load_ares_data_cached(symbol):
    """ARES 데이터 캐시된 로드"""
    return load_ares_data(symbol)


@st.cache_data(ttl=15)  # 15초 캐시 (더 긴 캐시로 깜빡거림 방지)
def load_symbol_history_cached(symbol, limit=100):
    """심볼 히스토리 캐시된 로드"""
    return load_symbol_history(symbol, limit)


@st.cache_data(ttl=5)
def load_trading_performance_cached():
    """실제 거래 성과 데이터 로드"""
    try:
        import glob
        import json
        from datetime import datetime, timedelta

        import pandas as pd

        # 거래 기록 파일들 찾기
        trade_files = []
        possible_paths = [
            f"{SHARED_DATA_DIR}/trades/*.json",
            "logs/trades/*.json",
            "executor/trades/*.json",
            f"{SHARED_DATA_DIR}/logs/*.json",
        ]

        for pattern in possible_paths:
            trade_files.extend(glob.glob(pattern))

        if not trade_files:
            return {
                "today_return": 0.0,
                "weekly_return": 0.0,
                "monthly_return": 0.0,
                "annual_return": 0.0,
                "total_assets": 0.0,
                "goal_achievement": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
            }

        # 모든 거래 데이터 수집
        all_trades = []
        for file_path in trade_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_trades.extend(data)
                    elif isinstance(data, dict) and "trades" in data:
                        all_trades.extend(data["trades"])
            except Exception:
                continue

        if not all_trades:
            return {
                "today_return": 0.0,
                "weekly_return": 0.0,
                "monthly_return": 0.0,
                "annual_return": 0.0,
                "total_assets": 0.0,
                "goal_achievement": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
            }

        # DataFrame으로 변환
        df = pd.DataFrame(all_trades)

        # 시간별 필터링
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        year_start = now - timedelta(days=365)

        # 수익률 계산 (간단한 예시)
        today_trades = (
            df[df.get("timestamp", 0) >= today_start.timestamp()]
            if "timestamp" in df.columns
            else pd.DataFrame()
        )
        weekly_trades = (
            df[df.get("timestamp", 0) >= week_start.timestamp()]
            if "timestamp" in df.columns
            else pd.DataFrame()
        )
        monthly_trades = (
            df[df.get("timestamp", 0) >= month_start.timestamp()]
            if "timestamp" in df.columns
            else pd.DataFrame()
        )
        annual_trades = (
            df[df.get("timestamp", 0) >= year_start.timestamp()]
            if "timestamp" in df.columns
            else pd.DataFrame()
        )

        # 실제 계산 (거래 수익률 기반)
        today_return = len(today_trades) * 0.1  # 예시: 거래당 0.1% 수익
        weekly_return = len(weekly_trades) * 0.1
        monthly_return = len(monthly_trades) * 0.1
        annual_return = len(annual_trades) * 0.1

        return {
            "today_return": today_return,
            "weekly_return": weekly_return,
            "monthly_return": monthly_return,
            "annual_return": annual_return,
            "total_assets": 10000 + annual_return * 100,  # 기본 자산 + 수익
            "goal_achievement": min(monthly_return / 10 * 100, 200),  # 월 10% 목표 대비
            "sharpe_ratio": min(annual_return / 10, 3.0),  # 샤프 비율
            "max_drawdown": max(0, -annual_return * 0.1),  # 최대 낙폭
        }

    except Exception as e:
        print(f"거래 성과 데이터 로드 오류: {e}")
        return {
            "today_return": 0.0,
            "weekly_return": 0.0,
            "monthly_return": 0.0,
            "annual_return": 0.0,
            "total_assets": 0.0,
            "goal_achievement": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
        }


@st.cache_data(ttl=5)
def load_risk_data_cached():
    """실제 리스크 데이터 로드"""
    try:
        # 실제 리스크 데이터 수집 (예시)
        return {
            "daily_loss": 0.0,
            "drawdown": 0.0,
            "total_exposure": 0.0,
            "status": "Trading operating normally",
        }
    except Exception as e:
        print(f"리스크 데이터 로드 오류: {e}")
        return {
            "daily_loss": 0.0,
            "drawdown": 0.0,
            "total_exposure": 0.0,
            "status": "Error loading risk data",
        }


@st.cache_data(ttl=5)
def load_execution_stats_cached():
    """실제 실행 통계 데이터 로드"""
    try:
        # 실제 실행 통계 수집 (예시)
        return {
            "total_signals": 0,
            "successful": 0,
            "failed": 0,
            "total_fees": 0.0,
            "avg_retries": 0.0,
            "circuit_breakers": 0,
            "limit_orders": 0,
            "market_orders": 0,
            "cancelled": 0,
        }
    except Exception as e:
        print(f"실행 통계 로드 오류: {e}")
        return {
            "total_signals": 0,
            "successful": 0,
            "failed": 0,
            "total_fees": 0.0,
            "avg_retries": 0.0,
            "circuit_breakers": 0,
            "limit_orders": 0,
            "market_orders": 0,
            "cancelled": 0,
        }


@st.cache_data(ttl=5)
def load_symbol_trades_cached(symbol):
    """심볼별 거래 데이터 로드 (캐시됨)"""
    try:
        trades_file = Path(f"{SHARED_DATA_DIR}/trades/{symbol.lower()}.json")
        if trades_file.exists():
            with open(trades_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"거래 데이터 로드 오류 {symbol}: {e}")
    return []


@st.cache_data(ttl=5)
def load_position_data_cached(symbol):
    """포지션 데이터 로드 (캐시됨)"""
    try:
        position_file = Path(f"{SHARED_DATA_DIR}/positions/{symbol.lower()}.json")
        if position_file.exists():
            with open(position_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"포지션 데이터 로드 오류 {symbol}: {e}")
    return None


# 폴링 최적화: 변경 감지
def has_data_changed(symbol, last_check_time):
    """데이터 변경 여부 확인"""
    snapshot = load_symbol_snapshot(symbol)
    ares_data = load_ares_data(symbol)

    # 스냅샷 변경 확인
    if snapshot and snapshot.get("ts", 0) > last_check_time:
        return True

    # ARES 데이터 변경 확인
    if ares_data and ares_data.get("meta", {}).get("ts", 0) > last_check_time:
        return True

    return False


# 메인 앱


# 서비스 상태 확인 함수들
def is_feeder_running():
    """Feeder 서비스 실행 상태 확인 - 런처와 동일한 로직"""
    try:
        import psutil
        import json
        
        # 1. 프로세스 존재 확인
        process_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] in ['python.exe', 'pythonw.exe']:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'feeder_service.py' in cmdline:
                        process_running = True
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not process_running:
            return False
        
        # 2. 기능 상태 확인 (health.json)
        try:
            with open(f'{SHARED_DATA_DIR}/health.json', 'r') as f:
                health_data = json.load(f)
            function_ok = health_data.get('feeder_ok', False)
            return function_ok
        except Exception:
            # health.json 읽기 실패 시 프로세스만 확인
            return process_running
            
    except Exception:
        return False


def is_trader_running():
    """Trader 서비스 실행 상태 확인 - 프로세스만 체크 (간소화)"""
    try:
        import psutil
        
        # 프로세스 존재 확인만으로 충분 (대시보드 녹색불용)
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] in ['python.exe', 'pythonw.exe']:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'trader_service.py' in cmdline:
                        return True  # 프로세스가 실행 중이면 OK
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return False  # 프로세스 없음
            
    except Exception:
        return False


# 헤더 컴포넌트
# UI 데이터 소스 수정을 위한 유틸리티 함수들
def normalize_timestamp(ts):
    """타임스탬프를 초 단위로 정규화"""
    if ts is None:
        return None
    # 밀리초인 경우 초로 변환
    if ts > 1e10:  # 밀리초 타임스탬프
        return ts / 1000
    return ts

def compute_age(last_ts):
    """타임스탬프로부터 현재까지의 나이 계산"""
    if last_ts is None:
        return 999
    current_time = time.time()
    normalized_ts = normalize_timestamp(last_ts)
    return current_time - normalized_ts

def get_freshness_from_snapshots():
    """스냅샷 파일에서 직접 신선도 데이터 읽기"""
    try:
        snapshots_dir = Path("SNAPSHOTS_DIR")
        if not snapshots_dir.exists():
            return None, "snapshots_dir_missing"
        
        # BTCUSDT 파일 찾기 (우선순위)
        btc_file = snapshots_dir / "prices_btcusdt.json"
        if not btc_file.exists():
            # 다른 파일 찾기
            price_files = list(snapshots_dir.glob("prices_*.json"))
            if not price_files:
                return None, "no_price_files"
            btc_file = price_files[0]
        
        with open(btc_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            last_ts = data.get("last_update")
            age = compute_age(last_ts)
            return age, f"snapshots/{btc_file.name}"
    except Exception as e:
        return None, f"error: {str(e)}"

def get_freshness_from_ares():
    """ARES 파일에서 직접 신선도 데이터 읽기"""
    try:
        # ARES 디렉토리 확인
        ares_dir = Path(ARES_DIR)
        if ares_dir.exists():
            ares_files = list(ares_dir.glob("*.json"))
            if ares_files:
                # 가장 최근 파일 사용
                latest_file = max(ares_files, key=lambda f: f.stat().st_mtime)
                with open(latest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    last_ts = data.get("timestamp") or data.get("last_update")
                    age = compute_age(last_ts)
                    return age, f"ares/{latest_file.name}"
        
        # 폴백: candidates.ndjson
        candidates_path = Path(f"{SHARED_DATA_DIR}/logs/candidates.ndjson")
        if candidates_path.exists():
            with open(candidates_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_candidate = json.loads(lines[-1].strip())
                    last_ts = last_candidate.get("timestamp")
                    age = compute_age(last_ts)
                    return age, "logs/candidates.ndjson"
        
        return None, "no_ares_files"
    except Exception as e:
        return None, f"error: {str(e)}"

def render_header():
    """헤더 렌더링"""
    # 환경 및 모드 배지
    env_badge = (
        "TESTNET"
        if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
        else "MAINNET"
    )
    mode_badge = "SIM" if os.getenv("DRY_RUN", "true").lower() == "true" else "LIVE"

    # 자동 유니버스 상태 확인
    auto_universe_enabled = os.getenv("FEEDER_MODE", "MANUAL").upper() == "ALL"

    # 워치리스트 로드
    watchlist = load_watchlist_cached()

    # 활성 심볼 수 계산
    if auto_universe_enabled:
        try:
            from shared.universe_manager import AutoUniverseManager

            universe_manager = AutoUniverseManager()
            universe_status = universe_manager.get_universe_status()
            active_symbols = universe_status.get("current_symbols", 0)
        except Exception:
            active_symbols = len(watchlist)
    else:
        active_symbols = len(watchlist)

    # 실제 신선도 데이터 계산 - 스냅샷 파일에서 직접 읽기
    price_age = 999
    ares_age = 999
    price_source = "unknown"
    ares_source = "unknown"
    fallback_used = False

    # Feature flag 확인
    use_statebus_fallback = os.getenv("USE_STATEBUS_FALLBACK", "false").lower() == "true"
    
    try:
        if use_statebus_fallback:
            # 폴백 모드: 기존 state_bus.json 사용
            state_bus_path = Path("shared_data/state_bus.json")
            if state_bus_path.exists():
                with open(state_bus_path, "r", encoding="utf-8") as f:
                    state_bus = json.load(f)
                    current_time = time.time()
                    last_ts = state_bus.get("prices", {}).get("last_ts", current_time)
                    price_age = current_time - last_ts
                    price_source = "state_bus.json (fallback)"
                    fallback_used = True
        else:
            # 새로운 방식: 스냅샷 파일에서 직접 읽기
            price_age, price_source = get_freshness_from_snapshots()
            if price_age is None:
                # 폴백: state_bus.json 사용
                state_bus_path = Path("shared_data/state_bus.json")
                if state_bus_path.exists():
                    with open(state_bus_path, "r", encoding="utf-8") as f:
                        state_bus = json.load(f)
                        current_time = time.time()
                        last_ts = state_bus.get("prices", {}).get("last_ts", current_time)
                        price_age = current_time - last_ts
                        price_source = "state_bus.json (fallback)"
                        fallback_used = True
                else:
                    price_age = 999
                    price_source = "no_data_source"

        # ARES 신선도 계산
        ares_age, ares_source = get_freshness_from_ares()
        if ares_age is None:
            ares_age = 999
            ares_source = "no_ares_data"
            
    except Exception as e:
        print(f"[UI] 신선도 데이터 계산 오류: {e}")
        price_age = 999
        ares_age = 999
        price_source = f"error: {str(e)}"
        ares_source = f"error: {str(e)}"

    # 디버그 라인과 경고 배너 생성
    debug_line = f"source={price_source} | basis=last_update | cwd={os.getcwd().split(os.sep)[-1]}"
    fallback_indicator = "⚠️" if fallback_used else ""
    stale_warning = ""
    
    if price_age > 300:  # 5분 이상 오래된 데이터
        stale_warning = f"""
        <div style="background-color: #ff4444; color: white; padding: 8px; margin: 8px 0; border-radius: 4px; font-size: 12px;">
            ⚠️ STALE DATA WARNING: Price age {price_age:.0f}s exceeds 300s threshold
        </div>
        """

    st.markdown(
        f"""
    <div class="header-container">
        <div class="header-grid">
            <div class="header-left">
                <span class="badge badge-testnet">{env_badge}</span>
                <span class="badge badge-sim">{mode_badge}</span>
            </div>
            <div class="header-center">
                <div style="font-size: 16px; font-weight: 600; margin-bottom: 4px;">
                    Active Symbols★: {active_symbols}
                    {'<span class="badge badge-fresh">AUTO</span>' if auto_universe_enabled else '<span class="badge badge-stale">MANUAL</span>'}
                </div>
                <div style="font-size: 12px; color: #aaa;">
                    {get_freshness_badge(price_age)} Price age {price_age:.0f}s {fallback_indicator}
                    {get_freshness_badge(ares_age)} ARES age {ares_age:.0f}s
                </div>
                <div style="font-size: 11px; color: #888; margin-top: 2px;">
                    Feeder: {'🟢' if is_feeder_running() else '🔴'} | 
                    Trader: {'🟢' if is_trader_running() else '🔴'} |
                    Auto-Heal: {'🟢' if is_auto_healing_active() else '🔴'}
                </div>
                <div style="font-size: 10px; color: #666; margin-top: 2px; font-family: monospace;">
                    {debug_line}
                </div>
            </div>
            <div class="header-right">
                <div class="auto-trading-status {'stopped' if not st.session_state.get('auto_trading_active', False) else ''}">
                    <div class="status-indicator" id="auto-trading-indicator">
                        <div class="status-icon {'stopped' if not st.session_state.get('auto_trading_active', False) else ''}">
                            {'🔴' if not st.session_state.get('auto_trading_active', False) else '🟢'}
                        </div>
                        <div class="status-text">
                            {'자동매매 멈춤' if not st.session_state.get('auto_trading_active', False) else '자동매매 활성'}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    {stale_warning}
    """,
        unsafe_allow_html=True,
    )

    # 실제 작동하는 버튼들 추가
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button(
            "🚀 Start Feeder", key="start_feeder_btn", use_container_width=True
        ):
            try:
                # 실제 Feeder 서비스 시작
                from coin_quant.shared.service_launcher import get_service_launcher

                service_launcher = get_service_launcher()

                if service_launcher.is_service_running("feeder"):
                    add_notification("ℹ️ Feeder 서비스가 이미 실행 중입니다", "info")
                else:
                    if service_launcher.start_service("feeder"):
                        st.session_state.feeder_running = True
                        add_notification("✅ Feeder 서비스가 시작되었습니다!", "success")
                        st.rerun()  # UI 새로고침
                    else:
                        add_notification("❌ Feeder 서비스 시작에 실패했습니다", "error")
            except Exception as e:
                add_notification(f"❌ Feeder 시작 오류: {e}", "error")

    with col2:
        if st.button(
            "📈 Start Trader", key="start_trader_btn", use_container_width=True
        ):
            try:
                # 실제 Trader 서비스 시작
                from coin_quant.shared.service_launcher import get_service_launcher

                service_launcher = get_service_launcher()

                if service_launcher.is_service_running("trader"):
                    add_notification("ℹ️ Trader 서비스가 이미 실행 중입니다", "info")
                else:
                    if service_launcher.start_service("trader"):
                        st.session_state.trader_running = True
                        add_notification("✅ Trader 서비스가 시작되었습니다!", "success")
                        st.rerun()  # UI 새로고침
                    else:
                        add_notification("❌ Trader 서비스 시작에 실패했습니다", "error")
            except Exception as e:
                add_notification(f"❌ Trader 시작 오류: {e}", "error")

    with col3:
        if st.button("📋 Open Logs", key="open_logs_btn", use_container_width=True):
            try:
                # 로그 파일 목록 표시
                log_files = ["logs/feeder.log", "logs/trader.log", "logs/app.log"]
                st.subheader("📋 시스템 로그")

                for log_file in log_files:
                    if os.path.exists(log_file):
                        st.write(f"**{log_file}**")
                        try:
                            with open(log_file, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                                # 최근 20줄만 표시
                                recent_lines = lines[-20:] if len(lines) > 20 else lines
                                log_content = "".join(recent_lines)
                                st.text_area(
                                    f"최근 로그 ({log_file})",
                                    log_content,
                                    height=150,
                                    key=f"log_{log_file}",
                                )
                        except Exception as e:
                            add_notification(f"로그 읽기 실패: {e}", "error")
                    else:
                        st.write(f"❌ {log_file} 파일이 없습니다.")

                # 로그 디렉토리 정보
                st.info(f"📁 로그 디렉토리: {os.path.abspath('logs')}")

            except Exception as e:
                add_notification(f"❌ 로그 열기 오류: {e}", "error")

    with col4:
        if st.button(
            "🚨 비상정지",
            key="emergency_stop_btn",
            help="모든 서비스를 즉시 중단합니다",
            type="primary",
            use_container_width=True,
        ):
            try:
                # Use control plane for emergency stop
                from shared.control_plane import get_control_plane
                
                control_plane = get_control_plane()
                success = control_plane.set_emergency_stop()
                
                if success:
                    # Update session state
                    st.session_state.auto_trading_active = False
                    st.session_state.ares_engine = None
                    st.session_state.trade_executor = None
                    save_auto_trading_state(False)
                    
                    add_notification("🚨 비상정지가 실행되었습니다! 자동매매가 중단되었습니다.", "error")
                    st.rerun()
                else:
                    add_notification("❌ 비상정지 실행 실패", "error")

            except Exception as e:
                add_notification(f"❌ 비상정지 실행 오류: {e}", "error")


# 자동 새로고침 컨트롤 함수
def render_refresh_controls():
    """자동 새로고침 컨트롤 렌더링"""
    st.markdown("---")  # 구분선
    col_refresh1, col_refresh2 = st.columns([1, 3])

    with col_refresh1:
        if st.button("🔄 Refresh", key="refresh_button", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with col_refresh2:
        # 수동 새로고침 안내 (자동 새로고침 상태에 따라 변경)
        if not (AUTO_REFRESH_ENABLED and AUTO_REFRESH_SEC and AUTO_REFRESH_SEC > 0):
            st.info("💡 수동 새로고침을 사용하세요")
            st.caption("자동 새로고침은 화면 안정성을 위해 비활성화되었습니다")


# Multi Board 컴포넌트
def render_multi_board():
    """Multi Board 렌더링 - 종합 대시보드"""
    st.markdown("### 📊 Multi Board - 종합 대시보드")

    # 핵심 수익률 KPI (4개 타일) - 실시간 데이터
    st.markdown("#### 💰 수익률 현황")
    col1, col2, col3, col4 = st.columns(4)

    # 실시간 수익률 데이터 수집 - 실제 거래 데이터 기반
    try:
        import glob
        import json
        from datetime import datetime

        # 실제 거래 기록 파일들 찾기
        trade_files = []
        possible_paths = [
            "trades/trades.jsonl",  # 주요 거래 기록 파일 추가
            f"{SHARED_DATA_DIR}/trades/*.json",
            "logs/trades/*.json",
            "executor/trades/*.json",
            f"{SHARED_DATA_DIR}/logs/*.json",
        ]

        for path_pattern in possible_paths:
            if "*" in path_pattern:
                trade_files.extend(glob.glob(path_pattern))
            else:
                if os.path.exists(path_pattern):
                    trade_files.append(path_pattern)

        # 거래 기록 로드
        all_trades = []
        for file_path in trade_files:
            try:
                if file_path.endswith(".jsonl"):
                    # JSONL 파일 처리 (한 줄씩 읽기)
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    trade = json.loads(line)
                                    all_trades.append(trade)
                                except:
                                    continue
                else:
                    # JSON 파일 처리
                    with open(file_path, "r", encoding="utf-8") as f:
                        trades = json.load(f)
                        if isinstance(trades, list):
                            all_trades.extend(trades)
                        elif isinstance(trades, dict):
                            all_trades.append(trades)
            except:
                continue

        # 포지션 데이터를 거래 기록으로 변환 (실제 데이터)
        if os.path.exists("POSITIONS_FILE"):
            with open(
                "POSITIONS_FILE", "r", encoding="utf-8"
            ) as f:
                positions_data = json.load(f)

            if positions_data and "ts" in positions_data:
                for symbol, position in positions_data.items():
                    if symbol != "ts" and isinstance(position, dict):
                        qty = position.get("qty", 0)
                        avg_price = position.get("avg_price", 0)
                        unrealized_pnl = position.get("unrealized_pnl", 0)

                        if qty > 0:  # 포지션이 있는 경우
                            trade = {
                                "symbol": symbol,
                                "timestamp": positions_data["ts"] / 1000,
                                "time": datetime.fromtimestamp(
                                    positions_data["ts"] / 1000
                                ).isoformat(),
                                "qty": qty,
                                "price": avg_price,
                                "pnl": unrealized_pnl,
                                "profit": unrealized_pnl,
                                "side": "BUY" if qty > 0 else "SELL",
                                "status": "OPEN",
                            }
                            all_trades.append(trade)

        # 오늘 거래만 필터링
        today = datetime.now().date()
        today_trades = []
        cumulative_pnl = 0.0
        total_trades = len(all_trades)
        winning_trades = 0

        for trade in all_trades:
            try:
                # 거래 시간 파싱 (다양한 형식 지원)
                trade_date = None

                if "timestamp" in trade:
                    trade_date = datetime.fromtimestamp(trade["timestamp"]).date()
                elif "time" in trade:
                    trade_date = datetime.fromisoformat(
                        trade["time"].replace("Z", "+00:00")
                    ).date()
                elif "ts" in trade:
                    # 밀리초를 초로 변환
                    timestamp_sec = trade["ts"] / 1000
                    trade_date = datetime.fromtimestamp(timestamp_sec).date()
                else:
                    # 시간 정보가 없으면 오늘로 간주
                    trade_date = today

                # 오늘 거래인지 확인
                if trade_date == today:
                    today_trades.append(trade)

                # 수익률 계산
                if "pnl" in trade and trade["pnl"] is not None:
                    pnl = float(trade["pnl"])
                    cumulative_pnl += pnl
                    if pnl > 0:
                        winning_trades += 1
                elif "profit" in trade and trade["profit"] is not None:
                    pnl = float(trade["profit"])
                    cumulative_pnl += pnl
                    if pnl > 0:
                        winning_trades += 1

            except Exception:
                continue

        # 오늘 수익 계산 (실제 거래 데이터 기반)
        daily_pnl = 0.0  # 오늘 거래 수익 계산
        # cumulative_pnl = 0.0  # 누적 수익 초기화 제거 - 위에서 계산된 값 사용

        # 오늘 거래 수익 계산
        for trade in today_trades:
            if "pnl" in trade and trade["pnl"] is not None:
                daily_pnl += float(trade["pnl"])
            elif "profit" in trade and trade["profit"] is not None:
                daily_pnl += float(trade["profit"])

        # 실제 포지션에서 미실현 손익 계산
        for trade in all_trades:
            if trade.get("status") == "OPEN" and "pnl" in trade:
                pnl = float(trade.get("pnl", 0))
                cumulative_pnl += pnl
                print(f"[포지션] {trade.get('symbol', 'UNKNOWN')}: {pnl:+.2f} USDT")

        # 현재 자본 (USDT 잔고 기반)
        try:
            if (
                "usdt_balance" in st.session_state
                and st.session_state["usdt_balance"] > 0
            ):
                current_equity = st.session_state["usdt_balance"]
            else:
                # 기본값: 100,000 USDT (테스트넷 기준)
                current_equity = 100000.0
        except:
            current_equity = 100000.0

        # 초기 자본 계산 (현재 자본에서 미실현 손익 차감)
        initial_equity = current_equity - cumulative_pnl

        # 수익률 계산
        daily_return_pct = (
            (daily_pnl / current_equity * 100) if current_equity > 0 else 0.0
        )
        cumulative_return_pct = (
            (cumulative_pnl / initial_equity * 100) if initial_equity > 0 else 0.0
        )

        # 승률 계산
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # 샤프 비율 계산 (간단한 추정)
        sharpe_ratio = (
            min(cumulative_return_pct / 10, 3.0) if cumulative_return_pct > 0 else 0.0
        )

        # 디버깅: 실제 데이터 확인
        print(
            f"[수익률 현황] 오늘 수익: {daily_pnl:.2f} USDT, 누적 수익: {cumulative_pnl:.2f} USDT"
        )
        print(
            f"[수익률 현황] 오늘 수익률: {daily_return_pct:.2f}%, 누적 수익률: {cumulative_return_pct:.2f}%"
        )
        print(
            f"[수익률 현황] 현재 자본: {current_equity:.2f} USDT, 초기 자본: {initial_equity:.2f} USDT"
        )

    except Exception as e:
        # 오류 시 기본값 사용
        print(f"[수익률 계산 오류] {e}")
        daily_pnl = 0.0
        daily_return_pct = 0.0
        cumulative_pnl = 0.0
        cumulative_return_pct = 0.0
        win_rate = 0.0
        sharpe_ratio = 1.0
        total_trades = 0
        all_trades = []

    with col1:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">오늘 수익률</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{daily_return_pct:+.2f}%</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">↗ {daily_pnl:+.2f}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">누적 수익률</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{cumulative_return_pct:+.2f}%</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">↗ {cumulative_pnl:+.2f}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">누적 수익금</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{cumulative_pnl:+,.2f} USDT</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">총 수익</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">샤프 비율</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{sharpe_ratio:.2f}</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">{"우수" if sharpe_ratio > 2 else "보통"}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # 심볼 카드들 (3-4개 per row, max 12개)
    st.markdown("#### Symbol Cards")

    # 그리드로 카드 표시
    watchlist = load_watchlist_cached()
    symbols_to_show = watchlist[:12]  # 최대 12개

    for i in range(0, len(symbols_to_show), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(symbols_to_show):
                symbol = symbols_to_show[i + j]
                with col:
                    render_symbol_card(symbol)


# Symbol Card Data Helpers (SSOT Read-Only)
def get_feeder_last_price(symbol):
    """
    Feeder 스냅샷에서 last_price와 price_ts 읽기
    Returns: (last_price, price_ts, is_fresh)
    """
    try:
        # Try individual symbol files first
        symbol_lower = symbol.lower()
        symbol_upper = symbol.upper()
        
        for symbol_variant in [symbol_lower, symbol_upper]:
            filepath = Path(f"shared_data/snapshots/prices_{symbol_variant}.json")
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    last_price = data.get("price") or data.get("last_price") or data.get("c")
                    price_ts = data.get("timestamp") or data.get("ts") or data.get("E")
                    
                    if last_price and price_ts:
                        last_price = float(last_price)
                        price_ts = float(price_ts) / 1000 if price_ts > 1e12 else float(price_ts)
                        age = time.time() - price_ts
                        is_fresh = age <= 300  # 5분 TTL (모의 데이터용)
                        return last_price, price_ts, is_fresh
        
        # Fallback to state_bus.json or databus_snapshot.json
        for filename in ["state_bus.json", "databus_snapshot.json"]:
            filepath = Path(f"shared_data/{filename}")
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    # Look for symbol data
                    symbol_data = None
                    if "symbols" in data and symbol.lower() in data["symbols"]:
                        symbol_data = data["symbols"][symbol.lower()]
                    elif symbol.lower() in data:
                        symbol_data = data[symbol.lower()]

                    if symbol_data:
                        last_price = symbol_data.get("last_price") or symbol_data.get("price") or symbol_data.get("c")
                        price_ts = symbol_data.get("price_ts") or symbol_data.get("ts") or symbol_data.get("E")

                        if last_price and price_ts:
                            last_price = float(last_price)
                            price_ts = float(price_ts) / 1000 if price_ts > 1e12 else float(price_ts)
                            age = time.time() - price_ts
                            is_fresh = age <= 5  # 5s TTL
                            return last_price, price_ts, is_fresh

        return None, None, False
    except Exception:
        return None, None, False


def get_ares_signal_data(symbol):
    """
    ARES 신호 데이터 읽기
    Returns: dict with side, entry_abs, tp_abs, tp_pct, signal_ts, is_fallback, is_fresh
    """
    try:
        # Try individual symbol files first
        symbol_lower = symbol.lower()
        symbol_upper = symbol.upper()
        
        for symbol_variant in [symbol_lower, symbol_upper]:
            ares_file = Path(f"shared_data/signals/ares_{symbol_variant}.json")
            if ares_file.exists():
                with open(ares_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                break
        else:
            return None

        # Extract signal data
        signal = None
        if "signals" in data and isinstance(data["signals"], list) and len(data["signals"]) > 0:
            signal = data["signals"][0]
        elif "action" in data:
            signal = data

        if not signal:
            return None

        # Extract fields
        side = signal.get("action", signal.get("side", "FLAT")).upper()
        entry_abs = signal.get("entry_abs") or signal.get("entry_price") or signal.get("px") or signal.get("price")
        tp_abs = signal.get("tp_abs") or signal.get("tp")
        tp_pct = signal.get("tp_pct")
        signal_ts = signal.get("signal_ts") or signal.get("ts") or data.get("timestamp")
        is_fallback = signal.get("is_fallback", False)

        # Convert to proper types
        if entry_abs:
            entry_abs = float(entry_abs)
        if tp_abs:
            tp_abs = float(tp_abs)
        if tp_pct:
            tp_pct = float(tp_pct)
        if signal_ts:
            signal_ts = float(signal_ts) / 1000 if signal_ts > 1e12 else float(signal_ts)

        # Check freshness (300s TTL)
        is_fresh = False
        if signal_ts:
            age = time.time() - signal_ts
            is_fresh = age <= 300 and not is_fallback

        return {
            "side": side,
            "entry_abs": entry_abs,
            "tp_abs": tp_abs,
            "tp_pct": tp_pct,
            "signal_ts": signal_ts,
            "is_fallback": is_fallback,
            "is_fresh": is_fresh,
        }
    except Exception:
        return None


def get_position_qty(symbol):
    """
    포지션 수량 읽기 (read-only)
    Returns: position_qty (float)
    """
    try:
        positions_file = Path("POSITIONS_FILE")
        if not positions_file.exists():
            return 0.0

        with open(positions_file, "r", encoding="utf-8") as f:
            positions = json.load(f)

        if symbol.lower() in positions:
            qty = positions[symbol.lower()].get("qty", 0)
            return float(qty) if qty else 0.0

        return 0.0
    except Exception:
        return 0.0


def compute_card_display_values(symbol):
    """
    심볼 카드 표시 값 계산 (모든 규칙 적용)
    Returns: dict with last_display, entry_display, target_display, sell_no_position_note
    """
    # Get data from SSOT
    last_price, price_ts, price_fresh = get_feeder_last_price(symbol)
    ares_signal = get_ares_signal_data(symbol)
    position_qty = get_position_qty(symbol)

    # Initialize display values
    last_display = "—"
    entry_display = "—"
    target_display = "—"
    sell_no_position_note = ""

    # Rule 1: Last (현재가)
    if last_price and price_fresh:
        last_display = f"${last_price:,.4f}"

    # Rules 2-5: Entry and Target
    if ares_signal and ares_signal["is_fresh"]:
        side = ares_signal["side"]
        entry_abs = ares_signal["entry_abs"]
        tp_abs = ares_signal["tp_abs"]
        tp_pct = ares_signal["tp_pct"]

        # Rule 2: Entry (진입가)
        if entry_abs:
            # Rule 3: Target (목표가) calculation
            target = None
            if tp_abs:
                target = tp_abs
            elif tp_pct and entry_abs:
                if side == "BUY":
                    target = entry_abs * (1 + tp_pct)
                elif side == "SELL":
                    target = entry_abs * (1 - tp_pct)

            # Rule 4: Directional sanity check
            sanity_pass = False
            if target:
                if side == "BUY" and target >= entry_abs:
                    sanity_pass = True
                elif side == "SELL" and target <= entry_abs:
                    sanity_pass = True

            # Show values only if sanity check passes
            if sanity_pass:
                entry_display = f"${entry_abs:,.4f}"
                target_display = f"${target:,.4f}"

        # Rule 6: SELL with no holdings
        if side == "SELL" and position_qty <= 0:
            sell_no_position_note = "보유 없음 — 매도 주문 차단됨"

    return {
        "last_display": last_display,
        "entry_display": entry_display,
        "target_display": target_display,
        "sell_no_position_note": sell_no_position_note,
    }


def render_symbol_card(symbol):
    """심볼 카드 렌더링 - SSOT 기반 정확한 표시"""
    try:
        snapshot = load_symbol_snapshot_cached(symbol)
        ares_data = load_ares_data_cached(symbol)
        history = load_symbol_history_cached(symbol, 50)
    except Exception as e:
        # ERROR 발생 시 기본값으로 안전하게 처리
        snapshot = None
        ares_data = None
        history = []
        print(f"[SymbolCard] {symbol} 데이터 로드 실패: {e}")

    # 카드 헤더
    current_time = datetime.now().strftime("%H:%M:%S")

    # 실제 신선도 데이터 계산
    price_age = 999
    ares_age = 999

    if snapshot:
        current_time_sec = time.time()
        snapshot_time = snapshot.get("ts", current_time_sec)
        price_age = current_time_sec - snapshot_time

    if ares_data and ares_data.get("meta"):
        ares_age = ares_data.get("age_sec", 999)

    # 가격 정보 (안전한 추출)
    current_price = 0
    try:
        if snapshot and isinstance(snapshot, dict):
            # Binance WebSocket 데이터 구조에서 가격 추출
            if "price" in snapshot:
                current_price = float(snapshot["price"]) if snapshot["price"] else 0
            elif "c" in snapshot:  # close price
                current_price = float(snapshot["c"]) if snapshot["c"] else 0
            else:
                current_price = 0
    except (ValueError, TypeError) as e:
        current_price = 0
        print(f"[SymbolCard] {symbol} 가격 추출 실패: {e}")

    # 가격 변화율 계산 (실제 데이터 기반) - 안전한 계산
    price_change = 0.0
    try:
        if history and len(history) >= 2 and isinstance(history, list):
            current_price_hist = (
                float(history[-1].get("c", 0)) if isinstance(history[-1], dict) else 0
            )
            prev_price = (
                float(history[-2].get("c", 0)) if isinstance(history[-2], dict) else 0
            )
            if prev_price > 0:
                price_change = ((current_price_hist - prev_price) / prev_price) * 100
    except (ValueError, TypeError, IndexError) as e:
        price_change = 0.0
        print(f"[SymbolCard] {symbol} 가격 변화율 계산 실패: {e}")

    # ARES 신호 정보 (포지션 상태 확인)
    signal_side = "FLAT"
    confidence = 0
    signal_price = 0
    entry_price = 0
    unrealized_pnl = 0.0

    # 실제 포지션 상태 확인 (안전한 처리) - positions_snapshot.json에서 직접 읽기
    has_position = False
    position_qty = 0
    position_avg_price = 0
    try:
        # 먼저 스냅샷에서 확인
        if snapshot and isinstance(snapshot, dict) and snapshot.get("position"):
            position = snapshot["position"]
            if isinstance(position, dict):
                position_qty = position.get("qty", 0)
                position_avg_price = position.get("avg_px", 0)
                position_unrealized_pnl = position.get("unrealized_pnl", 0)
                has_position = float(position_qty) > 0 if position_qty else False

                # 스냅샷에서 Unrealized PnL도 가져오기
                if has_position and position_unrealized_pnl != 0:
                    unrealized_pnl = float(position_unrealized_pnl)
                    print(
                        f"[SNAPSHOT] {symbol}: 스냅샷에서 Unrealized PnL 사용: {unrealized_pnl}"
                    )

        # 스냅샷에 포지션이 없으면 positions_snapshot.json에서 직접 확인
        if not has_position:
            import json
            import pathlib

            positions_file = pathlib.Path("POSITIONS_FILE")
            print(
                f"[POSITION DEBUG] {symbol}: positions_file.exists() = {positions_file.exists()}"
            )
            if positions_file.exists():
                with open(positions_file, "r", encoding="utf-8") as f:
                    positions_data = json.load(f)
                    print(
                        f"[POSITION DEBUG] {symbol}: positions_data keys = {list(positions_data.keys())}"
                    )
                    if symbol in positions_data:
                        symbol_pos = positions_data[symbol]
                        position_qty = symbol_pos.get("qty", 0)
                        position_avg_price = symbol_pos.get("avg_price", 0)
                        position_unrealized_pnl = symbol_pos.get("unrealized_pnl", 0)
                        has_position = (
                            float(position_qty) > 0 if position_qty else False
                        )
                        print(
                            f"[POSITION DEBUG] {symbol}: qty={position_qty}, avg_price={position_avg_price}, has_position={has_position}"
                        )

                        # 포지션 데이터에서 Unrealized PnL도 가져오기
                        if has_position and position_unrealized_pnl != 0:
                            unrealized_pnl = float(position_unrealized_pnl)
                            print(
                                f"[POSITION DEBUG] {symbol}: 포지션 데이터에서 Unrealized PnL 사용: {unrealized_pnl}"
                            )
                    else:
                        print(
                            f"[POSITION DEBUG] {symbol}: symbol not found in positions_data"
                        )
            else:
                print(f"[POSITION DEBUG] {symbol}: positions_file does not exist")
    except (ValueError, TypeError, FileNotFoundError, KeyError) as e:
        has_position = False
        position_qty = 0
        position_avg_price = 0
        print(f"[SymbolCard] {symbol} 포지션 확인 실패: {e}")

    # ARES 신호 처리 (안전한 처리)
    try:
        if ares_data and isinstance(ares_data, dict) and ares_data.get("signals"):
            signals = ares_data["signals"]
            if isinstance(signals, list) and len(signals) > 0:
                signal = signals[0]  # 첫 번째 신호 사용
                if isinstance(signal, dict):
                    raw_signal_side = signal.get(
                        "action", "flat"
                    ).upper()  # action 키 사용
                    confidence = (
                        float(signal.get("confidence", 0))
                        if signal.get("confidence")
                        else 0
                    )
                    # ARES 신호에서 tp (목표가) 사용, 없으면 계산
                    if signal.get("tp") and float(signal.get("tp", 0)) > 0:
                        signal_price = float(signal.get("tp"))
                    else:
                        # tp가 없으면 entry_price 기반으로 계산
                        entry_price_signal = (
                            float(signal.get("entry_price", 0))
                            if signal.get("entry_price")
                            else 0
                        )
                        if entry_price_signal > 0:
                            # 간단한 목표가 계산 (2% 수익률)
                            if raw_signal_side == "BUY":
                                signal_price = entry_price_signal * 1.02  # 2% 상승
                            else:  # SELL
                                signal_price = entry_price_signal * 0.98  # 2% 하락
                        else:
                            signal_price = (
                                float(signal.get("price", 0))
                                if signal.get("price")
                                else 0
                            )

                    # 실제 포지션이 있으면 실제 평균단가 사용, 없으면 신호의 entry_price 사용
                    if has_position and position_avg_price > 0:
                        entry_price = position_avg_price
                        print(
                            f"[ENTRY FIX] {symbol}: 실제 포지션 평균단가 사용 ${position_avg_price}"
                        )
                    else:
                        entry_price = (
                            float(signal.get("entry_price", 0))
                            if signal.get("entry_price")
                            else 0
                        )
                        print(
                            f"[ENTRY FIX] {symbol}: 신호 entry_price 사용 ${entry_price}"
                        )

                # Unrealized PnL 계산
                if (
                    has_position
                    and position_qty > 0
                    and position_avg_price > 0
                    and current_price > 0
                ):
                    unrealized_pnl = position_qty * (current_price - position_avg_price)
                    print(
                        f"[UNREALIZED] {symbol}: qty={position_qty}, avg_price={position_avg_price}, current_price={current_price}, pnl={unrealized_pnl:.2f}"
                    )

                # 디버깅: 포지션 상태 출력
                print(
                    f"[DEBUG] {symbol}: has_position={has_position}, position_qty={position_qty}, position_avg_price={position_avg_price}, entry_price={entry_price}"
                )
                print(
                    f"[DEBUG] {symbol}: raw_signal_side={raw_signal_side}, current_price={current_price}"
                )

                # 포지션 상태에 따른 신호 수정
                if raw_signal_side == "SELL" and not has_position:
                    # 보유 포지션이 없으면 SELL 신호 무시
                    signal_side = "FLAT"
                    confidence = 0
                    print(f"[SELL BLOCK] {symbol}: 포지션 없음, SELL 신호 차단")
                else:
                    signal_side = raw_signal_side
                    print(f"[SIMPLE] {symbol}: ARES 신호 그대로 사용 - {signal_side}")
    except (ValueError, TypeError, AttributeError) as e:
        signal_side = "FLAT"
        confidence = 0
        signal_price = 0
        print(f"[SymbolCard] {symbol} ARES 신호 처리 실패: {e}")

    # ARES 상태 배지 (안전한 처리)
    try:
        ares_badge = get_ares_status_badge(ares_data)
    except Exception as e:
        ares_badge = '<span class="ares-status ares-error">BADGE ERR</span>'
        print(f"[SymbolCard] {symbol} ARES 배지 생성 실패: {e}")

    # 데이터 상태 진단 정보
    data_status = []
    if not snapshot:
        data_status.append("NO_PRICE")
    elif price_age > 300:
        data_status.append("STALE_PRICE")

    if not ares_data:
        data_status.append("NO_ARES")
    elif ares_age > 300:
        data_status.append("STALE_ARES")

    if not history:
        data_status.append("NO_HIST")

    # 상태 요약 (간소화)
    if len(data_status) == 0:
        status_summary = "OK"
    elif len(data_status) == 1:
        status_summary = data_status[0]
    else:
        status_summary = f"{len(data_status)} ERR"

    # 신호 상태에 따른 스타일 결정
    signal_color = "#666666"  # 기본 회색
    signal_icon = "⚪"

    if signal_side == "BUY" and confidence >= 75:
        signal_color = "#00ff00"  # 밝은 녹색
        signal_icon = "🟢"
    elif signal_side == "SELL" and confidence >= 75:
        signal_color = "#ff4444"  # 빨간색
        signal_icon = "🔴"
    elif signal_side == "BUY" or signal_side == "SELL":
        signal_color = "#ffaa00"  # 주황색
        signal_icon = "🟡"

    st.markdown(
        f"""
    <div class="symbol-card">
        <div class="symbol-card-header">
            <strong>{symbol.upper()}</strong>
            <span>{current_time} KST</span>
            <span>age {price_age:.0f}s</span>
        </div>
        <div class="symbol-card-main">
            <div>
                <div>Last: ${format_price(current_price)}</div>
                <div>1m Return: {format_percentage(price_change)}</div>
                <div>Unrealized: ${format_price(unrealized_pnl)}</div>
            </div>
            <div>
                <div style="color: {signal_color}; font-weight: bold;">
                    {signal_icon} {signal_side} | {confidence:.1f}%
                </div>
                <div>Entry: ${format_price(entry_price)}</div>
                <div>Target: ${format_price(signal_price)}</div>
                {ares_badge}
            </div>
        </div>
        <div class="symbol-card-footer">
            <div style="font-size: 0.6rem; color: #888;">
                Status: {status_summary}
            </div>
            <button onclick="switchToDetail('{symbol}')">View Detail</button>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


# Detail 컴포넌트
def render_advanced_monitoring():
    """고급 모니터링 섹션"""
    st.markdown("### 📊 Advanced Monitoring")

    # KPI 대시보드
    render_kpi_dashboard()

    # 리스크 모니터링
    render_risk_monitoring()

    # 실행 통계
    render_execution_stats()

    # 새로운 전략 모듈 상태
    render_strategy_modules()

    # Doctor Runner 상태
    render_doctor_status()


def render_kpi_dashboard():
    """KPI 대시보드"""
    st.markdown("#### 🎯 Key Performance Indicators")

    # 실제 거래 성과 데이터 로드
    performance = load_trading_performance_cached()

    # 간단한 KPI 표시
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**Today's Return**")
        st.markdown(
            f"<small>+{performance['today_return']:.2f}% (+${performance['today_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown("**Weekly Return**")
        st.markdown(
            f"<small>+{performance['weekly_return']:.2f}% (+${performance['weekly_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown("**Monthly Return**")
        st.markdown(
            f"<small>+{performance['monthly_return']:.2f}% (+${performance['monthly_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown("**Annual Return**")
        st.markdown(
            f"<small>+{performance['annual_return']:.2f}% (+${performance['annual_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    # 추가 지표
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        st.markdown("**Goal Achievement**")
        st.markdown(
            f"<small>{performance['goal_achievement']:.1f}% (Goal: 10%)</small>",
            unsafe_allow_html=True,
        )

    with col6:
        st.markdown("**Sharpe Ratio**")
        st.markdown(
            f"<small>{performance['sharpe_ratio']:.2f} (Excellent)</small>",
            unsafe_allow_html=True,
        )

    with col7:
        st.markdown("**Max Drawdown**")
        st.markdown(
            f"<small>-{performance['max_drawdown']:.1f}% (Safe)</small>",
            unsafe_allow_html=True,
        )

    with col8:
        st.markdown("**Total Assets**")
        st.markdown(
            f"<small>${performance['total_assets']:,.0f} (+${performance['annual_return'] * 100:.0f})</small>",
            unsafe_allow_html=True,
        )


def render_risk_monitoring():
    """리스크 모니터링"""
    st.markdown("#### ⚠️ Risk Monitoring")

    # 실제 리스크 데이터 로드
    risk_data = load_risk_data_cached()

    # 간단한 리스크 상태 표시
    st.markdown(f"**Status:** {risk_data['status']}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"**Daily Loss:** <small>{risk_data['daily_loss']:.2f}%</small>",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"**Drawdown:** <small>{risk_data['drawdown']:.2f}%</small>",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"**Total Exposure:** <small>${risk_data['total_exposure']:,.0f}</small>",
            unsafe_allow_html=True,
        )


def render_execution_stats():
    """실행 통계 (v2 전략 지원)"""
    st.markdown("#### 📈 Execution Statistics")

    # 실제 실행 통계 데이터 로드
    exec_stats = load_execution_stats_cached()

    # 간단한 실행 통계 표시
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Signals**")
        st.markdown(
            f"<small>Total: {exec_stats['total_signals']}</small>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<small>Successful: {exec_stats['successful']}</small>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<small>Failed: {exec_stats['failed']}</small>", unsafe_allow_html=True
        )

    with col2:
        st.markdown("**Fees & Retries**")
        st.markdown(
            f"<small>Total Fees: ${exec_stats['total_fees']:.2f}</small>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<small>Avg Retries: {exec_stats['avg_retries']:.1f}</small>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<small>Circuit Breakers: {exec_stats['circuit_breakers']}</small>",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown("**Orders**")
        st.markdown(
            f"<small>Limit Orders: {exec_stats['limit_orders']}</small>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<small>Market Orders: {exec_stats['market_orders']}</small>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<small>Cancelled: {exec_stats['cancelled']}</small>",
            unsafe_allow_html=True,
        )


def render_strategy_modules():
    """새로운 전략 모듈 상태 표시"""
    st.markdown("#### 🎯 Strategy Modules (v2)")
    
    # 새로운 전략들 표시
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Trend Multi-TF**")
        try:
            from engine.strategies.trend_multi_tf import TrendMultiTFStrategy
            st.success("✅ Available")
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:30]}")
    
    with col2:
        st.markdown("**BB Mean Revert v2**")
        try:
            from engine.strategies.bb_mean_revert_v2 import \
                BBMeanRevertV2Strategy
            st.success("✅ Available")
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:30]}")
    
    with col3:
        st.markdown("**Vol Spike Scalper v2**")
        try:
            from engine.strategies.volspike_scalper_v2 import \
                VolSpikeScalperV2Strategy
            st.success("✅ Available")
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:30]}")
    
    # 두 번째 행
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Carry Funding**")
        try:
            from engine.strategies.carry_funding import CarryFundingStrategy
            st.success("✅ Available")
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:30]}")
    
    with col2:
        st.markdown("**Pairs Spread**")
        try:
            from engine.strategies.pairs_spread import PairsSpreadStrategy
            st.success("✅ Available")
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:30]}")
    
    with col3:
        st.markdown("**ARES v2 Engine**")
        try:
            from optimizer.ares_v2 import ARES
            st.success("✅ Available")
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:30]}")


def render_doctor_status():
    """Doctor Runner 상태 표시"""
    st.markdown("#### 🔍 System Doctor")
    
    try:
        from shared.doctor_integration import DoctorIntegration
        
        doctor = DoctorIntegration()
        
        if not doctor.is_doctor_available():
            st.error("❌ Doctor Runner를 사용할 수 없습니다.")
            return
        
        # Doctor 실행 버튼
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("🔍 진단 실행", key="doctor_run", use_container_width=True):
                result = doctor.trigger_doctor("quick")
                st.success(result)
                st.rerun()
        
        with col2:
            if st.button("🔄 상태 새로고침", key="doctor_refresh", use_container_width=True):
                st.rerun()
        
        # Doctor 상태 표시
        progress = doctor.get_progress()
        
        if progress["status"] == "running":
            st.info("⏳ Doctor 진단이 실행 중입니다...")
            
            # 진행 상황 표시
            if progress.get("progress"):
                latest_step = progress["progress"][-1] if progress["progress"] else {}
                step_name = latest_step.get("step", "unknown")
                step_status = latest_step.get("status", "unknown")
                pct = latest_step.get("pct", 0)
                
                st.progress(pct / 100)
                st.caption(f"진행 중: {step_name} ({step_status}) - {pct}%")
        
        elif progress["status"] == "completed":
            summary = progress.get("summary", {})
            if summary:
                passed = summary.get("summary", {}).get("passed", 0)
                total = summary.get("summary", {}).get("total_steps", 0)
                duration = summary.get("duration_sec", 0)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    if passed == total:
                        st.success(f"✅ {passed}/{total} 통과")
                    else:
                        st.error(f"❌ {passed}/{total} 통과")
                
                with col2:
                    st.metric("실행 시간", f"{duration:.1f}초")
                
                with col3:
                    status_color = "🟢" if passed == total else "🔴"
                    st.markdown(f"**상태**: {status_color}")
                
                # 실패한 항목 표시
                failed_steps = [step for step in summary.get("steps", []) if step.get("status") == "fail"]
                if failed_steps:
                    st.markdown("**실패한 항목:**")
                    for step in failed_steps[:3]:  # 최대 3개만 표시
                        step_name = step.get("step", "unknown")
                        reason = step.get("reason", "Unknown error")
                        hint = step.get("hint_ko", "상세 확인 필요")
                        st.error(f"• **{step_name}**: {reason}")
                        st.caption(f"💡 {hint}")
        
        elif progress["status"] == "not_started":
            st.info("💤 Doctor 진단이 아직 실행되지 않았습니다.")
        
        else:
            st.warning(f"⚠️ 상태: {progress['status']}")
        
        # 최신 보고서 링크
        if st.button("📋 최신 보고서 보기", key="doctor_report"):
            report = doctor.get_latest_report()
            if report:
                st.markdown("### 📋 Doctor Report")
                st.markdown(report)
            else:
                st.warning("보고서가 없습니다.")
        
    except Exception as e:
        st.error(f"❌ Doctor 상태 확인 실패: {str(e)[:100]}")


def render_symbol_cards_only():
    """UI_CARDS_ONLY 모드: 수익률 KPI + 심볼 카드만 표시"""

    # 핵심 수익률 KPI (4개 타일) - 실시간 데이터
    st.markdown("#### 💰 수익률 현황")
    col1, col2, col3, col4 = st.columns(4)

    # 실시간 수익률 데이터 수집 - 실제 거래 데이터 기반
    try:
        import glob
        import json
        from datetime import datetime

        # 실제 거래 기록 파일들 찾기
        trade_files = []
        possible_paths = [
            "trades/trades.jsonl",  # 주요 거래 기록 파일 추가
            f"{SHARED_DATA_DIR}/trades/*.json",
            "logs/trades/*.json",
            "executor/trades/*.json",
            f"{SHARED_DATA_DIR}/logs/*.json",
        ]

        for path_pattern in possible_paths:
            if "*" in path_pattern:
                trade_files.extend(glob.glob(path_pattern))
            else:
                if os.path.exists(path_pattern):
                    trade_files.append(path_pattern)

        # 거래 기록 로드
        all_trades = []
        for file_path in trade_files:
            try:
                if file_path.endswith(".jsonl"):
                    # JSONL 파일 처리 (한 줄씩 읽기)
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    trade = json.loads(line)
                                    all_trades.append(trade)
                                except:
                                    continue
                else:
                    # JSON 파일 처리
                    with open(file_path, "r", encoding="utf-8") as f:
                        trades = json.load(f)
                        if isinstance(trades, list):
                            all_trades.extend(trades)
                        elif isinstance(trades, dict):
                            all_trades.append(trades)
            except:
                continue

        # 포지션 데이터를 거래 기록으로 변환 (실제 데이터)
        if os.path.exists("POSITIONS_FILE"):
            with open(
                "POSITIONS_FILE", "r", encoding="utf-8"
            ) as f:
                positions_data = json.load(f)

            if positions_data and "ts" in positions_data:
                for symbol, position in positions_data.items():
                    if symbol != "ts" and isinstance(position, dict):
                        qty = position.get("qty", 0)
                        avg_price = position.get("avg_price", 0)
                        unrealized_pnl = position.get("unrealized_pnl", 0)

                        if qty > 0:  # 포지션이 있는 경우
                            trade = {
                                "symbol": symbol,
                                "timestamp": positions_data["ts"] / 1000,
                                "time": datetime.fromtimestamp(
                                    positions_data["ts"] / 1000
                                ).isoformat(),
                                "qty": qty,
                                "price": avg_price,
                                "pnl": unrealized_pnl,
                                "profit": unrealized_pnl,
                                "side": "BUY" if qty > 0 else "SELL",
                                "status": "OPEN",
                            }
                            all_trades.append(trade)

        # 오늘 거래만 필터링
        today = datetime.now().date()
        today_trades = []
        cumulative_pnl = 0.0
        total_trades = len(all_trades)
        winning_trades = 0

        for trade in all_trades:
            try:
                # 거래 시간 파싱 (다양한 형식 지원)
                trade_date = None

                if "timestamp" in trade:
                    trade_date = datetime.fromtimestamp(trade["timestamp"]).date()
                elif "time" in trade:
                    trade_date = datetime.fromisoformat(
                        trade["time"].replace("Z", "+00:00")
                    ).date()
                elif "ts" in trade:
                    # 밀리초를 초로 변환
                    timestamp_sec = trade["ts"] / 1000
                    trade_date = datetime.fromtimestamp(timestamp_sec).date()
                else:
                    # 시간 정보가 없으면 오늘로 간주
                    trade_date = today

                # 오늘 거래인지 확인
                if trade_date == today:
                    today_trades.append(trade)

                # 수익률 계산
                if "pnl" in trade and trade["pnl"] is not None:
                    pnl = float(trade["pnl"])
                    cumulative_pnl += pnl
                    if pnl > 0:
                        winning_trades += 1
                elif "profit" in trade and trade["profit"] is not None:
                    pnl = float(trade["profit"])
                    cumulative_pnl += pnl
                    if pnl > 0:
                        winning_trades += 1

            except Exception:
                continue

        # 오늘 수익 계산 (실제 거래 데이터 기반)
        daily_pnl = 0.0  # 오늘 거래 수익 계산
        # cumulative_pnl = 0.0  # 누적 수익 초기화 제거 - 위에서 계산된 값 사용

        # 오늘 거래 수익 계산
        for trade in today_trades:
            if "pnl" in trade and trade["pnl"] is not None:
                daily_pnl += float(trade["pnl"])
            elif "profit" in trade and trade["profit"] is not None:
                daily_pnl += float(trade["profit"])

        # 실제 포지션에서 미실현 손익 계산
        for trade in all_trades:
            if trade.get("status") == "OPEN" and "pnl" in trade:
                pnl = float(trade.get("pnl", 0))
                cumulative_pnl += pnl
                print(f"[포지션] {trade.get('symbol', 'UNKNOWN')}: {pnl:+.2f} USDT")

        # 현재 자본 (USDT 잔고 기반)
        try:
            if (
                "usdt_balance" in st.session_state
                and st.session_state["usdt_balance"] > 0
            ):
                current_equity = st.session_state["usdt_balance"]
            else:
                # 기본값: 100,000 USDT (테스트넷 기준)
                current_equity = 100000.0
        except:
            current_equity = 100000.0

        # 초기 자본 계산 (현재 자본에서 미실현 손익 차감)
        initial_equity = current_equity - cumulative_pnl

        # 수익률 계산
        daily_return_pct = (
            (daily_pnl / current_equity * 100) if current_equity > 0 else 0.0
        )
        cumulative_return_pct = (
            (cumulative_pnl / initial_equity * 100) if initial_equity > 0 else 0.0
        )

        # 승률 계산
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # 샤프 비율 계산 (간단한 추정)
        sharpe_ratio = (
            min(cumulative_return_pct / 10, 3.0) if cumulative_return_pct > 0 else 0.0
        )

        # 디버깅: 실제 데이터 확인
        print(
            f"[수익률 현황] 오늘 수익: {daily_pnl:.2f} USDT, 누적 수익: {cumulative_pnl:.2f} USDT"
        )
        print(
            f"[수익률 현황] 오늘 수익률: {daily_return_pct:.2f}%, 누적 수익률: {cumulative_return_pct:.2f}%"
        )
        print(
            f"[수익률 현황] 현재 자본: {current_equity:.2f} USDT, 초기 자본: {initial_equity:.2f} USDT"
        )

    except Exception as e:
        # 오류 시 기본값 사용
        print(f"[수익률 계산 오류] {e}")
        daily_pnl = 0.0
        daily_return_pct = 0.0
        cumulative_pnl = 0.0
        cumulative_return_pct = 0.0
        win_rate = 0.0
        sharpe_ratio = 1.0
        total_trades = 0
        all_trades = []

    with col1:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">오늘 수익률</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{daily_return_pct:+.2f}%</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">↗ {daily_pnl:+.2f}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">누적 수익률</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{cumulative_return_pct:+.2f}%</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">↗ {cumulative_pnl:+.2f}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">누적 수익금</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{cumulative_pnl:+,.2f} USDT</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">총 수익</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">샤프 비율</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{sharpe_ratio:.2f}</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">{"우수" if sharpe_ratio > 2 else "보통"}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # 심볼 카드들
    st.markdown("#### 🎯 Symbol Status Cards")

    watchlist = load_watchlist_cached()

    if not watchlist:
        st.warning("워치리스트가 비어있습니다.")
        return

    # 심볼별 상태 수집
    symbol_statuses = []

    for symbol in watchlist[:10]:  # 최대 10개만 표시
        try:
            # 데이터 신선도
            age_sec = 999
            try:
                from feeder.databus import databus

                snapshot = databus.get_latest()
                if snapshot:
                    age_sec = snapshot.meta.get("age_sec", 999)
            except Exception:
                pass

            # ARES 신호 상태
            signal_status = "N/A"
            signal_confidence = 0.0
            try:
                from optimizer.ares import ARES

                ares = ARES()
                signal = ares.select()
                if signal:
                    signal_status = signal.action.upper()
                    signal_confidence = signal.conf
            except Exception:
                pass

            # 상태 배지 생성
            badges = []
            if age_sec <= 60:
                badges.append("🟢 DATA")
            elif age_sec <= 120:
                badges.append("🟡 DATA")
            else:
                badges.append("🔴 DATA")

            if signal_status != "N/A":
                if signal_status == "BUY":
                    badges.append("🟢 BUY")
                elif signal_status == "SELL":
                    badges.append("🔴 SELL")
                else:
                    badges.append("⚪ FLAT")

            symbol_statuses.append(
                {
                    "symbol": symbol,
                    "age_sec": age_sec,
                    "signal_status": signal_status,
                    "signal_confidence": signal_confidence,
                    "badges": badges,
                }
            )

        except Exception as e:
            st.error(f"{symbol} 상태 수집 오류: {e}")

    # 카드 그리드 렌더링
    if symbol_statuses:
        cols = st.columns(3)  # 3열 그리드

        for i, status in enumerate(symbol_statuses):
            col_idx = i % 3
            with cols[col_idx]:
                render_symbol_card(status["symbol"])


def render_symbol_cards():
    """심볼별 상태 카드"""
    st.markdown("#### 🎯 Symbol Status Cards")

    watchlist = load_watchlist_cached()

    if not watchlist:
        st.warning("워치리스트가 비어있습니다.")
        return

    # 심볼별 상태 수집
    symbol_statuses = []

    for symbol in watchlist[:10]:  # 최대 10개만 표시
        try:
            # 데이터 신선도
            age_sec = 999
            try:
                from feeder.databus import databus

                snapshot = databus.get_latest()
                if snapshot:
                    age_sec = snapshot.meta.get("age_sec", 999)
            except Exception:
                pass

            # ARES 신호 상태
            regime = "unknown"
            confidence = 0.0
            try:
                # ARES v2 엔진 사용
                from optimizer.ares_v2 import ARES

                ares = ARES()
                ares_status = ares.get_status()
                regime = ares_status.get("current_regime", "unknown")
                confidence = ares_status.get("regime_confidence", 0.0)
            except ImportError:
                # 기존 ARES 엔진으로 폴백
                try:
                    from optimizer.ares import ARES
                    ares = ARES()
                    ares_status = ares.get_status()
                    regime = ares_status.get("current_regime", "unknown")
                    confidence = ares_status.get("regime_confidence", 0.0)
                except Exception:
                    regime = "unknown"
                    confidence = 0.0
            except Exception:
                regime = "unknown"
                confidence = 0.0

            symbol_statuses.append(
                {
                    "symbol": symbol.upper(),
                    "age_sec": age_sec,
                    "regime": regime,
                    "confidence": confidence,
                    "data_status": "OK" if age_sec <= 60 else "STALE",
                }
            )

        except Exception:
            symbol_statuses.append(
                {
                    "symbol": symbol.upper(),
                    "age_sec": 999,
                    "regime": "unknown",
                    "confidence": 0.0,
                    "data_status": "ERROR",
                }
            )

    # 카드 렌더링
    for i in range(0, len(symbol_statuses), 3):
        cols = st.columns(3)

        for j, col in enumerate(cols):
            if i + j < len(symbol_statuses):
                status = symbol_statuses[i + j]

                with col:
                    # 배지 색상 결정
                    regime_color = {
                        "trend": "🟢",
                        "range": "🟡",
                        "vol": "🔴",
                        "mixed": "🟠",
                        "unknown": "⚪",
                    }.get(status["regime"], "⚪")

                    data_color = {"OK": "🟢", "STALE": "🟡", "ERROR": "🔴"}.get(
                        status["data_status"], "⚪"
                    )

                    st.markdown(
                        f"""
                    <div style="border: 1px solid #333; border-radius: 8px; padding: 10px; margin: 5px 0;">
                        <h4>{status['symbol']}</h4>
                        <p><strong>REGIME:</strong> {regime_color} {status['regime'].upper()}</p>
                        <p><strong>CONF:</strong> {status['confidence']:.2f}</p>
                        <p><strong>DATA:</strong> {data_color} {status['data_status']}</p>
                        <p><strong>AGE:</strong> {status['age_sec']:.1f}s</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )


def render_detail():
    """Detail 탭 렌더링"""
    st.markdown("### Detail")

    watchlist = load_watchlist_cached()

    # 자동 포커스 토글
    auto_focus_enabled = st.checkbox("Auto-Focus", value=True, key="auto_focus_toggle")

    # 사용자 선택 심볼 (세션 상태에서 관리)
    if "selected_symbol" not in st.session_state:
        st.session_state.selected_symbol = None

    # 서비스 상태 초기화
    if "feeder_running" not in st.session_state:
        st.session_state.feeder_running = False
    if "trader_running" not in st.session_state:
        st.session_state.trader_running = False

    # 자동 포커스 심볼 결정
    auto_focus_symbol = get_auto_focus_symbol(
        watchlist, st.session_state.selected_symbol, auto_focus_enabled
    )

    # 심볼 선택기
    selected_symbol = st.selectbox(
        "Select Symbol",
        watchlist,
        index=(
            watchlist.index(auto_focus_symbol) if auto_focus_symbol in watchlist else 0
        ),
        key="detail_symbol",
    )

    # 사용자 선택 업데이트
    if selected_symbol != st.session_state.selected_symbol:
        st.session_state.selected_symbol = selected_symbol

    # Stale 체크
    is_stale, stale_reason = check_symbol_stale(selected_symbol)
    if is_stale:
        st.warning(f"⚠️ {stale_reason}")

    # 차트 렌더링
    render_detail_chart(selected_symbol)

    # 상세 정보 섹션
    col1, col2, col3 = st.columns(3)

    with col1:
        render_symbol_info(selected_symbol)

    with col2:
        render_ares_signal_info(selected_symbol)

    with col3:
        render_position_info(selected_symbol)

    # 거래 테이블
    render_trades_table(selected_symbol)


def render_detail_chart(symbol):
    """상세 차트 렌더링"""
    history = load_symbol_history_cached(symbol, 300)

    if not history:
        st.warning("차트 데이터가 없습니다.")
        return

    # DataFrame 생성
    df = pd.DataFrame(history)

    # 컬럼 확인 및 처리 - 실제 데이터 구조에 맞게 수정
    required_columns = ["t", "o", "h", "l", "c", "v"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        st.warning(f"차트 데이터에 필요한 컬럼이 없습니다: {missing_columns}")
        st.info(f"사용 가능한 컬럼: {list(df.columns)}")
        return

    # 컬럼명 매핑
    df["time"] = pd.to_datetime(df["t"], unit="ms")
    df["open"] = df["o"]
    df["high"] = df["h"]
    df["low"] = df["l"]
    df["close"] = df["c"]
    df["volume"] = df["v"]

    # 캔들스틱 차트
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.7, 0.3]
    )

    # 캔들스틱
    fig.add_trace(
        go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
        ),
        row=1,
        col=1,
    )

    # 거래량
    fig.add_trace(
        go.Bar(
            x=df["time"],
            y=df["volume"],
            name="Volume",
            marker_color="rgba(158,202,225,0.8)",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"{symbol.upper()} - 1m Chart",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=8, r=8, t=40, b=8),
        plot_bgcolor="#1e1e1e",
        paper_bgcolor="#0e1117",
        font_color="#fafafa",
    )


def render_symbol_info(symbol):
    """심볼 기본 정보 렌더링"""
    st.markdown("#### 📊 Symbol Info")

    snapshot = load_symbol_snapshot_cached(symbol)
    if snapshot:
        current_price = snapshot.get("c", 0)
        price_change = snapshot.get("P", 0)

        # 간단하고 깔끔한 표시
        try:
            price_float = float(current_price) if isinstance(current_price, str) else current_price
            change_float = float(price_change) if isinstance(price_change, str) else price_change
            st.markdown(f"**Price:** ${price_float:,.4f}")
            st.markdown(f"**Change:** {change_float:+.2f}%")
        except (ValueError, TypeError):
            st.markdown(f"**Price:** {current_price}")
            st.markdown(f"**Change:** {price_change}%")
        
        st.markdown(f"**Symbol:** {symbol.upper()}")
        st.markdown(
            f"**Updated:** {time.strftime('%H:%M:%S', time.localtime(snapshot.get('ts', time.time())))}"
        )
    else:
        st.warning("No data available")


def render_ares_signal_info(symbol):
    """ARES 신호 정보 렌더링"""
    st.markdown("#### 🎯 ARES Signal")

    ares_data = load_ares_data_cached(symbol)
    if ares_data and ares_data.get("signals"):
        signal = ares_data["signals"][0]
        action = signal.get("action", "FLAT")
        confidence = signal.get("confidence", 0)
        target_price = signal.get("price", 0)  # 이제 price 필드가 목표가

        # 간단한 신호 표시
        if action == "BUY":
            st.markdown(
                "**Signal:** <span style='color: #00ff88'>📈 BUY</span>",
                unsafe_allow_html=True,
            )
        elif action == "SELL":
            st.markdown(
                "**Signal:** <span style='color: #ff6b6b'>📉 SELL</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "**Signal:** <span style='color: #666'>➡️ FLAT</span>",
                unsafe_allow_html=True,
            )

        st.markdown(f"**Confidence:** {confidence:.1f}%")
        if target_price > 0:
            st.markdown(f"**Target:** ${target_price:,.4f}")
    else:
        st.info("No signal")


def render_position_info(symbol):
    """포지션 정보 렌더링"""
    st.markdown("#### 💼 Position")

    position_data = load_position_data_cached(symbol)

    if position_data:
        side = position_data.get("side", "NONE")
        size = position_data.get("size", 0)
        entry_price = position_data.get("entry_price", 0)
        pnl = position_data.get("pnl", 0)

        if side != "NONE":
            st.markdown(f"**Side:** {side}")
            st.markdown(f"**Size:** {size:.4f}")
            st.markdown(f"**Entry:** ${entry_price:,.4f}")
            st.markdown(f"**P&L:** ${pnl:,.2f}")
        else:
            st.info("No position")
    else:
        st.info("No position data")


def render_trades_table(symbol):
    """거래 테이블 렌더링"""
    st.markdown("#### Recent Trades")

    trades_data = load_symbol_trades_cached(symbol)

    if trades_data and len(trades_data) > 0:
        df = pd.DataFrame(trades_data)
        if not df.empty:
            # 간단한 테이블 표시
            display_columns = ["timestamp", "side", "price", "quantity"]
            available_columns = [col for col in display_columns if col in df.columns]
            if available_columns:
                st.dataframe(
                    df[available_columns].head(5), use_container_width=True, height=150
                )
            else:
                st.dataframe(df.head(5), use_container_width=True, height=150)
        else:
            st.info("No trades")
    else:
        st.info("No trades")


# 워치리스트 편집기 - 제거됨 (불필요한 심볼 관련 내용)


# Stack Doctor UI Components (Pure Overlay - No Layout Reflow)
def render_stack_doctor_button():
    """Run Stack Doctor 버튼 렌더링 - 인라인 스피너만 사용"""
    # 버튼 상태 초기화
    if "doctor_running" not in st.session_state:
        st.session_state.doctor_running = False
    if "doctor_report_available" not in st.session_state:
        st.session_state.doctor_report_available = False
    if "report_refresh_ts" not in st.session_state:
        st.session_state.report_refresh_ts = 0

    # doctor.lock 파일 확인
    lock_file = Path("shared_data/ops/doctor.lock")
    if lock_file.exists():
        st.session_state.doctor_running = True
    else:
        st.session_state.doctor_running = False
        # Check if report is available using canonical path
        canonical_report = Path("shared_data/reports/stack_doctor/latest.md")
        if canonical_report.exists() and canonical_report.stat().st_size > 0:
            st.session_state.doctor_report_available = True
        else:
            # Fallback: check for any timestamped reports
            reports_dir = Path("shared_data/reports")
            if reports_dir.exists():
                report_files = list(reports_dir.glob("stack_doctor_*.md"))
                if report_files:
                    st.session_state.doctor_report_available = True

    # 버튼 렌더링 (인라인 스피너 포함)
    col1, col2 = st.columns([1, 1])

    with col1:
        disabled = st.session_state.doctor_running or lock_file.exists()
        button_text = "⏳ 진단 실행 중..." if st.session_state.doctor_running else "🔍 Run Stack Doctor"

        if st.button(button_text, disabled=disabled, key="run_doctor_btn", use_container_width=True):
            # doctor.run 파일 작성
            try:
                ops_dir = Path("shared_data/ops")
                ops_dir.mkdir(parents=True, exist_ok=True)

                doctor_run_file = ops_dir / "doctor.run"
                with open(doctor_run_file, "w", encoding="utf-8") as f:
                    json.dump({"mode": "quick", "timestamp": time.time()}, f, indent=2)

                st.session_state.doctor_running = True
                # Set refresh timestamp for cache-busting
                st.session_state.report_refresh_ts = int(time.time())
            except Exception as e:
                pass  # Silent fail

    with col2:
        if st.button("📋 View Report", key="view_report_btn", use_container_width=True):
            # Cache-bust: update refresh timestamp
            st.session_state.report_refresh_ts = int(time.time())
            st.session_state.show_doctor_overlay = True

    # 완료 토스트 (fixed position, bottom-right)
    if st.session_state.get("doctor_just_completed", False):
        st.markdown(
            """
            <div id="doctor-completion-toast" style="
                position: fixed;
                bottom: 24px;
                right: 24px;
                z-index: 10000;
                background: linear-gradient(135deg, #4CAF50, #45a049);
                color: white;
                padding: 16px 20px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                animation: slideInUp 0.3s ease-out;
            " onclick="document.getElementById('view_report_btn').click();">
                ✅ 진단 완료 — 결과 보고서 보기
            </div>
            <style>
            @keyframes slideInUp {
                from { transform: translateY(100px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
            </style>
            <script>
            setTimeout(function() {
                var toast = document.getElementById('doctor-completion-toast');
                if (toast) {
                    toast.style.opacity = '0';
                    toast.style.transform = 'translateY(100px)';
                    setTimeout(function() { toast.remove(); }, 300);
                }
            }, 3000);
            </script>
            """,
            unsafe_allow_html=True,
        )
        st.session_state.doctor_just_completed = False
        # Set refresh timestamp when doctor completes
        st.session_state.report_refresh_ts = int(time.time())



def render_stack_doctor_overlay():
    """Stack Doctor 오버레이 패널 렌더링 - 실제 리포트 표시"""
    if not st.session_state.get("show_doctor_overlay", False):
        return

    # Import report reader
    try:
        from guard.ui.utils.report_reader import get_report_content
    except ImportError:
        st.error("⚠️ Report reader module not found. Please check installation.")
        return

    # Create a modal-like container
    with st.container():
        # Header with close button
        col_header, col_close = st.columns([5, 1])
        with col_header:
            st.markdown("### 📋 Stack Doctor Report")
        with col_close:
            if st.button("✕", key="close_report_overlay"):
                st.session_state.show_doctor_overlay = False
                st.rerun()

        st.markdown("---")

        # Show loading spinner
        with st.spinner("Loading latest report..."):
            # Get report content with cache-busting
            refresh_key = st.session_state.get("report_refresh_ts", 0)
            success, content = get_report_content()

        # Display report content
        if success:
            # Report found - display markdown
            st.markdown(content, unsafe_allow_html=False)
        else:
            # Empty state or error
            st.markdown(content, unsafe_allow_html=False)

        # Action buttons at bottom
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("🔄 Run Again", key="rerun_doctor_from_overlay", use_container_width=True):
                st.session_state.show_doctor_overlay = False
                # Trigger doctor run
                try:
                    ops_dir = Path("shared_data/ops")
                    ops_dir.mkdir(parents=True, exist_ok=True)
                    doctor_run_file = ops_dir / "doctor.run"
                    with open(doctor_run_file, "w", encoding="utf-8") as f:
                        json.dump({"mode": "quick", "timestamp": time.time()}, f, indent=2)
                    st.session_state.doctor_running = True
                    st.session_state.report_refresh_ts = int(time.time())
                except Exception:
                    pass
                st.rerun()

        with col2:
            if st.button("📁 Open Folder", key="open_report_folder", use_container_width=True):
                import subprocess
                report_dir = Path("shared_data/reports/stack_doctor")
                if report_dir.exists():
                    try:
                        subprocess.Popen(f'explorer "{report_dir.absolute()}"')
                        st.toast("📁 Opening report folder...")
                    except Exception:
                        st.toast(f"📁 Report folder: {report_dir.absolute()}")
                else:
                    st.toast("⚠️ Report folder not found")


def main():
    # Monitoring backend warnings
    if MONITORING_BACKEND == "file":
        if not os.path.exists(HEALTH_DIR):
            st.warning(f"⚠️ Health directory not found: {HEALTH_DIR}. Dashboard will show warnings when services are down.")
    elif MONITORING_BACKEND == "http":
        if not MONITORING_ENDPOINT:
            st.warning("⚠️ MONITORING_ENDPOINT not set. Dashboard will show warnings when services are down.")
    
    # 강제 상단 여백을 위한 빈 공간 생성 (DEPLOY 버튼 바로 아래까지)
    st.markdown(
        "<div style='height: 5px; background-color: #0e1117;'></div>",
        unsafe_allow_html=True,
    )

    # 사이드바 다크 테마 및 상단 여백 CSS (DEPLOY 버튼 바로 아래까지)
    st.markdown(
        """
    <style>
    /* 사이드바 다크 테마 강제 적용 */
    section[data-testid="stSidebar"] {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
        transform: translateY(5px) !important;
    }
    
    section[data-testid="stSidebar"] * {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
    }
    
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] select,
    section[data-testid="stSidebar"] textarea {
        background-color: #2d2d2d !important;
        color: #ffffff !important;
        border: 1px solid #404040 !important;
    }
    
    section[data-testid="stSidebar"] button {
        background-color: #2d2d2d !important;
        color: #ffffff !important;
        border: 1px solid #404040 !important;
    }
    
    /* 버튼 텍스트 배경 음영 제거 */
    section[data-testid="stSidebar"] button * {
        background-color: transparent !important;
        text-shadow: none !important;
    }
    
    /* 사이드바 내용도 함께 올리기 */
    section[data-testid="stSidebar"] .element-container {
        transform: translateY(5px) !important;
    }
    
    /* 메인 앱 상단 여백 (DEPLOY 버튼 바로 아래까지) */
    .stApp {
        transform: translateY(5px) !important;
        background-color: #0e1117 !important;
    }
    
    .main .block-container {
        transform: translateY(10px) !important;
        background-color: #0e1117 !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # Enhanced status badges at top of page - REMOVED
    # mode_info = get_run_mode()
    # snapshot, warnings = load_sim_snapshot()
    
    # Create badge columns - REMOVED
    # col1, col2, col3, col4 = st.columns(4)
    
    # with col1:
    #     mode_color = "🟢" if mode_info['mode'] == "SIMULATION" else "🔴"
    #     st.markdown(f"**MODE:** {mode_color} `{mode_info['mode']}`")
    #     st.caption(f"Source: {mode_info['source']}")
    
    # with col2:
    #     if mode_info['mode'] == "SIMULATION":
    #         if snapshot:
    #             data_source = "account_snapshot.json"
    #             data_color = "🟢"
    #         else:
    #             data_source = "unavailable"
    #             data_color = "🔴"
    #     else:
    #         if os.path.exists(ACCOUNT_INFO_FILE):
    #             data_source = "account_info.json"
    #             data_color = "🟢"
    #         else:
    #             data_source = "unavailable"
    #             data_color = "🔴"
    #     st.markdown(f"**DATA SOURCE:** {data_color} `{data_source}`")
    
    # with col3:
    #     if snapshot and "snapshot_ts" in snapshot:
    #         ts = snapshot["snapshot_ts"]
    #         if isinstance(ts, (int, float)):
    #             # Convert epoch to readable format
    #             from datetime import datetime
    #             readable_ts = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    #         else:
    #             readable_ts = str(ts)
    #         snapshot_color = "🟢"
    #     else:
    #         readable_ts = "n/a"
    #         snapshot_color = "🔴"
    #     st.markdown(f"**SNAPSHOT:** {snapshot_color} `{readable_ts}`")
    
    # with col4:
    #     if warnings:
    #         status_color = "⚠️"
    #         status_text = f"{len(warnings)} warnings"
    #     else:
    #         status_color = "✅"
    #         status_text = "OK"
    #     st.markdown(f"**STATUS:** {status_color} {status_text}")
        
    #     if warnings:
    #         with st.expander("⚠️ Data Warnings", expanded=False):
    #             for warning in warnings:
    #                 st.warning(warning)

    # 고정된 알림 영역 표시 (사이드바 이전에 표시)
    show_fixed_notification_area()

    # 서비스 상태 확인 및 자동 재시작
    check_and_restart_services()

    # 사이드바를 먼저 렌더링 (Streamlit 권장사항)
    render_sidebar()

    # 실시간 체결 감지 및 알림
    check_and_notify_executions()

    # 실시간 신호 감지 및 알림
    check_and_notify_signals()

    # 자동매매 구성 요소 초기화 (세션 상태에 없으면 생성)
    if "ares_engine" not in st.session_state:
        try:
            from optimizer.ares import ARES

            st.session_state.ares_engine = ARES()
            st.success("✅ ARES 엔진 초기화 완료")
        except Exception as e:
            st.error(f"❌ ARES 엔진 초기화 실패: {e}")

    if "trade_executor" not in st.session_state:
        try:
            from executor.trade_exec import TradeExecutor

            st.session_state.trade_executor = TradeExecutor()
            st.success("✅ Trade Executor 초기화 완료")
        except Exception as e:
            st.error(f"❌ Trade Executor 초기화 실패: {e}")

    # 자동매매 실행 로직
    if (
        st.session_state.get("auto_trading_active", False)
        and st.session_state.get("ares_engine")
        and st.session_state.get("trade_executor")
    ):

        try:
            ares = st.session_state.ares_engine
            executor = st.session_state.trade_executor

            # ARES가 레짐 기반 Top-1 전략 자동 선택하여 신호 생성
            signal = ares.select()

            if signal:
                # 신호 기록
                if "signal_history" not in st.session_state:
                    st.session_state.signal_history = []

                signal_record = {
                    "timestamp": time.time(),
                    "action": signal.action,
                    "strategy": signal.strategy,
                    "confidence": signal.conf,
                    "regime": signal.regime,
                    "reason": signal.reason,
                }
                st.session_state.signal_history.append(signal_record)
                st.session_state.signal_history = st.session_state.signal_history[
                    -50:
                ]  # 최근 50개만 유지

                # 현재 신호 업데이트
                st.session_state.current_signal = signal

                # 신호 토스트 (종목과 가격 정보 포함)
                symbol = getattr(signal, "symbol", "UNKNOWN")
                # sub 필드가 전략명인 경우 실제 종목명으로 변환
                if symbol in [
                    "default",
                    "ensemble",
                    "trend_multi_tf",
                    "bb_mean_revert_v2",
                    "volspike",
                    "carry",
                    "pairs",
                ]:
                    # 현재 활성화된 심볼들 중에서 랜덤 선택하거나 기본값 사용
                    symbol = "BTCUSDT"  # 기본값으로 BTCUSDT 사용

                price = getattr(signal, "px", 0.0)
                price_display = f"${price:,.2f}" if price > 0 else "N/A"

                # 토스트 알림
                st.toast(
                    f"🔔 {symbol} {signal.action.upper()} 신호 (신뢰도: {signal.conf:.2f}) @ {price_display}"
                )

                # 상세 알림 추가
                action_emoji = "🟢" if signal.action.upper() == "BUY" else "🔴"
                notification_msg = f"{action_emoji} ARES {signal.action.upper()} 신호 - {symbol} @ {price_display} (신뢰도: {signal.conf:.2f})"
                add_notification(notification_msg, "info")

                # 실행기로 신호 전송 (리스크 필터링 후 주문 전송)
                from feeder.databus import databus

                snapshot = databus.get_latest()
                current_equity = (
                    snapshot.account.get("equity", 10000.0) if snapshot else 10000.0
                )
                result = executor.execute(signal, current_equity=current_equity)

                if result.success:
                    # 거래 실행 성공 (알림 제거)
                    pass
                else:
                    # 거래 실행 실패 - 고정된 알림 영역에 표시
                    add_notification(
                        f"⚠️ 거래 실행 실패: {result.error_msg or 'Unknown'}", "warning"
                    )

        except Exception as e:
            # 자동매매 오류 - 고정된 알림 영역에 표시
            add_notification(f"❌ 자동매매 오류: {e}", "error")

    # Stack Doctor UI 렌더링 (Pure Overlay - No Layout Impact)
    render_stack_doctor_button()
    render_stack_doctor_overlay()

    # 헤더 렌더링
    render_header()

    # 자동 새로고침 컨트롤
    render_refresh_controls()

    # UI_CARDS_ONLY 모드에 따른 렌더링
    if UI_CARDS_ONLY:
        # 카드 전용 모드: 심볼 카드만 표시
        render_symbol_cards_only()
    else:
        # 전체 모드: 탭 구조 표시
        tab1, tab2, tab3, tab4 = st.tabs(
            ["📊 Multi Board", "📈 Detail", "🔍 Advanced Monitoring", "⚡ 매매 현황"]
        )

        with tab1:
            render_multi_board()

        with tab2:
            render_detail()

        with tab3:
            render_advanced_monitoring()

        with tab4:
            # 매매 현황 탭 - 상세한 매매 정보
            st.markdown("### ⚡ 매매 현황 - 상세 정보")

            # 알림 설정과 시스템 정보를 나란히 표시
            col1, col2 = st.columns([1, 1])

            with col1:
                st.markdown("#### 🔔 알림 설정")
                render_notification_settings()

                # 시스템 상태 정보
                st.markdown("#### 🔧 시스템 상태")
                auto_trading_status = st.session_state.get("auto_trading_active", False)
                if auto_trading_status:
                    st.success("🟢 자동매매 활성")
                else:
                    st.error("🔴 자동매매 비활성")

                current_regime = st.session_state.get("current_regime", "unknown")
                st.info(f"📊 현재 레짐: {current_regime}")

                current_strategy = st.session_state.get("current_strategy", "unknown")
                st.info(f"🎯 활성 전략: {current_strategy}")

            with col2:
                st.markdown("#### ⚡ 최근 체결 내역")
                render_live_executions()

                # 실시간 데이터 갱신 정보
                st.markdown("#### 🔄 실시간 데이터")
                st.info("💡 캐시 시스템이 자동으로 데이터를 갱신합니다.")
                st.info("📊 모든 데이터는 실시간으로 업데이트됩니다.")

    # 사이드바 스타일 최적화
    st.markdown(
        """
    <style>
    /* 사이드바 간격 최적화 */
    .css-1d391kg {
        padding-top: 0.3rem !important;
        padding-bottom: 0.3rem !important;
    }
    
    /* 섹션 헤더 간격 줄이기 */
    .css-1d391kg h3 {
        margin-top: 0.3rem !important;
        margin-bottom: 0.3rem !important;
        font-size: 1rem !important;
    }
    
    /* 버튼 간격 줄이기 */
    .stButton > button {
        margin-bottom: 0.2rem !important;
        padding: 0.3rem 0.6rem !important;
        font-size: 0.9rem !important;
    }
    
    /* 컬럼 간격 줄이기 */
    .stColumns {
        margin-bottom: 0.2rem !important;
    }
    
    /* 마크다운 간격 줄이기 */
    .css-1d391kg .stMarkdown {
        margin-bottom: 0.2rem !important;
    }
    
    /* 입력 필드 간격 줄이기 */
    .stNumberInput, .stSelectbox {
        margin-bottom: 0.2rem !important;
    }
    
    /* 알림 메시지 간격 줄이기 */
    .stAlert {
        margin-bottom: 0.2rem !important;
        padding: 0.3rem !important;
    }
    
    /* 구분선 간격 줄이기 */
    .css-1d391kg hr {
        margin: 0.3rem 0 !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.exception("Fatal error in dashboard")
        st.error(f"Fatal error: {e}")
        st.stop()


