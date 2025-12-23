# hantubot_prod/hantubot/execution/order_manager.py
import threading
from datetime import datetime, timedelta
from ..core.portfolio import Portfolio
from ..core.clock import MarketClock
from ..reporting.logger import get_logger, get_data_logger

logger = get_logger(__name__)
trades_logger = get_data_logger("trades")

class OrderManager:
    """
    모든 주문 요청을 중앙에서 처리하고 검증하는 클래스.
    SSOT(Single Source of Truth) 원칙을 강제한다.
    """
    def __init__(self, broker, portfolio: Portfolio, clock: MarketClock):
        self._broker = broker # The broker instance for placing actual orders
        self._portfolio = portfolio
        self._clock = clock
        self._locks: dict[str, threading.Lock] = {}  # 종목별 잠금을 위한 딕셔너리
        # 멱등성 키 저장소 (key: (strategy_id, symbol, side), value: (order_id, timestamp))
        self._idempotency_keys: dict[tuple, tuple] = {} 
        self._cooldown = timedelta(seconds=60) # 동일 신호 쿨다운

    def get_lock(self, symbol: str) -> threading.Lock:
        """종목 코드에 대한 Lock 객체를 가져오거나 생성"""
        if symbol not in self._locks:
            self._locks[symbol] = threading.Lock()
        return self._locks[symbol]

    def _is_duplicate_signal(self, strategy_id: str, symbol: str, side: str) -> bool:
        """짧은 시간 내 동일한 주문 신호가 있었는지 확인 (멱등성)"""
        key = (strategy_id, symbol, side)
        if key in self._idempotency_keys:
            last_order_id, timestamp = self._idempotency_keys[key]
            if datetime.now() - timestamp < self._cooldown:
                logger.warning(f"[OrderManager] Duplicate signal ignored by idempotency key {key}. Last order: {last_order_id}")
                return True
        return False

    def process_signal(self, signal: dict):
        """
        전략으로부터 받은 신호를 처리하여 주문 요청을 생성.
        :param signal: {'strategy_id': str, 'symbol': str, 'side': 'buy'|'sell', 'quantity': int, 'price': float, 'order_type': 'limit'|'market'}
        """
        symbol = signal['symbol']
        side = signal['side']
        quantity = signal['quantity']
        strategy_id = signal['strategy_id']
        price = signal.get('price', 0) # 시장가 주문의 경우 가격이 없을 수 있음
        
        # 1. 거래 시간 확인
        if not self._clock.is_market_open():
            logger.warning(f"[OrderManager] Signal for {symbol} received outside of market hours. Ignored.")
            return

        with self.get_lock(symbol):
            logger.info(f"[OrderManager] Processing signal with lock: {signal}")

            # 2. 멱등성 검사
            if self._is_duplicate_signal(strategy_id, symbol, side):
                return

            # 3. 포지션 및 잔고 검증
            if side == 'buy':
                required_cash = price * quantity
                if not self._portfolio.is_sufficient_cash(required_cash):
                    logger.error(f"[OrderManager] Insufficient cash for BUY {symbol}. Required: {required_cash:,.0f}, Available: {self._portfolio.get_cash():,.0f}")
                    return
            elif side == 'sell':
                if not self._portfolio.has_position(symbol, quantity):
                    logger.error(f"[OrderManager] Not enough position for SELL {symbol}. Required: {quantity}, Held: {self._portfolio.get_position_quantity(symbol)}")
                    return
            
            # 4. 브로커를 통해 주문 실행 요청
            try:
                order_result = self._broker.place_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    order_type=signal.get('order_type', 'limit')
                )
                
                if order_result and order_result.get('order_id'):
                    # 5. 성공 시 포트폴리오 상태 업데이트 및 멱등성 키 기록
                    # 주문 정보에 전략 ID를 추가하여 포트폴리오에 전달
                    order_to_log = {**order_result, 'strategy_id': strategy_id}
                    self._portfolio.update_on_new_order(order_to_log)
                    
                    self._idempotency_keys[(strategy_id, symbol, side)] = (order_result['order_id'], datetime.now())
                    logger.info(f"주문 접수 성공: {order_result}")
                    
                    # 6. 주문 데이터를 JSONL 파일에 로깅
                    trades_logger.info({'event_type': 'NEW_ORDER', **order_to_log})
                else:
                    logger.error(f"주문 접수 실패: {order_result}")

            except Exception as e:
                logger.critical(f"[OrderManager] Exception during order placement for {symbol}: {e}", exc_info=True)

    def handle_fill_update(self, fill_details: dict):
        """
        체결 정보를 받아 포트폴리오를 업데이트하고 데이터를 로깅합니다.
        이 메서드는 Broker로부터 체결 콜백을 받거나, 주기적으로 미체결 내역을 조회하여 호출됩니다.
        :param fill_details: {'order_id': str, 'symbol': str, 'side': str, 'filled_quantity': int, 'fill_price': float}
        """
        logger.info(f"Handling fill update: {fill_details}")
        
        # 1. 포트폴리오 상태 업데이트
        self._portfolio.update_on_fill(fill_details)
        
        # 2. 체결 데이터를 JSONL 파일에 로깅
        trades_logger.info({'event_type': 'FILL', **fill_details})

if __name__ == '__main__':
    # --- Mock Objects for Testing ---
    class MockBroker:
        def __init__(self):
            self.order_counter = 0

        def place_order(self, **kwargs):
            self.order_counter += 1
            order_id = f"mock_order_{self.order_counter}"
            logger.info(f"[MockBroker] Placing order: {kwargs}")
            return {
                'order_id': order_id,
                'status': 'open',
                'strategy_id': kwargs.get('strategy_id', 'test_strat'),
                **kwargs
            }

    # --- Test Setup ---
    config_path = "configs/config.yaml"
    mock_broker = MockBroker()
    portfolio = Portfolio(initial_cash=20_000_000)
    clock = MarketClock(config_path=config_path)

    def force_market_open():
        return True
    clock.is_market_open = force_market_open

    order_manager = OrderManager(broker=mock_broker, portfolio=portfolio, clock=clock)

    # --- Test Scenarios ---
    print("\n--- Scenario 1: Valid BUY signal ---")
    buy_signal_1 = {'strategy_id': 'test_strat', 'symbol': '005930', 'side': 'buy', 'quantity': 10, 'price': 75000, 'order_type': 'limit'}
    order_manager.process_signal(buy_signal_1)
    
    print("\n--- Scenario 2: Simulate a fill for the buy order ---")
    fill_details_1 = {'order_id': 'mock_order_1', 'symbol': '005930', 'side': 'buy', 'filled_quantity': 10, 'fill_price': 74900}
    order_manager.handle_fill_update(fill_details_1)
    print(f"Portfolio positions: {portfolio.get_positions()}")
    print(f"Portfolio cash: {portfolio.get_cash():,.0f}")

    print("\n--- Scenario 3: Valid SELL signal ---")
    sell_signal_1 = {'strategy_id': 'test_strat', 'symbol': '005930', 'side': 'sell', 'quantity': 5, 'price': 76000, 'order_type': 'limit'}
    order_manager.process_signal(sell_signal_1)
    
    print("\n--- Check logs/trades_YYYY-MM-DD.jsonl file for logged data ---")
