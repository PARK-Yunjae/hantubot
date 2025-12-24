# hantubot_prod/hantubot/reporting/study.py
import os
import time
from datetime import datetime
from typing import List, Dict
import json

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
from pykrx import stock
import google.generativeai as genai  # 안정 버전 사용

from .logger import get_logger

logger = get_logger(__name__)

# --- Configuration ---
GSHEET_SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
GSHEET_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'configs', 'google_service_account.json')
GSHEET_NAME = "시장 관심주 추적"

# --- Gemini API Functions (Batch Optimized) ---
def get_batch_summaries_with_gemini(stocks_to_summarize: List[Dict]) -> Dict[str, str]:
    """
    Uses the Gemini API to generate concise summaries for a batch of stocks in a single call.
    Returns a dictionary mapping ticker to summary.
    """
    summaries = {stock['ticker']: "요약 생성 실패" for stock in stocks_to_summarize}
    
    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.warning("GEMINI_API_KEY not found in .env file. Skipping summary.")
            return summaries

        genai.configure(api_key=api_key)
        # 무료 티어에서 사용 가능한 최신 안정 모델
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Build a single prompt for all stocks
        stock_list_str = "\n".join([f"- {s['name']} ({s['ticker']})" for s in stocks_to_summarize])
        prompt = (
            "아래 주식 종목들에 대해, 각각의 핵심 사업 내용을 한국어로 2~3 문장으로 요약해줘.\n"
            "각 문장 끝에는 줄바꿈 문자(\\n)를 포함해서 가독성을 높여줘.\n"
            "결과는 반드시 아래와 같은 JSON 형식으로 '종목코드': '요약' 형태로 제공해줘. 다른 설명은 모두 제외해줘.\n"
            "```json\n"
            "{\n"
            '  "005930": "세계적인 종합 반도체 기업으로, 메모리 반도체와 시스템 LSI 사업을 영위함.\n스마트폰, TV, 가전제품 등 다양한 전자제품을 생산 및 판매하며 글로벌 IT 시장을 선도함.",\n'
            '  "000660": "DRAM, 낸드플래시 등 메모리 반도체를 주력으로 생산하는 기업임.\n서버, 모바일, PC 등 다양한 IT 기기에 필수적인 부품을 공급하며 기술 경쟁력을 확보하고 있음."\n'
            "}\n"
            "```\n\n"
            f"요약할 종목 목록:\n{stock_list_str}"
        )
        
        response = model.generate_content(prompt)
        
        # Clean up and parse the JSON response
        response_text = response.text.strip()
        
        # Remove markdown code blocks
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        # Find JSON content (sometimes Gemini adds extra text)
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            json_text = response_text[start_idx:end_idx+1]
            json_response = json.loads(json_text)
            
            # Gemini might return summaries for different tickers, so we update our dict safely
            for ticker, summary in json_response.items():
                if ticker in summaries:
                    summaries[ticker] = summary
            
            logger.info(f"Successfully generated summaries for {len(json_response)} stocks in a single batch call.")
        else:
            logger.warning("Gemini 응답에서 JSON을 찾을 수 없습니다.")
        
        return summaries

    except Exception as e:
        logger.error(f"Failed to get batch company summaries using Gemini API: {e}", exc_info=True)
        return summaries


# --- Google Sheets Functions ---
def get_gsheet_client():
    """Authenticate with Google and return the gspread client."""
    if not os.path.exists(GSHEET_CONFIG_PATH):
        raise FileNotFoundError(f"Google Service Account key not found at {GSHEET_CONFIG_PATH}")
    creds = Credentials.from_service_account_file(GSHEET_CONFIG_PATH, scopes=GSHEET_SCOPE)
    return gspread.authorize(creds)

def get_worksheet_or_create(spreadsheet: gspread.Spreadsheet, name: str):
    """Get a worksheet by name, or create it if it doesn't exist."""
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        logger.info(f"Worksheet '{name}' not found, creating it.")
        return spreadsheet.add_worksheet(title=name, rows=1, cols=1)

