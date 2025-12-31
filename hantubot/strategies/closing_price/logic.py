from typing import Dict, Any, List, Tuple
import pandas as pd
from ta.trend import CCIIndicator, SMAIndicator
from .config import ClosingPriceConfig

class ClosingPriceLogic:
    """
    [ClosingPriceLogic v4] 2025년 유동성 기준 + 정교한 필터링(MA20, 캔들)
    
    1. 기본 필터 (Essential)
       - 가격: 2,000원 이상
       - 추세: 현재가 >= MA20
       - 캔들: 양봉, 윗꼬리 관리 (몸통보다 너무 길면 탈락)
       
    2. 스코어링 (총 100점)
       - A. 거래대금 (50점): 3,000억 이상 50점 ~ 1,000억 미만 0점
       - B. CCI 추세 (30점): 100~200 구간 최적
       - C. 등락률 (20점): 15~29% 구간 최적
       
    3. 선발 로직 (Plan B 포함)
       - [1군] 1,000억+ & 필터 통과
       - [2군] 300억+ & 필터 통과 (1군 없을 시)
    """
    
    def __init__(self, config: ClosingPriceConfig):
        self.config = config

    def _calculate_cci(self, df: pd.DataFrame, period: int = 14) -> float:
        """CCI 지표 계산"""
        try:
            if df is None or len(df) < period:
                return 0.0
            
            cci_indicator = CCIIndicator(
                high=df['stck_hgpr'], 
                low=df['stck_lwpr'], 
                close=df['stck_clpr'], 
                window=period
            )
            return cci_indicator.cci().iloc[-1]
        except Exception:
            return 0.0

    def _is_good_candle(self, open_p: float, high_p: float, low_p: float, close_p: float) -> Tuple[bool, str]:
        """
        좋은 양봉인지 판단
        1. 양봉 필수 (Close >= Open)
        2. 윗꼬리가 몸통의 2배를 넘지 않아야 함 (너무 긴 윗꼬리 제외)
        """
        if close_p < open_p:
            return False, "음봉"
            
        body = close_p - open_p
        upper_shadow = high_p - close_p
        
        # 몸통이 거의 없는 도지형 양봉은 윗꼬리 비율 계산 시 주의
        if body == 0:
            if upper_shadow > 0: # 윗꼬리만 있는 비석형 등
                return False, "도지/비석형"
            return True, "점상/보합" # 점상 등은 통과
            
        ratio = upper_shadow / body
        if ratio > 2.0:
            return False, f"윗꼬리과다({ratio:.1f}배)"
            
        return True, "적격캔들"

    def is_valid_candidate(self, df: pd.DataFrame, stock_info: Dict[str, Any] = None) -> Tuple[bool, str]:
        """
        기본 필터 검증 (가격, MA20, 캔들)
        """
        if df is None or len(df) < 20:
            return False, "데이터부족"
            
        try:
            today = df.iloc[-1]
            
            # 데이터 추출 (API 데이터 우선)
            if stock_info:
                current_price = float(stock_info.get('stck_prpr', today['stck_clpr']))
                open_price = float(stock_info.get('stck_oprc', today['stck_oprc']))
                high_price = float(stock_info.get('stck_hgpr', today['stck_hgpr']))
                low_price = float(stock_info.get('stck_lwpr', today['stck_lwpr']))
            else:
                current_price = float(today['stck_clpr'])
                open_price = float(today['stck_oprc'])
                high_price = float(today['stck_hgpr'])
                low_price = float(today['stck_lwpr'])

            # 1. 동전주 제외
            if current_price < 2000:
                return False, f"동전주({current_price}원)"

            # 2. MA20 추세 확인
            # 과거 데이터로 MA20 계산 (오늘 포함 20일)
            sma20 = df['stck_clpr'].rolling(window=20).mean().iloc[-1]
            if pd.isna(sma20):
                return False, "MA20계산불가"
            
            if current_price < sma20:
                return False, f"MA20이탈({current_price} < {sma20:.0f})"

            # 3. 캔들 분석
            is_good, reason = self._is_good_candle(open_price, high_price, low_price, current_price)
            if not is_good:
                return False, reason

            return True, "통과"

        except Exception as e:
            return False, f"에러:{str(e)}"

    def calculate_score(self, current_price: float, trading_value: float, change_rate: float, cci_val: float) -> Tuple[float, str]:
        """
        점수 계산 (100점 만점) - 2025년 기준
        Returns: (total_score, score_detail_str)
        """
        score_tv = 0
        score_cci = 0
        score_rate = 0
        
        # A. 거래대금 (50점)
        if trading_value >= 300_000_000_000: # 3000억 이상
            score_tv = 50
        elif trading_value >= 200_000_000_000: # 2000억 ~ 3000억
            score_tv = 40
        elif trading_value >= 150_000_000_000: # 1500억 ~ 2000억
            score_tv = 30
        elif trading_value >= 100_000_000_000: # 1000억 ~ 1500억
            score_tv = 20
        else:
            score_tv = 0 # 1000억 미만
            
        # B. CCI 추세 (30점)
        if 100 <= cci_val <= 200:
            score_cci = 30
        elif cci_val > 200:
            score_cci = 20
        elif 0 <= cci_val < 100:
            score_cci = 15
        else:
            score_cci = 0
            
        # C. 등락률 (20점)
        if 15 <= change_rate <= 29:
            score_rate = 20
        elif 5 <= change_rate < 15:
            score_rate = 15
        else:
            score_rate = 5
            
        total_score = score_tv + score_cci + score_rate
        detail = f"대금({score_tv})+CCI({score_cci})+등락({score_rate})"
        
        return total_score, detail

    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """필요한 보조지표 일괄 계산"""
        return {
            'cci': self._calculate_cci(df)
        }

    def filter_and_rank(self, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        후보군 필터링 및 랭킹 선정 (1군 -> 2군)
        Returns: (selected_top_3, selection_type)
        """
        # 이미 is_valid_candidate를 통과한 종목들만 candidates에 들어옴
        # 따라서 거래대금 기준만 적용하면 됨
        
        # [1군] 유목민 메이저: 거래대금 1,000억 이상
        group_1 = [c for c in candidates if c['trading_value'] >= 100_000_000_000]
        
        if group_1:
            group_1.sort(key=lambda x: x['score'], reverse=True)
            return group_1[:3], "1군(메이저)"
            
        # [2군] Plan B: 1군 없을 시, 거래대금 300억 이상
        group_2 = [c for c in candidates if c['trading_value'] >= 30_000_000_000]
        
        if group_2:
            group_2.sort(key=lambda x: x['score'], reverse=True)
            return group_2[:3], "2군(마이너)"
            
        return [], "없음"
