#!/usr/bin/env python3
"""
Risk Modes - 거래 모드별 리스크 파라미터 관리
Safe/Aggressive 모드에 따른 리스크 설정
"""

from typing import Any, Dict

from shared.state_bus import get_state_bus, get_trading_mode

# 모드별 리스크 파라미터 맵
RISK_MAP = {
    "SAFE": {
        "per_trade_risk": 0.25,      # 거래당 리스크 0.25%
        "max_positions": 4,           # 최대 포지션 수 4개
        "daily_loss_cap": 2.0,        # 일일 손실 한도 2%
        "loss_streak_cap": 3,         # 연속 손실 한도 3회
        "position_size_multiplier": 0.5,  # 포지션 크기 배수
        "cooldown_seconds": 300,      # 쿨다운 5분
        "min_confidence": 0.6,        # 최소 신뢰도 60%
        "max_drawdown": 5.0,          # 최대 드로우다운 5%
    },
    "AGGRESSIVE": {
        "per_trade_risk": 0.5,        # 거래당 리스크 0.5%
        "max_positions": 12,          # 최대 포지션 수 12개
        "daily_loss_cap": 3.0,        # 일일 손실 한도 3%
        "loss_streak_cap": 2,         # 연속 손실 한도 2회
        "position_size_multiplier": 1.0,  # 포지션 크기 배수
        "cooldown_seconds": 180,      # 쿨다운 3분
        "min_confidence": 0.4,        # 최소 신뢰도 40%
        "max_drawdown": 8.0,          # 최대 드로우다운 8%
    }
}


def get_risk_params(mode: str = None) -> Dict[str, Any]:
    """현재 모드의 리스크 파라미터 조회"""
    if mode is None:
        # 현재 모드 조회
        mode = get_trading_mode()
    
    return RISK_MAP.get(mode, RISK_MAP["SAFE"]).copy()


def get_current_risk_params() -> Dict[str, Any]:
    """현재 설정된 모드의 리스크 파라미터 조회"""
    current_mode = get_trading_mode()
    return get_risk_params(current_mode)


def apply_mode(mode: str) -> bool:
    """모드 적용 (리스크 파라미터 업데이트)"""
    if mode not in RISK_MAP:
        return False
    
    # StateBus에 모드 저장
    state_bus = get_state_bus()
    success = state_bus.set_trading_mode(mode)
    
    if success:
        # 리스크 매니저에 새 파라미터 적용
        try:
            from shared.risk_manager_integration import apply_risk_params
            params = get_risk_params(mode)
            apply_risk_params(params)
        except ImportError:
            # risk_manager_integration이 없으면 무시
            pass
    
    return success


def should_auto_downgrade(daily_loss_pct: float, loss_streak: int) -> bool:
    """자동 다운그레이드 필요 여부 확인"""
    current_params = get_current_risk_params()
    
    # 일일 손실 한도 초과
    if daily_loss_pct >= current_params["daily_loss_cap"]:
        return True
    
    # 연속 손실 한도 초과
    if loss_streak >= current_params["loss_streak_cap"]:
        return True
    
    return False


def auto_downgrade_to_safe() -> bool:
    """자동으로 Safe 모드로 다운그레이드"""
    current_mode = get_trading_mode()
    
    if current_mode == "SAFE":
        return True  # 이미 Safe 모드
    
    # Safe 모드로 전환
    success = apply_mode("SAFE")
    
    if success:
        # 감사 로그 기록
        try:
            from shared.audit import log_auto_downgrade
            log_auto_downgrade(current_mode, "SAFE")
        except ImportError:
            pass
    
    return success


def get_mode_display_name(mode: str) -> str:
    """모드 표시 이름"""
    display_names = {
        "SAFE": "🛡️ Safe",
        "AGGRESSIVE": "⚡ Aggressive"
    }
    return display_names.get(mode, mode)


def get_mode_description(mode: str) -> str:
    """모드 설명"""
    descriptions = {
        "SAFE": "보수적 거래 모드 - 낮은 리스크, 안정적 수익",
        "AGGRESSIVE": "공격적 거래 모드 - 높은 리스크, 높은 수익 기회"
    }
    return descriptions.get(mode, "")


def get_mode_color(mode: str) -> str:
    """모드 색상"""
    colors = {
        "SAFE": "#28a745",      # 녹색
        "AGGRESSIVE": "#dc3545"  # 빨간색
    }
    return colors.get(mode, "#6c757d")  # 회색


def validate_mode_switch(current_mode: str, target_mode: str, open_positions: int) -> tuple[bool, str]:
    """모드 전환 유효성 검사"""
    if current_mode == target_mode:
        return False, "이미 선택된 모드입니다."
    
    if open_positions > 0:
        return False, f"열린 포지션이 {open_positions}개 있습니다. 모든 포지션을 정리한 후 모드를 변경하세요."
    
    if target_mode not in RISK_MAP:
        return False, f"유효하지 않은 모드입니다: {target_mode}"
    
    return True, ""


def get_mode_comparison() -> Dict[str, Dict[str, Any]]:
    """모드 비교 정보"""
    comparison = {}
    
    for mode, params in RISK_MAP.items():
        comparison[mode] = {
            "display_name": get_mode_display_name(mode),
            "description": get_mode_description(mode),
            "color": get_mode_color(mode),
            "params": params
        }
    
    return comparison
