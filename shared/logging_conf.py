"""
안전한 로깅 설정
로그 롤테이션 및 핸들 유실 문제 해결
"""

import logging
import logging.handlers
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class SafeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """
    안전한 시간 기반 로그 롤테이션 핸들러
    핸들 유실 방지 및 자동 복구 기능
    """

    def __init__(
        self,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        backupCount: int = 7,
        encoding: str = "utf-8",
        delay: bool = True,
        utc: bool = False,
        atTime: Optional[Any] = None,
        checksum: bool = True,
        check_interval: int = 60,
    ):
        """
        Args:
            filename: 로그 파일 경로
            when: 롤오버 주기 ('midnight', 'H', 'M' 등)
            interval: 롤오버 간격
            backupCount: 보관할 백업 파일 수
            encoding: 파일 인코딩
            delay: 지연 열기 여부
            utc: UTC 시간 사용 여부
            atTime: 롤오버 시간 (midnight 사용 시)
            checksum: 체크섬 검증 여부
            check_interval: 헬스체크 간격 (초)
        """
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            utc=utc,
            atTime=atTime,
        )

        self.checksum = checksum
        self.check_interval = check_interval
        self.last_check = 0
        self.file_stats = {}
        self._lock = threading.RLock()

        # 헬스체크 타이머 시작
        if checksum:
            self._start_health_check()

    def _start_health_check(self):
        """헬스체크 타이머 시작"""

        def health_check_loop():
            while True:
                try:
                    time.sleep(self.check_interval)
                    self._perform_health_check()
                except Exception as e:
                    print(f"헬스체크 오류: {e}")

        thread = threading.Thread(target=health_check_loop, daemon=True)
        thread.start()

    def _perform_health_check(self):
        """로그 파일 헬스체크 수행"""
        try:
            with self._lock:
                current_time = time.time()

                # 체크 간격 확인
                if current_time - self.last_check < self.check_interval:
                    return

                self.last_check = current_time

                # 파일 존재 및 접근 가능 여부 확인
                if not os.path.exists(self.baseFilename):
                    self._reopen_handler()
                    return

                # 파일 크기 변화 확인
                try:
                    stat = os.stat(self.baseFilename)
                    current_size = stat.st_size
                    current_mtime = stat.st_mtime

                    if self.baseFilename in self.file_stats:
                        prev_size, prev_mtime = self.file_stats[self.baseFilename]

                        # 파일이 롤오버되었는지 확인 (크기가 크게 줄어들었거나 타임스탬프가 변경됨)
                        if (
                            current_size < prev_size * 0.5
                            or current_mtime != prev_mtime
                        ):
                            self._reopen_handler()

                    self.file_stats[self.baseFilename] = (current_size, current_mtime)

                except OSError:
                    # 파일 접근 불가 - 핸들러 재열기
                    self._reopen_handler()

        except Exception as e:
            print(f"헬스체크 수행 오류: {e}")

    def _reopen_handler(self):
        """핸들러 재열기"""
        try:
            if hasattr(self, "stream") and self.stream:
                self.stream.close()
                self.stream = None

            # 새 핸들러 열기
            self.stream = self._open()
            # 재열기 로그 제거 (무한 루프 방지)
            # print(f"로그 핸들러 재열기 완료: {self.baseFilename}")

        except Exception as e:
            print(f"핸들러 재열기 실패: {e}", file=sys.stderr)

    def emit(self, record):
        """로그 레코드 출력 (안전한 버전)"""
        try:
            # 헬스체크 수행 (간격 증가: 1초 → 10초, CPU 부하 감소)
            if self.checksum and time.time() - self.last_check > max(10, self.check_interval):
                self._perform_health_check()

            # 부모 클래스의 emit 호출
            super().emit(record)

        except Exception:
            # 핸들러 재열기 시도
            try:
                self._reopen_handler()
                super().emit(record)
            except Exception:
                self.handleError(record)


