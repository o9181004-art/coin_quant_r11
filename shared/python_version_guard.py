#!/usr/bin/env python3
"""
Python 3.11 Runtime Guard
프로젝트 venv에서 Python 3.11로만 실행되도록 강제
"""

import sys
from pathlib import Path


def enforce_python_311_venv():
    """
    Python 3.11 버전과 venv 사용 강제
    
    조건:
    1. Python 버전이 3.11.x여야 함
    2. 현재 인터프리터가 프로젝트 venv의 것이어야 함
    
    조건 불만족 시 즉시 종료
    """
    # Python 버전 체크
    version_info = sys.version_info
    if version_info.major != 3 or version_info.minor != 11:
        print(
            f"❌ Python 3.11 필수! 현재 버전: {version_info.major}.{version_info.minor}.{version_info.micro}",
            file=sys.stderr
        )
        print(f"   실행 경로: {sys.executable}", file=sys.stderr)
        print(f"   힌트: 프로젝트 venv (Python 3.11)를 사용하세요.", file=sys.stderr)
        print(f"   명령어: venv\\Scripts\\python.exe -m <module>", file=sys.stderr)
        sys.exit(1)
    
    # venv 체크 (프로젝트 루트 기준)
    try:
        # 현재 실행 파일 경로
        current_python = Path(sys.executable).resolve()
        
        # 프로젝트 루트 찾기 (__file__ 기준 상위 디렉토리)
        project_root = Path(__file__).resolve().parent.parent
        
        # 예상되는 venv 경로들
        expected_venv_paths = [
            project_root / "venv" / "Scripts" / "python.exe",
            project_root / ".venv" / "Scripts" / "python.exe",
            project_root / "venv" / "Scripts" / "pythonw.exe",
            project_root / ".venv" / "Scripts" / "pythonw.exe",
        ]
        
        # Linux/Mac 경로도 지원
        if sys.platform != "win32":
            expected_venv_paths.extend([
                project_root / "venv" / "bin" / "python",
                project_root / ".venv" / "bin" / "python",
                project_root / "venv" / "bin" / "python3",
                project_root / ".venv" / "bin" / "python3",
            ])
        
        # 현재 Python이 venv 중 하나인지 확인
        is_in_venv = any(current_python == p.resolve() for p in expected_venv_paths if p.exists())
        
        if not is_in_venv:
            # VIRTUAL_ENV 환경변수로도 확인
            virtual_env = Path(sys.prefix)
            if virtual_env == Path(sys.base_prefix):
                # venv가 아님
                print(
                    f"❌ 프로젝트 venv에서 실행해야 합니다!",
                    file=sys.stderr
                )
                print(f"   현재 인터프리터: {current_python}", file=sys.stderr)
                print(f"   프로젝트 루트: {project_root}", file=sys.stderr)
                print(f"   예상 venv 경로: {expected_venv_paths[0]}", file=sys.stderr)
                print(f"   힌트: venv\\Scripts\\python.exe -m <module>", file=sys.stderr)
                sys.exit(1)
    
    except Exception as e:
        print(f"⚠️ venv 검증 실패: {e}", file=sys.stderr)
        print(f"   실행은 계속되나, venv 사용을 권장합니다.", file=sys.stderr)
    
    # 성공 - 로그 출력 (stderr로 출력하여 서비스 로그와 분리)
    print(
        f"✅ Python {version_info.major}.{version_info.minor}.{version_info.micro} (venv) 확인 완료",
        file=sys.stderr
    )


def get_venv_python_path() -> Path:
    """
    프로젝트 venv의 Python 경로 반환
    
    Returns:
        Path: venv Python 실행 파일 경로
    """
    project_root = Path(__file__).resolve().parent.parent
    
    if sys.platform == "win32":
        venv_python = project_root / "venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = project_root / "venv" / "bin" / "python"
        if not venv_python.exists():
            venv_python = project_root / ".venv" / "bin" / "python"
    
    return venv_python


if __name__ == "__main__":
    # 직접 실행 시 검증 수행
    enforce_python_311_venv()
    print("✅ 모든 검증 통과")
