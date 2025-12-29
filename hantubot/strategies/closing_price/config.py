from dataclasses import dataclass
from typing import Dict, Any
import datetime as dt

@dataclass
class ClosingPriceConfig:
    """종가매매 전략 설정"""
    
    # 시간 설정 (기본값 고정, 필요시 변경 가능하도록)
    webhook_time: dt.time = dt.time(15, 3)
    buy_start_time: dt.time = dt.time(15, 15)
    buy_end_time: dt.time = dt.time(15, 19)

    # 지표 설정
    cci_period: int = 14
    sma_period: int = 20
    adx_period: int = 14
    volume_sma_period: int = 20

    # 스크리닝 설정
    cci_target: int = 180
    cci_tolerance: int = 50
    adx_min_threshold: int = 18
    top_n_volume: int = 30
    top_n_screen: int = 3

    # 매매 설정
    auto_buy_enabled: bool = True
    buy_quantity: int = 1
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'ClosingPriceConfig':
        """딕셔너리 설정에서 인스턴스 생성"""
        # dt.time 객체는 yaml 설정에서 직접 오지 않을 수 있으므로, 
        # 문자열로 받아서 파싱하는 로직이 필요할 수 있으나, 
        # 현재는 코드 내 기본값을 주로 사용하고 오버라이드만 처리.
        
        instance = cls(
            cci_period=config.get('cci_period', 14),
            sma_period=config.get('sma_period', 20),
            adx_period=config.get('adx_period', 14),
            volume_sma_period=config.get('volume_sma_period', 20),
            cci_target=config.get('cci_target', 180),
            cci_tolerance=config.get('cci_tolerance', 50),
            adx_min_threshold=config.get('adx_min_threshold', 18),
            top_n_volume=config.get('top_n_volume', 30),
            top_n_screen=config.get('top_n_screen', 3),
            auto_buy_enabled=config.get('auto_buy_enabled', True),
            buy_quantity=config.get('buy_quantity', 1)
        )
        return instance
