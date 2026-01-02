from typing import Dict, Any, List, Tuple
import pandas as pd
import time
from ta.trend import CCIIndicator
from pykrx import stock  # 시장 지수 조회용
from .config import ClosingPriceConfig

class ClosingPriceLogic:
    """
    [ClosingPriceLogic v6] Nomad Score V3 (Whale Radar)
    (1,000억 클럽 + Nomad Score V3)
    
    1. Hard Filters (Gatekeeper)
       - 거래대금: 1,000억 원 이상 (필수)
       - 추세: 현재가 >= MA20
       - 관리종목/정지 등 제외
       
    2. Nomad Score V3 (Total 100 Points)
       A. Supply & Liquidity (30pts)
          - 외인/프로그램 수급 (+15)
          - 회전율 > 10% (+15)
       B. Technical (30pts)
          - CCI(14) (+10~30)
          - 지지(Low >= Prev Close) (+5)
          - 정배열 (+10)
       C. Market & Sector (20pts)
          - 코스닥 지수 > 20MA (+10)
          - 주도 섹터 (+10)
       D. Momentum (20pts)
          - 52주 신고가 근접 (+10)
          - 종가 고가 마감 (+10)
       
    3. Final Classification
       - S-Class (>= 90)
       - A-Class (>= 80)
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
            # 코스닥 지수 조회 (최근 60일)
            df_index = stock.get_index_ohlcv("20240101", today, "2001") # 2001: 코스닥
            if df_index is None or df_index.empty:
                return 'bull'
            
            # 최근 데이터 기준 MA20 계산
            df_index['MA20'] = df_index['종가'].rolling(window=20).mean()
            
            last_close = df_index['종가'].iloc[-1]
            last_ma20 = df_index['MA20'].iloc[-1]
            
            if pd.isna(last_ma20):
                return 'bull'
                
            if last_close >= last_ma20:
                return 'bull' # 상승장
            
            return 'bear' # 하락장
            
        except Exception as e:
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

    def is_valid_candidate(self, df: pd.DataFrame, stock_info: Dict[str, Any] = None) -> Tuple[bool, str]:
        """Hard Filters 검증"""
        if df is None or len(df) < 20:
            return False, "데이터부족"
        try:
            today = df.iloc[-1]
            if stock_info:
                current_price = float(stock_info.get('stck_prpr', today['stck_clpr']))
                trading_value = float(stock_info.get('acml_tr_pbmn', today['acml_vol'] * current_price))
            else:
                current_price = float(today['stck_clpr'])
                trading_value = float(today['acml_vol']) * current_price # 근사치

            # 1. 거래대금 1,000억 이상 (Strict)
            if trading_value < 100_000_000_000:
                return False, f"대금미달({trading_value/100000000:.0f}억)"

            # 2. 추세: Price >= 20MA
            sma20 = df['stck_clpr'].rolling(window=20).mean().iloc[-1]
            if pd.isna(sma20): return False, "MA20계산불가"
            if current_price < sma20:
                return False, f"MA20이탈"

            # 3. 관리종목 등 필터 (stock_info에 status code가 있다면)
            # KIS API 'iscd_stat_cls_code' 사용 가정
            if stock_info and 'iscd_stat_cls_code' in stock_info:
                code = stock_info['iscd_stat_cls_code']
                if code in ['51', '52', '53', '54', '58', '59']:
                    return False, f"관리/위험({code})"

            return True, "통과"
        except Exception as e:
            return False, f"에러:{str(e)}"

    def calculate_nomad_score_v3(self, df: pd.DataFrame, stock_info: Dict[str, Any], market_trend: str) -> Tuple[float, str, Dict[str, Any]]:
        """Nomad Score V3 계산"""
        score = 0
        details = []
        features = {}
        
        try:
            today_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]
            
            current_price = float(stock_info.get('stck_prpr', today_candle['stck_clpr']))
            volume = float(stock_info.get('acml_vol', today_candle['acml_vol']))
            
            # === A. Supply & Liquidity (Max 30pts) ===
            
            # 1. Foreigner Net Buy (+15)
            # stock_info needs 'frgn_ntby_qty' or similar
            # If not present, try to use df if available (unlikely for intraday)
            frgn_buy = float(stock_info.get('frgn_ntby_qty', 0))
            if frgn_buy > 0:
                score += 15
                details.append("외인수급(+15)")
                
            # 2. Turnover Ratio (+15)
            # Need Shares Outstanding. Try fetching via pykrx if not provided.
            shares = float(stock_info.get('lstn_stcn', 0))
            if shares == 0:
                # Fallback: pykrx (This might be slow if called frequently, check performance)
                # For safety, skip or assume 0 if cannot fetch.
                pass
            
            if shares > 0 and (volume / shares) > 0.10:
                score += 15
                details.append("회전율10%↑(+15)")
            
            # === B. Technical & Pattern (Max 30pts) ===
            
            # CCI(14)
            cci_val = self._calculate_cci(df)
            features['cci'] = cci_val
            
            if 150 <= cci_val <= 180:
                score += 30
                details.append("CCI_Best(+30)")
            elif 100 <= cci_val < 150:
                score += 10
                details.append("CCI_Warming(+10)")
            elif cci_val > 200:
                score += 10
                details.append("CCI_Over(+10)")

            # Support (Low >= Prev Close) (+5)
            prev_close = float(prev_candle['stck_clpr'])
            low_price = float(today_candle['stck_lwpr'])
            
            if low_price >= prev_close:
                score += 5
                details.append("지지(+5)")
                
            # MA Arrangement (5 > 20 > 60) (+10)
            ma5 = df['stck_clpr'].rolling(5).mean().iloc[-1]
            ma20 = df['stck_clpr'].rolling(20).mean().iloc[-1]
            ma60 = df['stck_clpr'].rolling(60).mean().iloc[-1]
            
            if ma5 > ma20 > ma60:
                score += 10
                details.append("정배열(+10)")
            elif ma5 < ma20 < ma60:
                score -= 5
                details.append("역배열(-5)")
                
            # === C. Market & Sector (Max 20pts) ===
            
            # Market Index (Kosdaq) (+10)
            if market_trend == 'bull':
                score += 10
                details.append("시장상승(+10)")
            
            # Sector Leader (+10) - Handled in filter_and_rank or if passed in stock_info
            # logic.py cannot easily check other stocks here.
            # We will handle this in filter_and_rank by adding bonus points.
            
            # === D. Momentum (Max 20pts) ===
            
            # 52-Week High (+10)
            hist_1y = df.tail(250)
            high_52w = hist_1y['stck_hgpr'].max()
            
            if current_price >= high_52w * 0.95:
                score += 10
                details.append("신고가근접(+10)")
                
            # Strong Close (+10)
            high_price = float(today_candle['stck_hgpr'])
            if current_price == high_price:
                score += 10
                details.append("종가고가(+10)")

            detail_str = " + ".join(details)
            return score, detail_str, features
            
        except Exception as e:
            return 0, f"Error: {e}", {}

    def get_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        return {'cci': self._calculate_cci(df)}

    def filter_and_rank(self, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        최종 랭킹 및 섹터 보너스 적용
        """
        # [Step 1] 주도 섹터 보너스 적용 (Check if 2+ stocks in same industry have >10% rise)
        # candidates must have 'sector' and 'change_rate'
        
        sector_risers = {} # Sector -> Count of >10% risers
        for c in candidates:
            sector = c.get('sector', 'Unknown')
            change_rate = c.get('features', {}).get('change_rate', 0)
            
            if sector != 'Unknown' and change_rate >= 10.0:
                sector_risers[sector] = sector_risers.get(sector, 0) + 1
                
        # Apply Bonus
        for c in candidates:
            sector = c.get('sector', 'Unknown')
            if sector != 'Unknown' and sector_risers.get(sector, 0) >= 2:
                c['score'] += 10
                if c.get('reason'):
                    c['reason'] += " + 주도섹터(+10)"
                else:
                    c['reason'] = "주도섹터(+10)"
        
        # [Step 2] 등급 분류
        final_list = []
        for c in candidates:
            score = c.get('score', 0)
            
            if score >= 90:
                c['grade'] = "S-Class"
                final_list.append(c)
            elif score >= 80:
                c['grade'] = "A-Class"
                final_list.append(c)
            # < 80 Discard
        
        final_list.sort(key=lambda x: x['score'], reverse=True)
        
        # Return Top 3
        if final_list:
            return final_list[:3], "Nomad V3"
            
        return [], "없음"
