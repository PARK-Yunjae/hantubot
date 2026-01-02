import pandas as pd
import os
import glob
from tqdm import tqdm

# === 설정 ===
ADJ_DIR = "data/adjusted"
RESULT_FILE = "data/news_candidates.csv" # 이 파일이 '보물지도'가 됩니다.

# 파일 목록 가져오기
file_list = glob.glob(f"{ADJ_DIR}/*.csv")
candidates = []

print(f"🚀 3단계: 과거 데이터에서 후보군 추출 시작 (파일 {len(file_list)}개)")

for file in tqdm(file_list, desc="스카우팅 중"):
    ticker = os.path.basename(file).replace(".csv", "")
    
    try:
        # 데이터 로드
        df = pd.read_csv(file)
        
        # 날짜 컬럼 인덱스 설정 (파일명이 index거나 Date거나.. 확인 필요)
        # 02번 코드 결과물은 'Unnamed: 0'이 날짜일 확률이 높습니다.
        if 'Unnamed: 0' in df.columns:
            df = df.rename(columns={'Unnamed: 0': 'Date'})
        
        # 조건 필터링 (작성자님의 로직)
        # 1. 거래대금 150억 이상
        # 2. 양봉 (종가 > 시가)
        # 3. 동전주 제외 (2000원 이상)
        cond = (
            (df['TradingValue'] >= 30000000000) &  # 300억 원 (0 7개 -> 0 10개 주의!)
            (df['Close'] > df['Open']) & 
            (df['Close'] >= 2000)
        )
        
        # 조건 만족하는 행만 추출
        selected_rows = df[cond]
        
        # 결과 리스트에 담기
        for _, row in selected_rows.iterrows():
            candidates.append({
                'Code': ticker,
                'Date': row['Date'],       # 언제?
                'Close': row['Close'],     # 얼마에?
                'Volume': row['TradingValue'] # 얼마나 터졌나?
            })
            
    except Exception as e:
        continue

# 결과 저장
df_candidates = pd.DataFrame(candidates)
df_candidates.to_csv(RESULT_FILE, index=False)

print(f"\n🎉 3단계 완료! 총 {len(df_candidates)}번의 매매 기회가 포착되었습니다.")
print(f"👉 저장 위치: {RESULT_FILE}")