# Hantubot 변경 이력

## [2025-12-26] - 시스템 최적화 및 안정성 개선

### 개요
실계좌 운영 안정성 향상을 위한 종합 최적화 작업

### 📄 문서 추가

#### AUTO_BOOT_SETUP.md
- Windows 작업 스케줄러 설정 가이드
- BIOS Wake-on-RTC 설정 방법
- 자동 로그인 및 시작 프로그램 등록
- 배치 파일 개선 (백그라운드 실행)
- 15:40 자동 종료 설정
- 트러블슈팅 및 체크리스트

#### EMAIL_SETUP.md
- Gmail 앱 비밀번호 생성 가이드
- 이메일 알림 트리거 정의 (CRITICAL, 주문 실패, 포트폴리오 이상)
- 이메일 템플릿 샘플
- Rate Limiting 설정
- Discord vs Email 비교
- 테스트 및 트러블슈팅

#### CHANGELOG.md (본 문서)
- 변경 이력 추적

---

## [계획 중] - P0 작업 (즉시)

### 🐛 버그 수정

#### Bug #1: volume_spike.py - top_n 제한 미적용
**파일**: `hantubot/strategies/volume_spike.py`
**라인**: 99
**변경 전**:
```python
def find_volume_spike_stocks(self, top_n=50):
    # ...
    return candidates  # 제한 없음
```
**변경 후**:
```python
def find_volume_spike_stocks(self, top_n=50):
    # ...
    return candidates[:top_n]  # 명시적 제한
```
**영향**: 후보 종목 수 제한으로 API 호출 감소

#### Bug #2: 슬리피지 버퍼 부족
**파일**: `hantubot/strategies/base_strategy.py`
**라인**: 슬리피지 버퍼 정의 위치
**변경 전**:
```python
self.slippage_buffer = 0.003  # 0.3%
```
**변경 후**:
```python
self.slippage_buffer = 0.007  # 0.7%
```
**사유**: 체결 실패율 감소 (급등주 변동성 대응)

#### Bug #3: 종가 매매 타이밍 지연
**파일**: `configs/config.yaml`, `hantubot/core/engine.py`
**변경 전**:
```yaml
closing_price:
  execution_start: "15:20"
```
**변경 후**:
```yaml
closing_price:
  recommendation_time: "15:03"  # TOP3 웹훅 필수
  execution_start: "15:15"      # 15:20 → 15:15
  execution_end: "15:19"
```
**사유**: 장마감 직전 체결률 향상

---

### 📊 로깅 시스템 개선

#### RotatingFileHandler 추가
**파일**: `hantubot/reporting/logger.py`
**추가 내용**:
```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'logs/hantubot.log', 
    maxBytes=10485760,  # 10MB
    backupCount=5
)
```
**효과**: 로그 파일 자동 로테이션, 디스크 공간 절약

#### 레벨별 로그 분리
**추가 파일**: 
- `logs/hantubot_INFO.log` - 일반 로그
- `logs/hantubot_WARNING.log` - 경고
- `logs/hantubot_ERROR.log` - 오류
- `logs/hantubot_CRITICAL.log` - 치명적 오류

**효과**: 오류 추적 용이, 디버깅 시간 단축

---

### 📧 이메일 알림 시스템

#### 신규 파일: hantubot/utils/email_alert.py
**기능**:
- CRITICAL 로그 즉시 이메일 발송
- 주문 실패 5회 연속 시 알림
- API 토큰 갱신 실패 알림
- 포트폴리오 이상 (-10% 초과) 알림
- 시스템 재시작 알림

**구현**:
```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_critical_alert(subject, message):
    """CRITICAL 로그 이메일 발송"""
    # Gmail SMTP 사용
    # Rate limiting 적용
    # 중복 방지 로직
```

**설정**:
```bash
# configs/.env
EMAIL_ENABLED=true
EMAIL_RECEIVER=dbswoql0712@gmail.com
```

---

### 🚀 자동 시작 구현

#### GUI 자동 시작 옵션
**파일**: `hantubot/gui/main_window.py`
**추가 내용**:
```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ...
        self.auto_start_enabled = os.getenv('AUTO_START_ENGINE', 'false').lower() == 'true'
        
        if self.auto_start_enabled:
            self.log_handler.emitter.log_signal.emit("자동 시작 모드 - 1초 후 엔진 시작")
            QTimer.singleShot(1000, self.start_engine)
```

