#!/usr/bin/env python3
"""
Robust Health Reader
Schema-robust and unit-safe health file reader with timestamp parsing
Updated to use new health_writer.py for Windows-safe reading
"""

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class RobustHealthReader:
    """강화된 헬스 파일 리더"""
    
    def __init__(self):
        self.thresholds = {
            "positions": 60,
            "ares": 75,
            "trader": 300,
            "env": 300,
            "integration": 90
        }
    
    def parse_timestamp(self, ts: Union[int, float, str]) -> Optional[float]:
        """타임스탬프 파싱 (epoch seconds/ms, ISO string 지원)"""
        if ts is None:
            return None
        
        try:
            # 정수/실수 처리
            if isinstance(ts, (int, float)):
                # 밀리초 감지 (> 10^12)
                if ts > 1e12:
                    return ts / 1000.0
                else:
                    return float(ts)
            
            # 문자열 처리 (ISO 형식)
            if isinstance(ts, str):
                # ISO 형식 파싱
                if 'T' in ts or 'Z' in ts or '+' in ts:
                    # ISO 8601 형식
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    return dt.timestamp()
                else:
                    # 숫자 문자열
                    return float(ts)
            
            return None
            
        except (ValueError, TypeError, OverflowError):
            return None
    
    def validate_age(self, age_seconds: float) -> bool:
        """나이 유효성 검증"""
        if age_seconds < 0 or age_seconds > (10 * 365 * 24 * 3600):  # 10년
            return False
        return True
    
    def read_json_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """JSON 파일 읽기 (Windows-safe, non-locking)"""
        if not file_path.exists():
            return None
        
        # Retry logic for Windows-safe reading
        for attempt in range(5):
            try:
                # Check if file is being written (recent modification)
                file_age = time.time() - file_path.stat().st_mtime
                if file_age < 0.1:  # Very recent, might be mid-write
                    if attempt < 4:
                        jitter_ms = random.uniform(20, 40)
                        time.sleep(jitter_ms / 1000.0)
                        continue
                
                # Read file (short-lived handle)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse JSON
                data = json.loads(content)
                
                logger.debug(f"health_read_ok file={file_path.name} attempt={attempt + 1}")
                return data
                
            except json.JSONDecodeError as e:
                logger.warning(f"health_read_retry file={file_path.name} attempt={attempt + 1} err=json_decode")
                if attempt < 4:
                    jitter_ms = random.uniform(20, 40)
                    time.sleep(jitter_ms / 1000.0)
                    continue
                else:
                    logger.error(f"health_read_failed file={file_path.name} err=json_decode_failed")
                    return None
                    
            except Exception as e:
                logger.warning(f"health_read_retry file={file_path.name} attempt={attempt + 1} err={e}")
                if attempt < 4:
                    jitter_ms = random.uniform(20, 40)
                    time.sleep(jitter_ms / 1000.0)
                    continue
                else:
                    logger.error(f"health_read_failed file={file_path.name} err={e}")
                    return None
        
        return None
    
    def read_ndjson_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """NDJSON 파일 읽기"""
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            entries = []
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            
            return entries
            
        except Exception:
            return []
    
    def get_positions_health(self, file_path: Path) -> Dict[str, Any]:
        """포지션 헬스 정보 조회"""
        data = self.read_json_file(file_path)
        if not data:
            return {
                "status": "missing",
                "age": None,
                "raw_ts": None,
                "parsed_ts": None,
                "threshold": self.thresholds["positions"],
                "pass": False,
                "error": "File not found or invalid JSON"
            }
        
        # 키 선택: snapshot_ts 우선
        raw_ts = data.get("snapshot_ts") or data.get("timestamp")
        parsed_ts = self.parse_timestamp(raw_ts)
        
        if parsed_ts is None:
            return {
                "status": "timestamp_invalid",
                "age": None,
                "raw_ts": raw_ts,
                "parsed_ts": None,
                "threshold": self.thresholds["positions"],
                "pass": False,
                "error": "Invalid timestamp"
            }
        
        age = time.time() - parsed_ts
        if not self.validate_age(age):
            return {
                "status": "timestamp_invalid",
                "age": age,
                "raw_ts": raw_ts,
                "parsed_ts": parsed_ts,
                "threshold": self.thresholds["positions"],
                "pass": False,
                "error": "Age out of valid range"
            }
        
        pass_status = age <= self.thresholds["positions"]
        
        return {
            "status": "ok" if pass_status else "stale",
            "age": age,
            "raw_ts": raw_ts,
            "parsed_ts": parsed_ts,
            "threshold": self.thresholds["positions"],
            "pass": pass_status,
            "error": None
        }
    
    def get_ares_health(self, file_path: Path) -> Dict[str, Any]:
        """ARES 헬스 정보 조회"""
        data = self.read_json_file(file_path)
        if not data:
            return {
                "status": "missing",
                "age": None,
                "raw_ts": None,
                "parsed_ts": None,
                "threshold": self.thresholds["ares"],
                "pass": False,
                "error": "File not found or invalid JSON"
            }
        
        # 키 선택: last_signal_update 우선
        raw_ts = data.get("data", {}).get("last_signal_update") or data.get("timestamp")
        parsed_ts = self.parse_timestamp(raw_ts)
        
        if parsed_ts is None:
            return {
                "status": "timestamp_invalid",
                "age": None,
                "raw_ts": raw_ts,
                "parsed_ts": None,
                "threshold": self.thresholds["ares"],
                "pass": False,
                "error": "Invalid timestamp"
            }
        
        age = time.time() - parsed_ts
        if not self.validate_age(age):
            return {
                "status": "timestamp_invalid",
                "age": age,
                "raw_ts": raw_ts,
                "parsed_ts": parsed_ts,
                "threshold": self.thresholds["ares"],
                "pass": False,
                "error": "Age out of valid range"
            }
        
        pass_status = age <= self.thresholds["ares"]
        
        return {
            "status": "ok" if pass_status else "stale",
            "age": age,
            "raw_ts": raw_ts,
            "parsed_ts": parsed_ts,
            "threshold": self.thresholds["ares"],
            "pass": pass_status,
            "error": None
        }
    
    def get_trader_health(self, file_path: Path) -> Dict[str, Any]:
        """트레이더 헬스 정보 조회"""
        data = self.read_json_file(file_path)
        if not data:
            return {
                "status": "missing",
                "age": None,
                "raw_ts": None,
                "parsed_ts": None,
                "threshold": self.thresholds["trader"],
                "pass": False,
                "error": "File not found or invalid JSON"
            }
        
        # 키 선택: 가장 최신 타임스탬프 선택
        candidates = []
        
        # heartbeat_ts
        if "data" in data and "heartbeat_ts" in data["data"]:
            candidates.append(("heartbeat_ts", data["data"]["heartbeat_ts"]))
        
        # balances.updated_ts
        if "data" in data and "balances" in data["data"]:
            balances = data["data"]["balances"]
            if "updated_ts" in balances:
                candidates.append(("balances.updated_ts", balances["updated_ts"]))
            elif "fresh_ts" in balances:
                candidates.append(("balances.fresh_ts", balances["fresh_ts"]))
        
        # ts
        if "timestamp" in data:
            candidates.append(("timestamp", data["timestamp"]))
        
        # 가장 최신 타임스탬프 선택
        best_ts = None
        best_key = None
        for key, ts in candidates:
            parsed = self.parse_timestamp(ts)
            if parsed is not None and (best_ts is None or parsed > best_ts):
                best_ts = parsed
                best_key = key
        
        if best_ts is None:
            return {
                "status": "timestamp_invalid",
                "age": None,
                "raw_ts": None,
                "parsed_ts": None,
                "threshold": self.thresholds["trader"],
                "pass": False,
                "error": "No valid timestamp found"
            }
        
        age = time.time() - best_ts
        if not self.validate_age(age):
            return {
                "status": "timestamp_invalid",
                "age": age,
                "raw_ts": best_key,
                "parsed_ts": best_ts,
                "threshold": self.thresholds["trader"],
                "pass": False,
                "error": "Age out of valid range"
            }
        
        pass_status = age <= self.thresholds["trader"]
        
        return {
            "status": "ok" if pass_status else "stale",
            "age": age,
            "raw_ts": best_key,
            "parsed_ts": best_ts,
            "threshold": self.thresholds["trader"],
            "pass": pass_status,
            "error": None
        }
    
    def get_env_health(self, file_path: Path) -> Dict[str, Any]:
        """환경 헬스 정보 조회"""
        data = self.read_json_file(file_path)
        if not data:
            return {
                "status": "missing",
                "age": None,
                "raw_ts": None,
                "parsed_ts": None,
                "threshold": self.thresholds["env"],
                "pass": False,
                "error": "File not found or invalid JSON"
            }
        
        # 키 선택: ts 우선, fallback snapshot_ts
        raw_ts = data.get("ts") or data.get("snapshot_ts") or data.get("timestamp")
        parsed_ts = self.parse_timestamp(raw_ts)
        
        if parsed_ts is None:
            return {
                "status": "timestamp_invalid",
                "age": None,
                "raw_ts": raw_ts,
                "parsed_ts": None,
                "threshold": self.thresholds["env"],
                "pass": False,
                "error": "Invalid timestamp"
            }
        
        age = time.time() - parsed_ts
        if not self.validate_age(age):
            return {
                "status": "timestamp_invalid",
                "age": age,
                "raw_ts": raw_ts,
                "parsed_ts": parsed_ts,
                "threshold": self.thresholds["env"],
                "pass": False,
                "error": "Age out of valid range"
            }
        
        pass_status = age <= self.thresholds["env"]
        
        return {
            "status": "ok" if pass_status else "stale",
            "age": age,
            "raw_ts": raw_ts,
            "parsed_ts": parsed_ts,
            "threshold": self.thresholds["env"],
            "pass": pass_status,
            "error": None
        }
    
    def get_integration_health(self, file_path: Path) -> Dict[str, Any]:
        """통합 헬스 정보 조회"""
        entries = self.read_ndjson_file(file_path)
        if not entries:
            return {
                "status": "missing",
                "age": None,
                "raw_ts": None,
                "parsed_ts": None,
                "threshold": self.thresholds["integration"],
                "pass": False,
                "error": "File not found or empty"
            }
        
        # 마지막 유효한 엔트리의 타임스탬프 사용
        last_entry = entries[-1]
        raw_ts = last_entry.get("ts")
        parsed_ts = self.parse_timestamp(raw_ts)
        
        if parsed_ts is None:
            return {
                "status": "timestamp_invalid",
                "age": None,
                "raw_ts": raw_ts,
                "parsed_ts": None,
                "threshold": self.thresholds["integration"],
                "pass": False,
                "error": "Invalid timestamp in last entry"
            }
        
        age = time.time() - parsed_ts
        if not self.validate_age(age):
            return {
                "status": "timestamp_invalid",
                "age": age,
                "raw_ts": raw_ts,
                "parsed_ts": parsed_ts,
                "threshold": self.thresholds["integration"],
                "pass": False,
                "error": "Age out of valid range"
            }
        
        pass_status = age <= self.thresholds["integration"]
        
        return {
            "status": "ok" if pass_status else "stale",
            "age": age,
            "raw_ts": raw_ts,
            "parsed_ts": parsed_ts,
            "threshold": self.thresholds["integration"],
            "pass": pass_status,
            "error": None
        }
    
    def get_ws_stream_databus_health(self, file_path: Path) -> Dict[str, Any]:
        """WebSocket Stream DataBus 헬스 정보 조회"""
        data = self.read_json_file(file_path)
        if not data:
            return {
                "status": "missing",
                "age": None,
                "raw_ts": None,
                "parsed_ts": None,
                "threshold": 30,  # ws_stream_databus ≤ 30s
                "pass": False,
                "error": "File not found or invalid JSON"
            }
        
        # 키 선택: timestamp 우선
        raw_ts = data.get("timestamp")
        parsed_ts = self.parse_timestamp(raw_ts)
        
        if parsed_ts is None:
            return {
                "status": "timestamp_invalid",
                "age": None,
                "raw_ts": raw_ts,
                "parsed_ts": None,
                "threshold": 30,
                "pass": False,
                "error": "Invalid timestamp"
            }
        
        age = time.time() - parsed_ts
        if not self.validate_age(age):
            return {
                "status": "timestamp_invalid",
                "age": age,
                "raw_ts": raw_ts,
                "parsed_ts": parsed_ts,
                "threshold": 30,
                "pass": False,
                "error": "Age out of valid range"
            }
        
        pass_status = age <= 30  # ws_stream_databus ≤ 30s
        
        return {
            "status": "ok" if pass_status else "stale",
            "age": age,
            "raw_ts": raw_ts,
            "parsed_ts": parsed_ts,
            "threshold": 30,
            "pass": pass_status,
            "error": None
        }

    def get_all_health_status(self, path_registry) -> Dict[str, Dict[str, Any]]:
        """모든 헬스 상태 조회"""
        return {
            "ws_stream_databus": self.get_ws_stream_databus_health(path_registry.get("shared_data") / "databus_snapshot.json"),
            "positions": self.get_positions_health(path_registry.get("health_positions")),
            "ares": self.get_ares_health(path_registry.get("health_ares")),
            "trader": self.get_trader_health(path_registry.get("health_trader")),
            "env": self.get_env_health(path_registry.get("ssot_env")),
            "integration": self.get_integration_health(path_registry.get("candidates_ndjson"))
        }


def get_robust_health_reader() -> RobustHealthReader:
    """강화된 헬스 리더 인스턴스 획득"""
    return RobustHealthReader()
