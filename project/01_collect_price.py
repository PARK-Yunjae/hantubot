import os
import time
import pandas as pd
from pykrx import stock
from tqdm import tqdm

# === 설정 값 ===
START_DATE = "20160616"
END_DATE = "20251231"
SAVE_DIR = "data/raw"

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

print(f"🚀 데이터 수집 시작 (가격 + 거래대금): {START_DATE} ~ {END_DATE}")

# 1. 종목 리스트 가져오기
today = time.strftime("%Y%m%d")
kospi = stock.get_market_ticker_list(today, market="KOSPI")
kosdaq = stock.get_market_ticker_list(today, market="KOSDAQ")
all_tickers = kospi + kosdaq

print(f"📌 총 수집 대상: {len(all_tickers)}개")

# 2. 수집 시작
for ticker in tqdm(all_tickers, desc="진행률"):
    try:
        file_path = f"{SAVE_DIR}/{ticker}.csv"
        # 이어하기 기능
        if os.path.exists(file_path):
            continue

        # [요청 1] 가격 데이터 (시가, 고가, 저가, 종가, 거래량)
        df_price = stock.get_market_ohlcv(START_DATE, END_DATE, ticker)
        
        # [요청 2] 펀더멘탈 데이터 (거래대금, 시가총액, 상장주식수)
        # ⚠️ 거래대금은 여기에 들어있습니다!
        df_cap = stock.get_market_cap_by_date(START_DATE, END_DATE, ticker)

        if df_price.empty or df_cap.empty:
            continue

        # 3. 데이터 병합 (날짜 기준 합치기)
        # 가격 데이터와 거래대금 데이터를 합칩니다.
        df = pd.concat([df_price, df_cap], axis=1)

        # 4. 컬럼 정리 및 필터링
        # 중복된 컬럼이나 불필요한 컬럼 정리
        # (df_price의 컬럼: 시가, 고가, 저가, 종가, 거래량, 등락률)
        # (df_cap의 컬럼: 시가총액, 거래대금, 상장주식수)
        
        # 필요한 컬럼만 선택 (영어로 올 수도 있으니 안전하게 처리)
        target_cols = ['시가', '고가', '저가', '종가', '거래량', '등락률', '거래대금', '시가총액', '상장주식수']
        available_cols = [c for c in target_cols if c in df.columns]
        
        # 만약 영어로 되어 있다면 한글로 변환 시도
        if 'Open' in df.columns:
            df = df.rename(columns={
                'Open': '시가', 'High': '고가', 'Low': '저가', 'Close': '종가', 
                'Volume': '거래량', 'Trading Value': '거래대금', 'Market Cap': '시가총액'
            })
            
        # 다시 확인
        if '거래대금' not in df.columns:
            # print(f"Skip {ticker}: 거래대금 컬럼 없음")
            continue

        # 거래대금 0인 날 제거 (거래정지일 등)
        df = df[df['거래대금'] > 0]

        if not df.empty:
            df.to_csv(file_path)

        # 서버 부하 방지 (2번 호출했으므로 조금 더 여유롭게)
        time.sleep(0.5)

    except Exception as e:
        # print(f"Error ({ticker}): {e}")
        time.sleep(0.5)

print("\n🎉 수집 완료! 이제 진짜 거래대금이 포함된 파일이 생길 겁니다.")