**설정**:
```bash
# configs/.env
AUTO_START_ENGINE=true  # 자동 시작 활성화
```

**효과**: 
- GUI 실행 시 자동으로 엔진 시작
- 수동 버튼은 재시작용으로 유지
- 무인 운영 가능

---

### ⏰ 자동 종료 (15:40)

#### 스케줄러 종료 로직
**파일**: `hantubot/core/engine.py`
**추가 내용**:
```python
def schedule_daily_tasks(self):
    # 기존 스케줄...
    
    # 15:40 프로그램 종료
    schedule.every().day.at("15:40").do(self.shutdown_system)

def shutdown_system(self):
    """일일 작업 완료 후 정상 종료"""
    self.logger.info("=" * 80)
    self.logger.info("일일 작업 완료 - 프로그램 종료")
    self.logger.info("=" * 80)
    
    # Discord 알림
    self.notifier.send_alert("✅ Hantubot 일일 작업 완료 - 정상 종료")
    
    # 정상 종료
    self.stop()
    sys.exit(0)
```

**스케줄 전체**:
```
09:00 - 장초반 전략 (OpeningBreakout)
09:30 - 장초반 청산
09:30~15:00 - 급등주 스캔 (VolumeSpike)
15:03 - TOP3 웹훅 전송 (필수)
15:15 - 종가 매매 실행
15:30 - 로그 분석 + 학습
15:35 - 유목민 공부법 수집 + GitHub 커밋
15:40 - 프로그램 정상 종료 ← 신규
```

---

### 🔄 프로그램 자동 재시작

#### 크래시 감지 및 재시작
**파일**: `run.py`
**변경 내용**:
```python
def main():
    """Main entry point with auto-restart on crash"""
    max_restarts = 3
    restart_count = 0
    
    while restart_count < max_restarts:
        try:
            app = QApplication(sys.argv)
            window = MainWindow()
            window.show()
            sys.exit(app.exec())
        
        except Exception as e:
            restart_count += 1
            logger = get_logger("hantubot.main")
            logger.critical(f"프로그램 크래시 (재시작 {restart_count}/{max_restarts}): {e}", exc_info=True)
            
            # 이메일 알림
            send_critical_alert(
                subject=f"🚨 [Hantubot] 크래시 (재시작 {restart_count}/{max_restarts})",
                message=f"오류: {str(e)}\n\n자동 재시작 중..."
            )
            
            if restart_count < max_restarts:
                time.sleep(5)
                logger.info(f"5초 후 자동 재시작... ({restart_count}/{max_restarts})")
            else:
                logger.critical("최대 재시작 횟수 초과 - 프로그램 종료")
                sys.exit(1)
```

**효과**: 
- 무인 운영 안정성 향상
- 크래시 시 자동 복구
- 최대 3회 재시도 후 종료

---

### 🔧 배치 파일 개선

#### start_hantubot.bat (백그라운드 실행)
**변경 전**:
```batch
@echo off
cd /d C:\Coding\hantubot_prod
call venv\Scripts\activate.bat
python run.py
pause
```

**변경 후**:
```batch
@echo off
:: 현재 디렉토리를 배치 파일 위치로 변경
cd /d %~dp0

:: 가상환경 활성화
call venv\Scripts\activate.bat

:: 백그라운드 실행 (창 최소화)
start /min pythonw run.py

:: 즉시 종료
exit
```

#### start_hantubot_debug.bat (디버그용 신규)
```batch
@echo off
cd /d %~dp0
call venv\Scripts\activate.bat
python run.py
pause
```

**효과**:
- 백그라운드 실행으로 화면 깔끔
- 디버그용 배치 파일 분리
- 자동 부팅 시 적합

---

## [계획 중] - P1 작업 (1주 내)

### 💰 켈리 공식 적용

