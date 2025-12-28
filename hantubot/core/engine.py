# hantubot_prod/hantubot/core/engine.py
import asyncio
import datetime as dt
import importlib
import os
import time # For time.sleep for non-async parts
from typing import Dict, List, Any

from ..core.clock import MarketClock
from ..core.portfolio import Portfolio
from ..core.regime_manager import RegimeManager # RegimeManager 임포트
from ..execution.broker import Broker
from ..execution.order_manager import OrderManager
from ..reporting.logger import get_logger, get_data_logger
from ..reporting.notifier import Notifier
from ..reporting.report import ReportGenerator
from ..reporting.study import run_daily_study
from ..optimization.analyzer import run_daily_optimization # New import
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
                 portfolio: Portfolio, order_manager: OrderManager, notifier: Notifier,
                 regime_manager: RegimeManager): # Add regime_manager here
        self.config = config
        self.market_clock = market_clock
        self.broker = broker
        self.portfolio = portfolio
        self.order_manager = order_manager
        self.notifier = notifier
        self.active_strategies: List[BaseStrategy] = []
        self.daily_data_cache: Dict[str, Any] = {}
        self.cache_date = None
        self._processed_fill_ids: set = set()
        self._test_signal_injected = False # 가짜 신호 주입 여부 플래그
        
        # 레짐 관리자는 이제 외부에서 주입됩니다.
        self.regime_manager = regime_manager
        
        self._load_strategies()
        self._running = False
        logger.info("트레이딩 엔진 초기화 완료.")

    def _load_strategies(self):
        """설정 파일에 정의된 전략들을 동적으로 로드하고, 실행 환경(모의/실전) 적합성을 검사합니다."""
        strategy_names = self.config.get('active_strategies', [])
        all_strategy_settings = self.config.get('strategy_settings', {})
        current_mode = 'mock' if self.broker.IS_MOCK else 'live'
        
        for strat_name in strategy_names:
            try:
                # 해당 전략의 설정을 config.yaml에서 가져옵니다.
                strategy_config = all_strategy_settings.get(strat_name, {})
                
                # 1. 실행 모드 호환성 검사
                supported_modes = strategy_config.get('supported_modes')
                if supported_modes and current_mode not in supported_modes:
                    logger.warning(
                        f"전략 '{strat_name}' 로드 건너뜀. "
                        f"이 전략은 {supported_modes} 모드만 지원하지만 현재 모드는 '{current_mode}'입니다."
                    )
                    continue

                # 2. 개별 전략 활성화 여부 검사
                if not strategy_config.get('enabled', True):
                    logger.warning(f"Strategy '{strat_name}' is disabled in config. Skipping.")
                    continue
                
                # 3. 전략 모듈 동적 로딩 및 초기화
                module_path = f"hantubot.strategies.{strat_name}"
                module = importlib.import_module(module_path)
                
                strategy_class_name = ''.join(word.capitalize() for word in strat_name.split('_'))
                strategy_class = getattr(module, strategy_class_name)

                strategy_instance = strategy_class(
                    strategy_id=strat_name,
                    config=strategy_config, # 개별 전략 설정을 전달
                    broker=self.broker,
                    clock=self.market_clock,
                    notifier=self.notifier
                )
                self.active_strategies.append(strategy_instance)
                logger.info(f"Strategy '{strat_name}' loaded successfully for '{current_mode}' mode.")
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to load strategy '{strat_name}': {e}", exc_info=True)
                self.notifier.send_alert(f"전략 로드 실패: {strat_name} ({e})", level='error')
        
        if not self.active_strategies:
            logger.warning("활성화된 전략이 없습니다. 봇이 매매 신호를 생성하지 않습니다.")

    async def _poll_for_fills(self):
        """백그라운드에서 주기적으로 실제 주문 체결 여부를 확인합니다."""
        logger.info("Fill polling task started.")
        while self._running:
            try:
                if not self.portfolio._open_orders:
                    await asyncio.sleep(15)
                    continue
                
                # 동시호가 시간(15:20-15:30)에는 체결 조회 API가 작동하지 않으므로 건너뜀
                now = dt.datetime.now()
                if now.hour == 15 and 20 <= now.minute < 30:
                    logger.debug("동시호가 시간(15:20-15:30)입니다. 체결 조회를 건너뜁니다.")
                    await asyncio.sleep(15)
                    continue
                
                loop = asyncio.get_running_loop()
                concluded_orders = await loop.run_in_executor(None, self.broker.get_concluded_orders)
                
                for fill in concluded_orders:
                    execution_id = fill.get('execution_id')
                    
                    if not execution_id or execution_id in self._processed_fill_ids:
                        continue
                        
                    logger.info(f"Detected new fill: {fill}")
                    
                    required_keys = ['order_id', 'symbol', 'side', 'filled_quantity', 'fill_price']
                    if not all(k in fill for k in required_keys):
                        logger.error(f"Incomplete fill data received from broker: {fill}. Skipping.")
                        continue

                    self.order_manager.handle_fill_update(fill)
                    self._processed_fill_ids.add(execution_id)
                    
                    # 상세 체결 알림 생성
                    side = fill['side']
                    symbol = fill['symbol']
                    quantity = int(fill['filled_quantity'])
                    price = float(fill['fill_price'])
                    total_amount = quantity * price
                    
                    # 종목명 조회
                    try:
                        from pykrx import stock
                        stock_name = stock.get_market_ticker_name(symbol)
                    except:
                        stock_name = symbol
                    
                    # 매수/매도 구분
                    if side == 'buy':
                        emoji = "💰"
                        color = 5763719  # 파란색
                        title = f"✅ 매수 체결: {stock_name} ({symbol})"
                    else:
                        emoji = "💵"
                        color = 15844367  # 빨간색
                        title = f"✅ 매도 체결: {stock_name} ({symbol})"
                    
                    # 현재 포트폴리오 상태
                    current_cash = self.portfolio.get_cash()
                    positions = self.portfolio.get_positions()
                    
                    # 필드 구성
                    fields = [
                        {"name": "체결 수량", "value": f"{quantity:,}주", "inline": True},
                        {"name": "체결 가격", "value": f"{price:,.0f}원", "inline": True},
                        {"name": "체결 금액", "value": f"{total_amount:,.0f}원", "inline": True},
                    ]
                    
                    # 매도 시 수익률 정보 추가
                    if side == 'sell':
                        original_order = self.portfolio._open_orders.get(fill.get('order_id'), {})
                        # 이전에 계산된 PnL 정보 활용
                        position_info = ""
                        if positions:
                            for sym, pos in positions.items():
                                position_info += f"▪️ {sym}: {pos['quantity']}주\n"
                        else:
                            position_info = "없음 (전부 청산)"
                        
                        fields.append({"name": "현재 보유 종목", "value": position_info or "없음", "inline": False})
                    
                    fields.append({"name": "현금 잔고", "value": f"{current_cash:,.0f}원", "inline": False})
                    
                    embed = {
                        "title": title,
                        "color": color,
                        "fields": fields,
                        "footer": {"text": f"체결 시간: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                    }
                    
                    self.notifier.send_alert(f"{emoji} {title}", embed=embed)
            
            except Exception as e:
                logger.error(f"Error in fill polling task: {e}", exc_info=True)

            await asyncio.sleep(15)
    
    async def _run(self):
        """메인 루프와 백그라운드 작업을 함께 실행합니다."""
        self._running = True
        fill_poller_task = asyncio.create_task(self._poll_for_fills())
        
        await self.run_trading_loop()

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
        """장 시작 (09:00) 시 실행될 로직. 모든 보유 포지션을 시초가에 청산합니다."""
        logger.info("장 시작! 시초가 청산 로직을 실행합니다.")
        
        positions = self.portfolio.get_positions()
        
        if positions:
            for symbol, position in positions.items():
                strategy_id = position.get('strategy_id', 'unknown')
                logger.info(f"시초가 매도 대상: {symbol} (전략: {strategy_id})")
                
                sell_signal = {
                    'strategy_id': 'market_open_liquidation', 
                    'symbol': position['symbol'], 
                    'side': 'sell', 
                    'quantity': position['quantity'], 
                    'price': 0, 
                    'order_type': 'market'
                }
                self.order_manager.process_signal(sell_signal)
            
            logger.info(f"시초가에 {len(positions)}개 포지션 청산 신호 생성 완료.")
        else:
            logger.info("시초가에 청산할 포지션이 없습니다.")
    
    async def _check_forced_liquidation(self):
        """
        전략별 시간대 강제 청산 로직 (우선 처리)
        
        시간대 종료 1분 전부터 청산하여 시간 넘어가는 일 방지
        """
        now = dt.datetime.now()
        positions = self.portfolio.get_positions()
        
        if not positions:
            return False  # 청산할 것이 없음
        
        liquidated = False
        
        for symbol, position in list(positions.items()):
            strategy_id = position.get('strategy_id', '')
            
            # opening_breakout_strategy: 09:29부터 청산 시작
            if 'opening_breakout' in strategy_id:
                # 09:29 이상이면 청산 (1분 전부터 시작)
                if (now.hour == 9 and now.minute >= 29) or now.hour > 9:
                    logger.warning(f"[우선 청산] {symbol} - opening_breakout 시간 종료 임박 (09:30)")
                    sell_signal = {
                        'strategy_id': 'forced_liquidation_0930',
                        'symbol': symbol,
                        'side': 'sell',
                        'quantity': position['quantity'],
                        'price': 0,
                        'order_type': 'market'
                    }
                    self.order_manager.process_signal(sell_signal)
                    liquidated = True
            
            # volume_spike_strategy: 14:58부터 청산 시작 (2분 여유)
            elif 'volume_spike' in strategy_id:
                # 14:58 이상이면 청산 (종가매매와 충돌 방지)
                if (now.hour == 14 and now.minute >= 58) or now.hour >= 15:
                    logger.warning(f"[우선 청산] {symbol} - volume_spike 시간 종료 임박 (15:00, 2분 전 청산)")
                    sell_signal = {
                        'strategy_id': 'forced_liquidation_1500',
                        'symbol': symbol,
                        'side': 'sell',
                        'quantity': position['quantity'],
                        'price': 0,
                        'order_type': 'market'
                    }
                    self.order_manager.process_signal(sell_signal)
                    liquidated = True
        
        return liquidated  # 청산 실행 여부 반환

    async def _run_strategies(self, data_payload: Dict, closing_call: bool = False):
        """주어진 데이터로 적절한 시점의 전략을 실행하고 신호를 처리합니다."""
        
        # --- [테스트용] 가짜 신호 주입 로직 ---
        test_config = self.config.get('testing', {})
        if test_config.get('force_signal_enabled', False) and not self._test_signal_injected:
            strategy_id = test_config.get('force_signal_strategy_id', 'volume_spike_strategy')
            symbol = test_config.get('force_signal_symbol', '005930')
            logger.warning(f"테스트용 가짜 신호를 주입합니다: 전략='{strategy_id}', 종목='{symbol}'")
            
            fake_signal = {
                'strategy_id': strategy_id,
                'symbol': symbol,
                'side': 'buy',
                'quantity': 1, # 테스트용 최소 수량
                'price': 0,
                'order_type': 'market',
            }
            self.order_manager.process_signal(fake_signal)
            self._test_signal_injected = True # 한번만 실행되도록 플래그 설정
            return # 가짜 신호 주입 후에는 실제 전략 로직을 건너뜀
        
        # 1. 현재 시장 레짐 결정
        current_regime = self.regime_manager.determine_regime()
        data_payload['regime'] = current_regime # 데이터 페이로드에 레짐 정보 추가
        
        active_strategies_count = 0
        for strategy in self.active_strategies:
            try:
                is_closing_strategy = 'closing_price' in strategy.strategy_id
                
                if closing_call != is_closing_strategy:
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
            logger.info(f"[{current_regime} 모드] {active_strategies_count}개의 활성 전략 실행 완료.")
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
            # 장 마감 후 1시간 이내 재실행이면 강제 실행 (force_run=True)
            now = dt.datetime.now()
            force_run = now.hour <= 16 and now.minute <= 30  # 16:30까지는 강제 실행
            run_daily_study(broker=self.broker, notifier=self.notifier, force_run=force_run)
        except Exception as e:
            logger.error(f"데일리 스터디 자료 생성 실패: {e}", exc_info=True)
            self.notifier.send_alert("데일리 스터디 자료 생성 중 오류가 발생했습니다.", level='error')

        # 3. 일일 전략 최적화 루틴 실행
        try:
            run_daily_optimization()
        except Exception as e:
            logger.error(f"일일 전략 최적화 루틴 실행 실패: {e}", exc_info=True)
            self.notifier.send_alert("일일 전략 최적화 루틴 실행 중 오류가 발생했습니다.", level='error')

        logger.info("모든 장 마감 후 작업 완료.")

    async def run_trading_loop(self):
        """메인 트레이딩 루프. 상태에 따라 로직을 실행하고 대기합니다."""
        wake_up_time = dt.time(8, 50)
        post_market_run_today = False

        while self._running:
            now = dt.datetime.now()
            logger.debug(f"트레이딩 루프 틱: {now.strftime('%H:%M:%S')}")

            is_trading_day = self.market_clock.is_trading_day(now.date())

            if is_trading_day:
                if self.market_clock.is_market_open(now):
                    post_market_run_today = False
                    logger.debug("장이 열려있습니다. 전략 실행 준비 중.")
                    
                    # 09:01 장 시작 시 모든 포지션 청산 (최우선 처리)
                    if now.hour == 9 and now.minute == 1:
                        await self._process_market_open_logic()
                        # 청산 후 3초 대기 (체결 처리 시간)
                        await asyncio.sleep(3)
                    
                    # 전략별 시간대 강제 청산 체크 (우선 처리)
                    liquidated = await self._check_forced_liquidation()
                    if liquidated:
                        logger.info("⚠️ 강제 청산 실행됨. 전략 실행 건너뜀 (청산 우선).")
                        # 청산 후 3초 대기하고 다음 루프로
                        await asyncio.sleep(3)
                        continue  # 전략 실행 건너뛰고 다음 루프로
                    
                    # 청산이 없을 때만 전략 실행
                    logger.debug("데이터 페이로드 준비 중...")
                    data_payload = await self._prepare_data_payload()
                    logger.debug("데이터 페이로드 준비 완료. 전략 실행 중...")
                    
                    is_closing_time = self.market_clock.is_market_closing_approach(now)
                    await self._run_strategies(data_payload, closing_call=is_closing_time)
                    logger.debug("전략 실행 완료.")
                    
                    interval = self.config.get('trading_loop_interval_seconds', 60)
                    logger.debug(f"다음 틱까지 {interval}초 대기 중...")
                    for _ in range(interval):
                        if not self._running:
                            break
                        await asyncio.sleep(1)
                    
                    continue
                elif now.time() >= self.market_clock.get_market_times()['close'] and not post_market_run_today:
                    logger.debug("장이 마감되었습니다. 장 마감 후 로직 실행 중.")
                    await self._process_post_market_logic()
                    post_market_run_today = True
                    
                    # 15:40 자동 종료 체크
                    auto_shutdown_enabled = os.getenv('AUTO_SHUTDOWN_ENABLED', 'false').lower() == 'true'
                    shutdown_time_str = os.getenv('AUTO_SHUTDOWN_TIME', '15:40')
                    
                    if auto_shutdown_enabled:
                        try:
                            shutdown_hour, shutdown_minute = map(int, shutdown_time_str.split(':'))
                            shutdown_time = dt.time(shutdown_hour, shutdown_minute)
                            
                            if now.time() >= shutdown_time:
                                logger.info("=" * 80)
                                logger.info(f"자동 종료 시간({shutdown_time_str})에 도달했습니다.")
                                logger.info("일일 작업 완료 - 프로그램을 정상 종료합니다.")
                                logger.info("=" * 80)
                                self.notifier.send_alert("✅ Hantubot 일일 작업 완료 - 정상 종료", level='info')
                                self._running = False
                                break
                            else:
                                logger.info(f"자동 종료 예정: {shutdown_time_str} ({shutdown_time_str} - 현재 {now.strftime('%H:%M')})")
                        except ValueError:
                            logger.error(f"AUTO_SHUTDOWN_TIME 형식 오류: {shutdown_time_str} (HH:MM 형식 사용)")
            
            # 장 외 시간이거나, 비거래일이거나, 장 마감 후 로직을 이미 실행한 경우
            logger.debug("장외 시간이거나 비거래일입니다. 장시간 대기 준비 중.")
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
