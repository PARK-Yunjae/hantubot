import yaml
from typing import Any, Dict, Optional, List

from ..reporting.logger import get_logger
from .kis.api import KisApi
from .kis.market_data import KisMarketData
from .kis.trading import KisTrading

logger = get_logger(__name__)

class Broker:
    """
    한국투자증권 OpenAPI 클라이언트 (국내주식)
    기존 Broker 클래스의 Facade 역할을 수행하며, 실제 로직은 
    kis.api, kis.market_data, kis.trading 모듈로 위임합니다.
    """

    def __init__(self, config: dict, is_mock: bool):
        # 1. API 통신 모듈 초기화
        self.api = KisApi(config, is_mock)
        
        # 2. 데이터 조회 모듈 초기화
        self.market_data = KisMarketData(self.api)
        
        # 3. 트레이딩 모듈 초기화
        self.trading = KisTrading(self.api, self.market_data, config)
        
        # 호환성을 위한 속성 노출
        self.ACCOUNT_NO = self.api.ACCOUNT_NO
        self.IS_MOCK = is_mock
        
        logger.info(f"Broker initialized for {'MOCK' if is_mock else 'LIVE'} trading. Account: {self.ACCOUNT_NO}")

    # --- Authentication (Delegated to KisApi) ---
    def _issue_new_token(self):
        self.api._issue_new_token()

    def _ensure_token(self):
        self.api._ensure_token()

    def _get_hashkey(self, data: Dict) -> str:
        return self.api.get_hashkey(data)

    @property
    def _access_token(self) -> str:
        return self.api.access_token

    def _request(self, *args, **kwargs) -> Dict:
        return self.api.request(*args, **kwargs)

    # --- Market Data (Delegated to KisMarketData) ---
    def get_current_price(self, symbol: str) -> float:
        return self.market_data.get_current_price(symbol)

    def get_volume_leaders(self, top_n: int = 100) -> list:
        return self.market_data.get_volume_leaders(top_n)

    def get_realtime_transaction_ranks(self, top_n: int = 30) -> list:
        """get_volume_leaders의 별칭"""
        return self.market_data.get_volume_leaders(top_n)

    def get_historical_daily_data(self, symbol: str, days: int = 60) -> list:
        return self.market_data.get_historical_daily_data(symbol, days)

    def get_intraday_minute_data(self, symbol: str) -> list:
        return self.market_data.get_intraday_minute_data(symbol)

    def _normalize_tick_price(self, price: int) -> int:
        return self.trading._normalize_tick_price(price)

    # --- Trading (Delegated to KisTrading) ---
    def _check_and_reset_daily_metrics(self):
        self.trading._check_and_reset_daily_metrics()

    def register_realized_pnl(self, pnl_krw: float):
        self.trading.register_realized_pnl(pnl_krw)

    def place_order(self, symbol: str, side: str, quantity: int, price: float, order_type: str) -> Optional[Dict]:
        return self.trading.place_order(symbol, side, quantity, price, order_type)

    def get_balance(self) -> Dict:
        return self.trading.get_balance()

    def get_concluded_orders(self) -> list:
        return self.trading.get_concluded_orders()

    def get_open_orders(self) -> list:
        return self.trading.get_open_orders()

    def cancel_order(self, order_id: str, quantity: int = 0, total: bool = True, order_type: str = None) -> bool:
        return self.trading.cancel_order(order_id, quantity, total)
