# Guard Tools - 시스템 관리 도구

## 📋 도구 목록

### 1. `healthcheck_recover.py` - 헬스체크 & 복구 도구

시스템 전체 상태를 점검하고 문제를 자동으로 복구하는 도구입니다.

#### 🎯 주요 기능

1. **프로세스 체크**
   - `feeder`, `trader`, `autoheal` 프로세스 실행 여부 확인
   - 실행 중인 프로세스의 PID 출력

2. **PID/Lock 파일 정리**
   - `shared_data/*.pid` 파일 삭제
   - `logs/*.lock` 파일 삭제
   - 오래된 잠금 파일로 인한 문제 해결

3. **로그 에러 스캔**
   - `logs/feeder.log` (마지막 200줄)
   - `logs/trader.log` (마지막 200줄)
   - `logs/autoheal.log` (마지막 200줄)
   - `ERROR`, `FAIL`, `CRITICAL` 키워드 검색

4. **Preflight 체크**
   - Feeder Health (연결 상태, 데이터 신선도)
   - UDS Heartbeat (User Data Stream)
   - Filters (주문 정규화)
   - Loss Limits (일손절/Fail-Safe)
   - Queue/ACK Wiring (명령 큐 배선)
   - TimeSync (시간 동기화)
   - Restart Recovery (재시작 복원)

#### 🚀 사용 방법

**방법 1: 배치 파일 실행 (권장)**
```bash
# 프로젝트 루트에서
헬스체크_실행.bat
```

**방법 2: 직접 실행**
```bash
# 가상환경 활성화 후
python guard/tools/healthcheck_recover.py
```

**방법 3: PowerShell**
```powershell
.\venv\Scripts\python.exe guard\tools\healthcheck_recover.py
```

#### 📊 출력 예시

```
**********************************************************************
*                                                                    *
*            🏥 코인퀀트 시스템 헬스체크 & 복구 도구                    *
*                                                                    *
**********************************************************************

======================================================================
  1️⃣ 프로세스 체크
======================================================================
✅ feeder       - 실행 중 (PID: 12345, 67890)
✅ trader       - 실행 중 (PID: 11111)
❌ autoheal     - 실행 중 아님

======================================================================
  2️⃣ PID/Lock 파일 정리
======================================================================
🗑️  삭제: shared_data\feeder.pid
✅ 총 1개 파일 삭제 완료

======================================================================
  3️⃣ 로그 에러 스캔
======================================================================
✅ 에러 없음

======================================================================
  4️⃣ Preflight 체크
======================================================================
✅ Feeder Health        - PASS
✅ UDS Heartbeat        - PASS
✅ Filters              - PASS
✅ Loss Limits          - PASS
✅ Queue/ACK Wiring     - PASS

🟢 시스템 정상 - START 가능
```

#### ⚙️ 의존성

- `psutil` - 프로세스 체크용 (선택사항, 없으면 건너뜀)
- `guard.ui.components.preflight_checker` - Preflight 체크용
- `guard.ui.readers.file_sources` - 파일 읽기용

#### 🔒 안전성

- 여러 번 실행해도 안전 ✅
- 파일이 없어도 크래시 없음 ✅
- 모든 작업에 `try/except` 적용 ✅
- 읽기 전용 작업 위주 (PID/Lock 삭제만 쓰기) ✅

#### 📝 권장 사용 시나리오

1. **시스템 시작 전**
   - 이전 실행의 잔여 PID/Lock 파일 정리
   - Preflight 체크로 시작 가능 여부 확인

2. **문제 발생 시**
   - 로그에서 에러 빠르게 확인
   - 프로세스 상태 점검
   - 오래된 잠금 파일 제거

3. **정기 점검**
   - 매일 1회 실행하여 시스템 상태 모니터링
   - 로그 에러 누적 확인

4. **재시작 후**
   - 모든 컴포넌트가 정상 작동하는지 확인
   - Preflight 통과 확인 후 START

#### 🆘 트러블슈팅

**Q: "psutil이 설치되지 않았습니다" 경고가 뜹니다**
```bash
pip install psutil
```

**Q: Preflight 모듈 임포트 실패**
- `guard/ui/components/preflight_checker.py` 파일 확인
- Python 경로 설정 확인 (프로젝트 루트에서 실행)

**Q: 로그 파일을 찾을 수 없습니다**
- 정상입니다. 해당 컴포넌트가 아직 실행되지 않았거나 로그가 없는 경우

**Q: 모든 게이트가 FAIL입니다**
- Feeder와 Trader를 먼저 실행하세요
- 시스템이 충분히 초기화될 때까지 1~2분 대기 후 재실행

---

## 🔧 기타 도구 (추후 추가)

- `process_manager.py` - 프로세스 시작/중지 관리
- `log_analyzer.py` - 로그 패턴 분석
- `config_validator.py` - 설정 파일 검증

