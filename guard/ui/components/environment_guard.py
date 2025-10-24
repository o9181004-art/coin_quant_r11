#!/usr/bin/env python3
"""
환경/권한 가드 시스템 - ENV/MODE 기반 단순화
ENV = {testnet|mainnet}, MODE = {control|read-only}
"""

import json
import os
import time
from typing import Tuple


class EnvironmentGuard:
    """환경/권한 가드 - ENV/MODE 기반"""

    def __init__(self):
        self.testnet_env = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"

    def get_env_mode(self) -> Tuple[str, str]:
        """ENV/MODE 반환: (env, mode)"""
        # ENV: .env 또는 설정 JSON의 exchange_env
        env = "testnet" if self.testnet_env else "mainnet"

        # MODE: UI 상태 JSON의 mode (control/read-only)
        mode = self._get_ui_mode()

        return env, mode

    def _get_ui_mode(self) -> str:
        """UI 모드 확인"""
        try:
            # UI 상태 JSON 확인
            mode_file = "shared_data/ui_mode.json"
            if os.path.exists(mode_file):
                with open(mode_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("mode", "read-only")

            # 기본값: control 모드로 설정
            self._set_ui_mode("control")
            return "control"

        except Exception:
            return "read-only"

    def _set_ui_mode(self, mode: str):
        """UI 모드 설정"""
        try:
            os.makedirs("shared_data", exist_ok=True)
            mode_file = "shared_data/ui_mode.json"

            data = {
                "mode": mode,
                "read_only_enforced": mode == "read-only",
                "timestamp": int(time.time() * 1000),
            }

            with open(mode_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"UI 모드 설정 실패: {e}")

    def set_control_mode(self):
        """컨트롤 모드로 전환"""
        self._set_ui_mode("control")

    def set_readonly_mode(self):
        """읽기 전용 모드로 전환"""
        self._set_ui_mode("read-only")

    def get_environment_badge(self, env: str, mode: str) -> str:
        """환경 배지 텍스트 - ENV/MODE만 표시"""
        return f"ENV: {env} · MODE: {mode}"

    def is_control_enabled(self, mode: str) -> bool:
        """컨트롤 활성화 여부"""
        return mode == "control"


# 전역 인스턴스
env_guard = EnvironmentGuard()
