# hantubot_prod/hantubot/execution/order_manager.py
import threading
from datetime import datetime, timedelta
from ..core.portfolio import Portfolio
from ..core.clock import MarketClock
from ..core.regime_manager import RegimeManager # New import
from ..reporting.logger import get_logger, get_data_logger
from ..reporting import trade_logger # New import

logger = get_logger(__name__)
trades_logger = get_data_logger("trades")

class OrderManager:
    """
    모든 주문 요청을 중앙에서 처리하고 검증하는 클래스.
    SSOT(Single Source of Truth) 원칙을 강제한다.
    """
    def __init__(self, broker, portfolio: Portfolio, clock: MarketClock, regime_manager: RegimeManager, config: dict = None):
        self._broker = broker # The broker instance for placing actual orders
        self._portfolio = portfolio
        self._clock = clock
        self._regime_manager = regime_manager # New attribute
        self._config = config or {} # 전역 설정
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
        order_type = signal.get('order_type', 'limit')

        # [Order Cleanup] 매수 신호 시, 기존 미체결 주문 전량 취소 (설거지 로직)
        if side == 'buy':
            try:
                open_orders = self._broker.get_open_orders()
                if open_orders:
                    logger.info(f"[Order Cleanup] 매수 전 미체결 주문 {len(open_orders)}건 발견. 전량 취소를 진행합니다.")
                    for order in open_orders:
                        order_id = order.get('odno')
                        rem_qty = int(order.get('nccs_qty', 0))
                        if order_id and rem_qty > 0:
                            self._broker.cancel_order(order_id, rem_qty, True, "00")
                            logger.info(f"[Order Cleanup] 미체결 주문 취소 완료: {order_id} ({rem_qty}주)")
            except Exception as e:
                logger.error(f"[Order Cleanup] 미체결 주문 취소 중 오류 발생: {e}")

        # --- [최종 방어] 신호 유효성 검증 ---
        symbol = str(symbol).strip()

        # 1) 종목코드 6자리 강제 (ex: 5930 -> "005930")
        if symbol.isdigit() and len(symbol) < 6:
            symbol = symbol.zfill(6)
        signal['symbol'] = symbol # 업데이트된 심볼을 signal 딕셔너리에 다시 반영

        # 2) 수량 검증
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            logger.error(f"[OrderManager] Invalid quantity type: {quantity} ({type(quantity)}) for signal: {signal}")
            return

        if quantity <= 0:
            logger.warning(f"[OrderManager] quantity<=0 ignored. symbol={symbol}, qty={quantity}, signal={signal}")
            return
        signal['quantity'] = quantity


        # 3) 주문 타입 검증
        order_type = str(order_type).lower().strip()
        if order_type not in ("market", "limit"):
            logger.warning(f"[OrderManager] Unknown order_type='{order_type}'. Forcing 'market'.")
            order_type = "market"
        signal['order_type'] = order_type

        # [전수조사 수정] 가격이 0이거나 그 이하일 경우, 주문 유형을 '시장가'로 강제합니다.
        if price <= 0:
            order_type = 'market'
        
        # 1. 거래 시간 확인
        if not self._clock.is_market_open():
            logger.warning(f"[OrderManager] Signal for {symbol} received outside of market hours. Ignored.")
            return

        with self.get_lock(symbol):
            logger.info(f"[OrderManager] Processing signal with lock: {signal}")

            # 2. 멱등성 검사
            if self._is_duplicate_signal(strategy_id, symbol, side):
                return

            # 3. 정책 검증 (Position Priority)
            if side == 'buy':
                policy = self._config.get('policy', {})
                priority = policy.get('position_priority', 'closing_over_intraday')
                now = datetime.now()
                
                # closing_over_intraday: 14:50 이후 intraday 신규 진입 금지
                # closing_price 전략은 허용
                if priority == 'closing_over_intraday':
                    if now.hour >= 14 and now.minute >= 50:
                        if 'closing_price' not in strategy_id:
                            logger.warning(f"[OrderManager] 14:50 이후 Intraday 진입 금지 ({strategy_id}). 종가전략 우선 정책.")
                            return

            # 4. 포지션 및 잔고 검증
            if side == 'buy':
                # [전수조사 수정] 중앙에서 "1종목 보유" 규칙 강제 적용
                if self._portfolio.get_positions():
                    logger.warning(f"[OrderManager] BUY signal for {symbol} ignored. A position is already held, adhering to one-stock-at-a-time rule.")
                    return

                # 시장가 주문일 경우 현재가를 조회하여 주문 금액 계산
                effective_price = price

                if order_type == 'market':
                    current_price = self._broker.get_current_price(symbol)
                    if current_price == 0:
                        logger.error(f"[OrderManager] Failed to fetch current price for market BUY on {symbol}. Order rejected.")
                        return
                    # 슬리피지를 고려하여 5%의 버퍼를 추가
                    effective_price = current_price * 1.05
                    logger.info(f"[OrderManager] Market BUY for {symbol}: using estimated price {effective_price:,.0f} (current: {current_price:,.0f} + 5% buffer) for cash check.")

                required_cash = effective_price * quantity
                if not self._portfolio.is_sufficient_cash(required_cash):
                    logger.error(f"[OrderManager] Insufficient cash for BUY {symbol}. Required: {required_cash:,.0f}, Available: {self._portfolio.get_cash():,.0f}")
                    return
            elif side == 'sell':
                if not self._portfolio.has_position(symbol, quantity):
                    logger.error(f"[OrderManager] Not enough position for SELL {symbol}. Required: {quantity}, Held: {self._portfolio.get_position_quantity(symbol)}")
                    return
            
            # 4. 브로커를 통해 주문 실행 요청 (매도는 3회 재시도)
            max_retries = 3 if side == 'sell' else 1
            order_result = None
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.warning(f"[OrderManager] 매도 주문 재시도 {attempt+1}/{max_retries}: {symbol}")
                        import time
                        time.sleep(0.5)  # 0.5초 대기 후 재시도
                    
                    order_result = self._broker.place_order(
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=price,
                        order_type=order_type
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
                        break  # 성공하면 루프 탈출
                    else:
                        logger.error(f"주문 접수 실패 (시도 {attempt+1}/{max_retries}): {order_result}")
                        if attempt == max_retries - 1:
                            # 최종 실패 시 긴급 알림 (매도만)
                            if side == 'sell':
                                from ..reporting.notifier import Notifier
                                notifier = Notifier()
                                notifier.send_alert(
                                    f"🚨 긴급: {symbol} 매도 주문 {max_retries}회 실패!",
                                    embed={
                                        "title": "매도 주문 최종 실패",
                                        "description": f"종목: {symbol}\n수량: {quantity}주\n시도: {max_retries}회",
                                        "color": 15158332,  # 빨간색
                                        "fields": [
                                            {"name": "전략", "value": strategy_id, "inline": True},
                                            {"name": "주문 타입", "value": order_type, "inline": True}
                                        ]
                                    },
                                    level='critical'
                                )

                except Exception as e:
                    logger.critical(f"[OrderManager] Exception during order placement for {symbol} (시도 {attempt+1}/{max_retries}): {e}", exc_info=True)
                    if attempt == max_retries - 1:
                        # 최종 실패 시 긴급 알림 (매도만)
                        if side == 'sell':
                            from ..reporting.notifier import Notifier
                            notifier = Notifier()
                            notifier.send_alert(
                                f"🚨 긴급: {symbol} 매도 주문 예외 발생!",
                                embed={
                                    "title": "매도 주문 예외",
                                    "description": f"종목: {symbol}\n오류: {str(e)}",
                                    "color": 15158332
                                },
                                level='critical'
                            )

    def handle_fill_update(self, fill_details: dict):
        """
        체결 정보를 받아 포트폴리오를 업데이트하고 데이터를 로깅합니다.
        이 메서드는 Broker로부터 체결 콜백을 받거나, 주기적으로 미체결 내역을 조회하여 호출됩니다.
        :param fill_details: {'order_id': str, 'symbol': str, 'side': str, 'filled_quantity': int, 'fill_price': float}
        """
        logger.info(f"Handling fill update: {fill_details}")

        # 1. 체결 정보에서 변수 추출
        order_id = fill_details.get('order_id')
        symbol = fill_details.get('symbol')
        side = fill_details.get('side')
        filled_quantity = fill_details.get('filled_quantity', 0)
        fill_price = fill_details.get('fill_price', 0.0)

        # 2. 포트폴리오 업데이트 전, PnL 계산 및 로깅에 필요한 정보 조회
        original_order = self._portfolio._open_orders.get(order_id, {})
        strategy_id = original_order.get('strategy_id', 'unknown')
        current_regime = self._regime_manager.get_current_regime()
        pnl_pct = None
        pnl_krw = None
        
        if side == 'sell':
            position_before_sale = self._portfolio.get_position(symbol)
            if position_before_sale and position_before_sale.get('avg_price', 0) > 0:
                avg_price = position_before_sale['avg_price']
                pnl_pct = ((fill_price / avg_price) - 1) * 100
                pnl_krw = (fill_price - avg_price) * filled_quantity
                
                # 실현 손익을 Broker에 등록 (일일 손실 한도 검사용)
                self._broker.register_realized_pnl(pnl_krw)
                logger.info(f"실현 손익 기록: {symbol}, PnL: {pnl_krw:,.0f}원 ({pnl_pct:.2f}%)")

        # 3. 포트폴리오 상태 업데이트 (가장 먼저 처리)
        self._portfolio.update_on_fill(fill_details)
        
        # 4. 체결 데이터를 JSONL 파일에 로깅
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "FILL",
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": filled_quantity,
            "price": fill_price,
            "strategy_id": strategy_id,
            "market_regime": current_regime,
            "pnl_pct": pnl_pct,
            "pnl_krw": pnl_krw, # PnL 원화 값 추가
        }
        trade_logger.log_trade_record(trade_record)

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
        
        def get_current_price(self, symbol):
            """Mock 현재가 조회"""
            return 75000
        
        def register_realized_pnl(self, pnl_krw):
            """Mock PnL 등록"""
            logger.info(f"[MockBroker] Registering realized PnL: {pnl_krw:,.0f}원")

    # --- Test Setup ---
    config_path = "configs/config.yaml"
    mock_broker = MockBroker()
    portfolio = Portfolio(initial_cash=20_000_000)
    clock = MarketClock(config_path=config_path)
    regime_manager = RegimeManager()  # 추가

    def force_market_open():
        return True
    clock.is_market_open = force_market_open

    order_manager = OrderManager(
        broker=mock_broker, 
        portfolio=portfolio, 
        clock=clock,
        regime_manager=regime_manager  # 추가
    )

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
