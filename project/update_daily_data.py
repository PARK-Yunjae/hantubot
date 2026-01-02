import pandas as pd
import os
import time
import datetime
from pykrx import stock
from tqdm import tqdm

# === 설정 ===
DATA_DIR = "data/adjusted"  # 시뮬레이션 데이터 경로
MARKET = "KOSDAQ"           # 코스닥 중심

def update_daily_data():
    """
    매일 장 종료 후 실행: 오늘 데이터를 기존 CSV에 추가 (Incremental Update)
    """
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    # 오늘이 휴장일인지 체크하지 않고, 데이터가 없으면 종료
    print(f"[{today_str}] 데이터 업데이트 시작...")
    
    # 1. 오늘자 코스닥 전 종목 시세 조회 (속도: 빠름)
    try:
        df_today = stock.get_market_ohlcv_by_ticker(today_str, market=MARKET)
        df_value = stock.get_market_trading_value_by_ticker(today_str, market=MARKET)
    except Exception as e:
        print(f"❌ 데이터 조회 실패: {e}")
        return

    if df_today.empty:
        print("💤 오늘은 휴장일이거나 장 데이터가 아직 없습니다.")
        return

    # 거래대금 컬럼 병합
    if df_value is not None:
        df_today = df_today.join(df_value['거래대금'], how='left')
        df_today.rename(columns={'거래대금': 'TradingValue'}, inplace=True)
    else:
        # 거래대금이 안 불러와지면 종가*거래량으로 근사
        df_today['TradingValue'] = df_today['종가'] * df_today['거래량']

    # 2. 파일 업데이트
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 컬럼 매핑 (한글 -> 영문, 기존 파일 형식에 맞춤)
    # 기존 파일 포맷: Date(Index), Open, High, Low, Close, Volume, TradingValue, Change
    
    update_count = 0
    new_count = 0
    
    # 진행률 표시
    for ticker, row in tqdm(df_today.iterrows(), total=len(df_today), desc="파일 업데이트 중"):
        file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
        
        # 오늘 데이터 한 줄 생성
        # row: 시가, 고가, 저가, 종가, 거래량, 거래대금, 등락률
        daily_data = {
            'Date': [today_str], # datetime보다는 string 추천
            'Open': [row['시가']],
            'High': [row['고가']],
            'Low': [row['저가']],
            'Close': [row['종가']],
            'Volume': [row['거래량']],
            'TradingValue': [row.get('TradingValue', 0)],
            'Change': [row['등락률']]
        }
        df_daily = pd.DataFrame(daily_data)
        df_daily.set_index('Date', inplace=True)
        
        if os.path.exists(file_path):
            # 기존 파일 로드
            try:
                # 마지막 날짜 확인하여 중복 방지
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                    last_line = lines[-1] if lines else ""
                    
                if today_str in last_line:
                    continue # 이미 업데이트 됨
                
                # Append 모드로 추가 (헤더 없이)
                df_daily.to_csv(file_path, mode='a', header=False)
                update_count += 1
            except Exception as e:
                # 파일 깨짐 등 에러 시 덮어쓰기 로직 등을 고려할 수 있음
                print(f"Error {ticker}: {e}")
        else:
            # 신규 파일 생성
            df_daily.to_csv(file_path, mode='w', header=True)
            new_count += 1

    print(f"\n✅ 업데이트 완료!")
    print(f"- 기존 종목 업데이트: {update_count}개")
    print(f"- 신규 종목 생성: {new_count}개")
    print(f"- 저장 위치: {DATA_DIR}")

if __name__ == "__main__":
    update_daily_data()
