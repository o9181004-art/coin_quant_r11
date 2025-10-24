#!/usr/bin/env python3
"""
Resource & Stability Checks - Phase 6
Memory pressure, duplicate prevention, log rotation
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.atomic_io import append_alert_atomic, read_json_atomic
from shared.environment_guardrails import (check_service_pid_lock,
                                           get_repo_paths)


class ResourceStabilityMonitor:
    """리소스 및 안정성 모니터"""
    
    def __init__(self):
        self.paths = get_repo_paths()
        self.memory_threshold = 90.0  # 90% 메모리 사용률 임계값
        self.last_memory_warn = 0
        self.memory_warn_interval = 3600  # 1시간 간격
        
    def check_memory_pressure(self) -> Tuple[bool, Dict[str, Any]]:
        """메모리 압박 확인"""
        try:
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            result = {
                "memory_percent": memory_percent,
                "available_gb": memory.available / (1024**3),
                "total_gb": memory.total / (1024**3),
                "threshold_exceeded": memory_percent > self.memory_threshold,
                "warning_issued": False
            }
            
            # 임계값 초과 시 경고 (1시간당 1회)
            if result["threshold_exceeded"]:
                current_time = time.time()
                if current_time - self.last_memory_warn > self.memory_warn_interval:
                    self._issue_memory_warning(memory_percent)
                    self.last_memory_warn = current_time
                    result["warning_issued"] = True
            
            return not result["threshold_exceeded"], result
            
        except Exception as e:
            return False, {"error": str(e)}
    
    def _issue_memory_warning(self, memory_percent: float):
        """메모리 경고 발행"""
        try:
            alert_data = {
                "level": "WARN",
                "component": "resource_monitor",
                "message": f"High memory usage: {memory_percent:.1f}%",
                "timestamp": time.time(),
                "action": "Reduce active symbols to whitelist"
            }
            append_alert_atomic(alert_data)
            print(f"⚠️ 메모리 사용률 높음: {memory_percent:.1f}%")
            
        except Exception as e:
            print(f"메모리 경고 발행 실패: {e}")
    
    def check_duplicate_prevention(self) -> Tuple[bool, Dict[str, Any]]:
        """중복 프로세스 방지 확인"""
        try:
            services = ["feeder", "trader", "ares", "uds", "autoheal"]
            duplicates = []
            
            for service in services:
                is_running, pid = check_service_pid_lock(service)
                if is_running:
                    # 실제 프로세스 확인
                    try:
                        process = psutil.Process(pid)
                        cmdline = " ".join(process.cmdline())
                        if service not in cmdline:
                            duplicates.append(f"{service}: PID {pid} not matching")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # PID 락은 있지만 프로세스가 없음 (stale)
                        pass
            
            result = {
                "duplicates_found": len(duplicates),
                "duplicate_details": duplicates,
                "services_checked": len(services)
            }
            
            return len(duplicates) == 0, result
            
        except Exception as e:
            return False, {"error": str(e)}
    
    def check_log_rotation(self) -> Tuple[bool, Dict[str, Any]]:
        """로그 회전 확인"""
        try:
            log_dirs = [
                self.paths["logs"],
                self.paths["shared_data"] / "logs"
            ]
            
            rotation_issues = []
            total_log_files = 0
            old_log_files = 0
            
            for log_dir in log_dirs:
                if log_dir.exists():
                    for log_file in log_dir.glob("*.log"):
                        total_log_files += 1
                        
                        # 파일 크기 확인 (>100MB)
                        file_size_mb = log_file.stat().st_size / (1024**2)
                        if file_size_mb > 100:
                            rotation_issues.append(f"{log_file.name}: {file_size_mb:.1f}MB")
                        
                        # 파일 나이 확인 (>7일)
                        file_age_days = (time.time() - log_file.stat().st_mtime) / (24 * 3600)
                        if file_age_days > 7:
                            old_log_files += 1
            
            result = {
                "total_log_files": total_log_files,
                "old_log_files": old_log_files,
                "rotation_issues": rotation_issues,
                "large_files": len(rotation_issues)
            }
            
            return len(rotation_issues) == 0, result
            
        except Exception as e:
            return False, {"error": str(e)}
    
    def check_disk_space(self) -> Tuple[bool, Dict[str, Any]]:
        """디스크 공간 확인"""
        try:
            disk_usage = psutil.disk_usage(str(self.paths["repo_root"]))
            free_gb = disk_usage.free / (1024**3)
            total_gb = disk_usage.total / (1024**3)
            free_percent = (disk_usage.free / disk_usage.total) * 100
            
            result = {
                "free_gb": free_gb,
                "total_gb": total_gb,
                "free_percent": free_percent,
                "low_space": free_gb < 1.0  # 1GB 미만
            }
            
            return not result["low_space"], result
            
        except Exception as e:
            return False, {"error": str(e)}
    
    def run_all_checks(self) -> Dict[str, Any]:
        """모든 리소스 및 안정성 체크 실행"""
        print("🔧 Resource & Stability Checks")
        print("=" * 50)
        
        results = {
            "memory": self.check_memory_pressure(),
            "duplicates": self.check_duplicate_prevention(),
            "log_rotation": self.check_log_rotation(),
            "disk_space": self.check_disk_space()
        }
        
        # 결과 출력
        for check_name, (success, details) in results.items():
            status = "✅" if success else "❌"
            print(f"{status} {check_name}: {'PASS' if success else 'FAIL'}")
            
            if not success and "error" not in details:
                if check_name == "memory" and details.get("threshold_exceeded"):
                    print(f"   메모리 사용률: {details['memory_percent']:.1f}%")
                elif check_name == "duplicates" and details.get("duplicates_found", 0) > 0:
                    print(f"   중복 발견: {details['duplicates_found']}개")
                elif check_name == "log_rotation" and details.get("large_files", 0) > 0:
                    print(f"   큰 로그 파일: {details['large_files']}개")
                elif check_name == "disk_space" and details.get("low_space"):
                    print(f"   디스크 여유공간: {details['free_gb']:.1f}GB")
        
        # 전체 성공 여부
        all_passed = all(success for success, _ in results.values())
        print(f"\n전체 상태: {'✅ PASS' if all_passed else '❌ FAIL'}")
        
        return {
            "overall_success": all_passed,
            "checks": results,
            "timestamp": time.time()
        }


# 전역 인스턴스
resource_monitor = ResourceStabilityMonitor()


def check_resource_stability() -> Dict[str, Any]:
    """리소스 및 안정성 체크 실행"""
    return resource_monitor.run_all_checks()


if __name__ == "__main__":
    # 직접 실행 시 리소스 체크
    print("🔧 Resource & Stability Monitor - 독립 실행")
    results = check_resource_stability()
    
    if results["overall_success"]:
        print("\n🎉 모든 리소스 및 안정성 체크 통과!")
    else:
        print("\n⚠️ 일부 리소스 또는 안정성 문제 발견")
