#!/usr/bin/env python3
"""
UDS (User Data Stream) Launcher
listenKey 발급/갱신 및 heartbeat 관리
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

# 환경변수 로드
from dotenv import load_dotenv

# Phase 0: Environment validation
from shared.env_guards import get_absolute_path, validate_environment
# Phase 1: PID lock enforcement
from shared.pid_lock import PIDLock

load_dotenv(REPO_ROOT / "config.env")

# 헬스 매니저 import
from shared.health_manager import set_component

# SSOT 경로
SHARED_DATA_DIR = REPO_ROOT / "shared_data"
LOGS_DIR = REPO_ROOT / "logs" / "hardening"

UDS_PID_FILE = SHARED_DATA_DIR / "uds.pid"
UDS_HEARTBEAT_FILE = LOGS_DIR / "userstream_heartbeat.log"


def get_binance_client():
    """Binance client 생성"""
    try:
        from engine.binance_client import new_client
        return new_client()
    except Exception as e:
        print(f"❌ Binance client 생성 실패: {e}")
        return None


def create_listen_key(client) -> tuple:
    """
    listenKey 생성
    
    Returns:
        (success: bool, listen_key: str or None)
    """
    try:
        result = client.new_listen_key()
        listen_key = result.get('listenKey')
        
        if listen_key:
            print(f"✅ listenKey 생성: {listen_key[:10]}...")
            return (True, listen_key)
        else:
            print(f"❌ listenKey 생성 실패: 응답 없음")
            return (False, None)
    
    except Exception as e:
        print(f"❌ listenKey 생성 실패: {e}")
        return (False, None)


def keepalive_listen_key(client, listen_key: str) -> bool:
    """
    listenKey keepalive
    
    Returns:
        성공 여부
    """
    try:
        client.renew_listen_key(listenKey=listen_key)
        return True
    except Exception as e:
        print(f"⚠️  listenKey keepalive 실패: {e}")
        return False


def heartbeat_loop(client, listen_key: str):
    """
    Heartbeat 루프 (10초 주기) - 헬스 게이트 포함
    
    Args:
        client: Binance client
        listen_key: listenKey
    """
    # Heartbeat 파일 디렉토리 생성
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    running = True
    renewal_interval = 30 * 60  # 30분마다 갱신
    last_renewal = time.time()
    listen_key_created_time = time.time()
    last_heartbeat_time = time.time()
    
    while running:
        try:
            current_time = time.time()
            
            # Heartbeat 기록
            heartbeat_data = {
                "ts": current_time,
                "listen_key": listen_key[:10] + "...",
                "status": "alive"
            }
            
            with open(UDS_HEARTBEAT_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(heartbeat_data, ensure_ascii=False) + "\n")
            
            # 헬스 상태 업데이트 (GREEN) - 표준 스키마
            heartbeat_age = 0  # 방금 성공했으므로 0
            listen_key_age = current_time - listen_key_created_time
            
            set_component("uds", "GREEN", {
                "listen_key_age_sec": listen_key_age,  # 표준 메트릭명
                "heartbeat_age_sec": heartbeat_age,
                "state": "CONNECTED",
                "last_heartbeat": current_time
            })
            
            # Runtime alerts 체크
            try:
                from shared.structured_alerts import emit_uds_age_alert
                emit_uds_age_alert(heartbeat_age)
            except Exception as e:
                print(f"Runtime alert check failed: {e}")
            
            last_heartbeat_time = current_time
            
            # Keepalive (30분마다)
            if current_time - last_renewal >= renewal_interval:
                success = keepalive_listen_key(client, listen_key)
                
                if not success:
                    # 갱신 실패 시 재발급
                    print("🔄 listenKey 재발급 시도...")
                    new_success, new_listen_key = create_listen_key(client)
                    
                    if new_success:
                        listen_key = new_listen_key
                        listen_key_created_time = current_time  # 새로운 listenKey 생성 시간
                        print(f"✅ listenKey 재발급 성공")
                    else:
                        print(f"❌ listenKey 재발급 실패 - 10초 후 재시도")
                        
                        # 헬스 상태 업데이트 (YELLOW) - 표준 스키마
                        heartbeat_age = current_time - last_heartbeat_time
                        listen_key_age = current_time - listen_key_created_time
                        
                        set_component("uds", "YELLOW", {
                            "listen_key_age_sec": listen_key_age,  # 표준 메트릭명
                            "heartbeat_age_sec": heartbeat_age,
                            "state": "RENEWAL_FAILED",
                            "last_heartbeat": last_heartbeat_time
                        })
                
                last_renewal = current_time
            
            # 10초 대기
            time.sleep(10)
        
        except KeyboardInterrupt:
            print("\n⚠️  UDS heartbeat 중지 요청")
            running = False
        except Exception as e:
            # 예외 발생 시 헬스 상태 업데이트 (RED)
            current_time = time.time()
            heartbeat_age = current_time - last_heartbeat_time
            listen_key_age = current_time - listen_key_created_time
            
            set_component("uds", "RED", {
                "listen_key_age_sec": listen_key_age,  # 표준 메트릭명
                "heartbeat_age_sec": heartbeat_age,
                "state": "EXCEPTION",
                "last_heartbeat": last_heartbeat_time
            })
            print(f"⚠️  Heartbeat 오류: {e}")
            time.sleep(10)


def launch_uds():
    """UDS 시작"""
    print("=" * 70)
    print("🔊 UDS Launcher")
    print("=" * 70)
    
    # 1. 기존 UDS 확인
    if UDS_PID_FILE.exists():
        try:
            pid = int(UDS_PID_FILE.read_text().strip())
            
            import psutil
            if psutil.pid_exists(pid):
                print(f"\n✅ UDS 이미 실행 중 (PID: {pid})")
                return 2
        except:
            pass
    
    # 2. Binance client 생성
    print("\n[1/3] Binance client 생성...")
    client = get_binance_client()
    if not client:
        return 1
    
    print("✅ Client 생성 완료")
    
    # 3. listenKey 생성
    print("\n[2/3] listenKey 생성...")
    success, listen_key = create_listen_key(client)
    
    if not success:
        return 1
    
    # 4. Heartbeat 시작 (백그라운드)
    print("\n[3/3] Heartbeat 시작...")
    
    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        args=(client, listen_key),
        daemon=True,
        name="UDS-Heartbeat"
    )
    heartbeat_thread.start()
    
    # PID 파일 저장
    current_pid = os.getpid()
    UDS_PID_FILE.write_text(str(current_pid))
    
    print(f"✅ UDS Heartbeat 시작 (PID: {current_pid})")
    print(f"   listenKey: {listen_key[:10]}...")
    print(f"   Heartbeat: {UDS_HEARTBEAT_FILE}")
    
    # 메인 루프 (프로세스 유지)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n⚠️  UDS 종료 요청")
        return 0


def main():
    try:
        exit_code = launch_uds()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  중단됨")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Phase 0: Environment validation
    validate_environment("uds")
    
    # Phase 1: PID lock enforcement
    with PIDLock("uds"):
        main()

