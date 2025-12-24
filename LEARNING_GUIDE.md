# 🎓 Hantubot 자동매매 봇 - 파이썬 학습 가이드

> **실전 코드로 배우는 파이썬: 기초부터 자동매매 전략 개발까지**

---

## 📖 목차

1. [파이썬 기초 복습](#1-파이썬-기초-복습)
2. [Class와 Self 완전 정복](#2-class와-self-완전-정복)
3. [Hantubot 코드 구조 이해](#3-hantubot-코드-구조-이해)
4. [단계별 학습 로드맵](#4-단계별-학습-로드맵)
5. [실습 프로젝트](#5-실습-프로젝트)
6. [FAQ](#6-faq)

---

## 1. 파이썬 기초 복습

### 1.1 변수 (Variables)

```python
# 변수 = 데이터를 담는 상자
cash = 1000000  # 현금 백만원
stock_name = "삼성전자"  # 주식 이름
is_open = True  # 장이 열렸는가?

# 변수 사용
print(f"내 현금: {cash}원")  # 출력: 내 현금: 1000000원
```

### 1.2 함수 (Functions)

```python
# def = 함수 정의
def calculate_profit(buy_price, sell_price, quantity):
    """수익 계산 함수"""
    profit = (sell_price - buy_price) * quantity
    return profit

# 함수 사용
result = calculate_profit(70000, 75000, 10)
print(f"수익: {result}원")  # 출력: 수익: 50000원
```

### 1.3 조건문 (If-Else)

```python
price = 75000
buy_threshold = 70000

if price > buy_threshold:
    print("비싸서 안 사요")
elif price == buy_threshold:
    print("딱 적정가!")
else:
    print("싸니까 사요!")
```

### 1.4 반복문 (Loops)

```python
# 리스트 = 여러 개 담는 상자
stocks = ["삼성전자", "SK하이닉스", "NAVER"]

# for = 하나씩 꺼내서 처리
for stock in stocks:
    print(f"분석 중: {stock}")

# 출력:
# 분석 중: 삼성전자
# 분석 중: SK하이닉스
# 분석 중: NAVER
```

### 1.5 딕셔너리 (Dictionary)

```python
# 딕셔너리 = 이름표 붙은 상자들
portfolio = {
    "삼성전자": 10,  # 10주 보유
    "SK하이닉스": 5,  # 5주 보유
    "현금": 1000000   # 현금
}

# 값 가져오기
samsung_qty = portfolio["삼성전자"]
print(f"삼성전자 {samsung_qty}주 보유")
```

---

## 2. Class와 Self 완전 정복

### 2.1 Class의 개념

**Class = 설계도 (붕어빵 틀)**

```python
# 자동차 설계도 만들기
class Car:
    def __init__(self, color, brand):
        """생성자: 차를 처음 만들 때 실행"""
        self.color = color    # 내 색깔
        self.brand = brand    # 내 브랜드
        self.speed = 0        # 처음엔 정지
    
    def accelerate(self, amount):
        """가속 함수"""
        self.speed += amount
        print(f"{self.color} {self.brand}가 {self.speed}km/h로 달립니다")
    
    def stop(self):
        """정지 함수"""
        self.speed = 0
        print(f"{self.brand} 정지!")

# 실제 차 만들기 (인스턴스 생성)
my_car = Car("빨강", "현대")
your_car = Car("파랑", "기아")

# 각자 다른 차 조작
my_car.accelerate(50)   # 빨강 현대가 50km/h로 달립니다
your_car.accelerate(80) # 파랑 기아가 80km/h로 달립니다
```

### 2.2 Self란?

**self = "나 자신" (이 인스턴스)**

```python
class BankAccount:
    def __init__(self, owner, balance):
        self.owner = owner      # 나의 주인
        self.balance = balance  # 나의 잔고
    
    def deposit(self, amount):
        """입금"""
        self.balance += amount  # 나의 잔고에 더하기
        print(f"{self.owner}님의 잔고: {self.balance}원")
    
    def withdraw(self, amount):
        """출금"""
        if self.balance >= amount:
            self.balance -= amount  # 나의 잔고에서 빼기
            return True
        return False

# 두 개의 계좌
john_account = BankAccount("John", 100000)
jane_account = BankAccount("Jane", 200000)

# 각자 다른 잔고
john_account.deposit(50000)   # John님의 잔고: 150000원
jane_account.withdraw(100000) # Jane 잔고: 100000원
```

**핵심:**
- `self.balance` = "나의" 잔고
- `john_account.balance` = John의 잔고
- `jane_account.balance` = Jane의 잔고
- 같은 설계도(Class)로 만들어도 각자 독립적!

### 2.3 상속 (Inheritance)

```python
# 부모 클래스
class Animal:
    def __init__(self, name):
        self.name = name
    
    def speak(self):
        print(f"{self.name}: 동물 소리!")

# 자식 클래스 (부모 기능 물려받음)
class Dog(Animal):
    def speak(self):
        print(f"{self.name}: 멍멍!")

class Cat(Animal):
    def speak(self):
        print(f"{self.name}: 야옹!")

# 사용
dog = Dog("바둑이")
cat = Cat("나비")

dog.speak()  # 바둑이: 멍멍!
cat.speak()  # 나비: 야옹!
```

---

## 3. Hantubot 코드 구조 이해

### 3.1 전체 구조

```
hantubot/
├── core/           # 핵심 엔진
│   ├── engine.py       # 메인 엔진 (총괄 관리자)
│   ├── portfolio.py    # 포트폴리오 (내 자산 관리)
│   └── clock.py        # 시장 시간 관리
│
├── strategies/     # 전략들
│   ├── opening_breakout_strategy.py
│   ├── volume_spike_strategy.py
│   └── closing_price_advanced_screener.py
│
├── execution/      # 주문 실행
│   ├── broker.py       # 증권사 API 연결
│   └── order_manager.py # 주문 관리
│
└── reporting/      # 보고 및 알림
    ├── notifier.py     # Discord 알림
    └── study.py        # 유목민 공부법
```

### 3.2 데이터 흐름

```
1. Engine (엔진 시작)
   ↓
2. Strategy (전략이 신호 생성)
   ↓ signals = [{"symbol": "005930", "side": "buy", ...}]
3. OrderManager (신호 검증)
   ↓ 현금 충분? 이미 보유?
4. Broker (증권사 API)
   ↓ 실제 주문 전송
5. Portfolio (포트폴리오 업데이트)
   ↓ 현금 - 주식가격, 주식 +1
6. Notifier (Discord 알림)
   ✅ "삼성전자 10주 매수!"
```

---

## 4. 단계별 학습 로드맵

### 🎯 레벨 1: 코드 읽기 마스터 (1주)

#### Day 1-2: Portfolio 완전 정복

**파일:** `hantubot/core/portfolio.py`

**학습 목표:** Class의 기본 구조 이해

```python
# portfolio.py 분석 포인트

class Portfolio:
    def __init__(self, initial_cash):
        # Q: 이 함수는 언제 실행되나?
        # A: Portfolio() 할 때 자동 실행!
        self._cash = initial_cash
        self._positions = {}
    
    def get_cash(self):
        # Q: self._cash는 뭐지?
        # A: 이 포트폴리오의 현금!
        return self._cash
    
    def update_on_fill(self, fill_details):
        # Q: 이 함수는 뭐하는 거지?
        # A: 주문 체결되면 현금/주식 업데이트!
        if side == 'buy':
            self._cash -= amount  # 현금 줄이기
```

**실습 과제:**
```python
# 1. portfolio.py 열기
# 2. 각 함수마다 주석 달기
# 3. print() 추가해서 실행해보기

def get_cash(self):
    """현금 조회"""
    print(f"[DEBUG] 현재 현금: {self._cash}원")  # 추가!
    return self._cash
```

#### Day 3-4: 간단한 전략 읽기

**파일:** `hantubot/strategies/closing_price_advanced_screener.py`

**분석 체크리스트:**
- [ ] `__init__`에서 뭘 초기화하나?
- [ ] `generate_signal`은 언제 호출되나?
- [ ] 어떤 조건일 때 매수하나?
- [ ] return 값은 무엇인가?

```python
async def generate_signal(self, data_payload, portfolio):
    signals = []  # 빈 리스트 (신호 담을 상자)
    
    # 1. 시간 체크
    if now.time() < self.run_time:
        return []  # 빈 리스트 반환 (신호 없음)
    
    # 2. 종목 분석
    for ticker in tickers:  # 하나씩 검사
        score = self._calculate_score(...)
        
        if score > 80:  # 점수 높으면
            signals.append({  # 리스트에 추가
                "symbol": ticker,
                "side": "buy"
            })
    
    return signals  # 신호 리스트 반환
```

#### Day 5-7: 흐름 추적 연습

**미션:** 주문이 어떻게 실행되는지 따라가기

```
파일 순서대로 열어서 읽기:
1. engine.py (_run_strategies 함수)
2. strategy.py (generate_signal 함수)
3. order_manager.py (process_signal 함수)
4. broker.py (place_order 함수)
5. portfolio.py (update_on_fill 함수)
```

**실습:**
각 파일에 `print(f"[1단계] 전략 실행")` 같은 로그 추가

---

### 🎯 레벨 2: 코드 수정 마스터 (1주)

#### Day 1-3: 설정값 바꾸기

**난이도:** ⭐ (매우 쉬움)

```python
# 파일: closing_price_advanced_screener.py

# 기존
self.cci_target = 180

# 수정
self.cci_target = 200  # 180 → 200 바꿔보기!
```

**과제:**
1. CCI 목표값 바꾸기 (180 → 200)
2. 실행 시간 바꾸기 (15:03 → 15:05)
3. 점수 기준 바꾸기 (80 → 85)

#### Day 4-5: 조건 추가하기

**난이도:** ⭐⭐ (쉬움)

```python
# 기존 코드
if price > 70000:
    매수()

# 수정: 조건 추가
if price > 70000 and volume > 1000000:
    매수()  # 가격 + 거래량 조건
```

**과제:**
1. 거래량 조건 추가
2. 시가총액 필터 추가
3. 업종 필터 추가

#### Day 6-7: 로그 확인하며 디버깅

```python
# 디버깅 팁
print(f"현재 가격: {price}")
print(f"현재 거래량: {volume}")
print(f"조건 통과? {price > 70000}")

# logger 사용 (더 전문적)
logger.info(f"[전략] 종목 분석: {symbol}")
logger.debug(f"[상세] 점수: {score}")
```

---

### 🎯 레벨 3: 전략 개발 마스터 (2주)

#### Week 1: 템플릿 복사 및 수정

**Step 1: 파일 복사**
```bash
# closing_price_advanced_screener.py 복사
# → my_first_strategy.py로 이름 변경
```

**Step 2: Class 이름 변경**
```python
# 기존
class ClosingPriceAdvancedScreener(BaseStrategy):

# 수정
class MyFirstStrategy(BaseStrategy):
```

**Step 3: 간단한 로직 구현**
```python
class MyFirstStrategy(BaseStrategy):
    def __init__(self, strategy_id, config, broker, clock, notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        self.target_symbols = ["005930", "000660"]  # 삼성, 하이닉스만
    
    async def generate_signal(self, data_payload, portfolio):
        signals = []
        now = dt.datetime.now()
        
        # 1. 시간 체크 (10시~11시만)
        if not (10 <= now.hour < 11):
            return signals
        
        # 2. 종목 검사
        for symbol in self.target_symbols:
            price = self.broker.get_current_price(symbol)
            
            # 3. 단순 조건: 가격이 70000원 이상
            if price >= 70000:
                signals.append({
                    'strategy_id': self.strategy_id,
                    'symbol': symbol,
                    'side': 'buy',
                    'quantity': 1,
                    'price': 0,
                    'order_type': 'market'
                })
                break  # 한 종목만
        
        return signals
```

#### Week 2: 전략 고도화

**추가할 기능:**
1. 기술적 지표 (이동평균, RSI 등)
2. 거래량 분석
3. 매도 로직
4. 손익 관리

```python
async def generate_signal(self, data_payload, portfolio):
    signals = []
    
    # 매도 로직 (보유 중이면)
    positions = portfolio.get_positions_by_strategy(self.strategy_id)
    for symbol, position in positions.items():
        current_price = self.broker.get_current_price(symbol)
        avg_price = position['avg_price']
        
        # 수익률 계산
        profit_pct = ((current_price / avg_price) - 1) * 100
        
        # 3% 익절 또는 -2% 손절
        if profit_pct >= 3.0 or profit_pct <= -2.0:
            signals.append({
                'strategy_id': self.strategy_id,
                'symbol': symbol,
                'side': 'sell',
                'quantity': position['quantity'],
                'price': 0,
                'order_type': 'market'
            })
    
    # 매수 로직...
    return signals
```

---

## 5. 실습 프로젝트

### 프로젝트 1: 간격 돌파 전략

**목표:** 전일 고가 돌파 시 매수

```python
class GapBreakoutStrategy(BaseStrategy):
    async def generate_signal(self, data_payload, portfolio):
        signals = []
        
        for symbol in ["005930", "000660"]:
            # 1. 어제 데이터 가져오기
            hist_data = self.broker.get_historical_daily_data(symbol, days=2)
            yesterday_high = float(hist_data[1]['stck_hgpr'])
            
            # 2. 현재가 가져오기
            current_price = self.broker.get_current_price(symbol)
            
            # 3. 전일 고가 돌파?
            if current_price > yesterday_high:
                signals.append({
                    'strategy_id': self.strategy_id,
                    'symbol': symbol,
                    'side': 'buy',
                    'quantity': 1,
                    'price': 0,
                    'order_type': 'market'
                })
        
        return signals
```

### 프로젝트 2: 이동평균 교차 전략

**목표:** 단기 이평선이 장기 이평선 돌파 시 매수

```python
def calculate_ma(prices, period):
    """이동평균 계산"""
    return sum(prices[-period:]) / period

class MaCrossStrategy(BaseStrategy):
    async def generate_signal(self, data_payload, portfolio):
        signals = []
        
        for symbol in self.target_symbols:
            hist_data = self.broker.get_historical_daily_data(symbol, days=60)
            
            # 종가 리스트
            closes = [float(d['stck_clpr']) for d in hist_data]
            
            # 5일 이평, 20일 이평
            ma5 = calculate_ma(closes, 5)
            ma20 = calculate_ma(closes, 20)
            
            # 골든크로스?
            if ma5 > ma20:
                signals.append({
                    'strategy_id': self.strategy_id,
                    'symbol': symbol,
                    'side': 'buy',
                    'quantity': 1,
                    'price': 0,
                    'order_type': 'market'
                })
        
        return signals
```

### 프로젝트 3: 변동성 돌파 전략

**목표:** 당일 변동폭의 일정 비율 돌파 시 매수

```python
class VolatilityBreakoutStrategy(BaseStrategy):
    async def generate_signal(self, data_payload, portfolio):
        signals = []
        
        for symbol in self.target_symbols:
            # 전일 데이터
            hist_data = self.broker.get_historical_daily_data(symbol, days=2)
            yesterday = hist_data[1]
            
            prev_high = float(yesterday['stck_hgpr'])
            prev_low = float(yesterday['stck_lwpr'])
            prev_close = float(yesterday['stck_clpr'])
            
            # 전일 변동폭
            prev_range = prev_high - prev_low
            
            # 목표가 = 시가 + (전일 변동폭 * 0.5)
            today_open = float(hist_data[0]['stck_oprc'])
            target_price = today_open + (prev_range * 0.5)
            
            # 현재가가 목표가 돌파?
            current_price = self.broker.get_current_price(symbol)
            if current_price > target_price:
                signals.append({
                    'strategy_id': self.strategy_id,
                    'symbol': symbol,
                    'side': 'buy',
                    'quantity': 1,
                    'price': 0,
                    'order_type': 'market'
                })
        
        return signals
```

---

## 6. FAQ

### Q1: 왜 `self`를 매번 쓰나요?

**A:** "나의" 것임을 명시하기 위해!

```python
class Person:
    def __init__(self, name):
        self.name = name  # 나의 이름
    
    def greet(self):
        print(f"안녕, 나는 {self.name}이야")  # 나의 이름 사용

john = Person("John")
jane = Person("Jane")

john.greet()  # 안녕, 나는 John이야
jane.greet()  # 안녕, 나는 Jane이야
```

### Q2: `async def`는 뭔가요?

**A:** 비동기 함수 (나중에 배워도 됨!)

```python
# 일반 함수
def normal_function():
    return "즉시 실행"

# 비동기 함수 (await와 함께 사용)
async def async_function():
    await some_task()  # 기다렸다가
    return "완료"      # 실행

# Hantubot에서는 그냥 패턴으로 이해하면 됨
async def generate_signal(self, ...):
    # 전략 로직
    return signals
```

### Q3: 딕셔너리와 리스트 차이?

```python
# 리스트 = 순서가 있는 상자들
stocks = ["삼성전자", "SK하이닉스", "NAVER"]
print(stocks[0])  # 삼성전자 (0번째)

# 딕셔너리 = 이름표 붙은 상자들
portfolio = {
    "삼성전자": 10,
    "SK하이닉스": 5
}
print(portfolio["삼성전자"])  # 10 (이름으로 찾기)
```

### Q4: 어떤 순서로 파일을 읽어야 하나요?

**추천 순서:**
1. `portfolio.py` ⭐ (가장 단순)
2. `closing_price_advanced_screener.py` ⭐⭐
3. `order_manager.py` ⭐⭐
4. `opening_breakout_strategy.py` ⭐⭐⭐
5. `volume_spike_strategy.py` ⭐⭐⭐
6. `engine.py` ⭐⭐⭐⭐ (가장 복잡)

### Q5: 에러가 나면 어떻게 하나요?

**디버깅 3단계:**

```python
# 1단계: print로 확인
def generate_signal(self, ...):
    print(f"[DEBUG] 함수 시작!")
    print(f"[DEBUG] 종목 수: {len(tickers)}")
    
    for ticker in tickers:
        print(f"[DEBUG] 분석 중: {ticker}")

# 2단계: try-except로 에러 잡기
try:
    price = self.broker.get_current_price(symbol)
except Exception as e:
    print(f"[ERROR] 가격 조회 실패: {e}")
    return []

# 3단계: logger 사용
logger.info(f"전략 실행: {now}")
logger.error(f"에러 발생: {e}")
```

---

## 7. 학습 리소스

### 추천 순서

**1주차: 파이썬 기초 복습**
- 점프 투 파이썬 (무료): https://wikidocs.net/book/1
- 주요 챕터: 변수, 함수, 조건문, 반복문, 딕셔너리

**2주차: Class 집중 학습**
- 파이썬 Class 가이드: https://wikidocs.net/28
- 실습: Car, BankAccount 예제 직접 타이핑

**3주차: Hantubot 코드 읽기**
- Portfolio → Strategy → Engine 순서
- 각 파일마다 주석 달기

**4주차: 간단한 전략 만들기**
- 템플릿 복사 → 수정 → 테스트

---

## 8. 체크리스트

### 레벨 1 완료 체크리스트
- [ ] Class와 Self 개념 이해
- [ ] portfolio.py 전체 이해
- [ ] 전략 파일 구조 파악
- [ ] 데이터 흐름 추적 가능

### 레벨 2 완료 체크리스트
- [ ] 설정값 수정 가능
- [ ] 조건 추가/수정 가능
- [ ] print/logger로 디버깅 가능
- [ ] 에러 메시지 이해 가능

### 레벨 3 완료 체크리스트
- [ ] 새 전략 파일 생성
- [ ] 기본 로직 구현
- [ ] 매수/매도 로직 작성
- [ ] config.yaml 연동

---

## 🎯 최종 목표

**1개월 후:**
- ✅ 코드 읽기 가능
- ✅ 기존 전략 수정 가능
- ✅ 간단한 전략 작성 가능

**3개월 후:**
- ✅ 복잡한 전략 개발
- ✅ 백테스팅 구현
- ✅ 자신만의 지표 추가

**6개월 후:**
- ✅ 완전한 자동매매 시스템 운영
- ✅ 커뮤니티 기여
- ✅ 새로운 아이디어 구현

