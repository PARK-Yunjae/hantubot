
import asyncio
import datetime
import sys
import os
import logging
from unittest.mock import MagicMock, patch

# 로깅 설정을 최상단으로 이동
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='simulation.log', filemode='w')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)
logger = logging.getLogger("Simulator")

# 프로젝트 루트 경로 설정
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hantubot.core.engine import TradingEngine
from hantubot.core.clock import MarketClock
from hantubot.core.portfolio import Portfolio
from hantubot.core.regime_manager import RegimeManager
from hantubot.execution.order_manager import OrderManager

# 가짜 시간 관리 클래스
class FakeClock:
    def __init__(self, start_time):
        self._current_time = start_time
    
    def now(self):
        return self._current_time
    
    def date(self):
        return self._current_time.date()
    
    def time(self):
        return self._current_time.time()
        
    def advance_time(self, seconds=0, minutes=0, hours=0):
        self._current_time += datetime.timedelta(seconds=seconds, minutes=minutes, hours=hours)
        return self._current_time

    def set_time(self, new_time):
        self._current_time = new_time
        return self._current_time

# 전역 FakeClock 인스턴스 (Mock 클래스에서 접근용)
fake_clock_instance = None

# Fake DateTime Class
class FakeDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return fake_clock_instance.now()

# Spy Notifier
class SpyNotifier:
    def __init__(self):
        self.logs = []
        self.sent_alerts = [] # (time, message, embed)
        self.dedup_cache = {}

    def send_alert(self, message, embed=None, level='info', dedup_key=None):
        if dedup_key:
            if dedup_key in self.dedup_cache:
                return # Deduped
            self.dedup_cache[dedup_key] = True

        log_entry = f"[ALERT] {message} (Embed: {embed is not None})"
        self.logs.append(log_entry)
        self.sent_alerts.append({
            'time': fake_clock_instance.now() if fake_clock_instance else None,
            'message': message,
            'embed': embed,
            'level': level,
            'dedup_key': dedup_key
        })
        print(f"  >>> 🔔 ALERT SENT: {message}")

# 원본 asyncio.sleep 저장
original_asyncio_sleep = asyncio.sleep

# Spy Broker
class SpyBroker:
    def __init__(self):
        self.IS_MOCK = True
        self.concluded_orders = []
    
    def get_current_price(self, symbol):
        return 50000 # Mock price
    
    def get_historical_daily_data(self, symbol, days=30):
        # Mock daily data
        data = []
        base_date = datetime.date.today() - datetime.timedelta(days=days)
        for i in range(days):
            d = base_date + datetime.timedelta(days=i)
            data.append({
                'stck_bsop_date': d.strftime("%Y%m%d"),
                'stck_clpr': '50000',
                'stck_oprc': '49000',
                'stck_hgpr': '51000',
                'stck_lwpr': '48000',
                'acml_vol': '1000000'
            })
        return data

    def get_realtime_transaction_ranks(self, top_n=20):
        # Mock ranking data for screening
        return [
            {'mksc_shrn_iscd': '005930', 'hts_kor_isnm': '삼성전자', 'acml_tr_pbmn': '500000000000', 'stck_prpr': '70000', 'prdy_ctrt': '1.5', 'frgn_ntby_qty': '100000'},
            {'mksc_shrn_iscd': '000660', 'hts_kor_isnm': 'SK하이닉스', 'acml_tr_pbmn': '300000000000', 'stck_prpr': '120000', 'prdy_ctrt': '-0.5', 'frgn_ntby_qty': '-5000'}
        ]
        
    def get_concluded_orders(self):
        return []
        
    def get_volume_leaders(self, top_n=50):
        # Mock volume leaders
        return [
            {'mksc_shrn_iscd': '005930', 'hts_kor_isnm': '삼성전자', 'acml_tr_pbmn': '60000000000'},
            {'mksc_shrn_iscd': '000660', 'hts_kor_isnm': 'SK하이닉스', 'acml_tr_pbmn': '40000000000'}
        ]
        
    def get_current_price_detail(self, symbol):
        return {'stck_oprc': '51000', 'stck_prpr': '53000'} # Gap 3.9%
        
    def get_intraday_minute_data(self, symbol):
        # Mock minute data with huge volume
        return [{'acml_tr_pbmn': '2000000000'}] # 20억

