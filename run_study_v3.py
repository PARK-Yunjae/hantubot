import os
import sys
import json
import datetime
import pytz
import pandas as pd
from pykrx import stock

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hantubot.reporting.logger import get_logger
from hantubot.utils.stock_filters import is_eligible_stock

logger = get_logger("NomadStudy")

def run_study():
    logger.info("=== Hantubot V3 Study Start ===")
    
    tz = pytz.timezone('Asia/Seoul')
    today_str = datetime.datetime.now(tz).strftime("%Y%m%d")
    
    logger.info(f"데이터 수집 시작: {today_str}")
    
    try:
        # pykrx로 전체 종목 조회
        df_all = stock.get_market_ohlcv_by_ticker(today_str, market="ALL")
        
        if df_all.empty:
            logger.warning("No market data available for today (Holiday?)")
            return
        
        # 필터 1: 거래량 1000만주 이상
        volume_filter = df_all['거래량'] >= 10_000_000
        
        # 필터 2: 상한가 (29.5% 이상으로 느슨하게 잡음)
        price_ceil_filter = df_all['등락률'] >= 29.5
        
        interesting_df = df_all[volume_filter | price_ceil_filter]
        
        results = []
        
        for ticker in interesting_df.index:
            try:
                name = stock.get_market_ticker_name(ticker)
                
                # ETF/스팩 등 제외
                if not is_eligible_stock(name):
                    continue
                
                row = interesting_df.loc[ticker]
                
                reasons = []
                if row['등락률'] >= 29.5: reasons.append("Upper Limit")
                if row['거래량'] >= 10_000_000: reasons.append("Top Volume")
                
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "close": int(row['종가']),
                    "change": float(row['등락률']),
                    "volume": int(row['거래량']),
                    "amount": int(row['거래대금']),
                    "reasons": reasons
                })
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                continue
        
        # 결과 저장
        if results:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            os.makedirs(data_dir, exist_ok=True)
            
            file_path = os.path.join(data_dir, f"daily_report_{today_str}.json")
            
            report_data = {
                "date": today_str,
                "count": len(results),
                "items": results
            }
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Saved {len(results)} items to {file_path}")
        else:
            logger.info("No stocks met the criteria today.")
            
    except Exception as e:
        logger.error(f"Critical Error in run_study: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run_study()
