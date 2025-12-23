# hantubot_prod/hantubot/reporting/study.py
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any
import requests
from bs4 import BeautifulSoup
from pykrx import stock

from .logger import get_logger
# from ..execution.broker import Broker # For type hinting

logger = get_logger(__name__)

def scrape_mk_news_headlines(stock_name: str, num_headlines: int = 5) -> List[str]:
    """
    매일경제에서 특정 종목의 최신 뉴스 헤드라인을 스크래핑합니다.
    """
    search_url = f"https://www.mk.co.kr/search?word={stock_name}"
    try:
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 뉴스 목록을 포함하는 엘리먼트 선택 (웹사이트 구조에 따라 변경될 수 있음)
        headlines = soup.select("ul.news_list > li > a.news_ttl")
        
        if not headlines:
            return ["최신 뉴스를 찾을 수 없습니다."]
            
        return [h.get_text(strip=True) for h in headlines[:num_headlines]]
    except Exception as e:
        logger.error(f"Failed to scrape news for {stock_name}: {e}")
        return [f"뉴스 스크래핑 중 오류 발생: {e}"]

def run_daily_study(broker):
    """
    "100일 공부"를 위한 장 마감 후 자동화된 리서치 루틴.
    - 상한가 및 거래량 천만주 이상 종목을 수집합니다.
    - 각 종목의 기본 정보와 뉴스를 취합하여 리서치 노트를 생성합니다.
    """
    logger.info("Running daily study for 'Youmokmin 100-Day Challenge'...")
    today_str = datetime.now().strftime("%Y%m%d")
    
    # --- 1. 대상 종목 선정 ---
    try:
        # 당일 OHLCV 데이터 가져오기
        df_all = stock.get_market_ohlcv_by_ticker(today_str, market="ALL")
        
        # 거래량 1000만주 이상 종목
        volume_filter = df_all['거래량'] >= 10_000_000
        
        # 상한가 종목 (등락률 29% 이상)
        price_ceil_filter = df_all['등락률'] >= 29.0
        
        # 두 조건 중 하나라도 만족하는 종목 필터링
        interesting_tickers_df = df_all[volume_filter | price_ceil_filter]
        interesting_tickers = interesting_tickers_df.index.tolist()

        if not interesting_tickers:
            logger.info("No stocks met the criteria for daily study today.")
            return

        logger.info(f"Found {len(interesting_tickers)} stocks for daily study: {interesting_tickers}")
        
        # --- 2. 재무 정보 일괄 조회 (버그 수정 및 효율화) ---
        df_funda = stock.get_market_fundamental_by_ticker(today_str)
        
    except Exception as e:
        logger.error(f"Failed to fetch stocks for daily study from pykrx: {e}", exc_info=True)
        return

    # --- 3. 리서치 노트 생성 ---
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    study_dir = os.path.join(base_dir, 'study_notes', today_str)
    os.makedirs(study_dir, exist_ok=True)

    for ticker in interesting_tickers:
        try:
            # --- 데이터 수집 ---
            stock_info = interesting_tickers_df.loc[ticker]
            stock_name = stock.get_market_ticker_name(ticker)
            
            # 선정 사유
            reason = []
            if stock_info['거래량'] >= 10_000_000:
                reason.append(f"거래량 1,000만 돌파 ({stock_info['거래량']:,}주)")
            if stock_info['등락률'] >= 29.0:
                reason.append(f"상한가 근접 ({stock_info['등락률']:.2f}%)")
            reason_str = ", ".join(reason)

            # 재무 정보 (조회된 df_funda에서 추출)
            pbr, per = 'N/A', 'N/A'
            if ticker in df_funda.index:
                fundamentals = df_funda.loc[ticker]
                pbr = fundamentals.get('PBR', 'N/A')
                per = fundamentals.get('PER', 'N/A')

            # 뉴스 헤드라인
            news_headlines = scrape_mk_news_headlines(stock_name)

            # --- 마크다운 파일 생성 ---
            note_content = f"""
# {stock_name} ({ticker}) - {today_str}

## Ⅰ. 선정 이유
- **핵심 트리거**: {reason_str}
- **종가**: {stock_info['종가']:,} 원
- **등락률**: {stock_info['등락률']:.2f} %
- **거래대금**: {stock_info['거래대금'] / 100_000_000:,.0f} 억원

## Ⅱ. 기본 정보
- **PBR**: {pbr}
- **PER**: {per}
- (여기에 기업 개요, 시가총액 등 추가 정보 기입 가능)

## Ⅲ. 최근 뉴스
"""
            for headline in news_headlines:
                note_content += f"- {headline}\n"

            note_content += """
## Ⅳ. 차트 분석 (직접 기록)
- 

## Ⅴ. 투자 아이디어 (직접 기록)
- **매수 관점**:
- **매도 관점**:
- **핵심 리스크**:

## Ⅵ. 추가 메모 (직접 기록)
- 
"""
            note_file_path = os.path.join(study_dir, f"{ticker}_{stock_name}.md")
            with open(note_file_path, 'w', encoding='utf-8') as f:
                f.write(note_content)
            logger.info(f"Created study note for {stock_name} at {note_file_path}")

        except Exception as e:
            logger.error(f"Failed to process and create study note for {ticker}: {e}")

if __name__ == '__main__':
    # 테스트를 위한 Mock Broker
    class MockBroker:
        def get_current_price(self, symbol): return 0
    
    run_daily_study(MockBroker())