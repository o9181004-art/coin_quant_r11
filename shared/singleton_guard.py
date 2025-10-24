#!/usr/bin/env python3
"""
크로스 프로세스 Singleton Guard
- 한 번에 하나의 프로세스만 실행 보장
- 파일 기반 락 메커니즘
"""
import json
import os
import pathlib
import socket
import time
from typing import Optional

# Windows에서는 msvcrt 사용
try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False
    # Linux/Mac에서는 portalocker 사용
    try:
        import portalocker
    except ImportError:
        portalocker = None


class SingletonAlreadyRunning(Exception):
    """이미 다른 인스턴스가 실행 중"""
    
    def __init__(self, owner_info: dict):
        self.owner_info = owner_info
        pid = owner_info.get('pid', 'unknown')
        start_time = owner_info.get('start_time', 'unknown')
        hostname = owner_info.get('hostname', 'unknown')
        
        message = (
            f"다른 인스턴스가 이미 실행 중입니다:\n"
            f"  PID: {pid}\n"
            f"  시작 시간: {start_time}\n"
            f"  호스트: {hostname}"
        )
        super().__init__(message)


class SingletonGuard:
    """Singleton 프로세스 가드"""
    
    def __init__(self, name: str, lock_dir: Optional[pathlib.Path] = None):
        """
        Args:
            name: 프로세스 이름 (예: "feeder", "trader")
            lock_dir: 락 파일 디렉토리 (기본: shared_data)
        """
        self.name = name
        
        if lock_dir is None:
            # 프로젝트 루트의 shared_data 사용
            project_root = pathlib.Path(__file__).parent.parent
            lock_dir = project_root / "shared_data"
        
        lock_dir.mkdir(parents=True, exist_ok=True)
        
        self.lock_file = lock_dir / f"{name}.singleton.lock"
        self.lock_handle = None
        self.is_locked = False
    
    def acquire(self) -> bool:
        """
        락 획득 시도
        
        Returns:
            True: 락 획득 성공
            
        Raises:
            SingletonAlreadyRunning: 이미 다른 인스턴스가 실행 중
        """
        try:
            # 락 파일 열기 (없으면 생성)
            self.lock_handle = open(self.lock_file, 'a+', encoding='utf-8')
            
            # 비차단 락 획득 시도
            if WINDOWS:
                # Windows: msvcrt 사용
                try:
                    msvcrt.locking(self.lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                except OSError:
                    locked = False
            else:
                # Linux/Mac: portalocker 사용
                if portalocker is None:
                    raise ImportError("portalocker가 설치되지 않았습니다. pip install portalocker")
                
                try:
                    portalocker.lock(self.lock_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
                    locked = True
                except portalocker.LockException:
                    locked = False
            
            if locked:
                # 락 획득 성공 - 프로세스 정보 기록
                self.is_locked = True
                self._write_owner_info()
                return True
            else:
                # 락 획득 실패 - 다른 인스턴스가 실행 중
                owner_info = self._read_owner_info()
                raise SingletonAlreadyRunning(owner_info)
        
        except SingletonAlreadyRunning:
            # 이미 실행 중 - 예외 전파
            if self.lock_handle:
                self.lock_handle.close()
                self.lock_handle = None
            raise
        
        except Exception as e:
            # 기타 오류
            if self.lock_handle:
                self.lock_handle.close()
                self.lock_handle = None
            raise RuntimeError(f"락 획득 중 오류: {e}")
    
    def release(self):
        """락 해제"""
        if not self.is_locked:
            return
        
        try:
            if self.lock_handle:
                # 락 파일 비우기
                self.lock_handle.seek(0)
                self.lock_handle.truncate()
                
                # 락 해제
                if WINDOWS:
                    try:
                        msvcrt.locking(self.lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except:
                        pass
                else:
                    if portalocker:
                        try:
                            portalocker.unlock(self.lock_handle)
                        except:
                            pass
                
                self.lock_handle.close()
                self.lock_handle = None
            
            # 락 파일 삭제 시도 (선택사항)
            try:
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except:
                pass
            
            self.is_locked = False
        
        except Exception:
            pass
    
    def _write_owner_info(self):
        """현재 프로세스 정보를 락 파일에 기록"""
        try:
            owner_info = {
                "pid": os.getpid(),
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "start_ts": time.time(),
                "hostname": socket.gethostname(),
                "name": self.name
            }
            
            self.lock_handle.seek(0)
            self.lock_handle.truncate()
            self.lock_handle.write(json.dumps(owner_info, ensure_ascii=False, indent=2))
            self.lock_handle.flush()
        
        except Exception:
            pass
    
    def _read_owner_info(self) -> dict:
        """락 파일에서 소유자 정보 읽기"""
        try:
            if self.lock_file.exists():
                with open(self.lock_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
        except Exception:
            pass
        
        return {"pid": "unknown", "start_time": "unknown", "hostname": "unknown"}
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.release()
        return False
    
    def __del__(self):
        """소멸자 - 락 해제"""
        self.release()


# 편의 함수
def acquire(name: str, lock_dir: Optional[pathlib.Path] = None) -> SingletonGuard:
    """
    Singleton 락 획득
    
    Args:
        name: 프로세스 이름
        lock_dir: 락 디렉토리 (선택사항)
        
    Returns:
        SingletonGuard 인스턴스
        
    Raises:
        SingletonAlreadyRunning: 이미 실행 중
    
    Example:
        guard = acquire("feeder")
        try:
            # 프로세스 실행
            ...
        finally:
            guard.release()
    """
    guard = SingletonGuard(name, lock_dir)
    guard.acquire()
    return guard


def is_running(name: str, lock_dir: Optional[pathlib.Path] = None) -> Optional[dict]:
    """
    프로세스가 실행 중인지 확인
    
    Args:
        name: 프로세스 이름
        lock_dir: 락 디렉토리 (선택사항)
        
    Returns:
        실행 중이면 소유자 정보 dict, 아니면 None
    """
    guard = SingletonGuard(name, lock_dir)
    
    try:
        guard.acquire()
        guard.release()
        return None  # 실행 중 아님
    except SingletonAlreadyRunning as e:
        return e.owner_info  # 실행 중

