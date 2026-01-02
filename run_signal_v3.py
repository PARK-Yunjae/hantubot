import os
import sys
import time
import datetime
import pytz
import pandas as pd
import requests
from pykrx import stock

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hantubot.execution.kis.api import KisApi
from hantubot.reporting.notifier import Notifier
from hantubot.reporting.logger import get_logger

logger = get_logger("NomadSignal")

# Nomad Score Weights
WEIGHTS = {
    "C1_top1_volume": -1,
    "C3_top10_value": -1,
    "C4_prev_limit_up": 0,
    "C5_three_up": -1,
    "C6_break_ath": -2,
    "C7_near_52w_high": 2,
    "C8_below_52w_high": -1,
    "C9_strong_close": 3,
    "C10_intraday_up": 1
}

def wait_until_market_close():
    """15:00:00 KST까지 대기"""
    tz = pytz.timezone('Asia/Seoul')
    now = datetime.datetime.now(tz)
    target = now.replace(hour=15, minute=0, second=0, microsecond=0)
    
    if now >= target:
        logger.info("이미 15:00가 지났습니다. 즉시 실행합니다.")
        return

    wait_seconds = (target - now).total_seconds()
    logger.info(f"15:00까지 {wait_seconds:.1f}초 대기합니다...")
    time.sleep(wait_seconds)

def get_kis_api():
    """환경변수에서 설정 로드하여 KisApi 객체 생성"""
    app_key = os.getenv("KIS_APP_KEY")
    app_secret = os.getenv("KIS_APP_SECRET")
    account_no = os.getenv("KIS_ACCOUNT_NO")
    
    if not all([app_key, app_secret, account_no]):
        logger.warning("KIS API 설정을 찾을 수 없습니다. (환경변수 확인 필요)")
        return None

    # KisApi가 기대하는 config 구조 생성
    config = {
        'api': {
            'app_key': app_key,
            'app_secret': app_secret,
            'account_no': account_no,
            'base_url': {
                'mock': 'https://openapivts.koreainvestment.com:29443',
                'live': 'https://openapi.koreainvestment.com:9443'
            }
        }
    }
    return KisApi(config, is_mock=False)

def calculate_nomad_score(ticker, df_daily, market_stats):
    """
    개별 종목의 Nomad Score 계산
    df_daily: 해당 종목의 일봉 데이터 (최근 1년치 이상)
    market_stats: 시장 전체 통계 (거래량 1위, 거래대금 상위 등 확인용)
    """
    score = 0
    details = []
    
    if df_daily.empty:
        return 0, []

    today_candle = df_daily.iloc[-1]
    prev_candle = df_daily.iloc[-2] if len(df_daily) > 1 else None
    
    # C1: 거래량 1위 (-1)
    # market_stats['top1_volume_ticker'] 와 비교
    if ticker == market_stats.get('top1_volume_ticker'):
        score += WEIGHTS["C1_top1_volume"]
        details.append("C1_거래량1위(-1)")

    # C3: 거래대금 Top 10 (-1)
    if ticker in market_stats.get('top10_value_tickers', []):
        score += WEIGHTS["C3_top10_value"]
        details.append("C3_대금Top10(-1)")

    # C4: 전일 상한가 (0) - 생략 가능하지만 명시
    # 상한가는 보통 29.5% 이상으로 판단
    if prev_candle is not None and prev_candle['등락률'] >= 29.5:
        score += WEIGHTS["C4_prev_limit_up"]
        details.append("C4_전일상한(0)")

    # C5: 3일 연속 상승 (-1)
    if len(df_daily) >= 3:
        if all(df_daily['등락률'].iloc[-3:] > 0):
            score += WEIGHTS["C5_three_up"]
            details.append("C5_3연양(-1)")

    # C6: 신고가 돌파 (-2)
    # 전체 데이터 기준 최고가 확인
    max_price = df_daily['종가'].max()
    if today_candle['종가'] >= max_price:
         score += WEIGHTS["C6_break_ath"]
         details.append("C6_신고가(-2)")

    # C7: 52주 신고가 근접 (2) - 95% 이상
    # 최근 250일(약 1년) 데이터
    df_52w = df_daily.tail(250)
    high_52w = df_52w['고가'].max()
    if today_candle['종가'] >= high_52w * 0.95 and today_candle['종가'] < high_52w:
        score += WEIGHTS["C7_near_52w_high"]
        details.append("C7_52주근접(+2)")

    # C8: 52주 신고가 아래 (-1) - C7과 겹치지 않는 범위? 
    # 보통 C7이 아니면 C8로 간주할 수도 있으나, 명확한 기준 필요.
    # 여기서는 단순히 52주 고가 대비 90% 미만으로 가정하거나, C7 미충족 시 적용
    if today_candle['종가'] < high_52w * 0.95:
        score += WEIGHTS["C8_below_52w_high"]
        details.append("C8_52주아래(-1)")

    # C9: 종가 고가 마감 (3) - 윗꼬리 거의 없음 (몸통의 10% 미만?)
    # (고가 - 종가)가 (종가 - 시가) * 0.1 보다 작거나 등등
    # 여기서는 고가 == 종가 로 단순화하거나 아주 근접한 경우
    if today_candle['고가'] == today_candle['종가']:
        score += WEIGHTS["C9_strong_close"]
        details.append("C9_종가고가(+3)")

    # C10: 분봉상 상승세 (1)
    # 실시간 데이터가 없으므로 일봉상 양봉으로 대체하거나 생략
    if today_candle['종가'] > today_candle['시가']:
        score += WEIGHTS["C10_intraday_up"]
        details.append("C10_장중상승(+1)")
    
    return score, details

