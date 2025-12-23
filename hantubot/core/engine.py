# hantubot_prod/hantubot/core/engine.py
import asyncio
import datetime as dt
import importlib
import os
import time # For time.sleep for non-async parts
from typing import Dict, List, Any

from ..core.clock import MarketClock
from ..core.portfolio import Portfolio
from ..execution.broker import Broker
from ..execution.order_manager import OrderManager
from ..reporting.logger import get_logger, get_data_logger
from ..reporting.notifier import Notifier
from ..reporting.report import ReportGenerator
from ..reporting.study import run_daily_study
from ..strategies.base_strategy import BaseStrategy

logger = get_logger(__name__)
signals_logger = get_data_logger("signals")

class TradingEngine:
    """
    자동매매 시스템의 메인 엔진.
    모든 핵심 컴포넌트를 통합하고, 시장 단계별 로직을 실행하며,
    주기적인 매매 루프를 관리합니다.
    """
    def __init__(self, config: Dict, market_clock: MarketClock, broker: Broker,
                 portfolio: Portfolio, order_manager: OrderManager, notifier: Notifier):
        self.config = config
        self.market_clock = market_clock
        self.broker = broker
        self.portfolio = portfolio
        self.order_manager = order_manager
        self.notifier = notifier
        self.active_strategies: List[BaseStrategy] = []
        self.daily_data_cache: Dict[str, Any] = {}
        self.cache_date = None
        self._load_strategies()
        self._running = False
        logger.info("트레이딩 엔진 초기화 완료.")

    def _load_strategies(self):
        """설정 파일에 정의된 전략들을 동적으로 로드합니다."""
        strategy_configs = self.config.get('active_strategies', [])
        
        for strat_name in strategy_configs:
            try:
                # 전략 모듈을 절대 경로로 임포트합니다.
                module_path = f"hantubot.strategies.{strat_name}"
                module = importlib.import_module(module_path)
                
                # 모듈 이름에서 클래스 이름을 유추합니다. (e.g., momentum_strategy -> MomentumStrategy)
                strategy_class_name = ''.join(word.capitalize() for word in strat_name.split('_'))
                
                strategy_class = getattr(module, strategy_class_name)
                
                # Instantiate the strategy, passing required dependencies
                strategy_instance = strategy_class(
                    strategy_id=strat_name,
                    config={}, # Placeholder for strategy-specific config
                    broker=self.broker,
                    clock=self.market_clock,
                    notifier=self.notifier
                )
                self.active_strategies.append(strategy_instance)
                logger.info(f"Strategy '{strat_name}' loaded successfully.")
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to load strategy '{strat_name}': {e}", exc_info=True)
                self.notifier.send_alert(f"전략 로드 실패: {strat_name} ({e})", level='error')
        
        if not self.active_strategies:
            logger.warning("전략이 로드되지 않았습니다. 봇이 매매 신호를 생성하지 않습니다.")

    async def _poll_for_fills(self):
        """백그라운드에서 주기적으로 주문 체결 여부를 확인합니다."""
        logger.info("Fill polling task started.")
        while self._running:
            try:
                # 포트폴리오에 기록된 미체결 주문 목록
                open_order_ids = list(self.portfolio._open_orders.keys())
                if not open_order_ids:
                    await asyncio.sleep(15) # 미체결 주문이 없으면 15초 대기
                    continue

                # API를 통해 실제 미체결 주문 목록 조회
                unclosed_orders_from_api = self.broker.get_unclosed_orders()
                api_order_ids = {order['odno'] for order in unclosed_orders_from_api}
                
                # 시스템에는 있지만 API 결과에는 없는 주문 찾기 = 체결된 주문
                filled_order_ids = [oid for oid in open_order_ids if oid not in api_order_ids]

                for order_id in filled_order_ids:
                    filled_order = self.portfolio._open_orders[order_id]
                    logger.info(f"Detected fill for order ID: {order_id}. Details: {filled_order}")
                    
                    # 체결 정보 구성 (API 응답을 파싱해야 하지만, 여기서는 주문 정보로 대체)
                    fill_details = {
                        'order_id': order_id,
                        'symbol': filled_order['symbol'],
                        'side': filled_order['side'],
                        'filled_quantity': filled_order['quantity'], # 단순화를 위해 완전 체결로 가정
                        'fill_price': filled_order['price'] # 실제 체결가는 별도 조회 필요
                    }
                    
                    self.order_manager.handle_fill_update(fill_details)
                    self.notifier.send_alert(f"주문 체결 감지: {fill_details['side']} {fill_details['symbol']} {fill_details['filled_quantity']}주", level='info')
            
            except Exception as e:
                logger.error(f"Error in fill polling task: {e}", exc_info=True)

            await asyncio.sleep(15) # 15초마다 폴링
    
    async def _run(self):
        """메인 루프와 백그라운드 작업을 함께 실행합니다."""
        self._running = True
        # 백그라운드에서 체결 확인 루프 시작
        fill_poller_task = asyncio.create_task(self._poll_for_fills())
        
        # 메인 트레이딩 루프 실행
        await self.run_trading_loop()

        # 종료 시 백그라운드 작업 취소
        fill_poller_task.cancel()
        try:
            await fill_poller_task
        except asyncio.CancelledError:
            logger.info("Fill polling task cancelled.")

    async def _prepare_data_payload(self) -> Dict[str, Any]:
        """전략에 필요한 모든 데이터를 준비하고 캐싱합니다."""
        today = dt.date.today()
        if self.cache_date != today:
            logger.info(f"새로운 거래일({today})입니다. 일봉 데이터 캐시를 초기화합니다.")
            self.daily_data_cache.clear()
            self.cache_date = today

        all_symbols = set()
        for strategy in self.active_strategies:
            all_symbols.update(getattr(strategy, 'target_symbols', []))

        payload = {'historical_daily': {}, 'realtime_price': {}}
        
        for symbol in all_symbols:
            if symbol not in self.daily_data_cache:
                try:
                    logger.debug(f"캐시 미스: {symbol}의 일봉 데이터를 API로부터 조회합니다.")
                    hist_data = self.broker.get_historical_daily_data(symbol, days=60)
                    if hist_data:
                        self.daily_data_cache[symbol] = hist_data
                except Exception as e:
                    logger.error(f"데이터 준비 중 {symbol} 과거 데이터 조회 실패: {e}")
            
            if symbol in self.daily_data_cache:
                payload['historical_daily'][symbol] = self.daily_data_cache[symbol]
            
            try:
                price = self.broker.get_current_price(symbol)
                if price > 0:
                    payload['realtime_price'][symbol] = {'price': price}
            except Exception as e:
                logger.error(f"데이터 준비 중 {symbol} 현재가 조회 실패: {e}")
        
        return payload

    async def _process_market_open_logic(self):
        """장 시작 (09:00) 시 실행될 로직. 종가매매 및 고아 포지션을 청산합니다."""
        logger.info("장 시작! 시초가 청산 로직을 실행합니다.")
        
        positions_to_sell = []
        for symbol, position in self.portfolio.get_positions().items():
            strategy_id = position.get('strategy_id', '')
            # 종가매매 포지션 또는 시작 시 로드된 알 수 없는 포지션을 매도 대상에 추가
            if 'closing_price' in strategy_id or strategy_id == 'loaded_on_startup':
                positions_to_sell.append(position)
                logger.info(f"시초가 매도 대상 발견: {symbol} (사유: {strategy_id})")

        if positions_to_sell:
            for pos in positions_to_sell:
                sell_signal = {
                    'strategy_id': 'market_open_liquidation', 
                    'symbol': pos['symbol'], 
                    'side': 'sell', 
                    'quantity': pos['quantity'], 
                    'price': 0, 'order_type': 'market'
                }
                self.order_manager.process_signal(sell_signal)
        else:
            logger.info("시초가에 청산할 포지션이 없습니다.")

    async def _run_strategies(self, data_payload: Dict, closing_call: bool = False):
        """주어진 데이터로 적절한 시점의 전략을 실행하고 신호를 처리합니다."""
        active_strategies_count = 0
        for strategy in self.active_strategies:
            try:
                is_closing_strategy = 'closing_price' in strategy.strategy_id
                
                if (closing_call and not is_closing_strategy) or \
                   (not closing_call and is_closing_strategy):
                    continue
                
                active_strategies_count += 1
                signals = await strategy.generate_signal(data_payload, self.portfolio)
                for signal in signals:
                    signals_logger.info(signal)
                    self.order_manager.process_signal(signal)
            except Exception:
                logger.exception(f"전략 '{strategy.strategy_id}' 실행 중 오류 발생")
                self.notifier.send_alert(f"전략 '{strategy.strategy_id}' 실행 중 오류 발생", level='error')
        
        if active_strategies_count > 0:
            logger.info(f"{active_strategies_count}개의 활성 전략 실행 완료.")
        else:
            logger.debug("현재 시간에 실행할 활성 전략이 없습니다.")

    async def _process_post_market_logic(self):
        """장 종료 후 실행될 로직."""
        logger.info("장 종료. 후처리 로직을 실행합니다.")
        self.notifier.send_alert("장 종료. 리포트 생성 및 학습 루틴 실행 중.", level='info')
        
        # 1. 일일 리포트 생성
        try:
            report_generator = ReportGenerator(config=self.config, notifier=self.notifier)
            report_generator.generate_daily_report()
        except Exception as e:
            logger.error(f"일일 리포트 생성 실패: {e}", exc_info=True)
            self.notifier.send_alert("일일 리포트 생성 중 오류가 발생했습니다.", level='error')

        # 2. "100일 공부" 자동화 루틴 실행
        try:
            run_daily_study(broker=self.broker, notifier=self.notifier)
        except Exception as e:
            logger.error(f"데일리 스터디 자료 생성 실패: {e}", exc_info=True)
            self.notifier.send_alert("데일리 스터디 자료 생성 중 오류가 발생했습니다.", level='error')

        logger.info("모든 장 마감 후 작업 완료.")

    async def run_trading_loop(self):
        """메인 트레이딩 루프. 상태에 따라 로직을 실행하고 대기합니다."""
        wake_up_time = dt.time(8, 50)
        post_market_run_today = False

        while self._running:
            now = dt.datetime.now()
            logger.debug(f"Trading loop tick: {now.strftime('%H:%M:%S')}")

            is_trading_day = self.market_clock.is_trading_day(now.date())

            if is_trading_day:
                if self.market_clock.is_market_open(now):
                    post_market_run_today = False
                    
                    if now.hour == 9 and now.minute == 0:
                        await self._process_market_open_logic()
                    
                    data_payload = await self._prepare_data_payload()
                    is_closing_time = self.market_clock.is_market_closing_approach(now)
                    await self._run_strategies(data_payload, closing_call=is_closing_time)
                    
                    # 60초 대기를 1초 단위로 쪼개어, 중간에 종료 신호를 받을 수 있도록 함
                    interval = self.config.get('trading_loop_interval_seconds', 60)
                    for _ in range(interval):
                        if not self._running:
                            break
                        await asyncio.sleep(1)
                    
                    continue
                elif now.time() < self.market_clock.get_market_times()['open']:
                    logger.info(f"개장 전입니다. {self.market_clock.get_market_times()['open']}까지 대기합니다.")
                    open_time = dt.datetime.combine(now.date(), self.market_clock.get_market_times()['open'])
                    await asyncio.sleep(max(1, (open_time - now).total_seconds()))
                    continue
                elif now.time() >= self.market_clock.get_market_times()['close'] and not post_market_run_today:
                    await self._process_post_market_logic()
                    post_market_run_today = True
            
            # 장 외 시간이거나, 비거래일이거나, 장 마감 후 로직을 이미 실행한 경우
            logger.info("장 외 시간입니다. 다음 개장까지 대기합니다.")
            next_trading_day = now.date()
            if now.time() >= wake_up_time:
                next_trading_day += dt.timedelta(days=1)

            while not self.market_clock.is_trading_day(next_trading_day):
                next_trading_day += dt.timedelta(days=1)
            
            next_wake_up = dt.datetime.combine(next_trading_day, wake_up_time)
            sleep_duration = (next_wake_up - now).total_seconds()
            
            if sleep_duration > 0:
                logger.info(f"다음 기상 시간 {next_wake_up.strftime('%Y-%m-%d %H:%M')}까지 대기합니다. (약 {sleep_duration / 3600:.1f}시간)")
                # 긴 잠을 짧은 잠으로 쪼개어, 중간에 종료 신호를 받을 수 있도록 함
                end_time = dt.datetime.now() + dt.timedelta(seconds=sleep_duration)
                while dt.datetime.now() < end_time:
                    if not self._running:
                        logger.info("대기 중 정지 신호를 감지하여 루프를 종료합니다.")
                        break
                    await asyncio.sleep(1)
            
            if not self._running:
                break

    async def _run(self):
        """메인 루프와 백그라운드 작업을 함께 실행합니다."""
        self._running = True
        fill_poller_task = asyncio.create_task(self._poll_for_fills())
        await self.run_trading_loop()
        fill_poller_task.cancel()
        try:
            await fill_poller_task
        except asyncio.CancelledError:
            logger.info("체결 감시 태스크를 종료합니다.")

    def start(self):
        """트레이딩 엔진을 시작합니다."""
        logger.info("트레이딩 엔진을 시작합니다...")
        try:
            asyncio.run(self._run())
        except (KeyboardInterrupt, SystemExit):
            logger.info("프로그램 종료 신호를 감지했습니다. 안전하게 종료합니다.")
        finally:
            self.stop()
    
    def stop(self):
        """트레이딩 엔진을 정지합니다."""
        if self._running:
            logger.info("트레이딩 엔진을 정지합니다...")
            self._running = False
            self.notifier.send_alert("Hantubot 시스템이 정지되었습니다.", level='warning')
