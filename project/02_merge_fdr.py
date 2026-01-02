import FinanceDataReader as fdr
import pandas as pd
import os
import time
from tqdm import tqdm

# === ⚙️ 설정 ===
RAW_DIR = "data/raw"      # 1단계 결과물 (거래대금 O, 수정주가 X)
ADJ_DIR = "data/adjusted" # 최종 결과물 (거래대금 O, 수정주가 O)

# 폴더 없으면 생성
if not os.path.exists(ADJ_DIR):
    os.makedirs(ADJ_DIR)

# 1단계에서 만든 파일 목록 가져오기
file_list = [f for f in os.listdir(RAW_DIR) if f.endswith('.csv')]

print(f"🚀 Step 2: 수정주가 병합 시작 (대상: {len(file_list)}개)")

# 반복문 시작
for file in tqdm(file_list, desc="데이터 가공 중"):
    ticker = file.replace(".csv", "")
    
    try:
        # 1. PyKRX 원본 로드 (1단계 결과물)
        # index_col=0: 날짜 컬럼을 인덱스로 사용 / parse_dates=True: 날짜 형식으로 인식
        df_krx = pd.read_csv(f"{RAW_DIR}/{file}", index_col=0, parse_dates=True)
        
        # 2. FDR 수정주가 로드 (2016년 ~ 현재)
        # 수정주가(액면분할 등이 반영된 차트용 가격)를 가져옵니다.
        df_fdr = fdr.DataReader(ticker, '2016-06-16', '2025-12-31')
        
        # FDR 데이터가 없으면(상장폐지 등) 스킵
        if df_fdr.empty:
            continue
            
        # 3. 데이터 병합 (교집합)
        # 날짜(인덱스)가 같은 날끼리만 합칩니다. 
        merged = df_krx.join(df_fdr, how='inner')
        
        # 4. 최종 컬럼 정리 (핵심 로직!)
        final_df = pd.DataFrame({
            # 가격 정보는 FDR(수정주가) 사용 -> 차트 분석용
            'Open': merged['Open'],     
            'High': merged['High'],
            'Low': merged['Low'],
            'Close': merged['Close'],
            'Volume': merged['Volume'], 
            'Change': merged['Change'],
            
            # 🔥 핵심: 돈(거래대금)은 PyKRX 원본 사용 -> 조건 검색용
            # 1단계 파일에 '거래대금'이라는 컬럼이 있어야 합니다. (확인 완료)
            'TradingValue': merged['거래대금'] 
        })
        
        # (선택) 시가총액 정보가 있다면 추가
        if '시가총액' in merged.columns:
            final_df['Marcap'] = merged['시가총액']
        if '상장주식수' in merged.columns:
            final_df['Shares'] = merged['상장주식수']

        # 5. 저장
        final_df.to_csv(f"{ADJ_DIR}/{ticker}.csv")
        
        # 너무 빠르면 차단될 수 있으니 0.1초 휴식
        time.sleep(0.1)
        
    except Exception as e:
        # 에러 발생 시 해당 종목만 건너뛰고 계속 진행
        # print(f"⚠️ Error {ticker}: {e}") 
        continue

print("\n🎉 2단계 완료! 'data/adjusted' 폴더 확인하세요.")  