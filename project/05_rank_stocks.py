import pandas as pd
import numpy as np
import os
import time
from tqdm import tqdm
from ta.trend import CCIIndicator
from pykrx import stock
import warnings

# 경고 무시
warnings.filterwarnings("ignore")

# === ⚙️ 설정 ===
CANDIDATE_FILE = "data/news_candidates.csv"
PRICE_DIR = "data/adjusted"  # 수정주가 + 거래대금
RAW_DIR = "data/raw"         # 상장주식수 확인용
RESULT_FILE = "data/final_ranking_v6.csv"

# === 🏦 시장 지수 프리로딩 (최적화) ===
print("⏳ 시장 지수(코스닥) 데이터 프리로딩 중...")
try:
    # 2016년부터 현재까지 코스닥 지수 한 번에 로딩
    kosdaq_index = stock.get_index_ohlcv("20160101", time.strftime("%Y%m%d"), "2001")
    kosdaq_index['MA20'] = kosdaq_index['종가'].rolling(window=20).mean()
except Exception as e:
    print(f"⚠️ 시장 지수 로딩 실패: {e}")
    kosdaq_index = pd.DataFrame()

def get_market_trend_cached(target_date):
    """캐싱된 데이터에서 시장 추세 조회"""
    try:
        if kosdaq_index.empty: return 'bull' # 데이터 없으면 상승장 가정
        
        # target_date가 인덱스에 없으면 가장 가까운 과거 날짜 찾기
        if target_date not in kosdaq_index.index:
            try:
                dt = pd.to_datetime(target_date)
                # target_date 이전 데이터 중 가장 최근 것
                row = kosdaq_index.loc[:dt].iloc[-1]
            except:
                return 'bull'
        else:
            row = kosdaq_index.loc[target_date]
            
        if row['종가'] >= row['MA20']:
            return 'bull'
        else:
            return 'bear'
    except:
        return 'bull'

# === 🧠 Nomad Score V6 Logic ===
class ClosingPriceLogicV6:
    def _calculate_cci(self, df: pd.DataFrame, period: int = 14) -> float:
        try:
            if len(df) < period: return 0.0
            cci = CCIIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=period)
            return cci.cci().iloc[-1]
        except: return 0.0

    def calculate_score(self, df_hist, df_raw_info, target_date):
        """
        백테스팅용 점수 계산
        df_hist: 과거 차트 데이터 (Price, Volume)
        df_raw_info: 상장주식수 등 정보가 있는 Raw 데이터
        """
        score = 0
        details = []
        features = {}
        
        # 타겟 날짜 데이터 확인
        if target_date not in df_hist.index: return 0, "데이터없음", {}
        
        today = df_hist.loc[target_date]
        # 전일 데이터 (인덱스 위치 찾기)
        idx_loc = df_hist.index.get_loc(target_date)
        if idx_loc < 1: return 0, "과거데이터부족", {}
        prev = df_hist.iloc[idx_loc - 1]
        
        # 데이터 추출
        close = float(today['Close'])
        volume = float(today['Volume'])
        trading_value = float(today['TradingValue'])
        
        # 상장주식수 (Turnover 계산용)
        try:
            # Raw 데이터에서 해당 날짜의 상장주식수 찾기
            if target_date in df_raw_info.index:
                shares_out = float(df_raw_info.loc[target_date]['상장주식수'])
            else:
                shares_out = float(df_raw_info.iloc[-1]['상장주식수']) # 없으면 최신값
        except:
            shares_out = 0

        # === 1. Hard Filters (Gatekeeper) ===
        # 거래대금 1,000억 (Strict)
        if trading_value < 100_000_000_000:
            return 0, f"대금미달({int(trading_value/100000000)}억)", {}
            
        # 추세: 현재가 >= MA20
        ma20 = df_hist['Close'].rolling(20).mean().loc[target_date]
        if pd.isna(ma20) or close < ma20:
            return 0, "MA20이탈", {}

        # === 2. Nomad Score V3 ===
        
        # A. Supply & Liquidity (30pts)
        # 1. 외인 수급 (+15) -> 백테스팅에선 데이터 부재로 0점 처리 (보수적 접근)
        # details.append("외인(Unknown)")
        
        # 2. 회전율 > 10% (+15)
        if shares_out > 0:
            turnover = (volume / shares_out) * 100
            if turnover >= 10:
                score += 15
                details.append(f"회전율{turnover:.1f}%(+15)")
            features['turnover'] = turnover
        
        # B. Technical (30pts)
        # CCI(14)
        # 해당 날짜까지의 데이터로 계산해야 함 (Look-ahead bias 방지)
        # 속도를 위해 전체 계산 후 loc
        cci_series = CCIIndicator(high=df_hist['High'], low=df_hist['Low'], close=df_hist['Close'], window=14).cci()
        cci_val = cci_series.loc[target_date]
        features['cci'] = cci_val
        
        if 150 <= cci_val <= 180:
            score += 30
            details.append("CCI_Best(+30)")
        elif 100 <= cci_val < 150:
            score += 10
            details.append("CCI_Warm(+10)")
        elif cci_val > 200:
            score += 10
            details.append("CCI_Over(+10)")
            
        # Support (Low >= Prev Close) (+5)
        if today['Low'] >= prev['Close']:
            score += 5
            details.append("지지(+5)")
            
        # 정배열 (5 > 20 > 60) (+10)
        ma5 = df_hist['Close'].rolling(5).mean().loc[target_date]
        ma60 = df_hist['Close'].rolling(60).mean().loc[target_date]
        if ma5 > ma20 > ma60:
            score += 10
            details.append("정배열(+10)")
            
        # C. Market & Sector (20pts)
        # Market Index (+10)
        market_trend = get_market_trend_cached(target_date)
        if market_trend == 'bull':
            score += 10
            details.append("시장상승(+10)")
        
        # 주도 섹터 (+10) -> 개별 종목 분석에선 판단 불가, 0점 처리
        
        # D. Momentum (20pts)
        # 52주 신고가 근접 (+10)
        # 과거 250일
        past_year = df_hist.loc[:target_date].tail(250)
        high_52w = past_year['High'].max()
        if close >= high_52w * 0.95:
            score += 10
            details.append("신고가(+10)")
            
        # 종가 고가 마감 (+10)
        if close == today['High']:
            score += 10
            details.append("종가고가(+10)")

        return score, " / ".join(details), features

