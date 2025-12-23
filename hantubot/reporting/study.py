# hantubot_prod/hantubot/reporting/study.py
import os
import time
from datetime import datetime
from typing import List

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
from pykrx import stock
from pykrx import stock
import google.generativeai as genai

from .logger import get_logger

logger = get_logger(__name__)

# --- Configuration ---
GSHEET_SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
GSHEET_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'configs', 'google_service_account.json')
GSHEET_NAME = "시장 관심주 추적"

# --- Gemini API Functions ---
def get_company_summary_with_gemini(stock_name: str, ticker: str) -> str:
    """
    Uses the Gemini API to generate a concise summary of a company's business.
    """
    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.warning("GEMINI_API_KEY not found in .env file. Skipping summary.")
            return "Gemini API 키가 설정되지 않았습니다."

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"'{stock_name}'({ticker})는 어떤 회사인가요? 핵심 사업 내용을 한국어로 2~3문장으로 요약해주세요."
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Failed to get company summary for {stock_name} using Gemini API: {e}")
        return f"Gemini API 요약 실패: {e}"

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
def run_daily_study(broker, notifier):
    """
    "100일 공부" 리서치 루틴: Google Sheets & Gemini API 완전 자동화 버전
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
        if not existing_df.empty and today_date_str_for_check in existing_df['Date'].values:
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
        
        interesting_tickers = interesting_tickers_df.index.tolist()
        logger.info(f"Found {len(interesting_tickers)} stocks for daily study.")
        df_funda = stock.get_market_fundamental_by_ticker(today_str)
    except Exception as e:
        logger.error(f"Failed to fetch stocks for daily study from pykrx: {e}", exc_info=True)
        return
        
    # 3. Process each stock and gather data
    daily_records = []
    for ticker in interesting_tickers:
        try:
            stock_info = interesting_tickers_df.loc[ticker]
            stock_name = stock.get_market_ticker_name(ticker)
            
            logger.info(f"Processing {stock_name} ({ticker})...")
            
            company_summary = get_company_summary_with_gemini(stock_name, ticker)
            
            pbr, per = 'N/A', 'N/A'
            if ticker in df_funda.index:
                fundamentals = df_funda.loc[ticker]
                pbr = fundamentals.get('PBR', 'N/A')
                per = fundamentals.get('PER', 'N/A')
            
            reason = ", ".join([r for r, c in [("거래량천만", stock_info['거래량'] >= 10_000_000), ("상한가", stock_info['등락률'] >= 29.0)] if c])

            daily_records.append({
                "날짜": today_date_str_for_check,
                "종목코드": ticker,
                "종목명": stock_name,
                "선정사유": reason,
                "종가": stock_info['종가'],
                "등락률": f"{stock_info['등락률']:.2f}%",
                "기업개요": company_summary,
                "PBR": pbr,
                "PER": per,
            })
            time.sleep(15)
        except Exception as e:
            logger.error(f"Failed to process {ticker} for GSheet: {e}")

    if not daily_records:
        logger.info("No records to update to Google Sheets.")
        return
        
    # 4. Update Google Sheets
    try:
        # Note: existing_df was fetched at the start of the function
        new_df = pd.DataFrame(daily_records)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True).astype(str)
        set_with_dataframe(log_ws, combined_df, include_index=False, resize=True)
        logger.info(f"Appended {len(new_df)} new records to 'DailyLog' worksheet.")

        # Update Frequency Analysis using Korean column name
        freq_counts = combined_df['종목명'].value_counts().reset_index()
        freq_counts.columns = ['종목명', '등장횟수']
        set_with_dataframe(freq_ws, freq_counts, include_index=False, resize=True)
        logger.info("Updated 'Frequency_Analysis' worksheet.")

        summary_fields = [{"name": f"- {rec['종목명']} ({rec['종목코드']})", "value": f"이유: {rec['선정사유']}", "inline": False} for rec in daily_records[:5]]
        embed = {"title": f"📝 유목민 공부법 리포트 -> GSheet 저장 완료", "description": f"금일의 관심 종목 **{len(daily_records)}개**가 자동 요약과 함께 Google Sheet에 저장되었습니다.", "color": 5814783, "fields": summary_fields}
        notifier.send_alert("유목민 공부법 분석 완료", embed=embed)

    except Exception as e:
        logger.error(f"Failed to update Google Sheets: {e}", exc_info=True)
        notifier.send_alert(f"Google Sheets 업데이트 실패: {e}", level='error')

if __name__ == '__main__':
    # This test won't work without a mock for gspread and gemini
    pass
