#!/usr/bin/env python3
"""
멀티심볼 제어판 UI
간소화된 Streamlit 제어판
"""

import os

import streamlit as st

from executor.multi_symbol_order_router import MultiSymbolOrderRouter
from executor.multi_symbol_risk_manager import MultiSymbolRiskManager
from feeder.multi_symbol_stream_bus import MultiSymbolStreamBus
from optimizer.multi_symbol_signal_generator import MultiSymbolSignalGenerator
from shared.mode_manager import mode_manager
from shared.watchlist_loader import WatchlistLoader


class MultiSymbolControlPanel:
    """멀티심볼 제어판"""

    def __init__(self):
        self.watchlist_loader = WatchlistLoader()
        self.signal_generator = MultiSymbolSignalGenerator()
        self.order_router = MultiSymbolOrderRouter()
        self.risk_manager = MultiSymbolRiskManager()

        # 서비스 상태
        self.feeder_running = False
        self.trader_running = False

    def render(self):
        """UI 렌더링"""
        st.set_page_config(
            page_title="멀티심볼 거래 제어판", page_icon="📊", layout="wide"
        )

        # 헤더
        self._render_header()

        # 메인 컨텐츠
        col1, col2 = st.columns([2, 1])

        with col1:
            self._render_main_controls()
            self._render_watchlist_management()
            self._render_service_status()

        with col2:
            self._render_risk_status()
            self._render_recent_logs()

    def _render_header(self):
        """헤더 렌더링"""
        st.title("📊 멀티심볼 거래 제어판")

        # 환경 배지
        col1, col2, col3 = st.columns(3)

        with col1:
            mode = mode_manager.get_current_mode()
            color = mode_manager.get_mode_color()
            st.markdown(f"**환경:** :{color}[{mode_manager.get_mode_display_name()}]")

        with col2:
            can_trade = mode_manager.can_trade()
            trade_status = "거래 가능" if can_trade else "거래 차단"
            trade_color = "green" if can_trade else "red"
            st.markdown(f"**거래 상태:** :{trade_color}[{trade_status}]")

        with col3:
            failsafe = self.risk_manager.failsafe_mode
            failsafe_status = "세이프가드 활성" if failsafe else "정상"
            failsafe_color = "red" if failsafe else "green"
            st.markdown(f"**세이프가드:** :{failsafe_color}[{failsafe_status}]")

        st.divider()

    def _render_main_controls(self):
        """메인 제어 버튼"""
        st.subheader("🎮 서비스 제어")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📡 Feeder 시작", disabled=self.feeder_running):
                self._start_feeder()

        with col2:
            if st.button("📡 Feeder 정지", disabled=not self.feeder_running):
                self._stop_feeder()

        col3, col4 = st.columns(2)

        with col3:
            if st.button("💰 Trader 시작", disabled=self.trader_running):
                self._start_trader()

        with col4:
            if st.button("💰 Trader 정지", disabled=not self.trader_running):
                self._stop_trader()

        # 상태 표시
        if self.feeder_running:
            st.success("✅ Feeder 실행 중")
        else:
            st.error("❌ Feeder 중지됨")

        if self.trader_running:
            st.success("✅ Trader 실행 중")
        else:
            st.error("❌ Trader 중지됨")

        st.divider()

    def _render_watchlist_management(self):
        """워치리스트 관리"""
        st.subheader("📋 워치리스트 관리")

        # 현재 워치리스트 표시
        current_symbols = self.watchlist_loader.load_watchlist()
        st.write(
            f"**현재 심볼 ({len(current_symbols)}개):** {', '.join(current_symbols)}"
        )

        # 심볼 추가/제거
        col1, col2 = st.columns(2)

        with col1:
            new_symbol = st.text_input("새 심볼 추가", placeholder="예: ethusdt")
            if st.button("추가"):
                if new_symbol:
                    success = self.watchlist_loader.add_symbol(new_symbol)
                    if success:
                        st.success(f"✅ {new_symbol} 추가됨")
                        st.rerun()
                    else:
                        st.error(f"❌ {new_symbol} 추가 실패")

        with col2:
            if current_symbols:
                remove_symbol = st.selectbox("심볼 제거", current_symbols)
                if st.button("제거"):
                    success = self.watchlist_loader.remove_symbol(remove_symbol)
                    if success:
                        st.success(f"✅ {remove_symbol} 제거됨")
                        st.rerun()
                    else:
                        st.error(f"❌ {remove_symbol} 제거 실패")

        st.divider()

    def _render_service_status(self):
        """서비스 상태"""
        st.subheader("📊 서비스 상태")

        # WebSocket 연결 상태
        if hasattr(st.session_state, "stream_bus"):
            stream_bus = st.session_state.stream_bus
            if stream_bus and hasattr(stream_bus, "get_all_symbols_health"):
                health_data = stream_bus.get_all_symbols_health()

                st.write("**WebSocket 연결 상태:**")
                for symbol, health in health_data.items():
                    status = "🟢 연결됨" if health.is_connected else "🔴 연결 끊김"
                    st.write(
                        f"- {symbol}: {status} (업데이트: {health.update_count}, 오류: {health.error_count}, 나이: {health.age_sec:.1f}초)"
                    )

        # 신호 상태
        signals = self.signal_generator.get_all_signals()
        st.write(f"**활성 신호:** {len(signals)}개")

        for symbol, signal in signals.items():
            signal_color = (
                "green"
                if signal.side == "buy"
                else "red" if signal.side == "sell" else "gray"
            )
            st.write(
                f"- {symbol}: :{signal_color}[{signal.side.upper()}] @ {signal.price_hint} (신뢰도: {signal.confidence:.2f})"
            )

        st.divider()

    def _render_risk_status(self):
        """리스크 상태"""
        st.subheader("⚠️ 리스크 상태")

        # 리스크 요약
        risk_summary = self.risk_manager.get_risk_summary()

        st.write("**노출 현황:**")
        st.write(
            f"- 총 노출: ${risk_summary['current_status']['total_exposure_usdt']:.2f}"
        )
        st.write(
            f"- 일일 손익: ${risk_summary['current_status']['total_daily_pnl_usdt']:.2f}"
        )
        st.write(
            f"- 활성 포지션: {risk_summary['current_status']['active_positions']}개"
        )
        st.write(
            f"- 노출 활용률: {risk_summary['current_status']['exposure_utilization']:.1f}%"
        )

        # 리스크 한도
        st.write("**리스크 한도:**")
        limits = risk_summary["risk_limits"]
        st.write(f"- 심볼당 최대: ${limits['max_position_usdt']:.0f}")
        st.write(f"- 총 노출 최대: ${limits['max_total_exposure_usdt']:.0f}")
        st.write(f"- 일손실 최대: ${limits['max_daily_loss_usdt']:.0f}")

        # 블랙리스트
        if risk_summary["symbol_blacklist"]:
            st.write(f"**블랙리스트:** {', '.join(risk_summary['symbol_blacklist'])}")

        # 세이프가드 제어
        if risk_summary["failsafe_mode"]:
            if st.button("🔓 세이프가드 해제"):
                self.risk_manager.deactivate_failsafe()
                st.success("세이프가드 해제됨")
                st.rerun()
        else:
            if st.button("🔒 세이프가드 활성화"):
                self.risk_manager._activate_failsafe()
                st.error("세이프가드 활성화됨")
                st.rerun()

        st.divider()

    def _render_recent_logs(self):
        """최근 로그"""
        st.subheader("📝 최근 로그")

        # 로그 파일 읽기
        log_files = ["logs/feeder.log", "logs/trader.log", "logs/system.log"]
        recent_logs = []

        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        recent_logs.extend(lines[-10:])  # 최근 10줄
                except:
                    pass

        if recent_logs:
            # 최근 로그 표시
            log_text = "".join(recent_logs[-20:])  # 최근 20줄
            st.text_area("로그", log_text, height=200)
        else:
            st.write("로그 파일이 없습니다.")

        # 로그 새로고침
        if st.button("🔄 로그 새로고침"):
            st.rerun()

    def _start_feeder(self):
        """Feeder 시작"""
        try:
            if not hasattr(st.session_state, "stream_bus"):
                st.session_state.stream_bus = MultiSymbolStreamBus()

            st.session_state.stream_bus.start()
            self.feeder_running = True
            st.success("✅ Feeder 시작됨")
        except Exception as e:
            st.error(f"❌ Feeder 시작 실패: {e}")

    def _stop_feeder(self):
        """Feeder 정지"""
        try:
            if hasattr(st.session_state, "stream_bus"):
                st.session_state.stream_bus.stop()
            self.feeder_running = False
            st.success("✅ Feeder 정지됨")
        except Exception as e:
            st.error(f"❌ Feeder 정지 실패: {e}")

    def _start_trader(self):
        """Trader 시작"""
        try:
            # 신호 생성 및 주문 처리
            results = self.order_router.process_signals()

            if results["orders_placed"] > 0:
                st.success(f"✅ {results['orders_placed']}개 주문 실행됨")
            else:
                st.info("ℹ️ 실행할 주문이 없습니다.")

            if results["errors"]:
                for error in results["errors"]:
                    st.error(f"❌ {error}")

            self.trader_running = True
        except Exception as e:
            st.error(f"❌ Trader 시작 실패: {e}")

    def _stop_trader(self):
        """Trader 정지"""
        try:
            self.trader_running = False
            st.success("✅ Trader 정지됨")
        except Exception as e:
            st.error(f"❌ Trader 정지 실패: {e}")


def main():
    """메인 함수"""
    control_panel = MultiSymbolControlPanel()
    control_panel.render()


if __name__ == "__main__":
    main()
