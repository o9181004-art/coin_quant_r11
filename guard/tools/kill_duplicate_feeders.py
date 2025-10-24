#!/usr/bin/env python3
"""
중복 Feeder 프로세스 제거 도구 (오탐 제거 강화)
- 가장 최근에 시작된 Feeder만 유지
- 나머지는 안전하게 종료
- Streamlit, LSP 서버 등은 무시

Exit Codes:
0 - Success
1 - Nothing to do
2 - Partial success
3 - Access denied
>=128 - Fatal error
"""
import os
import pathlib
import sys
import time
from typing import List, Optional, Tuple

try:
    import psutil
except ImportError:
    print("❌ 오류: psutil이 설치되지 않았습니다.")
    print("   설치: pip install psutil")
    sys.exit(128)


def get_repo_root():
    """레포지토리 루트 경로 반환 (정규화)"""
    root = pathlib.Path(__file__).parent.parent.parent.resolve()
    return root


def normalize_path(path: str) -> str:
    """경로 정규화 (대소문자 무시, 슬래시 통일)"""
    return str(path).lower().replace("\\", "/")


def is_feeder_process(proc: psutil.Process, repo_root_normalized: str) -> bool:
    """
    Feeder 프로세스인지 엄격하게 판단
    
    조건:
    1) ImageName이 python.exe 또는 pythonw.exe
    2) CommandLine에 레포 루트 경로 포함
    3) CommandLine에 "feeder/main.py" 또는 "feeder\\main.py" 포함
    4) Streamlit, LSP 서버 등은 제외
    """
    try:
        proc_info = proc.as_dict(attrs=['name', 'cmdline', 'pid'])
        
        name = proc_info.get('name', '').lower()
        cmdline = proc_info.get('cmdline', [])
        
        # 조건 1: Python 실행 파일인가?
        if name not in {'python.exe', 'pythonw.exe'}:
            return False
        
        # 명령줄 문자열 생성 (정규화)
        if not cmdline:
            return False
        
        cmdline_str = ' '.join(cmdline)
        cmdline_normalized = normalize_path(cmdline_str)
        
        # 조건 2: 레포 루트 경로 포함?
        if repo_root_normalized not in cmdline_normalized:
            return False
        
        # 조건 3: feeder/main.py 포함?
        if "feeder/main.py" not in cmdline_normalized:
            return False
        
        # 조건 4: 제외할 프로세스
        exclude_keywords = ['streamlit', 'pylsp', 'pyright', 'jedi', 'language_server']
        for keyword in exclude_keywords:
            if keyword in cmdline_normalized:
                return False
        
        return True
        
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    except Exception:
        return False


def verify_process_stable(pid: int, sleep_ms: int = 500) -> Optional[dict]:
    """
    Race condition 방지: 프로세스가 안정적인지 확인
    
    Args:
        pid: 검증할 프로세스 ID
        sleep_ms: 대기 시간 (밀리초)
    
    Returns:
        프로세스 정보 dict 또는 None (사라진 경우)
    """
    try:
        # 첫 번째 스냅샷
        proc = psutil.Process(pid)
        first_cmdline = ' '.join(proc.cmdline())
        first_create_time = proc.create_time()
        
        # 대기
        time.sleep(sleep_ms / 1000.0)
        
        # 두 번째 스냅샷
        proc = psutil.Process(pid)
        second_cmdline = ' '.join(proc.cmdline())
        second_create_time = proc.create_time()
        
        # 명령줄이나 생성 시간이 변경되었으면 불안정
        if first_cmdline != second_cmdline or first_create_time != second_create_time:
            return None
        
        # 안정적이면 프로세스 정보 반환
        return proc.as_dict(attrs=['pid', 'ppid', 'name', 'cmdline', 'create_time'])
        
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
    except Exception:
        return None


