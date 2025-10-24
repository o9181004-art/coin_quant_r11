#!/usr/bin/env python3
"""
Atomic I/O - Phase 2
Windows-safe atomic writes & readers with unified helper
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union
import sys

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.environment_guardrails import get_repo_paths


class AtomicIOError(Exception):
    """Atomic I/O 관련 오류"""
    pass


class AtomicWriter:
    """Windows-safe atomic writer"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 0.1):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.paths = get_repo_paths()
    
    def write_json(self, file_path: Union[str, Path], data: Dict[str, Any], 
                   ensure_dirs: bool = True) -> bool:
        """JSON 파일 atomic write"""
        try:
            file_path = Path(file_path)
            
            if ensure_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 임시 파일명 생성 (PID + UUID)
            temp_file = file_path.parent / f".tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}.json"
            
            # JSON 데이터 직렬화
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            
            # atomic write with retry
            return self._atomic_write_with_retry(temp_file, json_data, file_path)
            
        except Exception as e:
            raise AtomicIOError(f"JSON write failed for {file_path}: {e}")
    
    def write_text(self, file_path: Union[str, Path], content: str, 
                   encoding: str = 'utf-8', ensure_dirs: bool = True) -> bool:
        """텍스트 파일 atomic write"""
        try:
            file_path = Path(file_path)
            
            if ensure_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 임시 파일명 생성
            temp_file = file_path.parent / f".tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}.txt"
            
            # atomic write with retry
            return self._atomic_write_with_retry(temp_file, content, file_path, encoding)
            
        except Exception as e:
            raise AtomicIOError(f"Text write failed for {file_path}: {e}")
    
    def append_ndjson(self, file_path: Union[str, Path], data: Dict[str, Any],
                      ensure_dirs: bool = True) -> bool:
        """NDJSON 파일 append (atomic)"""
        try:
            file_path = Path(file_path)
            
            if ensure_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # NDJSON 라인 생성
            json_line = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
            
            # 파일에 직접 append (NDJSON은 append만 하므로 atomic write 불필요)
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json_line)
                f.flush()
                os.fsync(f.fileno())  # 디스크에 강제 쓰기
            
            return True
            
        except Exception as e:
            raise AtomicIOError(f"NDJSON append failed for {file_path}: {e}")
    
    def _atomic_write_with_retry(self, temp_file: Path, content: str, 
                                target_file: Path, encoding: str = 'utf-8') -> bool:
        """retry를 포함한 atomic write"""
        
        for attempt in range(self.max_retries):
            try:
                # 임시 파일에 쓰기
                with open(temp_file, 'w', encoding=encoding) as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())  # 디스크에 강제 쓰기
                
                # atomic replace (Windows-safe)
                temp_file.replace(target_file)
                
                return True
                
            except OSError as e:
                error_code = getattr(e, 'winerror', e.errno)
                
                if error_code == 183:  # ERROR_ALREADY_EXISTS (temp collision)
                    # 새로운 임시 파일명으로 재시도
                    temp_file = target_file.parent / f".tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
                    continue
                    
                elif error_code == 32:  # ERROR_SHARING_VIOLATION (file in use)
                    # 백오프 후 재시도
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    else:
                        raise AtomicIOError(f"File locked after {self.max_retries} attempts: {target_file}")
                        
                elif error_code == 2:  # ERROR_FILE_NOT_FOUND
                    # 디렉토리가 없을 수 있음
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    continue
                    
                else:
                    raise AtomicIOError(f"Write error (code {error_code}): {e}")
                    
            except Exception as e:
                raise AtomicIOError(f"Unexpected error during atomic write: {e}")
                
            finally:
                # 임시 파일 정리
                try:
                    temp_file.unlink(missing_ok=True)
                except Exception:
                    pass
        
        return False


