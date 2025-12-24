# hantubot_prod/hantubot/core/regime_manager.py
from typing import Dict, Any

from ..reporting.logger import get_logger

logger = get_logger(__name__)

class RegimeManager:
    """
    시장 레짐(상승, 하락, 횡보)을 결정하고 현재 상태를 관리합니다.
    """
    def __init__(self, config: Dict[str, Any], broker):
        self.config = config.get('regime_settings', {})
        self.broker = broker
        self.current_regime = "NEUTRAL"  # 기본값
        logger.info("RegimeManager 초기화 완료.")

    def determine_regime(self) -> str:
        """
        다양한 지표를 바탕으로 현재 시장 레짐을 결정합니다.
        
        초기 구현에서는 간단한 로직을 사용하며, 향후 확장될 수 있습니다.
        예: KOSPI/KOSDAQ 지수 등락률, 변동성 지수(VKOSPI) 등
        """
        # TODO: 향후 KOSPI, KOSDAQ 지수 API와 연동하여 동적으로 레짐 결정 로직 구현
        # 예시 로직:
        # try:
        #     kospi_change_pct = self.broker.get_index_change_pct("KOSPI")
        #     kosdaq_change_pct = self.broker.get_index_change_pct("KOSDAQ")
        #
        #     risk_on_threshold = self.config.get('risk_on_threshold', 0.7)
        #     risk_off_threshold = self.config.get('risk_off_threshold', -0.7)
        #
        #     if kospi_change_pct >= risk_on_threshold or kosdaq_change_pct >= risk_on_threshold:
        #         self.current_regime = "RISK_ON"
        #     elif kospi_change_pct <= risk_off_threshold or kosdaq_change_pct <= risk_off_threshold:
        #         self.current_regime = "RISK_OFF"
        #     else:
        #         self.current_regime = "NEUTRAL"
        # except Exception as e:
        #     logger.error(f"시장 레짐 결정 중 오류 발생: {e}. 기본값 'NEUTRAL' 사용.")
        #     self.current_regime = "NEUTRAL"
        
        # 현재는 고정된 값을 반환하도록 설정되어 있습니다.
        # 이 값을 'RISK_ON' 또는 'RISK_OFF'로 변경하여 테스트할 수 있습니다.
        determined_regime = "NEUTRAL" 
        if determined_regime != self.current_regime:
            self.current_regime = determined_regime
            logger.info(f"시장 레짐이 '{self.current_regime}'(으)로 변경되었습니다.")
            
        return self.current_regime

    def get_current_regime(self) -> str:
        """현재 결정된 레짐을 반환합니다."""
        return self.current_regime