#### 신규 파일: hantubot/utils/kelly_calculator.py
```python
def calculate_kelly_fraction(win_rate, avg_win, avg_loss):
    """
    Kelly Criterion 계산 (Half-Kelly 적용)
    
    f* = (p*b - q) / b
    
    Args:
        win_rate: 승률 (0~1)
        avg_win: 평균 수익률
        avg_loss: 평균 손실률
    
    Returns:
        Kelly 비율 (0~1)
    """
    q = 1 - win_rate
    b = avg_win / abs(avg_loss)
    kelly = (win_rate * b - q) / b
    
    # Half-Kelly (안전성)
    return max(0, min(kelly * 0.5, 1.0))
```

#### 적용 위치
**파일**: `hantubot/strategies/base_strategy.py`
**수정 메서드**: `calculate_position_size()`
```python
def calculate_position_size(self, symbol, current_price):
    """켈리 공식 적용한 포지션 크기 계산"""
    # 과거 데이터에서 승률, 평균 손익 계산
    win_rate, avg_win, avg_loss = self.get_historical_performance(symbol)
    
    # 켈리 비율 계산
    kelly_fraction = calculate_kelly_fraction(win_rate, avg_win, avg_loss)
    
    # 자본 * 켈리 비율
    position_value = self.portfolio.cash * kelly_fraction
    quantity = int(position_value / current_price)
    
    return max(1, quantity)  # 최소 1주
```

---

### 🛡️ 예외 처리 강화

#### 재시도 데코레이터
**파일**: `hantubot/execution/broker.py`
```python
from functools import wraps
import time

def retry_on_failure(max_retries=3, delay=1, exponential_backoff=True):
    """
    API 호출 실패 시 자동 재시도 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        delay: 초기 지연 시간 (초)
        exponential_backoff: 지수 백오프 사용 여부
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                
                except Exception as e:
                    logger = get_logger(f"{func.__module__}.{func.__name__}")
                    logger.warning(f"재시도 {attempt+1}/{max_retries}: {e}")
                    
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt) if exponential_backoff else delay
                        logger.info(f"{wait_time}초 후 재시도...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"최종 실패: {func.__name__}")
                        # 이메일 알림
                        send_critical_alert(
                            f"⚠️ [Hantubot] API 호출 최종 실패: {func.__name__}",
                            f"함수: {func.__name__}\n오류: {str(e)}\n재시도: {max_retries}회"
                        )
                        raise
        
        return wrapper
    return decorator
```

#### 적용 대상 메서드
```python
@retry_on_failure(max_retries=3, delay=1)
def get_access_token(self):
    """토큰 갱신 (3회 재시도)"""
    pass

@retry_on_failure(max_retries=5, delay=0.5)
def get_current_price(self, symbol):
    """현재가 조회 (5회 재시도, 짧은 지연)"""
    pass

@retry_on_failure(max_retries=3, delay=2)
def place_order(self, symbol, side, quantity, price):
    """주문 (3회 재시도, 긴 지연)"""
    pass

@retry_on_failure(max_retries=3, delay=1)
def get_volume_rank(self, market="ALL"):
    """거래량 순위 (3회 재시도)"""
    pass
```

#### Discord 웹훅 Fallback
**파일**: `hantubot/reporting/notifier.py`
```python
def send_alert(self, message, level='info'):
    """Discord 웹훅 발송 (실패 시 로그 저장)"""
    try:
        response = requests.post(self.webhook_url, json=payload, timeout=5)
        response.raise_for_status()
    
    except Exception as e:
        logger.warning(f"Discord 웹훅 실패: {e}")
        
        # 실패한 메시지 로그 파일에 저장
        with open('logs/discord_failed.log', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] {message}\n")
```

---

## [계획 중] - P2 작업 (2주 내)

### ⚡ 성능 최적화

#### Streamlit 캐싱
**파일**: `dashboard/app.py`
```python
import streamlit as st

@st.cache_data(ttl=60)
def load_performance_data():
    """성능 데이터 60초 캐싱"""
    return db.get_all_trades()

@st.cache_resource
def init_database_connection():
    """DB 연결 영구 캐싱"""
    return sqlite3.connect('data/trading_performance.db')
```

#### DB 인덱싱
**파일**: `hantubot/reporting/trade_logger.py`
```sql
CREATE INDEX IF NOT EXISTS idx_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_strategy ON trades(strategy_name);
CREATE INDEX IF NOT EXISTS idx_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_pnl ON trades(pnl);
```

