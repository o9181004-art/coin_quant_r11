"""
원자적 파일 쓰기 유틸리티
Windows 파일락/경합 문제 해결을 위한 안전한 파일 I/O
"""

import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def atomic_write(
    file_path: Union[str, Path],
    content: Union[str, bytes],
    encoding: str = "utf-8",
    max_retries: int = 8,
    backoff_ms: int = 50,
) -> bool:
    """
    원자적 파일 쓰기 - Windows 파일락 문제 해결

    Args:
        file_path: 대상 파일 경로
        content: 쓰기할 내용 (문자열 또는 바이트)
        encoding: 텍스트 인코딩 (기본값: utf-8)
        max_retries: 최대 재시도 횟수 (기본값: 8)
        backoff_ms: 백오프 시작 시간 (밀리초, 기본값: 50)

    Returns:
        bool: 쓰기 성공 여부
    """
    file_path = Path(file_path)

    # 디렉토리 자동 생성
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 임시 파일 생성 (같은 드라이브에)
    temp_dir = file_path.parent
    temp_fd, temp_path = tempfile.mkstemp(
        prefix=f".{file_path.name}.tmp_", suffix="", dir=temp_dir
    )
    temp_path = Path(temp_path)

    try:
        # 임시 파일에 쓰기
        if isinstance(content, str):
            with open(temp_fd, "w", encoding=encoding) as f:
                f.write(content)
        else:
            with open(temp_fd, "wb") as f:
                f.write(content)

        # 원자적 교체 (재시도 포함)
        return safe_replace(temp_path, file_path, max_retries, backoff_ms)

    except Exception as e:
        logger.error(f"임시 파일 쓰기 실패: {e}")
        return False
    finally:
        # 임시 파일 정리
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass


def safe_replace(
    src: Path, dst: Path, max_retries: int = 8, backoff_ms: int = 50
) -> bool:
    """
    안전한 파일 교체 - Windows WinError 32 대응

    Args:
        src: 소스 파일 (임시 파일)
        dst: 대상 파일 (최종 파일)
        max_retries: 최대 재시도 횟수
        backoff_ms: 백오프 시작 시간 (밀리초)

    Returns:
        bool: 교체 성공 여부
    """
    for attempt in range(max_retries):
        try:
            # Windows에서 원자적 교체
            os.replace(src, dst)
            logger.debug(f"파일 교체 성공: {dst}")
            return True

        except PermissionError as e:
            if attempt < max_retries - 1:
                # 지수형 백오프
                delay_ms = backoff_ms * (2**attempt)
                logger.warning(
                    f"파일 교체 실패 (시도 {attempt + 1}/{max_retries}): {e}, {delay_ms}ms 대기"
                )
                time.sleep(delay_ms / 1000.0)
            else:
                logger.error(f"파일 교체 최종 실패: {e}")
                return False

        except OSError as e:
            if e.winerror == 32:  # WinError 32: 파일이 다른 프로세스에서 사용 중
                if attempt < max_retries - 1:
                    delay_ms = backoff_ms * (2**attempt)
                    logger.warning(
                        f"파일 사용 중 (시도 {attempt + 1}/{max_retries}): {e}, {delay_ms}ms 대기"
                    )
                    time.sleep(delay_ms / 1000.0)
                else:
                    logger.error(f"파일 사용 중 최종 실패: {e}")
                    return False
            else:
                logger.error(f"파일 교체 OS 에러: {e}")
                return False

        except Exception as e:
            logger.error(f"파일 교체 예상치 못한 에러: {e}")
            return False

    return False


def ensure_directory(path: Union[str, Path]) -> bool:
    """
    디렉토리 존재 보장

    Args:
        path: 디렉토리 경로

    Returns:
        bool: 성공 여부
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"디렉토리 생성 실패: {e}")
        return False


def safe_json_write(file_path: Union[str, Path], data: dict, indent: int = 2) -> bool:
    """
    안전한 JSON 파일 쓰기

    Args:
        file_path: 파일 경로
        data: JSON 데이터
        indent: 들여쓰기 (기본값: 2)

    Returns:
        bool: 성공 여부
    """
    import json

    try:
        content = json.dumps(data, indent=indent, ensure_ascii=False)
        return atomic_write(file_path, content)
    except Exception as e:
        logger.error(f"JSON 쓰기 실패: {e}")
        return False


def safe_text_append(
    file_path: Union[str, Path], content: str, encoding: str = "utf-8"
) -> bool:
    """
    안전한 텍스트 추가 쓰기 (로그 파일용)

    Args:
        file_path: 파일 경로
        content: 추가할 내용
        encoding: 인코딩

    Returns:
        bool: 성공 여부
    """
    file_path = Path(file_path)

    # 디렉토리 생성
    if not ensure_directory(file_path.parent):
        return False

    try:
        # 기존 내용 읽기
        existing_content = ""
        if file_path.exists():
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    existing_content = f.read()
            except Exception:
                pass  # 읽기 실패해도 계속 진행

        # 새 내용 추가
        new_content = existing_content + content

        # 원자적 쓰기
        return atomic_write(file_path, new_content, encoding)

    except Exception as e:
        logger.error(f"텍스트 추가 실패: {e}")
        return False


# 단위 테스트
if __name__ == "__main__":
    import json
    import tempfile

    # 테스트 디렉토리 생성
    test_dir = Path(tempfile.mkdtemp())

    try:
        # 테스트 1: 기본 텍스트 쓰기
        test_file = test_dir / "test.txt"
        assert atomic_write(test_file, "Hello World")
        assert test_file.read_text() == "Hello World"

        # 테스트 2: JSON 쓰기
        test_json = test_dir / "test.json"
        sample_data = {"symbol": "btcusdt", "price": 50000.0}
        assert safe_json_write(test_json, sample_data)
        assert json.loads(test_json.read_text()) == sample_data

        # 테스트 3: 텍스트 추가
        test_append = test_dir / "test_append.txt"
        assert safe_text_append(test_append, "Line 1\n")
        assert safe_text_append(test_append, "Line 2\n")
        assert test_append.read_text() == "Line 1\nLine 2\n"

        print("✅ 모든 테스트 통과")

    finally:
        # 테스트 정리
        shutil.rmtree(test_dir, ignore_errors=True)
