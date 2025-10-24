#!/usr/bin/env python3
"""
Green Path Validator - Phase 4
Prove end-to-end auto trade on TESTNET with guardrails
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import sys

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.environment_guardrails import get_repo_paths, check_service_pid_lock
from shared.component_contracts import get_component_contract, get_component_ttl
from shared.atomic_io import read_json_atomic, read_ndjson_lines, append_alert_atomic
from shared.wire_checks import WireChecker


class GreenPathValidator:
    """GREEN Path 검증 시스템"""
    
    def __init__(self):
        self.paths = get_repo_paths()
        self.wire_checker = WireChecker()
        self.test_start_time = None
        self.observed_trades = []
        
    def validate_green_path(self, timeout_seconds: int = 300) -> Tuple[bool, Dict[str, Any]]:
        """GREEN Path 전체 검증"""
        print("🟢 GREEN Path 검증 시작")
        print("=" * 60)
        
        self.test_start_time = time.time()
        results = {
            "overall_success": False,
            "components_green": False,
            "trade_triggered": False,
            "order_flow": False,
            "position_update": False,
            "pnl_update": False,
            "guardrail_violations": [],
            "observed_trades": [],
            "test_duration": 0,
            "error_messages": []
        }
        
        try:
            # 1. 모든 컴포넌트 GREEN 확인
            print("1️⃣ 컴포넌트 GREEN 상태 확인...")
            components_green = self._check_all_components_green()
            results["components_green"] = components_green
            
            if not components_green:
                results["error_messages"].append("일부 컴포넌트가 GREEN 상태가 아님")
                print("❌ 일부 컴포넌트가 GREEN 상태가 아님")
                return False, results
            
            print("✅ 모든 컴포넌트가 GREEN 상태")
            
            # 2. 거래 트리거 (실제 신호 또는 force_signal)
            print("\n2️⃣ 거래 트리거...")
            trade_triggered = self._trigger_test_trade()
            results["trade_triggered"] = trade_triggered
            
            if not trade_triggered:
                results["error_messages"].append("거래 트리거 실패")
                print("❌ 거래 트리거 실패")
                return False, results
            
            print("✅ 거래 트리거 성공")
            
            # 3. 주문 플로우 관찰 (타임아웃 내)
            print(f"\n3️⃣ 주문 플로우 관찰 (최대 {timeout_seconds}초)...")
            order_flow_success = self._observe_order_flow(timeout_seconds)
            results["order_flow"] = order_flow_success
            
            if not order_flow_success:
                results["error_messages"].append("주문 플로우 관찰 실패")
                print("❌ 주문 플로우 관찰 실패")
                return False, results
            
            print("✅ 주문 플로우 성공")
            
            # 4. 포지션 업데이트 확인
            print("\n4️⃣ 포지션 업데이트 확인...")
            position_update = self._check_position_update()
            results["position_update"] = position_update
            
            if not position_update:
                results["error_messages"].append("포지션 업데이트 실패")
                print("❌ 포지션 업데이트 실패")
            
            # 5. PnL 롤업 업데이트 확인
            print("\n5️⃣ PnL 롤업 업데이트 확인...")
            pnl_update = self._check_pnl_update()
            results["pnl_update"] = pnl_update
            
            if not pnl_update:
                results["error_messages"].append("PnL 롤업 업데이트 실패")
                print("❌ PnL 롤업 업데이트 실패")
            
            # 6. 가드레일 위반 확인
            print("\n6️⃣ 가드레일 위반 확인...")
            guardrail_violations = self._check_guardrail_violations()
            results["guardrail_violations"] = guardrail_violations
            
            if guardrail_violations:
                print(f"⚠️ 가드레일 위반 발견: {len(guardrail_violations)}개")
                for violation in guardrail_violations:
                    print(f"   - {violation}")
            else:
                print("✅ 가드레일 위반 없음")
            
            # 전체 성공 판단
            core_success = (components_green and trade_triggered and order_flow_success)
            results["overall_success"] = core_success
            results["test_duration"] = time.time() - self.test_start_time
            results["observed_trades"] = self.observed_trades
            
            if core_success:
                print(f"\n🎉 GREEN Path 검증 성공! ({results['test_duration']:.1f}초)")
                print(f"   - 관찰된 거래: {len(self.observed_trades)}건")
                print(f"   - 가드레일 위반: {len(guardrail_violations)}건")
            else:
                print(f"\n❌ GREEN Path 검증 실패 ({results['test_duration']:.1f}초)")
            
            return core_success, results
            
        except Exception as e:
            results["error_messages"].append(f"예상치 못한 오류: {e}")
            results["test_duration"] = time.time() - self.test_start_time
            print(f"❌ GREEN Path 검증 중 오류: {e}")
            return False, results
    
    def _check_all_components_green(self) -> bool:
        """모든 컴포넌트가 GREEN 상태인지 확인"""
        wire_results = self.wire_checker.run_all_checks()
        
        # 모든 wire check가 통과해야 GREEN
        all_passed = all(result.passed for result in wire_results.values())
        
        return all_passed
    
    def _trigger_test_trade(self) -> bool:
        """테스트 거래 트리거"""
        try:
            # TESTNET 환경 확인
            is_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
            if not is_testnet:
                print("⚠️ LIVE 환경에서는 테스트 거래 트리거 불가")
                return False
            
            # ARES 신호 확인
            signals_file = self.paths["shared_data"] / "signals" / "ares_signals.json"
            if not signals_file.exists():
                print("❌ ARES 신호 파일이 없음")
                return False
            
            signals_data = read_json_atomic(signals_file, {})
            if not signals_data:
                print("❌ ARES 신호 데이터가 비어있음")
                return False
            
            # 실제 신호가 있는지 확인
            has_real_signals = False
            for symbol, signal_data in signals_data.items():
                if isinstance(signal_data, dict):
                    confidence = signal_data.get("confidence", 0)
                    if confidence > 50:  # 50% 이상 신뢰도
                        has_real_signals = True
                        print(f"✅ {symbol}에서 실제 신호 발견 (신뢰도: {confidence}%)")
                        break
            
            if not has_real_signals:
                print("❌ 실제 ARES 신호가 없음")
                return False
            
            # force_signal 후크 확인 (기존 시스템에 있는지)
            force_signal_file = self.paths["shared_data"] / "force_signal.json"
            if force_signal_file.exists():
                force_data = read_json_atomic(force_signal_file, {})
                if force_data.get("active", False):
                    print("✅ force_signal 후크 활성화됨")
                    return True
            
            print("✅ ARES 신호 기반 거래 트리거 준비됨")
            return True
            
        except Exception as e:
            print(f"❌ 거래 트리거 중 오류: {e}")
            return False
    
    def _observe_order_flow(self, timeout_seconds: int) -> bool:
        """주문 플로우 관찰"""
        print(f"   주문 플로우 관찰 중... (최대 {timeout_seconds}초)")
        
        start_time = time.time()
        orders_file = self.paths["shared_data"] / "orders" / "orders_log.ndjson"
        
        # 기존 주문 수 확인
        initial_orders = []
        if orders_file.exists():
            initial_orders = read_ndjson_lines(orders_file)
        
        print(f"   초기 주문 수: {len(initial_orders)}")
        
        # 타임아웃까지 대기하면서 주문 확인
        while time.time() - start_time < timeout_seconds:
            try:
                if orders_file.exists():
                    current_orders = read_ndjson_lines(orders_file)
                    
                    # 새로운 주문 확인
                    if len(current_orders) > len(initial_orders):
                        new_orders = current_orders[len(initial_orders):]
                        
                        for order in new_orders:
                            if isinstance(order, dict):
                                order_id = order.get("order_id", "unknown")
                                symbol = order.get("symbol", "unknown")
                                side = order.get("side", "unknown")
                                status = order.get("status", "unknown")
                                
                                print(f"   📋 새 주문: {symbol} {side} - {status} (ID: {order_id})")
                                
                                # FILLED 상태 확인
                                if status == "FILLED":
                                    print(f"   ✅ 주문 체결됨: {symbol} {side}")
                                    self.observed_trades.append({
                                        "order_id": order_id,
                                        "symbol": symbol,
                                        "side": side,
                                        "status": status,
                                        "timestamp": time.time(),
                                        "observed_at": time.time()
                                    })
                                    return True
                        
                        initial_orders = current_orders
                
                time.sleep(2)  # 2초마다 확인
                
            except Exception as e:
                print(f"   ⚠️ 주문 관찰 중 오류: {e}")
                time.sleep(5)
        
        print(f"   ⏰ 타임아웃 ({timeout_seconds}초) - 주문 체결 없음")
        return False
    
    def _check_position_update(self) -> bool:
        """포지션 업데이트 확인"""
        try:
            positions_file = self.paths["shared_data"] / "positions.json"
            if not positions_file.exists():
                return False
            
            # 파일 수정 시간 확인 (최근 5분 이내)
            file_age = time.time() - positions_file.stat().st_mtime
            if file_age > 300:  # 5분
                return False
            
            # 포지션 데이터 확인
            positions_data = read_json_atomic(positions_file, {})
            if not positions_data:
                return False
            
            # 실제 포지션이 있는지 확인
            has_positions = False
            for symbol, position in positions_data.items():
                if symbol != "ts" and isinstance(position, dict):
                    qty = position.get("qty", 0)
                    if qty != 0:
                        has_positions = True
                        print(f"   📊 포지션 발견: {symbol} qty={qty}")
                        break
            
            return has_positions
            
        except Exception as e:
            print(f"   ❌ 포지션 업데이트 확인 중 오류: {e}")
            return False
    
    def _check_pnl_update(self) -> bool:
        """PnL 롤업 업데이트 확인"""
        try:
            pnl_file = self.paths["shared_data"] / "pnl_rollup.ndjson"
            if not pnl_file.exists():
                return False
            
            # 파일 수정 시간 확인 (최근 10분 이내)
            file_age = time.time() - pnl_file.stat().st_mtime
            if file_age > 600:  # 10분
                return False
            
            # PnL 데이터 확인
            pnl_entries = read_ndjson_lines(pnl_file, max_lines=10)
            if not pnl_entries:
                return False
            
            # 최근 거래가 있는지 확인
            recent_trades = 0
            test_start = self.test_start_time or (time.time() - 600)
            
            for entry in pnl_entries:
                if isinstance(entry, dict):
                    timestamp = entry.get("timestamp", 0)
                    if timestamp >= test_start:
                        recent_trades += 1
            
            print(f"   💰 최근 PnL 항목: {recent_trades}개")
            return recent_trades > 0
            
        except Exception as e:
            print(f"   ❌ PnL 업데이트 확인 중 오류: {e}")
            return False
    
    def _check_guardrail_violations(self) -> List[str]:
        """가드레일 위반 확인"""
        violations = []
        
        try:
            # 서킷 브레이커 확인
            circuit_file = self.paths["shared_data"] / "circuit_breaker.json"
            if circuit_file.exists():
                circuit_data = read_json_atomic(circuit_file, {})
                if circuit_data.get("active", False):
                    violations.append("Circuit breaker is ACTIVE")
            
            # 헬스 상태 확인
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            for component, health in health_data.items():
                if isinstance(health, dict):
                    state = health.get("state", "UNKNOWN")
                    if state == "RED":
                        violations.append(f"Component {component} is RED")
                    elif state == "YELLOW":
                        violations.append(f"Component {component} is YELLOW")
            
            # 최근 알림에서 오류 확인
            alerts = read_ndjson_lines(self.paths["shared_data"] / "alerts.ndjson", max_lines=20)
            for alert in alerts:
                if isinstance(alert, dict):
                    level = alert.get("level", "")
                    if level in ["ERROR", "CRITICAL"]:
                        message = alert.get("message", "")
                        violations.append(f"Recent alert: {message}")
            
        except Exception as e:
            violations.append(f"Guardrail check error: {e}")
        
        return violations
    
    def generate_green_path_report(self, results: Dict[str, Any]) -> str:
        """GREEN Path 보고서 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        status = "✅ SUCCESS" if results["overall_success"] else "❌ FAILED"
        
        report = f"""# GREEN Path Validation Report - {timestamp}

## 요약
- **전체 상태**: {status}
- **테스트 시간**: {results['test_duration']:.1f}초
- **관찰된 거래**: {len(results['observed_trades'])}건
- **가드레일 위반**: {len(results['guardrail_violations'])}건

## 상세 결과

### 1. 컴포넌트 GREEN 상태
- **결과**: {'✅ PASS' if results['components_green'] else '❌ FAIL'}

### 2. 거래 트리거
- **결과**: {'✅ PASS' if results['trade_triggered'] else '❌ FAIL'}

### 3. 주문 플로우
- **결과**: {'✅ PASS' if results['order_flow'] else '❌ FAIL'}

### 4. 포지션 업데이트
- **결과**: {'✅ PASS' if results['position_update'] else '❌ FAIL'}

### 5. PnL 롤업 업데이트
- **결과**: {'✅ PASS' if results['pnl_update'] else '❌ FAIL'}

### 6. 관찰된 거래
"""
        
        if results['observed_trades']:
            for trade in results['observed_trades']:
                report += f"- {trade['symbol']} {trade['side']} - {trade['status']} (ID: {trade['order_id']})\n"
        else:
            report += "- 거래 없음\n"
        
        report += "\n### 7. 가드레일 위반\n"
        if results['guardrail_violations']:
            for violation in results['guardrail_violations']:
                report += f"- {violation}\n"
        else:
            report += "- 위반 없음\n"
        
        if results['error_messages']:
            report += "\n### 8. 오류 메시지\n"
            for error in results['error_messages']:
                report += f"- {error}\n"
        
        report += f"""
## 생성 시간
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 권장 조치
"""
        
        if results['overall_success']:
            report += "GREEN Path 검증이 성공했습니다. 시스템이 정상적으로 작동 중입니다.\n"
        else:
            report += "GREEN Path 검증이 실패했습니다. 다음 사항을 확인하세요:\n"
            for error in results['error_messages']:
                report += f"- {error}\n"
        
        return report


# 전역 인스턴스
green_path_validator = GreenPathValidator()


def validate_green_path(timeout_seconds: int = 300) -> Tuple[bool, Dict[str, Any]]:
    """GREEN Path 검증 실행"""
    return green_path_validator.validate_green_path(timeout_seconds)


def generate_green_path_report(results: Dict[str, Any]) -> str:
    """GREEN Path 보고서 생성"""
    return green_path_validator.generate_green_path_report(results)


if __name__ == "__main__":
    # 직접 실행 시 GREEN Path 검증
    print("🟢 GREEN Path Validator - 독립 실행")
    
    success, results = validate_green_path(timeout_seconds=60)  # 1분 타임아웃
    
    # 보고서 생성 및 저장
    report = generate_green_path_report(results)
    reports_dir = get_repo_paths()["shared_data_reports"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"green_path_{timestamp}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 보고서 저장: {report_file}")
    
    if success:
        print("\n🎉 GREEN Path 검증 완료!")
    else:
        print("\n❌ GREEN Path 검증 실패 - 시스템 점검 필요")
