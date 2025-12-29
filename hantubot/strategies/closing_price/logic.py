from typing import Dict, Any, Tuple
import pandas as pd
from ta.trend import cci, sma_indicator, ADXIndicator
from .config import ClosingPriceConfig

class ClosingPriceLogic:
    """종가매매 전략의 핵심 계산 로직"""
    
    def __init__(self, config: ClosingPriceConfig):
        self.config = config

    def calculate_candle_score(self, df: pd.DataFrame) -> Tuple[float, bool, str]:
        """
        캔들 패턴 점수 계산
        Returns: (score, is_bullish, details_str)
        """
        if len(df) < 2:
            return 0, False, "데이터부족"
        
        try:
            today_open = float(df['stck_oprc'].iloc[-1]) if 'stck_oprc' in df.columns and len(df) >= 1 else float(df['stck_clpr'].iloc[-2]) if len(df) >= 2 else 0
            today_close = float(df['stck_clpr'].iloc[-1])
            today_high = float(df['stck_hgpr'].iloc[-1])
            today_low = float(df['stck_lwpr'].iloc[-1])
        except (IndexError, ValueError) as e:
            return 0, False, f"데이터오류:{e}"
        
        # 1. 양봉 여부
        is_bullish = today_close > today_open
        if not is_bullish:
            return 0, False, "음봉"
        
        # 2. 캔들 범위
        candle_range = today_high - today_low
        if candle_range == 0:
            return 0, False, "범위없음"
        
        body_size = today_close - today_open
        upper_shadow = today_high - today_close
        
        # 3. 윗꼬리 비율 (낮을수록 좋음)
        upper_shadow_ratio = upper_shadow / candle_range
        score_upper_shadow = max(0, 100 - (upper_shadow_ratio * 200))
        
        # 4. 몸통 비율 (클수록 좋음)
        body_ratio = body_size / candle_range
        score_body = min(100, body_ratio * 150)
        
        # 5. 고가-종가 근접도
        high_close_gap = (today_high - today_close) / today_close * 100
        score_high_close = max(0, 100 - (high_close_gap * 50))
        
        # 종합 점수
        total_score = (score_upper_shadow * 0.4) + (score_body * 0.3) + (score_high_close * 0.3)
        details = f"윗꼬리:{upper_shadow_ratio*100:.1f}%|몸통:{body_ratio*100:.1f}%|고종갭:{high_close_gap:.2f}%"
        
        return total_score, True, details

    def get_buffer_ratio(self, consecutive_wins: int, stock_data: Dict[str, Any] = None) -> float:
        """연속 승리 횟수 + 거래대금에 따른 버퍼 비율 결정"""
        # 기본 버퍼 (연속 승리 기반)
        if consecutive_wins >= 5:
            base_buffer = 0.93  # 7% 버퍼
        elif consecutive_wins >= 3:
            base_buffer = 0.92  # 8% 버퍼
        elif consecutive_wins >= 2:
            base_buffer = 0.91  # 9% 버퍼
        else:
            base_buffer = 0.90  # 10% 버퍼
        
        # 거래대금 기반 추가 조정
        if stock_data:
            try:
                trading_value_str = stock_data.get('data_rank', '0')
                trading_value = float(trading_value_str) if trading_value_str else 0
                
                if trading_value >= 100_000_000_000:
                    base_buffer = min(0.95, base_buffer + 0.02)
                elif trading_value >= 10_000_000_000:
                    base_buffer = min(0.94, base_buffer + 0.01)
            except (ValueError, TypeError):
                pass
        
        return base_buffer

    def calculate_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """지표 계산"""
        result = {}
        
        try:
            # 1. Price & SMA
            current_price = df['stck_clpr'].iloc[-1]
            sma20 = sma_indicator(df['stck_clpr'], window=self.config.sma_period).iloc[-1]
            
            # 2. CCI
            try:
                current_cci = cci(df['stck_hgpr'], df['stck_lwpr'], df['stck_clpr'], window=self.config.cci_period).iloc[-1]
                if pd.isna(current_cci):
                    current_cci = 0
            except:
                current_cci = 0
                
            # 3. ADX
            try:
                adx_indicator = ADXIndicator(df['stck_hgpr'], df['stck_lwpr'], df['stck_clpr'], window=self.config.adx_period)
                current_adx = adx_indicator.adx().iloc[-1]
                if pd.isna(current_adx):
                    current_adx = 0
            except:
                current_adx = 0
                
            # 4. Volume SMA
            vol_sma = sma_indicator(df['acml_vol'], window=self.config.volume_sma_period).iloc[-1]
            last_volume = df['acml_vol'].iloc[-1]
            
            result = {
                'price': current_price,
                'sma20': sma20,
                'cci': current_cci,
                'adx': current_adx,
                'volume': last_volume,
                'vol_sma': vol_sma
            }
        except Exception as e:
            result['error'] = str(e)
            
        return result

    def calculate_total_score(self, indicators: Dict[str, Any], candle_score: float, is_bullish: bool) -> Tuple[float, str]:
        """종합 점수 계산"""
        current_cci = indicators.get('cci', 0)
        current_adx = indicators.get('adx', 0)
        current_price = indicators.get('price', 0)
        sma20 = indicators.get('sma20', 0)
        last_volume = indicators.get('volume', 0)
        vol_sma = indicators.get('vol_sma', 0)
        
        # CCI 점수 (25%)
        score_cci = max(0, 100 - abs(current_cci - self.config.cci_target) * 1.5)
        
        # 거래량 점수 (25%)
        if pd.isna(vol_sma) or vol_sma == 0:
            score_volume = 50
        else:
            score_volume = min(100, (last_volume / vol_sma) * 50)
            
        # ADX 점수 (15%)
        score_adx = min(100, current_adx * 2.5)
        
        # 캔들 점수 조정
        final_candle_score = candle_score if is_bullish else 0
        candle_details = "음봉(감점)" if not is_bullish else ""
        
        # 이평선 점수 (10%)
        if pd.isna(sma20) or sma20 == 0:
            score_sma = 50
        else:
            gap_from_sma = ((current_price - sma20) / sma20) * 100
            if current_price > sma20:
                score_sma = min(100, 50 + gap_from_sma * 5)
            else:
                score_sma = max(0, 50 + gap_from_sma * 5)

        total_score = (
            (score_cci * 0.25) + 
            (score_volume * 0.25) + 
            (score_adx * 0.15) + 
            (final_candle_score * 0.25) + 
            (score_sma * 0.10)
        )
        
        if is_bullish:
            total_score += 10
            
        score_detail = f"CCI:{round(score_cci)}|거래량:{round(score_volume)}|ADX:{round(score_adx)}|캔들:{round(final_candle_score)}|이평:{round(score_sma)}"
        
        return total_score, score_detail
