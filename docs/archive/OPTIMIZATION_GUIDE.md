# 🚀 Hantubot 최적화 가이드

**마지막 업데이트**: 2025-12-26  
**작업 범위**: P0 (시스템 안정성) + P1 (Kelly/Retry) + P2 (성능 지표/캐싱)

---

## 📋 목차

1. [완료된 작업 요약](#완료된-작업-요약)
2. [P0: 시스템 안정성](#p0-시스템-안정성)
3. [버그 수정](#버그-수정)
4. [P1: 고급 기능](#p1-고급-기능)
5. [P2: 성능 최적화](#p2-성능-최적화)
6. [환경 변수 설정](#환경-변수-설정)
7. [사용 방법](#사용-방법)
8. [모니터링 및 디버깅](#모니터링-및-디버깅)

---

## ✅ 완료된 작업 요약

### P0: 시스템 안정성 (즉시 적용 가능)
- ✅ **문서 작성** - AUTO_BOOT_SETUP.md, EMAIL_SETUP.md, CHANGELOG.md
- ✅ **로깅 시스템 개선** - Rotating, 레벨별 분리, 디스크 절약
- ✅ **이메일 알림** - CRITICAL 로그, 주문 실패, 포트폴리오 이상
- ✅ **자동 시작** - GUI 실행 1초 후 엔진 자동 시작
- ✅ **15:40 자동 종료** - 장 마감 후 정상 종료
- ✅ **크래시 재시작** - 최대 3회 자동 재시작

### 버그 수정
- ✅ **volume_spike_strategy** - 슬리피지 버퍼 0.93 (7%), 가격 필터 2000원
- ✅ **closing_price_advanced_screener** - 15:03 웹훅 / 15:15-19 매수 분리

### P1: 고급 기능
- ✅ **Kelly Criterion** - 과거 성과 기반 포지션 크기 최적화
- ✅ **Retry 데코레이터** - API 호출 자동 재시도, 지수 백오프

### P2: 성능 최적화
- ✅ **성능 지표 계산기** - Sharpe Ratio, Max Drawdown, Calmar Ratio, Profit Factor
- ✅ **데이터 캐싱** - TTL 기반 메모리 캐싱, LRU 방식

---

## 🛠️ P0: 시스템 안정성

### 1. 로깅 시스템 개선

**변경 사항**:
- RotatingFileHandler (10MB, 5개 백업)
- 레벨별 로그 분리 (WARNING, ERROR 별도 파일)
- 자동 디스크 공간 관리

**파일**: `hantubot/reporting/logger.py`

**로그 파일 구조**:
```
logs/
├── hantubot.log            # 전체 로그 (INFO 이상)
├── hantubot_warning.log    # 경고
└── hantubot_error.log      # 오류
```

**사용 예시**:
```python
from hantubot.reporting.logger import get_logger

logger = get_logger(__name__)
logger.info("일반 정보")
logger.warning("⚠️ 경고")
logger.error("❌ 오류")
logger.critical("🚨 심각한 오류")
```

### 2. 이메일 알림 시스템

**파일**: `hantubot/utils/email_alert.py`

**기능**:
- CRITICAL 로그 자동 이메일 발송
- 주문 실패 5회 연속 시 알림
- 포트폴리오 이상 (-10% 초과) 알림
- Rate limiting (시간당 10통, 일일 50통)

**설정**:
```bash
# configs/.env
EMAIL_ENABLED=true
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password  # Gmail 앱 비밀번호
EMAIL_RECEIVER=dbswoql0712@gmail.com
```

**Gmail 앱 비밀번호 설정**:
1. Google 계정 → 보안
2. 2단계 인증 활성화
3. 앱 비밀번호 생성
4. 생성된 16자리 비밀번호를 EMAIL_PASSWORD에 입력

### 3. 자동 시작

**파일**: `hantubot/gui/main_window.py`

**설정**:
```bash
AUTO_START_ENGINE=true  # 1초 후 자동 시작
```

**동작**:
- GUI 실행 → 1초 대기 → 엔진 자동 시작
- 무인 운영 가능

### 4. 15:40 자동 종료

**파일**: `hantubot/core/engine.py`

**설정**:
```bash
AUTO_SHUTDOWN_ENABLED=true
AUTO_SHUTDOWN_TIME=15:40  # 변경 가능
```

**동작**:
- 장 마감 후 작업 완료 시 정상 종료
- Discord 알림 발송

### 5. 크래시 자동 재시작

**파일**: `run.py`

**설정**:
```bash
MAX_AUTO_RESTARTS=3  # 최대 재시도 횟수
```

**동작**:
- 크래시 발생 시 5초 후 자동 재시작
- 이메일 알림 발송
- 최대 3회 재시도

---

## 🐛 버그 수정

### 1. volume_spike_strategy.py

**변경 사항**:
- 슬리피지 버퍼: `0.90` → `0.93` (7% 버퍼)
- 가격 필터: `1000원` → `2000원`

**코드 위치**: Line 142, 150

```python
# Before
if current_price < 1000: continue
buy_amount = (available_cash * 0.90 * allocation_weight) / params['max_positions']

# After
if current_price < 2000: continue
buy_amount = (available_cash * 0.93 * allocation_weight) / params['max_positions']
```

**효과**:
- 슬리피지 대응 능력 향상
- 초저가 종목 제외 (변동성 관리)

### 2. closing_price_advanced_screener.py

**변경 사항**: 15:03 웹훅 / 15:15-19 매수 완전 분리

**타임라인**:
- **15:03**: 스크리닝 실행 + Discord 웹훅 발송 (매수 안함)
- **15:15-15:19**: 저장된 1위 종목 매수 실행
- **현재가 재조회**: 15:03 가격이 아닌 15:15 시점 가격 사용

**코드 구조**:
```python
# 15:03-15:15: 스크리닝 + 웹훅
if self.webhook_time <= now.time() < self.buy_start_time:
    # 스크리닝 실행
    screened_stocks = await self._perform_screening(...)
    # TOP3 저장
    self.top_stocks_today = screened_stocks[:3]
    # Discord 웹훅 발송
    self.notifier.send_alert(...)
    return []  # 매수 안함!

# 15:15-15:19: 매수
if self.buy_start_time <= now.time() <= self.buy_end_time:
    top_stock = self.top_stocks_today[0]
    # 현재가 재조회
    current_price = self.broker.get_current_price(...)
    # 매수 신호 생성
    signals.append(...)
```

---

## 🎯 P1: 고급 기능

### 1. Kelly Criterion (포지션 크기 최적화)

**파일**: `hantubot/utils/kelly_calculator.py`

**기능**:
- 과거 매매 성과 기반 최적 포지션 크기 계산
- Half-Kelly 적용 (안정성)
- 종목별, 전략별 분석 가능

**사용 예시**:
```python
from hantubot.utils.kelly_calculator import calculate_position_size_kelly

# 과거 성과 기반 포지션 크기 계산
quantity = calculate_position_size_kelly(
    cash=1000000,           # 가용 현금
    current_price=50000,    # 현재가
    symbol='005930',        # 종목 (선택)
    strategy_id='volume_spike_strategy'  # 전략 (선택)
)

print(f"권장 매수 수량: {quantity}주")
```

**Kelly 공식**:
```
f* = (p*b - q) / b

p: 승률
q: 1 - 승률
b: 평균 수익 / 평균 손실
f*: Kelly 비율 (Half-Kelly = f* / 2)
```

### 2. Retry 데코레이터 (API 안정성)

**파일**: `hantubot/utils/retry_decorator.py`

**기능**:
- API 호출 실패 시 자동 재시도
- 지수 백오프 (1s, 2s, 4s...)
- 최종 실패 시 이메일 알림

**사용 예시**:
```python
from hantubot.utils.retry_decorator import retry_api_call, retry_on_failure

# 간단한 사용
@retry_api_call
def get_current_price(symbol):
    return broker.get_price(symbol)

# 커스텀 설정
@retry_on_failure(max_retries=5, delay=2.0)
def critical_api_call():
    return api.get_data()
```

**사전 정의 데코레이터**:
- `@retry_api_call` - 3회, 1초, 지수 백오프
- `@retry_network_call` - 5회, 0.5초
- `@retry_critical_call` - 3회, 2초, 실패 시 이메일

---

## 📊 P2: 성능 최적화

### 1. 성능 지표 계산기

**파일**: `hantubot/utils/performance_metrics.py`

**지표**:
- **Sharpe Ratio**: 위험 대비 수익률 (1.0 이상 양호, 2.0 이상 우수)
- **Max Drawdown**: 최대 낙폭 (%)
- **Calmar Ratio**: 연간 수익률 / 최대 낙폭 (3.0 이상 우수)
- **Profit Factor**: 총 수익 / 총 손실 (2.0 이상 우수)
- **Win Rate**: 승률 (%)

**사용 예시**:
```python
from hantubot.utils.performance_metrics import print_performance_report

# 최근 90일 성과 리포트
print_performance_report(days=90)
```

**출력 예시**:
```
============================================================
📊 트레이딩 성과 리포트 (최근 90일)
============================================================
총 거래 횟수: 45회
승률: 62.22%
평균 수익: 2.15%
평균 손실: -1.85%
Profit Factor: 1.87
------------------------------------------------------------
Sharpe Ratio: 1.85 🟡 양호
Max Drawdown: -8.50% 🟢 우수
Calmar Ratio: 3.24 🟢 우수
------------------------------------------------------------
총 수익률: 7.56%
연간 수익률 (추정): 30.68%
============================================================
```

### 2. 데이터 캐싱 시스템

**파일**: `hantubot/utils/data_cache.py`

**기능**:
- TTL (Time To Live) 기반 자동 만료
- LRU (Least Recently Used) 방식
- 스레드 안전
- 캐시 통계 (Hit Rate)

**전역 캐시**:
- `_price_cache`: 가격 데이터 (60초 TTL)
- `_daily_data_cache`: 일봉 데이터 (3600초 TTL)
- `_api_cache`: API 응답 (300초 TTL)

**사용 예시**:
```python
from hantubot.utils.data_cache import cached, _price_cache, get_cache_stats

# 데코레이터 방식
@cached(cache_instance=_price_cache)
def get_current_price(symbol):
    # 무거운 API 호출
    return broker.api_call(symbol)

# 캐시 통계 조회
stats = get_cache_stats()
print(stats)
# {'price_cache': {'size': 150, 'hits': 1250, 'misses': 50, 'hit_rate': 96.15%}}
```

**효과**:
- API 호출 감소 (90% 이상 캐시 적중률)
- 응답 속도 향상
- API Rate Limit 회피

---

## ⚙️ 환경 변수 설정

**파일**: `configs/.env`

```bash
# ===== 시스템 안정성 =====
# 자동 시작
AUTO_START_ENGINE=true

# 자동 종료
AUTO_SHUTDOWN_ENABLED=true
AUTO_SHUTDOWN_TIME=15:40

# 자동 재시작
MAX_AUTO_RESTARTS=3

# ===== 이메일 알림 =====
EMAIL_ENABLED=true
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=dbswoql0712@gmail.com

# ===== 한국투자증권 API =====
APP_KEY=your_app_key
APP_SECRET=your_app_secret
CANO=your_account_number
ACNT_PRDT_CD=01

# ===== Discord 웹훅 =====
DISCORD_WEBHOOK_URL=your_webhook_url

# ===== 거래 설정 =====
MOCK_TRADING=false  # true: 모의, false: 실전
```

---

## 📖 사용 방법

### 1. 일반 사용 (GUI)

```bash
# 프로그램 실행
python run.py

# AUTO_START_ENGINE=true 설정 시
# → 1초 후 자동 시작
# → 15:40 자동 종료
# → 크래시 시 자동 재시작
```

### 2. 작업 스케줄러 (무인 운영)

**참고**: `AUTO_BOOT_SETUP.md`

1. Windows 작업 스케줄러 열기
2. 새 작업 만들기
3. 트리거: 월~금 08:50
4. 동작: `C:\Coding\hantubot_prod\start_hantubot.bat`
5. 완료

### 3. 성능 모니터링

```python
# 성과 리포트 조회
from hantubot.utils.performance_metrics import print_performance_report
print_performance_report(90)

# 캐시 통계
from hantubot.utils.data_cache import get_cache_stats
print(get_cache_stats())

# Kelly 비율 계산
from hantubot.utils.kelly_calculator import calculate_kelly_fraction
kelly = calculate_kelly_fraction(win_rate=0.6, avg_win=0.03, avg_loss=-0.02)
print(f"Kelly 비율: {kelly:.2%}")
```

---

## 🔍 모니터링 및 디버깅

### 로그 확인

```bash
# 전체 로그
tail -f logs/hantubot.log

# 경고만
tail -f logs/hantubot_warning.log

# 오류만
tail -f logs/hantubot_error.log
```

### 이메일 알림 조건

1. **CRITICAL 로그**: 즉시 발송
2. **주문 실패 5회 연속**: 알림
3. **포트폴리오 -10% 이상**: 알림
4. **시스템 재시작**: 알림

### 캐시 성능 확인

```python
from hantubot.utils.data_cache import get_cache_stats

stats = get_cache_stats()
for cache_name, cache_stat in stats.items():
    print(f"{cache_name}:")
    print(f"  크기: {cache_stat['size']}/{cache_stat['max_size']}")
    print(f"  적중률: {cache_stat['hit_rate']}%")
```

---

## 🎉 작업 완료 체크리스트

- [x] P0: 시스템 안정성 개선 (로깅, 이메일, 자동 시작/종료, 재시작)
- [x] 버그 수정 (volume_spike, closing_price)
- [x] P1: Kelly 공식, Retry 데코레이터
- [x] P2: 성능 지표, 데이터 캐싱
- [x] 문서 작성 (OPTIMIZATION_GUIDE.md)
- [x] 유목민 공부법 업데이트 (2025-12-26)

---

## 📅 다음 단계

**월요일 실전 운영 체크리스트**:

1. ✅ 환경 변수 설정 확인 (.env)
2. ✅ 이메일 알림 테스트
3. ✅ 자동 시작/종료 동작 확인
4. ✅ 로그 파일 모니터링
5. ✅ Discord 웹훅 수신 확인
6. ✅ 15:03 웹훅 → 15:15 매수 타이밍 확인

**성공 기준**:
- 시스템 무인 운영 성공
- 크래시 시 자동 재시작
- 이메일 알림 정상 작동
- 로그 정상 기록

---

**🚀 준비 완료! 월요일 실전 운영을 기대합니다!**