def get_parent_cmdline(ppid: int) -> str:
    """부모 프로세스 명령줄 가져오기"""
    try:
        parent = psutil.Process(ppid)
        cmdline = ' '.join(parent.cmdline())
        # 길이 제한
        if len(cmdline) > 60:
            return cmdline[:57] + "..."
        return cmdline
    except:
        return "N/A"


def find_feeder_processes() -> List[dict]:
    """
    실행 중인 Feeder 프로세스 찾기 (엄격 모드 + Race condition 방지)
    
    Returns:
        List[dict] - 검증된 Feeder 프로세스 정보 목록
    """
    repo_root = get_repo_root()
    repo_root_normalized = normalize_path(str(repo_root))
    
    print(f"레포 루트: {repo_root}")
    print(f"정규화: {repo_root_normalized}\n")
    
    # 1차 스캔: 후보 수집
    print("1️⃣ 1차 스캔: Feeder 후보 수집 중...")
    candidates = []
    
    for proc in psutil.process_iter():
        if is_feeder_process(proc, repo_root_normalized):
            try:
                candidates.append(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    
    print(f"   후보 {len(candidates)}개 발견: {candidates}")
    
    if not candidates:
        return []
    
    # 2차 검증: Race condition 방지
    print("\n2️⃣ 2차 검증: 프로세스 안정성 확인 (500ms 대기)...")
    verified_feeders = []
    
    for pid in candidates:
        proc_info = verify_process_stable(pid, sleep_ms=500)
        if proc_info:
            verified_feeders.append(proc_info)
            print(f"   ✅ PID {pid} - 안정적")
        else:
            print(f"   ❌ PID {pid} - 사라짐 또는 변경됨")
    
    print(f"\n최종 {len(verified_feeders)}개 Feeder 확정\n")
    
    return verified_feeders


def print_process_table(feeders: List[dict]):
    """프로세스 정보 테이블 출력"""
    print("\n발견된 Feeder 프로세스:")
    print(f"{'PID':<8} {'PPID':<8} {'Name':<15} {'CommandLine':<50}")
    print("-" * 81)
    
    for proc_info in sorted(feeders, key=lambda x: x['create_time']):
        pid = proc_info['pid']
        ppid = proc_info['ppid']
        name = proc_info['name']
        cmdline = ' '.join(proc_info['cmdline'])
        
        # 생성 시간
        create_time_str = time.strftime(
            '%Y-%m-%d %H:%M:%S',
            time.localtime(proc_info['create_time'])
        )
        
        # 명령줄 길이 제한
        if len(cmdline) > 50:
            cmdline = cmdline[:47] + "..."
        
        print(f"{pid:<8} {ppid:<8} {name:<15} {cmdline:<50}")
        print(f"         시작: {create_time_str}")
        
        # 부모 프로세스 정보
        parent_cmd = get_parent_cmdline(ppid)
        print(f"         부모: {parent_cmd}")
        print()


def kill_duplicate_feeders() -> int:
    """중복 Feeder 제거 (개선된 로직)"""
    print("=" * 70)
    print("🔪 중복 Feeder 프로세스 제거 도구 (오탐 제거 강화)")
    print("=" * 70)
    print()
    
    # 1. Feeder 프로세스 찾기 (엄격 모드)
    feeders = find_feeder_processes()
    
    if not feeders:
        print("✅ 실행 중인 Feeder 프로세스가 없습니다.")
        return 1  # Nothing to do
    
    if len(feeders) == 1:
        proc_info = feeders[0]
        create_time_str = time.strftime(
            '%Y-%m-%d %H:%M:%S',
            time.localtime(proc_info['create_time'])
        )
        print(f"✅ Feeder 프로세스 1개만 실행 중 (정상)")
        print(f"   PID:  {proc_info['pid']}")
        print(f"   시작: {create_time_str}")
        return 1  # Nothing to do
    
    # 2. 중복 감지: 상세 정보 출력
    print(f"⚠️  Feeder 프로세스 {len(feeders)}개 발견!")
    print_process_table(feeders)
    
    # 3. 가장 최근 프로세스 유지 (NEWEST)
    feeders_sorted = sorted(feeders, key=lambda x: x['create_time'], reverse=True)
    keep_proc_info = feeders_sorted[0]
    kill_proc_infos = feeders_sorted[1:]
    
    keep_time_str = time.strftime(
        '%Y-%m-%d %H:%M:%S',
        time.localtime(keep_proc_info['create_time'])
    )
    print(f"✅ 유지할 프로세스 (NEWEST): PID {keep_proc_info['pid']} (시작: {keep_time_str})")
    print()
    
    # 4. 오래된 프로세스들 종료
    killed_pids = []
    failed_pids = []
    access_denied = False
    
    for proc_info in kill_proc_infos:
        pid = proc_info['pid']
        
        try:
            print(f"🔪 종료 시도: PID {pid}")
            
            proc = psutil.Process(pid)
            
            # Graceful 종료 시도 (SIGTERM)
            proc.terminate()
            print(f"   SIGTERM 전송...")
            
            # 최대 3초 대기
            try:
                proc.wait(timeout=3)
                killed_pids.append(pid)
                print(f"   ✅ 정상 종료됨 (3초 내)")
            except psutil.TimeoutExpired:
                # 강제 종료 (SIGKILL)
                print(f"   ⚠️  응답 없음, 강제 종료 시도...")
                proc.kill()
                proc.wait(timeout=2)
                killed_pids.append(pid)
                print(f"   ✅ 강제 종료됨 (SIGKILL)")
        
        except psutil.NoSuchProcess:
            print(f"   ℹ️  이미 종료됨")
            killed_pids.append(pid)
        except psutil.AccessDenied:
            print(f"   ❌ 접근 거부 (관리자 권한 필요)")
            failed_pids.append(pid)
            access_denied = True
        except Exception as e:
            print(f"   ❌ 종료 실패: {e}")
            failed_pids.append(pid)
        
        print()
    
    # 5. 재확인 (500ms 후)
    print("5️⃣ 재확인 중...")
    time.sleep(0.5)
    
    remaining_feeders = find_feeder_processes()
    
    # 6. 결과 요약
    print("\n" + "=" * 70)
    print("📊 요약")
    print("=" * 70)
    print(f"발견:                {len(feeders)}개")
    print(f"유지:                PID {keep_proc_info['pid']}")
    print(f"종료 시도:           {len(kill_proc_infos)}개")
    print(f"종료 성공:           {len(killed_pids)}개 - {killed_pids if killed_pids else '없음'}")
    
    if failed_pids:
        print(f"종료 실패:           {len(failed_pids)}개 - {failed_pids}")
    
    print(f"재확인 결과:         {len(remaining_feeders)}개 남음")
    
    # 재확인 상세
    if remaining_feeders:
        print("\n남은 프로세스:")
        for proc_info in remaining_feeders:
            print(f"   PID {proc_info['pid']}")
    
    print("\n" + "=" * 70)
    
    # Exit code 결정
    if failed_pids:
        if access_denied:
            print("❌ 일부 프로세스 접근 거부. 관리자 권한으로 다시 시도하세요.")
            return 3  # Access denied
        else:
            print("⚠️  일부 프로세스 종료 실패")
            return 2  # Partial success
    else:
        if len(remaining_feeders) == 1:
            print("✅ 중복 Feeder 제거 완료!")
            return 0  # Success
        elif len(remaining_feeders) == 0:
            print("⚠️  모든 Feeder가 종료됨. 재시작 필요")
            return 2  # Partial (no Feeder running)
        else:
            print("⚠️  여전히 중복 실행 중")
            return 2  # Partial


def main():
    """메인 함수"""
    try:
        return kill_duplicate_feeders()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단됨")
        return 130  # 128 + SIGINT(2)
    except Exception as e:
        print(f"\n\n❌ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        return 128  # Fatal error


if __name__ == "__main__":
    sys.exit(main())
