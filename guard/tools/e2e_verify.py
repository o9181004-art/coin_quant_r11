#!/usr/bin/env python3
"""
E2E Verify: 주문/체결 검증
Trace ID 기반으로 전체 파이프라인 검증
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()


def find_e2e_manifests() -> List[dict]:
    """E2E manifest 파일 찾기"""
    manifest_dir = REPO_ROOT / "shared_data"
    manifests = []
    
    for manifest_file in manifest_dir.glob("e2e_manifest_*.json"):
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
                manifest['_file'] = str(manifest_file)
                manifests.append(manifest)
        except Exception as e:
            print(f"⚠️  Manifest 읽기 실패: {manifest_file.name} - {e}")
    
    return sorted(manifests, key=lambda x: x.get('created_at', 0), reverse=True)


def find_orders_by_trace_id(trace_id: str, time_window_min: int = 15) -> List[dict]:
    """
    Trace ID로 주문 찾기
    
    Args:
        trace_id: E2E trace ID
        time_window_min: 시간 창 (분)
    
    Returns:
        주문 리스트
    """
    orders = []
    cutoff_time = time.time() - (time_window_min * 60)
    
    # 주문 로그 파일들
    order_log_paths = [
        REPO_ROOT / "data" / "orders_log.ndjson",
        REPO_ROOT / "logs" / "trading" / "orders.jsonl",
        REPO_ROOT / "shared_data" / "trades" / "trades.jsonl"
    ]
    
    for log_path in order_log_paths:
        if not log_path.exists():
            continue
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        order = json.loads(line.strip())
                        
                        # Trace ID 매칭
                        if order.get('trace_id') == trace_id or order.get('signal_id', '').startswith(trace_id):
                            order_time = order.get('ts', order.get('timestamp', 0))
                            if order_time >= cutoff_time:
                                orders.append(order)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"⚠️  로그 읽기 실패: {log_path.name} - {e}")
    
    return orders


def check_fills(orders: List[dict]) -> tuple:
    """
    체결 확인
    
    Returns:
        (has_fills: bool, fill_count: int, details: str)
    """
    fills = []
    
    for order in orders:
        # Fill 정보 확인
        if order.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
            fills.append(order)
        elif 'fills' in order and order['fills']:
            fills.append(order)
        elif order.get('executedQty', 0) > 0:
            fills.append(order)
    
    if fills:
        return (True, len(fills), f"✅ {len(fills)}개 체결 확인")
    else:
        return (False, 0, "❌ 체결 없음")


def check_position_delta(orders: List[dict]) -> tuple:
    """
    포지션 변화 확인 (BUY_SELL 패턴)
    
    Returns:
        (is_flat: bool, net_qty: float, details: str)
    """
    buy_qty = 0.0
    sell_qty = 0.0
    
    for order in orders:
        side = order.get('side', '').upper()
        qty = float(order.get('executedQty', order.get('qty', 0)))
        
        if side == 'BUY':
            buy_qty += qty
        elif side == 'SELL':
            sell_qty += qty
    
    net_qty = buy_qty - sell_qty
    is_near_flat = abs(net_qty) < 0.01  # 거의 flat
    
    details = f"BUY={buy_qty:.4f}, SELL={sell_qty:.4f}, NET={net_qty:.4f}"
    
    if is_near_flat:
        return (True, net_qty, f"✅ Near-flat: {details}")
    else:
        return (False, net_qty, f"⚠️  Not flat: {details}")


def generate_verification_report(
    trace_id: str,
    manifest: dict,
    orders: List[dict],
    fill_check: tuple,
    position_check: tuple
) -> dict:
    """검증 리포트 생성"""
    has_fills, fill_count, fill_msg = fill_check
    is_flat, net_qty, position_msg = position_check
    
    # PASS/FAIL 판정
    passed = has_fills and len(orders) > 0
    
    report = {
        "trace_id": trace_id,
        "timestamp": time.time(),
        "status": "PASS" if passed else "FAIL",
        "manifest": manifest,
        "orders": {
            "count": len(orders),
            "details": [
                {
                    "symbol": o.get('symbol'),
                    "side": o.get('side'),
                    "qty": o.get('executedQty', o.get('qty')),
                    "price": o.get('price'),
                    "status": o.get('status')
                }
                for o in orders
            ]
        },
        "fills": {
            "has_fills": has_fills,
            "fill_count": fill_count,
            "message": fill_msg
        },
        "position": {
            "is_flat": is_flat,
            "net_qty": net_qty,
            "message": position_msg
        }
    }
    
    return report


def save_verification_bundle(report: dict):
    """검증 번들 저장 (JSON + Markdown)"""
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    trace_id = report['trace_id']
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON 저장
    json_file = reports_dir / f"E2E_{timestamp_str}_{trace_id}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"💾 JSON 리포트: {json_file.name}")
    
    # Markdown 저장
    md_file = reports_dir / f"E2E_{timestamp_str}_{trace_id}.md"
    md_content = generate_markdown_report(report)
    
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"📄 MD 리포트: {md_file.name}")
    
    return (json_file, md_file)


def generate_markdown_report(report: dict) -> str:
    """Markdown 리포트 생성"""
    status_icon = "✅" if report['status'] == "PASS" else "❌"
    
    md = f"""# E2E Verification Report

