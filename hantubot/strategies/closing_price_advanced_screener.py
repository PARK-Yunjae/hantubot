# hantubot_prod/hantubot/strategies/closing_price_advanced_screener.py
"""
[DEPRECATED] 종가매매 고급 스크리너 전략 v3
이 모듈은 리팩토링된 hantubot.strategies.closing_price 패키지로 대체되었습니다.
하위 호환성을 위해 래퍼 클래스를 제공합니다.
"""
import warnings
from .closing_price import ClosingPriceStrategy as NewClosingPriceStrategy

class ClosingPriceAdvancedScreener(NewClosingPriceStrategy):
    """
    [Deprecated] 고급 종가매매 스크리너 전략.
    새로운 구조인 hantubot.strategies.closing_price.ClosingPriceStrategy를 상속받아 호환성을 유지합니다.
    """
    
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "ClosingPriceAdvancedScreener 모듈은 deprecated 되었습니다. "
            "hantubot.strategies.closing_price 패키지를 사용하세요.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)
