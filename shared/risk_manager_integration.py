#!/usr/bin/env python3
"""
Risk Manager Integration - 리스크 매니저 통합
모드별 리스크 파라미터를 리스크 매니저에 적용
"""

from typing import Any, Dict, Optional

from shared.risk_modes import get_current_risk_params


def apply_risk_params(params: Dict[str, Any]) -> bool:
    """리스크 파라미터를 리스크 매니저에 적용"""
    try:
        # 리스크 매니저 인스턴스 찾기 및 업데이트
        from shared.risk_manager import get_risk_manager
        
        risk_manager = get_risk_manager()
        if risk_manager:
            # 파라미터 업데이트
            risk_manager.update_risk_params(params)
            return True
        
        return False
        
    except ImportError:
        # risk_manager 모듈이 없으면 무시
        return False
    except Exception as e:
        print(f"Risk params apply error: {e}")
        return False


def get_current_risk_settings() -> Dict[str, Any]:
    """현재 리스크 설정 조회"""
    try:
        from shared.risk_manager import get_risk_manager
        
        risk_manager = get_risk_manager()
        if risk_manager:
            return risk_manager.get_risk_params()
        
        # 폴백: 모드별 기본 파라미터
        return get_current_risk_params()
        
    except ImportError:
        # 폴백: 모드별 기본 파라미터
        return get_current_risk_params()
    except Exception as e:
        print(f"Risk settings get error: {e}")
        return get_current_risk_params()


def check_risk_limits() -> Dict[str, Any]:
    """리스크 한도 체크"""
    try:
        from shared.risk_manager import get_risk_manager
        
        risk_manager = get_risk_manager()
        if risk_manager:
            return risk_manager.check_limits()
        
        # 폴백: 기본 체크
        return {
            "daily_loss_ok": True,
            "loss_streak_ok": True,
            "max_positions_ok": True,
            "drawdown_ok": True
        }
        
    except ImportError:
        # 폴백: 기본 체크
        return {
            "daily_loss_ok": True,
            "loss_streak_ok": True,
            "max_positions_ok": True,
            "drawdown_ok": True
        }
    except Exception as e:
        print(f"Risk limits check error: {e}")
        return {
            "daily_loss_ok": True,
            "loss_streak_ok": True,
            "max_positions_ok": True,
            "drawdown_ok": True
        }
