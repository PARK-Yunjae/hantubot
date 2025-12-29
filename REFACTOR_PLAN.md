# 시스템 아키텍처 리팩토링 계획 (REFACTOR_PLAN.md)

## 1. 개요 (Overview)

현재 `hantubot`은 핵심 파일들이 비대해져(God Object) 유지보수성과 확장성이 저하된 상태입니다. 본 리팩토링은 비즈니스 로직(매매 알고리즘, 자금 관리 등)을 100% 유지하면서, 코드 구조를 책임 단위로 명확히 분리하여 모듈성을 확보하는 것을 목표로 합니다.

**핵심 목표:**
1.  **단일 책임 원칙 (SRP):** 파일당 200~300줄 이내로 유지하며 하나의 역할만 수행.
2.  **안전성:** `ImportError` 및 순환 참조 방지, 기존 기능의 동일한 동작 보장.
3.  **확장성:** 새로운 전략이나 기능 추가 시 기존 코드를 수정하지 않고 확장 가능하도록 구조 개선.

---

## 2. 주요 변경 사항 (Key Changes)

### 2.1 Reporting & Study (유목민 공부법)
기존 `hantubot/reporting/study.py`와 `study_db.py`를 독립적인 패키지 `hantubot/study/`로 분리합니다.

*   **`hantubot/study/collector.py`**: 시장 데이터 수집 (pykrx), 뉴스 수집 (Naver) 담당.
*   **`hantubot/study/analyzer.py`**: Gemini LLM 기반 뉴스 요약 및 학습 메모 생성.
*   **`hantubot/study/repository.py`**: SQLite DB CRUD 작업 전담 (기존 `study_db.py` 대체).
*   **`hantubot/study/manager.py`**: 전체 워크플로우(`run_daily_study`) 오케스트레이션.
*   **`hantubot/study/exporter.py`**: Google Sheets 백업, Git 자동 커밋, 알림 발송.

### 2.2 Strategy (종가매매 스크리너)
`hantubot/strategies/closing_price_advanced_screener.py`를 패키지로 전환하여 로직과 설정을 분리합니다.

*   **`hantubot/strategies/closing_price/logic.py`**: 캔들 점수 계산, 지표 산출, 스크리닝 필터 로직.
*   **`hantubot/strategies/closing_price/config.py`**: 동적 파라미터(버퍼 비율 등) 및 설정 로드.
*   **`hantubot/strategies/closing_price/strategy.py`**: `BaseStrategy`를 상속받는 메인 클래스 (신호 생성 담당).

### 2.3 Execution (Broker)
`hantubot/execution/broker.py`의 비대한 API 래퍼와 트레이딩 로직을 분리합니다.

*   **`hantubot/execution/kis/api.py`**: KIS API 인증, 토큰 관리, 저수준 HTTP 요청 처리.
*   **`hantubot/execution/kis/market_data.py`**: 시세 조회, 거래량 상위 조회 (Mock 로직 포함).
*   **`hantubot/execution/kis/trading.py`**: 주문 전송, 잔고 조회, 체결 내역 조회 (Risk Check 로직 포함).
*   **`hantubot/execution/broker.py`**: 위 모듈들을 통합하여 기존 인터페이스를 제공하는 Facade 클래스 (하위 호환성 유지).

### 2.4 Core (Trading Engine)
`hantubot/core/engine.py`의 루프 로직과 상태 관리, 페이즈별 로직을 분리합니다.

*   **`hantubot/core/engine/loop.py`**: 메인 무한 루프 (`run_trading_loop`) 및 스케줄링.
*   **`hantubot/core/engine/phases.py`**: 장 시작(`market_open`), 장 중(`strategies`), 장 마감(`post_market`) 로직 핸들러.
*   **`hantubot/core/engine/monitor.py`**: 체결 확인 백그라운드 태스크 (`_poll_for_fills`).
*   **`hantubot/core/engine/main.py`**: `TradingEngine` 클래스 (통합 진입점).

---

## 3. 실행 계획 (Implementation Steps)

### Phase 1: 기반 마련 및 Study 모듈 리팩토링 (가장 안전)
독립성이 강한 `study` 모듈부터 시작하여 리스크를 최소화합니다.

1.  `hantubot/study/` 디렉토리 및 `__init__.py` 생성.
2.  `hantubot/study/repository.py` 작성: `study_db.py`의 내용을 엔티티별로 정리하여 이관.
3.  `hantubot/study/collector.py` 작성: `study.py`의 `collect_market_data`, `collect_news_for_candidates` 이관.
4.  `hantubot/study/analyzer.py` 작성: LLM 관련 함수(`generate_summaries` 등) 이관.
5.  `hantubot/study/exporter.py` 작성: 백업 및 알림 함수 이관.
6.  `hantubot/study/manager.py` 작성: `run_daily_study` 메인 로직 재구성.
7.  기존 `hantubot/reporting/study.py`를 `hantubot/study/manager.py`를 호출하는 래퍼로 변경 (하위 호환성).

### Phase 2: Execution 계층 구조화 (핵심 코어)
API 호출 로직을 명확히 분리합니다.

8.  `hantubot/execution/kis/` 디렉토리 생성.
9.  `hantubot/execution/kis/api.py` 작성: Auth 및 `_request` 로직 이관.
10. `hantubot/execution/kis/market_data.py` 작성: 시세 조회 로직 이관.
11. `hantubot/execution/kis/trading.py` 작성: 주문 및 잔고 로직 이관.
12. `hantubot/execution/broker.py` 재작성: 위 모듈들을 조합하여 `Broker` 클래스 재구성.

### Phase 3: Strategy 모듈화
복잡한 전략 파일 분해.

13. `hantubot/strategies/closing_price/` 디렉토리 생성.
14. `hantubot/strategies/closing_price/config.py`, `logic.py` 작성.
15. `hantubot/strategies/closing_price/strategy.py` 작성 및 기존 클래스 대체.

### Phase 4: Engine 분리 및 최종 통합
가장 민감한 메인 루프 리팩토링.

16. `hantubot/core/engine/` 디렉토리 생성.
17. `phases.py`, `monitor.py`, `loop.py` 순차 작성.
18. `hantubot/core/engine.py`가 새로운 모듈들을 import하여 사용하도록 수정.

---

## 4. 기술적 고려사항 & 안전장치 (Safeguards)

*   **Circular Import 방지:**
    *   타입 힌팅에 사용되는 순환 참조는 `if TYPE_CHECKING:` 블록 내부로 이동.
    *   공통 의존성(예: `Logger`, `Notifier`, `Config`)은 최하위 레벨 모듈이나 유틸리티로 유지.
*   **하위 호환성 유지:**
    *   기존 경로(`hantubot.reporting.study` 등)에서의 import가 깨지지 않도록, 기존 파일에 `deprecated` 경고와 함께 새 모듈을 import하여 다시 export하는 방식 적용.
*   **단계별 검증:**
    *   각 Phase 완료 시마다 `run.py --mock` 모드로 봇을 구동하여 정상 동작 확인.
    *   `run_daily_study` 등 독립 실행 가능한 기능은 단위 테스트 실행.

## 5. 성공 기준 (Success Criteria)

*   모든 타겟 파일의 라인 수가 300줄 이하로 감소하였는가?
*   `hantubot/study/` 구조가 명확히 분리되어 기능 추가가 용이한가?
*   리팩토링 후에도 봇이 정상적으로 실행되고 매매 신호를 생성하는가?
*   기존의 데이터(DB)와 설정(Config)이 그대로 유지되는가?
