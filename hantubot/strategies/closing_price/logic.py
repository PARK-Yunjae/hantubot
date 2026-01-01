from typing import Dict, Any, List, Tuple
import pandas as pd
import time
from ta.trend import CCIIndicator
from pykrx import stock  # 시장 지수 조회용
from .config import ClosingPriceConfig

class ClosingPriceLogic:
    """
    [ClosingPriceLogic v5.2] 유목민 전략 최종 완성형
    (1,000억 클럽 + CCI + 시장지수 + 주도섹터 + 외국인수급)
    
    1. 기본 필터 (Essential)
       - 가격: 2,000원 이상
       - 추세: 현재가 >= MA20
       - 캔들: 양봉, 윗꼬리 관리 (몸통 대비 2배 이하)
       
    2. 입체적 스코어링 (기본 100점 + 알파)
       - 거래대금(Max 50): 3000억(50), 2000억(40), 1500억(30), 1000억(20)
       - CCI(Max 30): 100~200(30), 200↑(20), 0~100(15)
       - 등락률(Max 20): 15~29%(20), 5~15%(15), 그외(5)
       - [Bonus] 외국인 수급(+5), 주도 섹터(+5)
       - [Penalty] 하락장(-10)
       
    3. 선발 로직
       - 1군(메이저): 거래대금 1,000억 이상
       - 2군(Plan B): 거래대금 300억 이상
    """
    
    def __init__(self, config: ClosingPriceConfig):
        self.config = config

    def get_market_trend(self) -> str:
        """
        코스닥 시장 추세 판단 (pykrx 사용)
        Returns: 'bull' (20일선 위) or 'bear' (20일선 아래)
        """
        try:
            today = time.strftime("%Y%m%d")
            # 코스닥 지수 조회 (최근 30일)
            df_index = stock.get_index_ohlcv("20240101", today, "2001") # 2001: 코스닥
            if df_index is None or df_index.empty:
                return 'bull' # 데이터 없으면 기본 상승장 가정 (안전)
            
            # 최근 데이터 기준 MA20 계산
            df_index['MA20'] = df_index['종가'].rolling(window=20).mean()
            
            last_close = df_index['종가'].iloc[-1]
            last_ma20 = df_index['MA20'].iloc[-1]
            
            if pd.isna(last_ma20):
                return 'bull'
                
            if last_close < last_ma20:
                return 'bear' # 하락장
            
            return 'bull' # 상승장
            
        except Exception as e:
            # 에러 발생 시 봇이 멈추지 않도록 기본값 반환
            return 'bull'

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
        """좋은 양봉인지 판단"""
        if close_p < open_p:
            return False, "음봉"
        body = close_p - open_p
        upper_shadow = high_p - close_p
        
        if body == 0:
            if upper_shadow > 0: return False, "도지/비석형"
            return True, "점상/보합"
            
        ratio = upper_shadow / body
        if ratio > 2.0:
            return False, f"윗꼬리과다({ratio:.1f}배)"
        return True, "적격캔들"

    def is_valid_candidate(self, df: pd.DataFrame, stock_info: Dict[str, Any] = None) -> Tuple[bool, str]:
        """기본 필터 검증"""
        if df is None or len(df) < 20:
            return False, "데이터부족"
        try:
            today = df.iloc[-1]
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

            if current_price < 2000:
                return False, f"동전주({current_price}원)"

            sma20 = df['stck_clpr'].rolling(window=20).mean().iloc[-1]
            if pd.isna(sma20): return False, "MA20계산불가"
            if current_price < sma20:
                return False, f"MA20이탈({current_price} < {sma20:.0f})"

            is_good, reason = self._is_good_candle(open_price, high_price, low_price, current_price)
            if not is_good: return False, reason
            return True, "통과"
        except Exception as e:
            return False, f"에러:{str(e)}"

    def calculate_base_score(self, current_price: float, trading_value: float, change_rate: float, cci_val: float, market_trend: str, is_foreigner_buy: bool) -> Tuple[float, str]:
        """
        기본 점수 계산 (섹터 보너스 제외)
        """
        score_tv = 0
        score_cci = 0
        score_rate = 0
        score_extra = 0
        
        # A. 거래대금 (50점)
        if trading_value >= 300_000_000_000: score_tv = 50
        elif trading_value >= 200_000_000_000: score_tv = 40
        elif trading_value >= 150_000_000_000: score_tv = 30
        elif trading_value >= 100_000_000_000: score_tv = 20
        else: score_tv = 0
            
        # B. CCI 추세 (30점)
        if 100 <= cci_val <= 200: score_cci = 30
        elif cci_val > 200: score_cci = 20
        elif 0 <= cci_val < 100: score_cci = 15
        else: score_cci = 0
            
        # C. 등락률 (20점)
        if 15 <= change_rate <= 29: score_rate = 20
        elif 5 <= change_rate < 15: score_rate = 15
        else: score_rate = 5
        
        # D. 추가 보정 (시장 상황 & 외국인)
        details = []
        if market_trend == 'bear':
            score_extra -= 10
            details.append("하락장(-10)")
        
        if is_foreigner_buy:
            score_extra += 5
            details.append("외인수급(+5)")
            
        total_score = score_tv + score_cci + score_rate + score_extra
        
        # 상세 내역 문자열
        detail_str = f"대금({score_tv})+CCI({score_cci})+등락({score_rate})"
        if details:
            detail_str += "+" + "+".join(details)
        
        return total_score, detail_str

    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        return {'cci': self._calculate_cci(df)}

    def filter_and_rank(self, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        최종 랭킹 선정 (주도 섹터 보너스 적용 -> 1군/2군 선발)
        """
        # [Step 1] 주도 섹터 보너스 적용
        # 업종(Sector) 카운팅
        sector_counts = {}
        for c in candidates:
            sector = c.get('sector', 'Unknown')
            if sector and sector != 'Unknown':
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
        
        # 3개 이상 종목이 나온 업종은 '주도 섹터'로 인정
        leading_sectors = [sec for sec, count in sector_counts.items() if count >= 3]
        
        # 보너스 점수 부여
        for c in candidates:
            if c.get('sector') in leading_sectors:
                c['score'] += 5
                c['features']['score_detail'] += "+주도섹터(+5)"
        
        # [Step 2] 1군/2군 선발
        # 1군: 거래대금 1,000억 이상
        group_1 = [c for c in candidates if c['trading_value'] >= 100_000_000_000]
        if group_1:
            group_1.sort(key=lambda x: x['score'], reverse=True)
            return group_1[:3], "1군(메이저)"
            
        # 2군: 300억 이상 (Plan B)
        group_2 = [c for c in candidates if c['trading_value'] >= 30_000_000_000]
        if group_2:
            group_2.sort(key=lambda x: x['score'], reverse=True)
            return group_2[:3], "2군(마이너)"
            
        return [], "없음"
