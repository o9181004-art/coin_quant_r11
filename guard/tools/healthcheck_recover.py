#!/usr/bin/env python3
"""
시스템 헬스체크 및 복구 도구
- 프로세스 상태 확인 (오탐 제거)
- PID/Lock 파일 정리
- 로그 에러 스캔
- Preflight 체크 재실행
"""
import os
import pathlib
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# psutil 임포트 (프로세스 체크용)
try:
    import psutil
except ImportError:
    print("경고: psutil이 설치되지 않았습니다. 프로세스 체크를 건너뜁니다.")
    psutil = None


class HealthCheckRecover:
    """시스템 헬스체크 및 복구 (오탐 제거 강화)"""

    def __init__(self):
        self.root = pathlib.Path(__file__).parent.parent.parent.resolve()
        self.shared_data = self.root / "shared_data"
        self.logs_dir = self.root / "logs"
        
        # 레포 루트 경로 정규화 (대소문자 무시, 슬래시 통일)
        self.repo_root_normalized = str(self.root).lower().replace("\\", "/")
        
        # 체크할 프로세스 이름
        self.process_names = ["feeder", "trader", "autoheal"]
        
        # 결과 저장
        self.running_processes: Dict[str, List[int]] = {}
        self.deleted_files: List[str] = []
        self.log_errors: Dict[str, List[str]] = {}

    def print_header(self, title: str):
        """섹션 헤더 출력"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)

    def print_subheader(self, title: str):
        """서브 헤더 출력"""
        print(f"\n--- {title} ---")

    # ========== 1. 프로세스 체크 (오탐 제거 강화) ==========
    def _is_feeder_process(self, proc: psutil.Process) -> bool:
        """
        Feeder 프로세스인지 엄격하게 판단
        
        조건:
        1) ImageName이 python.exe 또는 pythonw.exe
        2) CommandLine에 레포 루트 경로 포함
        3) CommandLine에 "feeder/main.py" 또는 "feeder\\main.py" 포함
        """
        try:
            proc_info = proc.as_dict(attrs=['name', 'cmdline', 'pid', 'ppid', 'create_time'])
            
            name = proc_info.get('name', '').lower()
            cmdline = proc_info.get('cmdline', [])
            
            # 조건 1: Python 실행 파일인가?
            if name not in {'python.exe', 'pythonw.exe'}:
                return False
            
            # 명령줄 문자열 생성 (정규화)
            if not cmdline:
                return False
            
            cmdline_str = ' '.join(cmdline).lower().replace("\\", "/")
            
            # 조건 2: 레포 루트 경로 포함?
            if self.repo_root_normalized not in cmdline_str:
                return False
            
            # 조건 3: feeder/main.py 포함?
            if "feeder/main.py" not in cmdline_str:
                return False
            
            # Streamlit 프로세스는 제외
            if "streamlit" in cmdline_str:
                return False
            
            # LSP 서버는 제외
            if "pylsp" in cmdline_str or "pyright" in cmdline_str or "jedi" in cmdline_str:
                return False
            
            return True
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception:
            return False

    def _verify_process_stable(self, pid: int, sleep_ms: int = 500) -> Optional[dict]:
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
            
            # 대기
            time.sleep(sleep_ms / 1000.0)
            
            # 두 번째 스냅샷
            proc = psutil.Process(pid)
            second_cmdline = ' '.join(proc.cmdline())
            
            # 명령줄이 변경되었거나 프로세스가 사라졌으면 불안정
            if first_cmdline != second_cmdline:
                return None
            
            # 안정적이면 프로세스 정보 반환
            return proc.as_dict(attrs=['pid', 'ppid', 'name', 'cmdline', 'create_time'])
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
        except Exception:
            return None

    def _get_parent_cmdline(self, ppid: int) -> str:
        """부모 프로세스 명령줄 가져오기"""
        try:
            parent = psutil.Process(ppid)
            return ' '.join(parent.cmdline())
        except:
            return "N/A"

    def check_processes(self):
        """실행 중인 프로세스 확인 (오탐 제거 강화)"""
        self.print_header("1️⃣ 프로세스 체크 (오탐 제거 강화)")
        
        if psutil is None:
            print("⚠️  psutil이 설치되지 않아 프로세스 체크를 건너뜁니다.")
            return
        
        try:
            # Feeder 프로세스 엄격 검증
            print("\n🔍 Feeder 프로세스 검색 중 (엄격 모드)...")
            
            # 1차 스캔: 후보 수집
            candidates = []
            for proc in psutil.process_iter():
                if self._is_feeder_process(proc):
                    try:
                        candidates.append(proc.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            
            print(f"   1차 스캔: {len(candidates)}개 후보 발견")
            
            # 2차 검증: Race condition 방지
            verified_feeders = []
            for pid in candidates:
                proc_info = self._verify_process_stable(pid, sleep_ms=500)
                if proc_info:
                    verified_feeders.append(proc_info)
            
            print(f"   2차 검증: {len(verified_feeders)}개 확정")
            
            # Feeder 프로세스 저장
            self.running_processes['feeder'] = [p['pid'] for p in verified_feeders]
            
            # 결과 출력
            if len(verified_feeders) == 0:
                print("\n❌ feeder        - 실행 중 아님")
            elif len(verified_feeders) == 1:
                proc_info = verified_feeders[0]
                print(f"\n✅ feeder        - 실행 중 (PID: {proc_info['pid']})")
            else:
                # 중복 감지: 상세 정보 출력
                print(f"\n🔴 feeder        - {len(verified_feeders)}개 중복 실행 감지!")
                print("\n상세 정보:")
                print(f"{'PID':<8} {'PPID':<8} {'Name':<15} {'CommandLine':<50}")
                print("-" * 81)
                
                for proc_info in verified_feeders:
                    pid = proc_info['pid']
                    ppid = proc_info['ppid']
                    name = proc_info['name']
                    cmdline = ' '.join(proc_info['cmdline'])
                    
                    # 명령줄 길이 제한
                    if len(cmdline) > 50:
                        cmdline = cmdline[:47] + "..."
                    
                    print(f"{pid:<8} {ppid:<8} {name:<15} {cmdline:<50}")
                    
                    # 부모 프로세스 정보
                    parent_cmd = self._get_parent_cmdline(ppid)
                    if len(parent_cmd) > 50:
                        parent_cmd = parent_cmd[:47] + "..."
                    print(f"         └─ Parent: {parent_cmd}")
                
                # 자동 해결 시도
                print("\n자동 해결 시도 중...")
                self._auto_resolve_duplicate_feeders()
            
            # 나머지 프로세스 체크 (기존 로직)
            for proc_name in ["trader", "autoheal"]:
                pids = []
                
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = proc.info.get('cmdline', [])
                        cmdline_str = ' '.join(cmdline) if cmdline else ''
                        
                        if proc_name.lower() in cmdline_str.lower():
                            pids.append(proc.info['pid'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                self.running_processes[proc_name] = pids
                
                if pids:
                    print(f"✅ {proc_name:12} - 실행 중 (PID: {', '.join(map(str, pids))})")
                else:
                    print(f"❌ {proc_name:12} - 실행 중 아님")
        
        except Exception as e:
            print(f"⚠️  프로세스 체크 중 오류: {e}")

    def _auto_resolve_duplicate_feeders(self):
        """중복 Feeder 자동 해결"""
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, str(self.root / "guard" / "tools" / "kill_duplicate_feeders.py")],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print("   ✅ 중복 제거 완료")
            elif result.returncode == 1:
                print("   ℹ️  아무 작업도 필요 없음")
            elif result.returncode == 2:
                print("   ⚠️  부분적 성공")
            elif result.returncode == 3:
                print("   ❌ 접근 거부 (관리자 권한 필요)")
            else:
                print(f"   ❌ 자동 해결 실패 (exit code: {result.returncode})")
            
            # 결과 출력이 있으면 표시
            if result.stdout:
                print("\n출력:")
                for line in result.stdout.strip().split('\n')[-5:]:  # 마지막 5줄만
                    print(f"   {line}")
        
        except subprocess.TimeoutExpired:
            print("   ❌ 타임아웃 (30초)")
        except Exception as e:
            print(f"   ❌ 자동 해결 실패: {e}")

    # ========== 2. PID/Lock 파일 정리 ==========
    def cleanup_stale_files(self):
        """오래된 PID 및 Lock 파일 삭제 (Artifact 처리)"""
        self.print_header("2️⃣ PID/Lock 파일 정리")
        
        deleted_count = 0
        
        # PID 파일은 정보용으로만 사용, 삭제하지 않음
        print("ℹ️  PID 파일은 정보용으로 유지합니다 (삭제 안 함)")
        
        # singleton.lock 파일만 검증 후 정리
        try:
            lock_file = self.shared_data / "feeder.singleton.lock"
            if lock_file.exists():
                # 락을 보유한 PID가 살아있는지 확인
                try:
                    with open(lock_file, 'r') as f:
                        lock_pid = int(f.read().strip())
                    
                    # PID가 살아있는지 확인
                    if psutil and psutil.pid_exists(lock_pid):
                        print(f"ℹ️  Singleton lock은 PID {lock_pid}가 보유 중 (유지)")
                    else:
                        # 죽은 PID의 락 파일 삭제
                        lock_file.unlink()
                        self.deleted_files.append(str(lock_file.relative_to(self.root)))
                        deleted_count += 1
                        print(f"🗑️  삭제: {lock_file.relative_to(self.root)} (죽은 PID {lock_pid})")
                except:
                    # 파일 읽기 실패 시 삭제
                    lock_file.unlink()
                    self.deleted_files.append(str(lock_file.relative_to(self.root)))
                    deleted_count += 1
                    print(f"🗑️  삭제: {lock_file.relative_to(self.root)} (잘못된 형식)")
        except Exception as e:
            print(f"⚠️  Lock 파일 정리 중 오류: {e}")
        
        # 로그 Lock 파일 정리
        try:
            if self.logs_dir.exists():
                for lock_file in self.logs_dir.glob("*.lock"):
                    try:
                        lock_file.unlink()
                        self.deleted_files.append(str(lock_file.relative_to(self.root)))
                        deleted_count += 1
                        print(f"🗑️  삭제: {lock_file.relative_to(self.root)}")
                    except Exception as e:
                        print(f"⚠️  삭제 실패: {lock_file.name} - {e}")
        except Exception as e:
            print(f"⚠️  Lock 파일 정리 중 오류: {e}")
        
        if deleted_count == 0:
            print("✨ 삭제할 파일 없음 (깨끗함)")
        else:
            print(f"\n✅ 총 {deleted_count}개 파일 삭제 완료")

    # ========== 3. 로그 에러 스캔 ==========
    def scan_logs(self):
        """로그 파일에서 에러 검색"""
        self.print_header("3️⃣ 로그 에러 스캔")
        
        log_files = {
            "feeder": self.logs_dir / "feeder.log",
            "trader": self.logs_dir / "trader.log",
            "autoheal": self.logs_dir / "autoheal.log"
        }
        
        error_pattern = re.compile(r'(ERROR|FAIL|CRITICAL)', re.IGNORECASE)
        
        for name, log_path in log_files.items():
            self.print_subheader(f"{name.capitalize()} 로그")
            
            if not log_path.exists():
                print(f"⚠️  로그 파일 없음: {log_path.name}")
                self.log_errors[name] = []
                continue
            
            try:
                # 마지막 200줄 읽기
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    last_200 = lines[-200:] if len(lines) > 200 else lines
                
                # 에러 라인 찾기
                errors = []
                for line in last_200:
                    if error_pattern.search(line):
                        errors.append(line.strip())
                
                self.log_errors[name] = errors
                
                if errors:
                    print(f"🔴 {len(errors)}개 에러 발견:")
                    # 최대 10개만 출력
                    for i, error in enumerate(errors[:10], 1):
                        # 너무 긴 라인은 잘라서 출력
                        display_line = error[:120] + "..." if len(error) > 120 else error
                        print(f"   {i}. {display_line}")
                    
                    if len(errors) > 10:
                        print(f"   ... 외 {len(errors) - 10}개 더")
                else:
                    print("✅ 에러 없음")
            
            except Exception as e:
                print(f"⚠️  로그 읽기 실패: {e}")
                self.log_errors[name] = []

    # ========== 4. Preflight 체크 ==========
    def run_preflight_checks(self):
        """Preflight 체크 재실행"""
        self.print_header("4️⃣ Preflight 체크")
        
        try:
            # FileSourceReader 임포트 및 초기화
            sys.path.insert(0, str(self.root))
            
            from guard.ui.components.preflight_checker import PreFlightChecker
            from guard.ui.readers.file_sources import FileSourceReader

            # Reader 초기화
            file_reader = FileSourceReader()
            
            # Preflight Checker 초기화
            checker = PreFlightChecker(file_reader)
            
            # 환경 확인
            env = "testnet" if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true" else "mainnet"
            mode = "control"
            
            print(f"환경: {env.upper()}, 모드: {mode.upper()}\n")
            
            # 모든 체크 실행
            results = checker.run_all_checks(env, mode)
            
            # 필수 체크 (첫 5개)
            required_checks = results[:5]
            warning_checks = results[5:] if len(results) > 5 else []
            
            self.print_subheader("필수 게이트 (5개)")
            
            all_pass = True
            for check in required_checks:
                status_icon = "✅" if check.status == "PASS" else "❌"
                print(f"{status_icon} {check.name:20} - {check.status:6} - {check.message}")
                if check.status != "PASS":
                    all_pass = False
            
            if warning_checks:
                self.print_subheader("경고 체크")
                for check in warning_checks:
                    status_icon = "✅" if check.status == "PASS" else "⚠️"
                    print(f"{status_icon} {check.name:20} - {check.status:6} - {check.message}")
            
            # 최종 판정
            print("\n" + "-" * 70)
            if all_pass:
                print("🟢 시스템 정상 - START 가능")
            else:
                print("🔴 시스템 비정상 - 문제 해결 필요")
                
                # 실패한 체크 목록
                failed = [c for c in required_checks if c.status == "FAIL"]
                if failed:
                    print("\n실패한 필수 체크:")
                    for check in failed:
                        print(f"  - {check.name}: {check.message}")
        
        except ImportError as e:
            print(f"⚠️  Preflight 모듈 임포트 실패: {e}")
            print("   guard/ui/components/preflight_checker.py 파일을 확인하세요.")
        except Exception as e:
            print(f"⚠️  Preflight 체크 실패: {e}")
            import traceback
            traceback.print_exc()

    # ========== 5. 요약 출력 ==========
    def print_summary(self):
        """전체 요약 출력"""
        self.print_header("📊 요약")
        
        # 프로세스 상태
        if self.running_processes:
            running_count = sum(1 for pids in self.running_processes.values() if pids)
            total_count = len(self.running_processes)
            print(f"프로세스:     {running_count}/{total_count} 실행 중")
            
            # Feeder 중복 경고
            feeder_count = len(self.running_processes.get('feeder', []))
            if feeder_count > 1:
                print(f"              ⚠️  Feeder {feeder_count}개 중복 실행!")
        
        # 정리된 파일
        print(f"파일 정리:    {len(self.deleted_files)}개 삭제")
        
        # 로그 에러
        total_errors = sum(len(errors) for errors in self.log_errors.values())
        if total_errors > 0:
            print(f"로그 에러:    {total_errors}개 발견 🔴")
        else:
            print(f"로그 에러:    없음 ✅")
        
        print("\n" + "=" * 70)
        print(f"완료 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

    # ========== 메인 실행 ==========
    def run(self):
        """전체 헬스체크 실행"""
        print("\n")
        print("*" * 70)
        print("*" + " " * 68 + "*")
        print("*" + "   🏥 코인퀀트 시스템 헬스체크 & 복구 도구".center(68) + "*")
        print("*" + " " * 68 + "*")
        print("*" * 70)
        print(f"\n시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 1. 프로세스 체크
        self.check_processes()
        
        # 2. PID/Lock 정리
        self.cleanup_stale_files()
        
        # 3. 로그 스캔
        self.scan_logs()
        
        # 4. Preflight 체크
        self.run_preflight_checks()
        
        # 5. 요약
        self.print_summary()


def main():
    """메인 함수"""
    try:
        checker = HealthCheckRecover()
        checker.run()
        return 0
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단됨")
        return 1
    except Exception as e:
        print(f"\n\n❌ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
