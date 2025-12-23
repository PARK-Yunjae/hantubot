# Hantubot-Production

**프로덕션 레벨 한국 주식 자동매매 시스템**

---

## 1. 프로젝트 개요

이 프로젝트는 한국투자증권(KIS) API를 사용하여 사용자가 정의한 전략에 따라 주식 거래를 자동으로 수행하는 시스템입니다. 안정성, 확장성, 안전성을 최우선으로 고려하여 설계되었으며, 모의투자와 실전투자를 모두 지원합니다.

모든 거래는 중앙화된 `OrderManager`를 통해 관리되어 중복 주문, 동시성 문제 등의 리스크를 최소화했으며, 거래 시간 외에는 주문이 실행되지 않도록 Time Gate 기능이 구현되어 있습니다. GUI 컨트롤러를 통해 시스템을 쉽게 시작하고 중지하며, 실시간으로 로그를 모니터링할 수 있습니다.

## 2. 주요 기능

- **거래 시간 강제 게이트**: 한국장 기준 09:00~15:30 외 모든 거래 행위 자동 금지 (주말/공휴일 포함)
- **중앙화된 주문 관리**: 모든 주문을 단일 `OrderManager`에서 처리하여 충돌 및 리스크 방지
- **전략 모듈화**: `hantubot/strategies` 폴더에 새로운 전략 파일을 추가하여 쉽게 확장 가능
- **실시간 로깅 및 알림**: 모든 시스템 활동과 거래 내역을 GUI 및 로그 파일에 기록하고, 주요 이벤트는 Discord로 알림
- **자동 리포팅 및 스터디**: 장 마감 후 일일 거래 리포트 및 관심 종목 리서치 노트 자동 생성
- **GUI 컨트롤러**: `PySide6` 기반의 GUI를 통해 시스템 시작/정지 및 실시간 로그 모니터링
- **실전/모의투자 지원**: `config.yaml` 파일 설정 변경만으로 실전/모의투자 모드 전환 가능

## 3. 시스템 아키텍처

본 시스템은 각 컴포넌트가 명확한 책임을 갖는 모듈식 아키텍처를 따릅니다.

- **`run.py`**: GUI 애플리케이션을 시작하는 메인 진입점
- **`GUI (main_window.py)`**: 사용자 인터페이스 및 엔진 제어. `TradingEngine`을 별도 스레드에서 실행.
- **`TradingEngine (engine.py)`**: 시장 상태(장 시작, 장중, 장 마감)에 따라 적절한 로직을 실행하는 메인 루프.
- **`StrategyEngine` (engine.py 내 구현)**: `config.yaml`에 명시된 활성 전략들을 동적으로 로드하고 실행.
- **`OrderManager (order_manager.py)`**: 전략으로부터 받은 '신호'를 검증(잔고, 시간, 중복 등)하고 안전한 '주문'으로 변환.
- **`Broker (broker.py)`**: KIS API와의 모든 통신을 책임지는 저수준 래퍼(Wrapper).
- **`Portfolio (portfolio.py)`**: 현재 계좌의 현금, 보유 주식 등 자산 상태를 관리하는 단일 진실 공급원(SSOT).
- **`MarketClock (clock.py)`**: 거래 가능 시간 및 휴장일을 판단하는 Time Gate.
- **`Logger/Notifier/Reporter`**: 로깅, 알림, 리포팅을 담당.

## 4. 설치 방법

1.  **프로젝트 클론**
    ```bash
    git clone <repository_url>
    cd hantubot_prod
    ```

2.  **가상환경 생성 및 활성화 (권장)**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

3.  **의존성 패키지 설치**
    ```bash
    pip install -r requirements.txt
    ```

## 5. 설정 방법

1.  **`.env` 파일 생성**
    `configs/.env.example` 파일을 복사하여 `configs/.env` 파일을 생성합니다.

    ```bash
    cp configs/.env.example configs/.env
    ```

2.  **API 키 및 개인정보 입력**
    `configs/.env` 파일을 열어 한국투자증권에서 발급받은 **모의투자 또는 실전투자**용 `APP_KEY`, `APP_SECRET`, `계좌번호`를 입력합니다. Discord 알림을 사용하려면 웹훅 URL도 입력합니다.

    ```dotenv
    # hantubot_prod/configs/.env
    KIS_APP_KEY="여기에_앱_키_입력"
    KIS_APP_SECRET="여기에_앱_시크릿_입력"
    KIS_ACCOUNT_NO="계좌번호-01"
    DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
    ```

3.  **`config.yaml` 설정**
    `configs/config.yaml` 파일을 열어 운영 모드 및 기타 설정을 확인합니다.

    - `mode`: 'mock' (모의투자) 또는 'live' (실전투자)로 설정합니다. **GUI에서 표시되며, 실행 중 변경할 수 없습니다.**
    - `active_strategies`: 실행하고자 하는 전략의 파일명(확장자 제외)을 리스트에 추가합니다.

## 6. 실행 방법

프로젝트 루트 디렉토리(`hantubot_prod`)에서 아래 명령어를 실행합니다.

```bash
python run.py
```

GUI 컨트롤러가 나타나면 "Start Engine" 버튼을 눌러 자동매매 시스템을 시작할 수 있습니다.

## 7. GUI 컨트롤

- **Start Engine**: 트레이딩 엔진을 별도 스레드에서 시작합니다. 버튼이 비활성화되고 'Stop Engine' 버튼이 활성화됩니다.
- **Stop Engine**: 실행 중인 트레이딩 엔진에 안전하게 정지 신호를 보냅니다.
- **Trading Mode**: `config.yaml`에 설정된 현재 모드를 보여줍니다. (읽기 전용)
- **Active Strategies**: `config.yaml`에 설정된 활성 전략 목록을 보여줍니다. (현재는 표시용)
- **Real-time Logs**: 시스템의 모든 활동이 실시간으로 이 창에 표시됩니다.

---
*Disclaimer: 이 소프트웨어는 학습 및 연구 목적으로 제작되었으며, 실제 투자에 사용 시 발생하는 모든 손실에 대한 책임은 사용자에게 있습니다.*