def run_signal():
    logger.info("=== Hantubot V3 Signal Start ===")
    
    # 1. 15:00 대기
    wait_until_market_close()
    
    # 2. 시장 데이터 수집 (pykrx)
    # 오늘 날짜
    tz = pytz.timezone('Asia/Seoul')
    today_str = datetime.datetime.now(tz).strftime("%Y%m%d")
    
    logger.info(f"데이터 수집 시작: {today_str}")
    
    try:
        # 전체 시세 조회
        df_kospi = stock.get_market_ohlcv_by_ticker(today_str, market="KOSPI")
        df_kosdaq = stock.get_market_ohlcv_by_ticker(today_str, market="KOSDAQ")
        df_all = pd.concat([df_kospi, df_kosdaq])
        
        # 거래대금 상위 50개 추출 (대상군)
        df_all['거래대금'] = df_all['거래대금'].astype(float)
        top_value_df = df_all.sort_values(by='거래대금', ascending=False).head(50)
        
        # 시장 통계 준비
        top1_vol = df_all.sort_values(by='거래량', ascending=False).index[0]
        top10_val = top_value_df.index[:10].tolist()
        
        market_stats = {
            'top1_volume_ticker': top1_vol,
            'top10_value_tickers': top10_val
        }
        
        # Notifier 초기화
        notifier = Notifier() # config.yaml 자동 로드
        
        # 3. 대상군 분석 및 스코어링
        signals = []
        
        for ticker in top_value_df.index:
            try:
                stock_name = stock.get_market_ticker_name(ticker)
                
                # 최근 1년 데이터 조회 (API 호출 최소화 위해 pykrx 사용)
                # 15:00~15:20 사이라 pykrx 데이터가 당일 포함 업데이트 되었을 수 있음
                # 하지만 장 마감 전이라 당일 데이터가 없을 수도 있으니 확인 필요
                # get_market_ohlcv_by_ticker는 실시간성이 떨어질 수 있음.
                # 하지만 run_signal은 15:03에 실행되므로, 
                # pykrx가 네이버금융 크롤링이면 장중 데이터 가져올 수 있음.
                
                # 과거 데이터 조회 (1년)
                start_date = (datetime.datetime.now(tz) - datetime.timedelta(days=365)).strftime("%Y%m%d")
                df_daily = stock.get_market_ohlcv_by_date(start_date, today_str, ticker)
                
                if df_daily.empty:
                    continue
                    
                score, details = calculate_nomad_score(ticker, df_daily, market_stats)
                
                if score >= 5: # 기준점
                    signals.append({
                        'ticker': ticker,
                        'name': stock_name,
                        'score': score,
                        'details': details,
                        'price': df_daily.iloc[-1]['종가']
                    })
                    logger.info(f"Signal Found: {stock_name} ({score}점)")
                
                time.sleep(0.1) # 부하 조절
                
            except Exception as e:
                logger.error(f"Error analyzing {ticker}: {e}")
                continue

        # 4. 결과 전송
        if signals:
            msg = f"📢 **Nomad V3 Signal ({today_str})**\nFound {len(signals)} candidates."
            
            # Embed 생성
            fields = []
            for s in signals:
                fields.append({
                    "name": f"{s['name']} ({s['score']}점)",
                    "value": f"{s['price']:,}원 / " + ", ".join(s['details']),
                    "inline": False
                })
                
            embed = {
                "title": "Nomad Signal Report",
                "color": 0x00ff00,
                "fields": fields[:25] # Discord limit
            }
            
            notifier.send_alert(msg, embed=embed)
        else:
            logger.info("No signals found.")
            notifier.send_alert(f"📉 Nomad V3 Signal ({today_str}): No candidates found.")
            
    except Exception as e:
        logger.error(f"Critical Error in run_signal: {e}", exc_info=True)
        # 에러 알림
        Notifier().send_alert(f"⚠️ Nomad V3 Error: {e}", level='error')

if __name__ == "__main__":
    run_signal()
