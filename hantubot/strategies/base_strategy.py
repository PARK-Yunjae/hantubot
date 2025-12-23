# hantubot_prod/hantubot/strategies/base_strategy.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from ..core.portfolio import Portfolio
from ..reporting.logger import get_logger
from ..execution.broker import Broker
from ..core.clock import MarketClock
from ..reporting.notifier import Notifier

logger = get_logger(__name__)

class BaseStrategy(ABC):
    """
    모든 자동매매 전략이 상속받아야 하는 추상 기본 클래스.
    모든 전략은 'generate_signal' 메서드를 구현해야 합니다.
    """
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker: Broker, clock: MarketClock, notifier: Notifier):
        self.strategy_id = strategy_id
        self.config = config
        self.broker = broker
        self.clock = clock
        self.notifier = notifier
        logger.info(f"Strategy '{self.name}' (ID: {self.strategy_id}) initialized with config: {self.config}")

    @property
    def name(self) -> str:
        """전략의 이름을 반환합니다."""
        return self.__class__.__name__

    @abstractmethod
    async def generate_signal(self, current_data: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        """
        주어진 시장 데이터와 현재 포트폴리오 상태를 기반으로
        매매 신호(signal) 목록을 생성하여 반환합니다.

        :param current_data: 현재 시장 데이터 (예: 종목별 현재가, 거래량 등)
                             format: {'symbol': {'price': float, 'volume': int, ...}, ...}
        :param portfolio: 현재 Portfolio 인스턴스 (잔고, 보유 종목 정보)
        :return: 매매 신호 목록. 각 신호는 OrderManager가 처리할 수 있는 dict 형태.
                 예: [{'strategy_id': self.strategy_id, 'symbol': '005930', 'side': 'buy', 'quantity': 10, 'price': 75000, 'order_type': 'limit'}]
        """
        pass

    def __str__(self):
        return f"{self.name}(ID: {self.strategy_id})"

    def __repr__(self):
        return self.__str__()
