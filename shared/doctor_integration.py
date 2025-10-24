#!/usr/bin/env python3
"""
Doctor Integration - UI에서 Doctor Runner를 호출하는 헬퍼
"""

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.atomic_io import read_json_atomic, write_json_atomic
from shared.environment_guardrails import get_repo_paths


class DoctorIntegration:
    """Doctor Integration - UI용 Doctor Runner 인터페이스"""
    
    def __init__(self):
        self.paths = get_repo_paths()
        self.trigger_file = self.paths["shared_data"] / "ops" / "doctor.run"
        self.progress_dir = self.paths["shared_data"] / "doctor"
        self.summary_file = self.paths["shared_data"] / "doctor" / "summary.json"
        self.lock_file = self.paths["shared_data"] / "doctor" / "doctor.lock"
    
    def trigger_doctor(self, mode: str = "quick") -> str:
        """Doctor 실행 트리거"""
        try:
            # 트리거 파일 생성
            trigger_data = {
                "mode": mode,
                "triggered_at": time.time(),
                "triggered_by": "ui"
            }
            
            write_json_atomic(self.trigger_file, trigger_data)
            
            # Doctor Runner 실행 (백그라운드)
            def run_doctor():
                try:
                    from shared.doctor_runner import run_doctor
                    run_doctor()
                except Exception as e:
                    print(f"Doctor execution failed: {e}")
            
            thread = threading.Thread(target=run_doctor, daemon=True)
            thread.start()
            
            return "Doctor 진단이 시작되었습니다."
            
        except Exception as e:
            return f"Doctor 실행 실패: {str(e)}"
    
    def get_progress(self) -> Dict[str, Any]:
        """진행 상황 조회"""
        try:
            # 락 파일 확인 (실행 중인지)
            is_running = self.lock_file.exists()
            
            if not is_running:
                # 실행 중이 아니면 최신 요약 반환
                if self.summary_file.exists():
                    summary = read_json_atomic(self.summary_file, {})
                    return {
                        "status": "completed",
                        "summary": summary,
                        "is_running": False
                    }
                else:
                    return {
                        "status": "not_started",
                        "summary": None,
                        "is_running": False
                    }
            
            # 실행 중이면 진행 상황 파일들 조회
            progress_files = list(self.progress_dir.glob("run_*.ndjson"))
            if not progress_files:
                return {
                    "status": "running",
                    "progress": [],
                    "is_running": True
                }
            
            # 가장 최신 진행 상황 파일 찾기
            latest_file = max(progress_files, key=lambda p: p.stat().st_mtime)
            
            # 진행 상황 읽기
            progress = []
            try:
                with open(latest_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            progress.append(json.loads(line))
            except Exception:
                pass
            
            return {
                "status": "running",
                "progress": progress,
                "is_running": True
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "is_running": False
            }
    
    def get_latest_report(self) -> Optional[str]:
        """최신 보고서 조회"""
        try:
            reports_dir = self.paths["shared_data_reports"]
            if not reports_dir.exists():
                return None
            
            # stack_doctor_*.md 파일들 찾기
            report_files = list(reports_dir.glob("stack_doctor_*.md"))
            if not report_files:
                return None
            
            # 가장 최신 파일
            latest_report = max(report_files, key=lambda p: p.stat().st_mtime)
            
            with open(latest_report, 'r', encoding='utf-8') as f:
                return f.read()
                
        except Exception as e:
            print(f"Report reading failed: {e}")
            return None
    
    def is_doctor_available(self) -> bool:
        """Doctor Runner 사용 가능 여부"""
        try:
            # Doctor Runner 모듈 임포트 가능한지 확인
            from shared.doctor_runner import DoctorRunner
            return True
        except ImportError:
            return False
        except Exception:
            return False


def create_doctor_ui_section():
    """UI용 Doctor 섹션 생성"""
    try:
        from shared.doctor_integration import DoctorIntegration
        
        doctor = DoctorIntegration()
        
        if not doctor.is_doctor_available():
            return "Doctor Runner를 사용할 수 없습니다."
        
        # Doctor 섹션 HTML
        ui_html = """
        <div style="margin: 1rem 0; padding: 1rem; border: 1px solid #444; border-radius: 8px; background-color: #1a1a1a;">
            <h4 style="margin: 0 0 1rem 0; color: #4CAF50;">🔍 System Doctor</h4>
            <div id="doctor-status">로딩 중...</div>
            <div style="margin-top: 1rem;">
                <button onclick="triggerDoctor()" style="background-color: #4CAF50; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                    진단 실행
                </button>
                <button onclick="refreshDoctorStatus()" style="background-color: #2196F3; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-left: 0.5rem;">
                    상태 새로고침
                </button>
            </div>
        </div>
        
        <script>
        function triggerDoctor() {
            fetch('/api/doctor/trigger', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    refreshDoctorStatus();
                });
        }
        
        function refreshDoctorStatus() {
            fetch('/api/doctor/status')
                .then(response => response.json())
                .then(data => {
                    updateDoctorStatus(data);
                });
        }
        
        function updateDoctorStatus(data) {
            const statusDiv = document.getElementById('doctor-status');
            
            if (data.is_running) {
                statusDiv.innerHTML = '<span style="color: #FF9800;">⏳ 진단 실행 중...</span>';
            } else if (data.status === 'completed') {
                const summary = data.summary;
                const passed = summary.summary.passed;
                const total = summary.summary.total_steps;
                const statusColor = passed === total ? '#4CAF50' : '#F44336';
                const statusIcon = passed === total ? '✅' : '❌';
                
                statusDiv.innerHTML = `
                    <div style="color: ${statusColor};">
                        ${statusIcon} 진단 완료: ${passed}/${total} 항목 통과
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.9em; color: #ccc;">
                        실행 시간: ${summary.duration_sec.toFixed(1)}초
                    </div>
                `;
            } else {
                statusDiv.innerHTML = '<span style="color: #9E9E9E;">💤 대기 중</span>';
            }
        }
        
        // 페이지 로드 시 상태 조회
        refreshDoctorStatus();
        
        // 5초마다 자동 새로고침
        setInterval(refreshDoctorStatus, 5000);
        </script>
        """
        
        return ui_html
        
    except Exception as e:
        return f"Doctor UI 생성 실패: {str(e)}"


if __name__ == "__main__":
    # 테스트
    doctor = DoctorIntegration()
    
    print("🔍 Doctor Integration 테스트")
    print(f"Doctor 사용 가능: {doctor.is_doctor_available()}")
    
    # Doctor 실행
    result = doctor.trigger_doctor("quick")
    print(f"트리거 결과: {result}")
    
    # 진행 상황 조회
    time.sleep(1)
    progress = doctor.get_progress()
    print(f"진행 상황: {progress['status']}")
    
    # 최신 보고서 조회
    report = doctor.get_latest_report()
    if report:
        print(f"최신 보고서: {len(report)} 문자")
    else:
        print("보고서 없음")
