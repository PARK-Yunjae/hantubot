# hantubot_prod/hantubot/core/portfolio.py
from ..reporting.logger import get_logger
from typing import Dict, List, Optional

logger = get_logger(__name__)

class Portfolio:
    """
    계좌의 현금, 보유 종목(포지션), 미체결 주문 등 모든 자산 상태를
    관리하는 클래스. 시스템의 단일 진실 공급원(SSOT) 역할을 수행한다.
    """
    def __init__(self, initial_cash: float, initial_positions: Optional[List[Dict]] = None):
        self._cash = initial_cash
        # key: 종목코드, value: {'quantity': int, 'avg_price': float, 'strategy_id': str}
        self._positions: Dict[str, Dict] = {}
        # key: 주문 ID, value: {'symbol': str, 'side': str, ..., 'strategy_id': str}
        self._open_orders: Dict[str, Dict] = {}
        
        if initial_positions:
            self._load_initial_positions(initial_positions)
            
        logger.info(f"포트폴리오 초기화. 초기 현금: {initial_cash:,.0f} 원. 보유 포지션 수: {len(self._positions)}")

    def _load_initial_positions(self, positions_data: List[Dict]):
        """봇 시작 시 증권사로부터 받은 초기 포지션 정보를 로드합니다."""
        for pos in positions_data:
            symbol = pos.get('symbol')
            quantity = pos.get('quantity', 0)
            if symbol and quantity > 0:
                self._positions[symbol] = {
                    'quantity': quantity,
                    'avg_price': pos.get('avg_price', 0),
                    'strategy_id': 'loaded_on_startup' # 주인을 알 수 없는 포지션
                }
                logger.info(f"초기 포지션 로드: {pos.get('name')} ({symbol}) {quantity}주 @ {pos.get('avg_price', 0):,.0f}원")

    # --- Query Methods ---

    def get_cash(self) -> float:
        """현재 보유 현금을 반환합니다."""
        return self._cash

    def get_positions(self) -> Dict[str, Dict]:
        """보유 중인 모든 포지션을 반환합니다."""
        return self._positions.copy()

    def get_position(self, symbol: str) -> Optional[Dict]:
        """특정 종목의 포지션 정보를 반환합니다."""
        return self._positions.get(symbol)

    def get_positions_by_strategy(self, strategy_id: str) -> Dict[str, Dict]:
        """특정 전략(strategy_id)에 의해 관리되는 포지션만 필터링하여 반환합니다."""
        return {
            symbol: pos for symbol, pos in self._positions.items()
            if pos.get('strategy_id') == strategy_id
        }

    def get_position_quantity(self, symbol: str) -> int:
        """특정 종목의 보유 수량을 반환합니다."""
        position = self.get_position(symbol)
        return position['quantity'] if position else 0

    def has_position(self, symbol: str, quantity: int) -> bool:
        """특정 종목을 특정 수량만큼 보유하고 있는지 확인합니다."""
        return self.get_position_quantity(symbol) >= quantity

    def is_sufficient_cash(self, required_cash: float) -> bool:
        """주어진 금액만큼의 현금을 보유하고 있는지 확인합니다."""
        return self._cash >= required_cash

    # --- State Update Methods ---

    def update_on_new_order(self, order_details: dict):
        """
        새로운 주문이 발생했을 때 포트폴리오 상태를 업데이트합니다.
        (OrderManager로부터 strategy_id가 포함된 dict를 받음)
        """
        order_id = order_details['order_id']
        self._open_orders[order_id] = order_details
        logger.info(f"신규 주문 접수: {order_details}")

    def update_on_fill(self, fill_details: dict):
        """
        주문이 체결되었을 때 포트폴리오 상태를 업데이트합니다.
        부분 체결을 올바르게 처리합니다.
        :param fill_details: {'order_id': str, 'symbol': str, 'side': str, 'filled_quantity': int, 'fill_price': float, 'execution_id': str}
        """
        order_id = fill_details['order_id']
        
        # 미체결 주문 목록에서 해당 주문 정보 가져오기 (제거하지 않음)
        original_order = self._open_orders.get(order_id)
        if not original_order:
            logger.warning(f"체결된 주문(ID: {order_id})이 미체결 목록에 없습니다. 이미 처리되었거나 외부에서 발생한 주문일 수 있습니다.")
            return

        symbol = fill_details['symbol']
        side = fill_details['side']
        filled_quantity = int(fill_details['filled_quantity'])
        fill_price = float(fill_details['fill_price'])
        strategy_id = original_order.get('strategy_id', 'unknown')
        transaction_amount = filled_quantity * fill_price

        # --- 자산 상태 업데이트 (현금 및 포지션) ---
        if side == 'buy':
            self._cash -= transaction_amount
            
            existing_position = self.get_position(symbol)
            if existing_position:
                total_quantity = existing_position['quantity'] + filled_quantity
                total_value = (existing_position['quantity'] * existing_position['avg_price']) + transaction_amount
                new_avg_price = total_value / total_quantity
                self._positions[symbol]['quantity'] = total_quantity
                self._positions[symbol]['avg_price'] = new_avg_price
            else:
                self._positions[symbol] = {
                    'quantity': filled_quantity, 
                    'avg_price': fill_price,
                    'strategy_id': strategy_id
                }
            logger.info(f"매수 체결: {symbol} {filled_quantity}주 @ {fill_price:,.0f}원 (전략: {strategy_id}) | 잔여 현금: {self._cash:,.0f}원")

        elif side == 'sell':
            self._cash += transaction_amount

            existing_quantity = self.get_position_quantity(symbol)
            if existing_quantity >= filled_quantity:
                self._positions[symbol]['quantity'] -= filled_quantity
                if self._positions[symbol]['quantity'] == 0:
                    del self._positions[symbol]
            else:
                logger.error(f"매도 수량({filled_quantity})이 보유 수량({existing_quantity})을 초과합니다. ({symbol}) 포지션을 0으로 초기화합니다.")
                del self._positions[symbol]
            logger.info(f"매도 체결: {symbol} {filled_quantity}주 @ {fill_price:,.0f}원 (전략: {strategy_id}) | 잔여 현금: {self._cash:,.0f}원")
        
        # --- 미체결 주문 상태 업데이트 ---
        original_order['quantity'] -= filled_quantity
        if original_order['quantity'] <= 0:
            self._open_orders.pop(order_id)
            logger.info(f"주문 ID {order_id}가 완전히 체결되었습니다. 미체결 목록에서 제거합니다.")
        else:
            logger.info(f"주문 ID {order_id}가 부분 체결되었습니다. 남은 미체결 수량: {original_order['quantity']}")


    def update_on_cancel(self, order_id: str):
        """주문이 취소되었을 때 포트폴리오 상태를 업데이트합니다."""
        if order_id in self._open_orders:
            cancelled_order = self._open_orders.pop(order_id)
            logger.info(f"Order cancelled: {cancelled_order}")
        else:
            logger.warning(f"Attempted to cancel a non-existent or already filled order ID: {order_id}")

