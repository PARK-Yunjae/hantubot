# 긴급 버그 수정 계획 (CRITICAL_HOTFIX_PLAN.md)

## 1. 개요 (Overview)

2025-12-29 보고된 치명적 오류 2건(중복 실행, 스케줄링 오류)을 긴급 수정(Hotfix)하는 계획입니다.
해당 수정은 운영 안정성을 위해 최우선으로 진행되며, 리팩토링보다 선행됩니다.

**긴급 수정 목표:**
1.  **중복 실행 방지:** 윈도우 스케줄러와 수동 실행 충돌 방지 (Lock File 적용).
2.  **스케줄링 로직 개선:** 08:50~15:30 사이 실행 시 대기 모드로 빠지지 않고 즉시 매매 로직 진입.

---

## 2. 문제 분석 및 수정 방안

### Issue 1: 중복 실행 (Double Instance)
*   **원인:** `run.py` 실행 시 기존 인스턴스 존재 여부를 체크하지 않음.
*   **증상:** API 토큰 충돌, 로그 혼선, 주문 중복 가능성.
*   **수정 방안:**
    *   `run.py` 진입점에 `tempfile`과 `os` 모듈을 이용한 Lock File 생성 로직 추가.
    *   프로그램 시작 시 `hantubot.lock` 파일이 있고, 해당 파일에 기록된 PID가 실제 실행 중인 프로세스라면 실행을 차단하고 즉시 종료.

### Issue 2: 스케줄링 오류 (Loop Logic Error)
*   **원인:** `hantubot/core/engine.py`의 `run_trading_loop`에서 `next_trading_day` 계산 로직이 단순함.
    *   현재 코드는 `if now.time() >= wake_up_time (08:50):` 조건만으로 다음 날짜로 넘겨버림.
    *   즉, 08:51에 켜거나, 09:30(장중)에 켜도 "이미 기상 시간 지났네? 내일 보자"라고 판단함.
*   **증상:** 봇이 장중에 켜져도 매매를 안 하고 내일 아침까지 대기함.
*   **수정 방안:**
    *   `wake_up_time`(08:50) 이후라도, `market_close_time`(15:30) 이전이라면 "오늘의 장중"으로 판단하고 대기 없이 루프 진행.
    *   `next_trading_day` 계산 로직을 "장 마감 시간 이후"에만 적용하도록 조건 변경.

---

## 3. 실행 단계 (Action Steps)

### Step 1: Lock File 구현 (`run.py`)
*   `hantubot.lock` 파일 생성 및 PID 기록.
*   `main()` 함수 시작 부에 중복 체크 로직 삽입.
*   종료 시 Lock File 삭제 (`try-finally` 블록).

### Step 2: Main Loop 로직 개선 (`hantubot/core/engine.py`)
*   `run_trading_loop` 메서드 수정.
*   **수정 전:**
    ```python
    if now.time() >= wake_up_time:
        next_trading_day += dt.timedelta(days=1)
    ```
*   **수정 후 (예시):**
    ```python
    market_times = self.market_clock.get_market_times()
    # 기상 시간은 지났지만, 장 마감 전이라면 내일로 넘기지 않음
    if now.time() >= wake_up_time and now.time() >= market_times['close']:
        next_trading_day += dt.timedelta(days=1)
    ```

### Step 3: 검증 (Verification)
*   수정 후 봇을 실행하여 `hantubot.lock` 파일 생성 여부 확인.
*   또 다른 터미널에서 `run.py` 실행 시 "이미 실행 중" 메시지와 함께 종료되는지 확인.
*   시간을 임의로 변경(Mocking)하거나 로직 흐름을 로그로 확인하여, 09:00~15:30 사이 실행 시 "대기"가 아닌 "매매 루프"로 진입하는지 확인.

---

## 4. 이후 계획

*   Hotfix 적용 및 검증 완료 후, 기존 `REFACTOR_PLAN.md`에 따라 구조 개선 작업을 진행합니다.
*   안전한 리팩토링을 위해 Hotfix가 적용된 버전을 베이스로 백업(Git commit)을 권장합니다.
