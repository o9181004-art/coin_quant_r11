#!/usr/bin/env python3
"""
Auto-Heal Service
Production-grade auto-healing service with FSM
"""

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from .auto_heal_fsm import get_auto_heal_fsm
from .centralized_path_registry import get_path_registry


class AutoHealService:
    """Auto-Heal 서비스"""
    
    def __init__(self, repo_root: Path):
        self.logger = logging.getLogger(__name__)
        self.repo_root = repo_root
        self.path_registry = get_path_registry(repo_root)
        self.auto_heal_fsm = get_auto_heal_fsm(repo_root)
        
        self.running = False
        self.start_time = time.time()
        
        # PID 파일
        self.runtime_dir = self.repo_root / ".runtime"
        self.runtime_dir.mkdir(exist_ok=True)
        self.pid_file = self.runtime_dir / "auto_heal.pid"
        
        # 시작 로그
        self._log_startup_info()
    
    def _log_startup_info(self):
        """시작 정보 로깅"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 AUTO-HEAL SERVICE STARTUP")
        self.logger.info(f"ROOT={self.repo_root}")
        self.logger.info(f"PY={sys.executable}")
        self.logger.info(f"PID={os.getpid()}")
        self.logger.info("=" * 60)
    
    def start(self):
        """서비스 시작"""
        if self.running:
            self.logger.warning("Auto-Heal service already running")
            return
        
        # PID 파일 작성
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            self.logger.error(f"Failed to write PID file: {e}")
            return
        
        # 시그널 핸들러 설정
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.running = True
        self.logger.info("🚀 Auto-Heal service started")
        
        try:
            # 메인 루프
            while self.running:
                self._run_heal_cycle()
                time.sleep(30)  # 30초마다 체크
                
        except KeyboardInterrupt:
            self.logger.info("Auto-Heal service stopped by user")
        except Exception as e:
            self.logger.error(f"Auto-Heal service error: {e}")
        finally:
            self._cleanup()
    
    def stop(self):
        """서비스 중지"""
        self.running = False
        self.logger.info("Auto-Heal service stopping...")
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        self.logger.info(f"Received signal {signum}")
        self.stop()
    
    def _run_heal_cycle(self):
        """치료 사이클 실행"""
        try:
            # 1. 헬스 평가
            services = self.auto_heal_fsm.assess_health()
            self.logger.debug(f"Health assessment completed: {len(services)} services")
            
            # 2. 치료 결정
            decisions = self.auto_heal_fsm.make_heal_decisions()
            if not decisions:
                self.logger.debug("No heal decisions needed")
                return
            
            self.logger.info(f"Generated {len(decisions)} heal decisions")
            
            # 3. 치료 액션 실행
            results = self.auto_heal_fsm.execute_heal_actions(decisions)
            
            # 4. 결과 로깅
            for service, success in results.items():
                if success:
                    self.logger.info(f"✅ Heal action successful for {service}")
                else:
                    self.logger.error(f"❌ Heal action failed for {service}")
            
            # 5. 통계 로깅
            stats = self.auto_heal_fsm.get_stats()
            self.logger.info(f"Auto-Heal stats: health_score={stats['health_score']:.1f}%, restarts_last_hour={stats['restarts_last_hour']}")
            
        except Exception as e:
            self.logger.error(f"Heal cycle error: {e}")
    
    def _cleanup(self):
        """정리 작업"""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
            self.logger.info("Auto-Heal service cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="Auto-Heal Service")
    parser.add_argument("--start", action="store_true", help="Start the service")
    parser.add_argument("--stop", action="store_true", help="Stop the service")
    parser.add_argument("--status", action="store_true", help="Check service status")
    
    args = parser.parse_args()
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 프로젝트 루트 자동 감지
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "shared").exists() and (parent / "guard").exists():
            repo_root = parent
            break
    else:
        print("❌ Could not find project root")
        return 1
    
    service = AutoHealService(repo_root)
    
    if args.start:
        service.start()
    elif args.stop:
        service.stop()
    elif args.status:
        # 상태 조회
        if service.pid_file.exists():
            try:
                with open(service.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                import psutil
                if psutil.pid_exists(pid):
                    print(f"🟢 Auto-Heal service is running (PID: {pid})")
                else:
                    print("⚪ Auto-Heal service not running (stale PID file)")
            except Exception:
                print("⚪ Auto-Heal service status unknown")
        else:
            print("⚪ Auto-Heal service not running")
    else:
        parser.print_help()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