class AtomicReader:
    """Atomic reader with tolerance for partial writes"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 0.05):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def read_json(self, file_path: Union[str, Path], 
                  default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """JSON 파일 atomic read"""
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return default or {}
            
            # retry를 포함한 read
            for attempt in range(self.max_retries):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if not content.strip():
                        return default or {}
                    
                    return json.loads(content)
                    
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    if attempt < self.max_retries - 1:
                        # 부분적 쓰기일 수 있음, 잠시 대기 후 재시도
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        # 마지막 시도에서도 실패하면 기본값 반환
                        print(f"Warning: Failed to read {file_path} after {self.max_retries} attempts: {e}")
                        return default or {}
                        
                except OSError as e:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        print(f"Warning: OS error reading {file_path}: {e}")
                        return default or {}
            
            return default or {}
            
        except Exception as e:
            print(f"Warning: Unexpected error reading {file_path}: {e}")
            return default or {}
    
    def read_text(self, file_path: Union[str, Path], 
                  default: str = "", encoding: str = 'utf-8') -> str:
        """텍스트 파일 atomic read"""
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return default
            
            # retry를 포함한 read
            for attempt in range(self.max_retries):
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                        
                except (UnicodeDecodeError, OSError) as e:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        print(f"Warning: Failed to read {file_path}: {e}")
                        return default
            
            return default
            
        except Exception as e:
            print(f"Warning: Unexpected error reading {file_path}: {e}")
            return default
    
    def read_ndjson_lines(self, file_path: Union[str, Path], 
                          max_lines: Optional[int] = None) -> list:
        """NDJSON 파일 읽기 (최근 N줄)"""
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return []
            
            lines = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        lines.append(data)
                        
                        # 최대 라인 수 제한
                        if max_lines and len(lines) >= max_lines:
                            lines = lines[-max_lines:]  # 최근 N줄만 유지
                            
                    except json.JSONDecodeError:
                        # 잘못된 JSON 라인은 건너뛰기
                        continue
            
            return lines
            
        except Exception as e:
            print(f"Warning: Failed to read NDJSON {file_path}: {e}")
            return []


# 전역 인스턴스들
atomic_writer = AtomicWriter()
atomic_reader = AtomicReader()


# 편의 함수들
def write_json_atomic(file_path: Union[str, Path], data: Dict[str, Any], 
                     ensure_dirs: bool = True) -> bool:
    """JSON 파일 atomic write"""
    return atomic_writer.write_json(file_path, data, ensure_dirs)


def read_json_atomic(file_path: Union[str, Path], 
                    default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """JSON 파일 atomic read"""
    return atomic_reader.read_json(file_path, default)


def write_text_atomic(file_path: Union[str, Path], content: str, 
                     encoding: str = 'utf-8', ensure_dirs: bool = True) -> bool:
    """텍스트 파일 atomic write"""
    return atomic_writer.write_text(file_path, content, encoding, ensure_dirs)


def read_text_atomic(file_path: Union[str, Path], 
                    default: str = "", encoding: str = 'utf-8') -> str:
    """텍스트 파일 atomic read"""
    return atomic_reader.read_text(file_path, default, encoding)


def append_ndjson_atomic(file_path: Union[str, Path], data: Dict[str, Any],
                        ensure_dirs: bool = True) -> bool:
    """NDJSON 파일 atomic append"""
    return atomic_writer.append_ndjson(file_path, data, ensure_dirs)


def read_ndjson_lines(file_path: Union[str, Path], 
                     max_lines: Optional[int] = None) -> list:
    """NDJSON 파일 읽기"""
    return atomic_reader.read_ndjson_lines(file_path, max_lines)


# 특화된 헬퍼 함수들
def write_health_atomic(component_name: str, health_data: Dict[str, Any]) -> bool:
    """컴포넌트 헬스 정보 atomic write"""
    paths = get_repo_paths()
    health_file = paths["shared_data"] / "health.json"
    
    # 기존 헬스 데이터 로드
    existing_health = read_json_atomic(health_file, {})
    existing_health[component_name] = health_data
    
    return write_json_atomic(health_file, existing_health)


def read_health_atomic(component_name: Optional[str] = None) -> Union[Dict[str, Any], Dict[str, Any]]:
    """헬스 정보 atomic read"""
    paths = get_repo_paths()
    health_file = paths["shared_data"] / "health.json"
    
    health_data = read_json_atomic(health_file, {})
    
    if component_name:
        return health_data.get(component_name, {})
    else:
        return health_data


def write_state_bus_atomic(state_data: Dict[str, Any]) -> bool:
    """상태 버스 atomic write"""
    paths = get_repo_paths()
    state_file = paths["shared_data"] / "state_bus.json"
    
    return write_json_atomic(state_file, state_data)


def read_state_bus_atomic() -> Dict[str, Any]:
    """상태 버스 atomic read"""
    paths = get_repo_paths()
    state_file = paths["shared_data"] / "state_bus.json"
    
    return read_json_atomic(state_file, {})


def append_alert_atomic(alert_data: Dict[str, Any]) -> bool:
    """알림 atomic append"""
    paths = get_repo_paths()
    alerts_file = paths["shared_data"] / "alerts.ndjson"
    
    # 타임스탬프 추가
    alert_data["timestamp"] = time.time()
    alert_data["datetime"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    return append_ndjson_atomic(alerts_file, alert_data)


def read_recent_alerts(max_alerts: int = 100) -> list:
    """최근 알림들 읽기"""
    paths = get_repo_paths()
    alerts_file = paths["shared_data"] / "alerts.ndjson"
    
    return read_ndjson_lines(alerts_file, max_alerts)


if __name__ == "__main__":
    # 직접 실행 시 테스트
    print("🔒 Atomic I/O - 테스트 실행")
    print("=" * 50)
    
    # 테스트 데이터
    test_data = {
        "test": True,
        "timestamp": time.time(),
        "message": "Atomic I/O 테스트"
    }
    
    # JSON write/read 테스트
    test_file = Path("shared_data/test_atomic.json")
    print(f"📝 JSON write 테스트: {test_file}")
    
    success = write_json_atomic(test_file, test_data)
    print(f"   Write: {'✅' if success else '❌'}")
    
    read_data = read_json_atomic(test_file)
    print(f"   Read: {'✅' if read_data == test_data else '❌'}")
    
    # NDJSON append 테스트
    test_ndjson = Path("shared_data/test_atomic.ndjson")
    print(f"\n📝 NDJSON append 테스트: {test_ndjson}")
    
    for i in range(3):
        alert_data = {"alert_id": i, "message": f"테스트 알림 {i}"}
        success = append_alert_atomic(alert_data)
        print(f"   Append {i}: {'✅' if success else '❌'}")
    
    recent_alerts = read_recent_alerts(5)
    print(f"   Read alerts: {len(recent_alerts)}개")
    
    # 헬스 테스트
    print(f"\n🏥 헬스 write/read 테스트")
    health_data = {"state": "GREEN", "last_update": time.time()}
    success = write_health_atomic("test_component", health_data)
    print(f"   Health write: {'✅' if success else '❌'}")
    
    read_health = read_health_atomic("test_component")
    print(f"   Health read: {'✅' if read_health == health_data else '❌'}")
    
    # 정리
    test_file.unlink(missing_ok=True)
    test_ndjson.unlink(missing_ok=True)
    
    print("\n✅ Atomic I/O 테스트 완료")