if __name__ == '__main__':
    # Test the Portfolio class
    portfolio = Portfolio(initial_cash=10_000_000)

    # 1. Buy Samsung Electronics
    buy_order_1 = {'order_id': 'samsung_buy_01', 'symbol': '005930', 'side': 'buy', 'quantity': 10, 'price': 75000, 'status': 'open'}
    portfolio.update_on_new_order(buy_order_1)
    
    # 2. Fill the order
    buy_fill_1 = {'order_id': 'samsung_buy_01', 'symbol': '005930', 'side': 'buy', 'filled_quantity': 10, 'fill_price': 74900}
    portfolio.update_on_fill(buy_fill_1)
    print(f"Positions after buy: {portfolio.get_positions()}")
    print(f"Cash after buy: {portfolio.get_cash():,.0f}")

    # 3. Buy SK Hynix
    buy_order_2 = {'order_id': 'hynix_buy_01', 'symbol': '000660', 'side': 'buy', 'quantity': 5, 'price': 130000, 'status': 'open'}
    portfolio.update_on_new_order(buy_order_2)
    buy_fill_2 = {'order_id': 'hynix_buy_01', 'symbol': '000660', 'side': 'buy', 'filled_quantity': 5, 'fill_price': 129500}
    portfolio.update_on_fill(buy_fill_2)
    print(f"Positions after 2nd buy: {portfolio.get_positions()}")
    print(f"Cash after 2nd buy: {portfolio.get_cash():,.0f}")

    # 4. Sell Samsung Electronics
    sell_order_1 = {'order_id': 'samsung_sell_01', 'symbol': '005930', 'side': 'sell', 'quantity': 5, 'price': 76000, 'status': 'open'}
    portfolio.update_on_new_order(sell_order_1)
    sell_fill_1 = {'order_id': 'samsung_sell_01', 'symbol': '005930', 'side': 'sell', 'filled_quantity': 5, 'fill_price': 76100}
    portfolio.update_on_fill(sell_fill_1)
    print(f"Positions after sell: {portfolio.get_positions()}")
    print(f"Cash after sell: {portfolio.get_cash():,.0f}")