#### 메모리 관리
**파일**: `hantubot/reporting/study.py`
```python
import gc

def collect_market_data(run_date, batch_size=100):
    """대량 데이터 배치 처리"""
    all_tickers = get_all_tickers()
    
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i+batch_size]
        process_batch(batch)
        
        # 메모리 정리
        gc.collect()
```

---

### 📈 추가 성능 지표

#### 샤프 비율
**파일**: `hantubot/optimization/analyzer.py`
```python
def calculate_sharpe_ratio(returns, rf=0.03):
    """
    샤프 비율 계산
    
    Args:
        returns: 일일 수익률 배열
        rf: 무위험 수익률 (연간)
    
    Returns:
        샤프 비율
    """
    excess_returns = returns - rf / 252
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std()
```

#### VaR (Value at Risk)
```python
def calculate_var(returns, confidence=0.95):
    """
    VaR 계산 (95% 신뢰수준)
    
    Returns:
        최악의 5% 손실
    """
    return np.percentile(returns, (1 - confidence) * 100)
```

#### MDD (Maximum Drawdown)
```python
def calculate_max_drawdown(equity_curve):
    """
    최대 낙폭 계산
    
    Returns:
        MDD (%)
    """
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    return drawdown.min()
```

---

## 테스트 체크리스트

### 1단계: 문서 확인
- [x] AUTO_BOOT_SETUP.md 작성 완료
- [x] EMAIL_SETUP.md 작성 완료
- [x] CHANGELOG.md 작성 완료

### 2단계: 버그 수정 테스트
- [ ] volume_spike.py 수정 후 후보 종목 수 확인
- [ ] slippage_buffer 0.7% 적용 후 체결률 확인
- [ ] 종가 매매 15:15 실행 확인

### 3단계: 로깅 시스템 테스트
- [ ] logs/ 폴더에 로그 파일 생성 확인
- [ ] RotatingFileHandler 동작 (10MB 초과 시)
- [ ] 레벨별 로그 분리 확인

### 4단계: 이메일 알림 테스트
- [ ] Gmail 앱 비밀번호 설정
- [ ] 테스트 이메일 발송 성공
- [ ] CRITICAL 로그 이메일 수신 확인

### 5단계: 자동 시작/종료 테스트
- [ ] AUTO_START_ENGINE=true 설정 후 자동 시작
- [ ] 15:40 자동 종료 확인
- [ ] Discord 알림 수신 확인

### 6단계: 실계좌 모니터링 (1주)
- [ ] 월요일 자동 실행 확인
- [ ] 매일 로그 파일 확인
- [ ] 주문 실패율 감소 확인
- [ ] 크래시 없이 안정 운영

---

## 백업 권장사항

### 수정 전 백업
```bash
# 프로젝트 전체 백업
xcopy C:\Coding\hantubot_prod C:\Backup\hantubot_prod_2025-12-26 /E /I /H

# 중요 파일만 백업
copy configs\.env configs\.env.backup
copy data\trading_performance.db data\trading_performance.db.backup
copy data\study.db data\study.db.backup
```

### Git 커밋
```bash
git add .
git commit -m "실계좌 운영 최적화 (문서 추가, 버그 수정, 로깅 개선)"
git push origin main
```

---

## 롤백 계획

### 문제 발생 시
1. **즉시 프로그램 정지** (GUI에서 Stop 버튼)
2. **백업 복원**:
   ```bash
   xcopy C:\Backup\hantubot_prod_2025-12-26 C:\Coding\hantubot_prod /E /I /H /Y
   ```
3. **로그 분석**: `logs/hantubot_root_YYYY-MM-DD.log`
4. **Git 롤백**:
   ```bash
   git reset --hard [이전 커밋 해시]
   ```

---

## 관련 이슈

### GitHub Issues (예시)
- #001: volume_spike.py top_n 버그
- #002: 슬리피지 버퍼 부족으로 체결 실패
- #003: 종가 매매 타이밍 지연
- #004: 로그 파일 용량 과다

---

## 작성자
Hantubot 최적화 팀

## 마지막 업데이트
2025-12-26 21:57:00 KST