# === 🚀 메인 실행 ===
if not os.path.exists(CANDIDATE_FILE):
    print("❌ 후보 파일이 없습니다.")
    exit()

print("🚀 Nomad V6 (Whale Radar) 랭킹 산정 시작...")

candidates = pd.read_csv(CANDIDATE_FILE)
candidates['Date'] = pd.to_datetime(candidates['Date'])
logic = ClosingPriceLogicV6()
results = []

for idx, row in tqdm(candidates.iterrows(), total=len(candidates), desc="V6 분석 중"):
    code = f"{row['Code']:0>6}"
    str_date = row['Date'].strftime('%Y-%m-%d')
    
    # 1. Adjusted Data (Price, Volume, TV)
    adj_path = f"{PRICE_DIR}/{code}.csv"
    if not os.path.exists(adj_path): continue
    df_hist = pd.read_csv(adj_path, index_col=0, parse_dates=True)
    
    # 2. Raw Data (Shares Outstanding)
    raw_path = f"{RAW_DIR}/{code}.csv"
    if os.path.exists(raw_path):
        df_raw = pd.read_csv(raw_path, index_col=0, parse_dates=True)
    else:
        df_raw = pd.DataFrame()
        
    try:
        # 점수 계산
        score, reason, feats = logic.calculate_score(df_hist, df_raw, str_date)
        
        # 점수가 0이면 (Hard Filter 탈락) 스킵
        if score == 0: continue
        
        # 수익률 계산 (Next Day)
        idx_loc = df_hist.index.get_loc(str_date)
        if idx_loc + 1 < len(df_hist):
            next_day = df_hist.iloc[idx_loc + 1]
            buy_price = df_hist.iloc[idx_loc]['Close']
            
            gap_profit = (next_day['Open'] - buy_price) / buy_price * 100
            max_profit = (next_day['High'] - buy_price) / buy_price * 100
            end_profit = (next_day['Close'] - buy_price) / buy_price * 100
        else:
            gap_profit = max_profit = end_profit = 0.0

        # 등급 판정 (외인/섹터 점수 부재로 기준 하향 조정: 90->70, 80->60)
        # 원본 로직: S(90), A(80) / 백테스트 보정: S(70), A(60)
        grade = "B-Class"
        if score >= 70: grade = "S-Class (Whale)"
        elif score >= 60: grade = "A-Class"
        
        results.append({
            'Date': str_date,
            'Code': code,
            'Name': stock.get_market_ticker_name(code),
            'Grade': grade,
            'Score': score,
            'Details': reason,
            'TradingValue_Bn': round(df_hist.loc[str_date]['TradingValue'] / 100000000, 1),
            'CCI': round(feats.get('cci', 0), 1),
            'Turnover': round(feats.get('turnover', 0), 1),
            'Gap_Profit': round(gap_profit, 2),
            'Max_Profit': round(max_profit, 2),
            'End_Profit': round(end_profit, 2)
        })
        
    except Exception as e:
        # print(f"Error {code}: {e}")
        continue

# === 💾 결과 저장 ===
if results:
    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values(by=['Date', 'Score', 'Gap_Profit'], ascending=[True, False, False])
    
    df_result.to_csv(RESULT_FILE, index=False, encoding='utf-8-sig')
    print(f"\n🎉 V6 분석 완료! 총 {len(df_result)}개 종목 선정.")
    print(f"📄 결과 파일: {RESULT_FILE}")
    
    # 상위 5개 출력
    print("\n[🏆 V6 Whale Radar Top 5]")
    print(df_result[['Date', 'Name', 'Grade', 'Score', 'Gap_Profit']].head(10))
    
    # 평균 수익률 통계
    print("\n[📊 등급별 평균 갭 수익률]")
    print(df_result.groupby('Grade')['Gap_Profit'].mean())
else:
    print("❌ 조건에 맞는 종목이 하나도 없습니다.")