def setup_safe_logging(
    log_name: str,
    log_file: str,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    when: str = "midnight",
    encoding: str = "utf-8",
) -> logging.Logger:
    """
    안전한 로깅 설정

    Args:
        log_name: 로거 이름
        log_file: 로그 파일 경로
        level: 로그 레벨
        max_bytes: 최대 파일 크기 (바이트)
        backup_count: 백업 파일 수
        when: 롤오버 주기
        encoding: 파일 인코딩

    Returns:
        logging.Logger: 설정된 로거
    """
    # 로거 생성
    logger = logging.getLogger(log_name)
    logger.setLevel(level)

    # 기존 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 디렉토리 생성
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 안전한 핸들러 생성
    handler = SafeTimedRotatingFileHandler(
        filename=log_file,
        when=when,
        backupCount=backup_count,
        encoding=encoding,
        delay=True,  # 지연 열기로 안전성 향상
        checksum=True,  # 체크섬 검증 활성화
        check_interval=60,  # 60초마다 헬스체크
    )

    # 포맷터 설정
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # 핸들러 추가
    logger.addHandler(handler)

    # 루트 로거에 전파하지 않음 (중복 방지)
    logger.propagate = False

    return logger


def get_feeder_logger() -> logging.Logger:
    """Feeder 전용 안전한 로거"""
    return setup_safe_logging(
        log_name="feeder",
        log_file="logs/feeder.log",
        level=logging.INFO,
        when="midnight",
        backup_count=7,
    )


def get_trader_logger() -> logging.Logger:
    """Trader 전용 안전한 로거"""
    return setup_safe_logging(
        log_name="trader",
        log_file="logs/trader.log",
        level=logging.INFO,
        when="midnight",
        backup_count=7,
    )


def get_app_logger() -> logging.Logger:
    """App 전용 안전한 로거"""
    return setup_safe_logging(
        log_name="app",
        log_file="logs/app.log",
        level=logging.INFO,
        when="midnight",
        backup_count=7,
    )


# 운영 가이드 함수
def clear_log_content(log_file: str) -> bool:
    """
    로그 파일 내용만 지우기 (파일 핸들 유지)
    운영자가 로그를 정리할 때 사용

    Args:
        log_file: 로그 파일 경로

    Returns:
        bool: 성공 여부
    """
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("")
        return True
    except Exception as e:
        print(f"로그 내용 지우기 실패: {e}")
        return False


def get_log_status(log_file: str) -> Dict[str, Any]:
    """
    로그 파일 상태 확인

    Args:
        log_file: 로그 파일 경로

    Returns:
        Dict[str, Any]: 로그 상태 정보
    """
    try:
        if not os.path.exists(log_file):
            return {"exists": False, "size": 0, "modified": None}

        stat = os.stat(log_file)
        return {
            "exists": True,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "readable": os.access(log_file, os.R_OK),
            "writable": os.access(log_file, os.W_OK),
        }
    except Exception as e:
        return {"error": str(e)}


# 단위 테스트
if __name__ == "__main__":
    import tempfile
    import time

    # 테스트 디렉토리 생성
    test_dir = Path(tempfile.mkdtemp())
    test_log = test_dir / "test.log"

    try:
        # 테스트 1: 기본 로거 생성
        logger = setup_safe_logging("test", str(test_log))
        logger.info("테스트 로그 메시지")

        # 테스트 2: 로그 파일 존재 확인
        assert test_log.exists()

        # 테스트 3: 로그 상태 확인
        status = get_log_status(str(test_log))
        assert status["exists"] == True
        assert status["size"] > 0

        # 테스트 4: 로그 내용 지우기
        assert clear_log_content(str(test_log))
        status = get_log_status(str(test_log))
        assert status["size"] == 0

        print("✅ 모든 로깅 테스트 통과")

    finally:
        # 테스트 정리
        import shutil

        shutil.rmtree(test_dir, ignore_errors=True)