# --- Main Study Logic ---
def run_daily_study(broker, notifier, force_run=False):
    """
    "100일 공부" 리서치 루틴: Google Sheets & Gemini API 완전 자동화 버전
    
    Args:
        broker: 브로커 인스턴스
        notifier: 알림 인스턴스
        force_run: True면 중복 체크 무시하고 강제 실행
    """
    logger.info("Running daily study: Fully Automated GSheet + Gemini Edition...")
    today_str = datetime.now().strftime("%Y%m%d")
    today_date_str_for_check = datetime.now().strftime("%Y-%m-%d")

    # 1. Connect to Google Sheets and check for duplicates FIRST
    try:
        gsheet_client = get_gsheet_client()
        spreadsheet = gsheet_client.open(GSHEET_NAME)
        log_ws = get_worksheet_or_create(spreadsheet, "DailyLog")
        
        existing_df = pd.DataFrame(log_ws.get_all_records())
        if not force_run and not existing_df.empty and today_date_str_for_check in existing_df['날짜'].values:
            logger.info(f"Today's study for {today_date_str_for_check} has already been completed. Skipping.")
            return

        freq_ws = get_worksheet_or_create(spreadsheet, "Frequency_Analysis")
    except Exception as e:
        logger.error(f"Failed to connect to Google Sheets for pre-check: {e}", exc_info=True)
        notifier.send_alert(f"Google Sheets 연결 실패 (사전 확인): {e}", level='error')
        return

    # 2. Fetch interesting stocks from pykrx
    try:
        df_all = stock.get_market_ohlcv_by_ticker(today_str, market="ALL")
        volume_filter = df_all['거래량'] >= 10_000_000
        price_ceil_filter = df_all['등락률'] >= 29.0
        interesting_tickers_df = df_all[volume_filter | price_ceil_filter]
        
        if interesting_tickers_df.empty:
            logger.info("No stocks met the criteria for daily study today.")
            return
        
        # [수정] ETF, 스팩 등 제외 필터링 적용
        from ..utils.stock_filters import is_eligible_stock
        
        unfiltered_tickers = interesting_tickers_df.index.tolist()
        interesting_tickers = [
            ticker for ticker in unfiltered_tickers 
            if is_eligible_stock(stock.get_market_ticker_name(ticker))
        ]
        
        if not interesting_tickers:
            logger.info("필터링된 종목이 없어 데일리 스터디 대상이 없습니다.")
            return
            
        logger.info(f"필터링 후 데일리 스터디 대상 적격 종목 {len(interesting_tickers)}개 발견.")
        df_funda = stock.get_market_fundamental_by_ticker(today_str)
    except Exception as e:
        logger.error(f"Failed to fetch stocks for daily study from pykrx: {e}", exc_info=True)
        return

    # 3. Get all summaries in one batch call
    stocks_to_summarize = [{'ticker': t, 'name': stock.get_market_ticker_name(t)} for t in interesting_tickers]
    all_summaries = get_batch_summaries_with_gemini(stocks_to_summarize)
    time.sleep(15) # Respect potential API rate limits after a large call

    # 4. Process each stock and gather data
    daily_records = []
    for ticker in interesting_tickers:
        try:
            stock_info = interesting_tickers_df.loc[ticker]
            stock_name = stock.get_market_ticker_name(ticker)
            
            company_summary = all_summaries.get(ticker, "요약 없음.")
            
            reason = ", ".join([r for r, c in [("거래량천만", stock_info['거래량'] >= 10_000_000), ("상한가", stock_info['등락률'] >= 29.0)] if c])

            # 간소화된 컬럼 (재무지표 제외)
            daily_records.append({
                "날짜": today_date_str_for_check,
                "종목코드": ticker,
                "종목명": stock_name,
                "선정사유": reason,
                "종가": f"{stock_info['종가']:,}",
                "등락률": f"{stock_info['등락률']:.2f}%",
                "거래량": f"{stock_info['거래량']:,}",
                "기업개요": company_summary,
            })
        except Exception as e:
            logger.error(f"Failed to process {ticker} for GSheet: {e}")

    if not daily_records:
        logger.info("No records to update to Google Sheets.")
        return
        
    # 5. Update Google Sheets
    try:
        new_df = pd.DataFrame(daily_records)
        if not existing_df.empty:
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        
        # Ensure all data is string to avoid gspread issues
        combined_df = combined_df.astype(str)

        set_with_dataframe(log_ws, combined_df, include_index=False, resize=True)
        logger.info(f"Appended {len(new_df)} new records to 'DailyLog' worksheet.")
        
        # 자동 열 너비 조정 (내용에 맞게)
        try:
            # 모든 열에 대해 자동 크기 조정 요청
            num_cols = len(combined_df.columns)
            log_ws.columns_auto_resize(0, num_cols - 1)
            logger.info("열 너비 자동 조정 완료.")
        except Exception as e:
            logger.warning(f"열 너비 자동 조정 실패 (무시 가능): {e}")

        # Update Frequency Analysis using Korean column name
        freq_counts = combined_df['종목명'].value_counts().reset_index()
        freq_counts.columns = ['종목명', '등장횟수']
        set_with_dataframe(freq_ws, freq_counts, include_index=False, resize=True)
        logger.info("Updated 'Frequency_Analysis' worksheet.")
        
        # Frequency 시트도 자동 크기 조정
        try:
            freq_ws.columns_auto_resize(0, 1)
            logger.info("Frequency 시트 열 너비 자동 조정 완료.")
        except Exception as e:
            logger.warning(f"Frequency 시트 열 너비 자동 조정 실패 (무시 가능): {e}")

        summary_fields = [{"name": f"- {rec['종목명']} ({rec['종목코드']})", "value": f"이유: {rec['선정사유']}", "inline": False} for rec in daily_records[:5]]
        embed = {"title": f"📝 유목민 공부법 리포트 -> GSheet 저장 완료", "description": f"금일의 관심 종목 **{len(daily_records)}개**가 자동 요약과 함께 Google Sheet에 저장되었습니다.", "color": 5814783, "fields": summary_fields}
        notifier.send_alert("유목민 공부법 분석 완료", embed=embed)

    except Exception as e:
        logger.error(f"Failed to update Google Sheets: {e}", exc_info=True)
        notifier.send_alert(f"Google Sheets 업데이트 실패: {e}", level='error')

if __name__ == '__main__':
    # This test won't work without a mock for gspread and gemini
    pass