# 시뮬레이션 실행 함수
async def run_simulation():
    global fake_clock_instance
    
    print("=" * 60)
    print("🚀 Hantubot Timeline Simulation Started")
    print("=" * 60)

    # 1. 시뮬레이션 시작 시간 설정 (08:30)
    start_dt = datetime.datetime(2025, 1, 2, 8, 30, 0) # 평일 목요일 가정
    fake_clock_instance = FakeClock(start_dt)
    
    # 2. 컴포넌트 초기화
    config = {
        'api': {'app_key': 'mock', 'app_secret': 'mock', 'account_no': 'mock'},
        'mode': 'mock',
        'active_strategies': ['closing_price_advanced_screener', 'opening_breakout_strategy', 'volume_spike_strategy'],
        'strategy_settings': {
            'closing_price_advanced_screener': {
                'enabled': True, 
                'supported_modes': ['mock'],
                'webhook_time': datetime.time(15, 3),
                'buy_start_time': datetime.time(15, 15),
                'buy_end_time': datetime.time(15, 20),
                'auto_buy_enabled': True
            },
            'opening_breakout_strategy': {'enabled': True, 'supported_modes': ['mock']},
            'volume_spike_strategy': {'enabled': True, 'supported_modes': ['mock']}
        },
        'policy': {'position_priority': 'closing_over_intraday'},
        'trading_hours': {
            'market_open': '09:00:00',
            'market_close': '15:30:00',
            'closing_call_start': '15:00:00'
        },
        'regime_settings': {'risk_on_threshold': 0.5, 'risk_off_threshold': -0.5}
    }
    
    # 중요: MarketClock 내부에서도 datetime.datetime을 쓰므로 patch가 필요함.
    # 하지만 MarketClock 생성자에서 현재 시간을 쓰지 않으므로 생성은 문제 없음.
    # is_trading_day 등에서 datetime.date를 씀.
    
    market_clock = MarketClock(config_path="configs/config.yaml") 
    broker = SpyBroker()
    notifier = SpyNotifier()
    portfolio = Portfolio(initial_cash=100000000)
    regime_manager = RegimeManager(config, broker)
    order_manager = OrderManager(broker, portfolio, notifier, regime_manager)
    
    engine = TradingEngine(config, market_clock, broker, portfolio, order_manager, notifier, regime_manager)
    
    # 3. 타임라인 정의
    timeline = [
        (datetime.time(8, 30), "엔진 시작 및 초기화"),
        (datetime.time(8, 50), "기상 시간 (Wake Up)"),
        (datetime.time(9, 0), "장 시작 (Market Open)"),
        (datetime.time(9, 1), "시초가 청산 로직"),
        (datetime.time(9, 30), "오전 리포트 (09:30)"),
        (datetime.time(12, 30), "점심 브리핑 (12:30)"),
        (datetime.time(14, 50), "오전/오후 전략 종료 (14:50)"),
        (datetime.time(15, 0), "오후 리포트 및 종가매매 준비 (15:00)"),
        (datetime.time(15, 3), "종가매매 Top3 웹훅 (15:03)"),
        (datetime.time(15, 15), "자동 매수 (15:15)"),
        (datetime.time(15, 20), "동시호가 진입 (15:20)"),
        (datetime.time(15, 30, 1), "장 종료 (Market Close)"),
        (datetime.time(16, 0), "장 마감 후 로직 (Post Market)"),
    ]
    
    print(f"\n[초기 상태] 시간: {fake_clock_instance.now()}")
    
    with patch('hantubot.core.engine.dt.datetime', FakeDateTime), \
         patch('hantubot.core.clock.datetime.datetime', FakeDateTime), \
         patch('hantubot.strategies.closing_price.strategy.dt.datetime', FakeDateTime), \
         patch('hantubot.strategies.volume_spike_strategy.dt.datetime', FakeDateTime), \
         patch('hantubot.strategies.opening_breakout_strategy.dt.datetime', FakeDateTime), \
         patch('hantubot.core.engine.asyncio.sleep') as mock_sleep:

        # asyncio.sleep이 호출되면 시간을 전진시키는 로직
        async def side_effect_sleep(seconds):
            current = fake_clock_instance.now()
            jump_seconds = seconds
            
            # [시간 가속] 장 시작 전(08:59 이전)과 장 마감 후(15:40 이후)에는 시간을 빨리 흐르게 함
            # 엔진이 1초씩 sleep하며 대기하는 구간을 빠르게 건너뛰기 위함
            if current.time() < datetime.time(8, 59) or current.time() >= datetime.time(15, 40):
                if seconds == 1:
                    jump_seconds = 60 # 1초 대기 요청 시 60초 전진 (60배속)
            
            fake_clock_instance.advance_time(seconds=jump_seconds)
            
            # 갱신된 시간 기준 로그 출력
            new_time = fake_clock_instance.now()
            if new_time.minute != current.minute and new_time.minute % 10 == 0:
                 print(f"  [Time] {new_time.strftime('%H:%M:%S')}")
            
            # 다른 태스크에게 실행 기회 양보 (중요!)
            await original_asyncio_sleep(0)
            return None

        mock_sleep.side_effect = side_effect_sleep
        
        simulation_end_time = datetime.datetime(2025, 1, 2, 16, 5, 0)
        
        async def stop_engine_at_end_time():
            while fake_clock_instance.now() < simulation_end_time:
                current_time = fake_clock_instance.now().time()
                await asyncio.sleep(0) # 양보
            
            print(f"\n🛑 시뮬레이션 종료 시간 도달: {fake_clock_instance.now()}")
            engine.stop()

        # Mocking specific methods to add spy logging
        original_process_signal = order_manager.process_signal
        def spy_process_signal(signal):
            print(f"  >>> 🛒 ORDER SIGNAL: {signal['side'].upper()} {signal['symbol']} (Strategy: {signal.get('strategy_id')})")
            return original_process_signal(signal)
        order_manager.process_signal = spy_process_signal

        # 실행
        engine._running = True
        
        task_engine = asyncio.create_task(engine._run())
        task_stopper = asyncio.create_task(stop_engine_at_end_time())
        
        try:
            await asyncio.gather(task_engine, task_stopper)
        except Exception as e:
            print(f"Simulation Error: {e}")
        
    # 결과 파일 저장
    with open("simulation_report.txt", "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("📊 시뮬레이션 결과 리포트\n")
        f.write("=" * 60 + "\n")
        
        f.write("\n[알림 발송 이력]\n")
        for alert in notifier.sent_alerts:
            t = alert['time'].strftime('%H:%M:%S') if alert['time'] else 'Unknown'
            msg = alert['message']
            dedup = alert['dedup_key']
            f.write(f"- [{t}] {msg} (Dedup: {dedup})\n")
        
        f.write("\n[Mock 주문 이력]\n")
        # 주문 이력은 OrderManager나 Broker에서 가져와야 하는데, SpyBroker는 기능이 약함
        # SpyBroker에 주문 기록 기능이 없으므로 로그에서 확인
        pass
    
    print("Simulation report saved to simulation_report.txt")
    
if __name__ == "__main__":
    try:
        asyncio.run(run_simulation())
    except KeyboardInterrupt:
        print("Simulation Interrupted")