## {status_icon} Status: {report['status']}

**Trace ID:** `{report['trace_id']}`  
**Timestamp:** {datetime.fromtimestamp(report['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}

---

## 📊 Summary

| Metric | Value |
|--------|-------|
| Orders Placed | {report['orders']['count']} |
| Fills Received | {report['fills']['fill_count']} |
| Position | {report['position']['message']} |

---

## 📋 Orders

"""
    
    for i, order in enumerate(report['orders']['details'], 1):
        md += f"{i}. **{order['side']}** {order['symbol']} - Qty: {order['qty']}, Price: {order['price']}, Status: {order['status']}\n"
    
    md += f"""
---

## ✅ Fills

{report['fills']['message']}

---

## 📈 Position

{report['position']['message']}

---

## 🎯 Result

**{report['status']}**
"""
    
    return md


def verify_e2e(trace_id: Optional[str] = None, time_window_min: int = 15):
    """E2E 검증 실행"""
    print("=" * 70)
    print("🔍 E2E Verification")
    print("=" * 70)
    
    # 1. Trace ID 확인
    if not trace_id:
        # 최신 manifest에서 가져오기
        manifests = find_e2e_manifests()
        if not manifests:
            print("\n❌ E2E manifest를 찾을 수 없습니다.")
            print("   E2E 신호를 먼저 주입하세요.")
            return 1
        
        manifest = manifests[0]
        trace_id = manifest['trace_id']
        print(f"\n📦 최신 manifest 사용: {trace_id}")
    else:
        # Manifest 로드
        manifest_file = REPO_ROOT / "shared_data" / f"e2e_manifest_{trace_id}.json"
        if not manifest_file.exists():
            print(f"\n⚠️  Manifest 없음: {trace_id}")
            manifest = {}
        else:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
    
    print(f"🔍 Trace ID: {trace_id}")
    print(f"⏱️  Time window: {time_window_min}분")
    
    # 2. 주문 찾기
    print(f"\n[1/3] 주문 검색...")
    orders = find_orders_by_trace_id(trace_id, time_window_min)
    print(f"   발견: {len(orders)}개 주문")
    
    if not orders:
        print("   ❌ 주문 없음")
        return 1
    
    # 3. 체결 확인
    print(f"\n[2/3] 체결 확인...")
    fill_check = check_fills(orders)
    print(f"   {fill_check[2]}")
    
    # 4. 포지션 확인
    print(f"\n[3/3] 포지션 확인...")
    position_check = check_position_delta(orders)
    print(f"   {position_check[2]}")
    
    # 5. 리포트 생성
    print(f"\n[Report] 검증 리포트 생성...")
    report = generate_verification_report(
        trace_id, manifest, orders, fill_check, position_check
    )
    
    json_file, md_file = save_verification_bundle(report)
    
    # 최종 결과
    print("\n" + "=" * 70)
    if report['status'] == "PASS":
        print("🎉 E2E Verification PASS")
    else:
        print("❌ E2E Verification FAIL")
    print("=" * 70)
    print(f"리포트: reports/{md_file.name}")
    print("=" * 70)
    
    return 0 if report['status'] == "PASS" else 1


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="E2E Verification")
    parser.add_argument('--trace_id', help='Trace ID (생략 시 최신 사용)')
    parser.add_argument('--time_window', type=int, default=15, help='Time window (minutes)')
    args = parser.parse_args()
    
    try:
        exit_code = verify_e2e(trace_id=args.trace_id, time_window_min=args.time_window)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

