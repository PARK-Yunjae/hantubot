# hantubot_prod/hantubot/strategies/base_strategy.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
import os
import json

from ..core.portfolio import Portfolio
from ..reporting.logger import get_logger
from ..execution.broker import Broker
from ..core.clock import MarketClock
from ..reporting.notifier import Notifier

logger = get_logger(__name__)

DYNAMIC_PARAMS_FILE = os.path.join("configs", "dynamic_params.json")

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
        self.dynamic_params: Dict[str, Any] = {} # 동적 파라미터 저장소
        
        self._load_dynamic_params() # 동적 파라미터 로드
        
        logger.info(f"Strategy '{self.name}' (ID: {self.strategy_id}) initialized with config: {self.config}, Dynamic: {self.dynamic_params}")

    def _load_dynamic_params(self):
        """
        configs/dynamic_params.json 파일에서 이 전략에 해당하는 동적 파라미터를 로드합니다.
        """
        if os.path.exists(DYNAMIC_PARAMS_FILE):
            try:
                with open(DYNAMIC_PARAMS_FILE, 'r', encoding='utf-8') as f:
                    all_dynamic_params = json.load(f)
                    self.dynamic_params = all_dynamic_params.get(self.strategy_id, {})
                    if self.dynamic_params:
                        logger.info(f"전략 '{self.name}' (ID: {self.strategy_id})에 동적 파라미터 로드: {self.dynamic_params}")
            except Exception as e:
                logger.error(f"전략 '{self.name}' 동적 파라미터 로드 중 오류 발생: {e}", exc_info=True)
        else:
            logger.debug(f"동적 파라미터 파일 {DYNAMIC_PARAMS_FILE}이(가) 존재하지 않습니다. 동적 파라미터를 로드하지 않습니다.")

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
