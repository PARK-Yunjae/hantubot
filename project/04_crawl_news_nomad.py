import pandas as pd
import requests
import time
import os
from tqdm import tqdm
from pykrx import stock
import urllib3
import warnings

# === ⚙️ 설정 ===
CLIENT_ID = "La91HyCspMz9MzCOarTd"
CLIENT_SECRET = "xATf_CxCzL"

CANDIDATE_FILE = "data/news_candidates.csv" 
RESULT_FILE = "data/final_dataset_nomad.csv" 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# === 📖 키워드 사전 ===
KEYWORDS = {
    "S": ["단독", "세계 최초", "세계최초", "국내 최초", "FDA 승인", "임상 3상", "인수", "경영권", "무상증자"],
    "A": ["계약", "수주", "공급", "체결", "MOU", "협약", "사상 최대", "흑자", "어닝", "특허", "개발", "단일판매", "공급계약"],
    "B": ["특징주", "속보", "급등", "상한가", "신고가", "투자", "진출", "협력"],
    "BAD": ["유상증자", "추가상장", "CB", "BW", "환기", "관리", "횡령", "배임", "소송", "불성실", "감자"]
}

# 1. 파일 확인
if not os.path.exists(CANDIDATE_FILE):
    print("❌ 3단계 파일(news_candidates.csv)이 없습니다.")
    exit()

# 2. 이어하기 설정 (핵심 수정 파트 🛠️)
processed_keys = set()
if os.path.exists(RESULT_FILE):
    # 읽을 때부터 종목코드를 '문자열'로 강제 지정 (dtype={'Code': str})
    df_existing = pd.read_csv(RESULT_FILE, dtype={'Code': str})
    
    # 6자리로 확실하게 포맷팅 (혹시 모를 오류 방지)
    processed_codes = df_existing['Code'].apply(lambda x: f"{str(x).strip():0>6}")
    processed_dates = df_existing['Date'].astype(str).str[:10]
    
    processed_keys = set(processed_codes + "_" + processed_dates)
    print(f"🔄 이어하기: 기존 {len(df_existing)}건 완료됨. (중복 스킵)")

# 타겟 파일 로드 시에도 문자열로 강제 변환
targets = pd.read_csv(CANDIDATE_FILE, dtype={'Code': str}) 
results = []
batch_count = 0
api_call_count = 0

# 3. 종목명 매핑
print("📌 종목명 매핑 중...")
ticker_to_name = {}
for code in targets['Code'].unique():
    try:
        str_code = f"{str(code):0>6}" # 문자열 보장
        ticker_to_name[str_code] = stock.get_market_ticker_name(str_code)
    except: continue

print(f"🚀 책 기반 뉴스 수집 시작 (대상: {len(targets)}건)")

# 4. 크롤링 루프
for idx, row in tqdm(targets.iterrows(), total=len(targets), desc="재료 분석 중"):
    # 여기서도 6자리 문자열로 확실히 변환
    code = f"{str(row['Code']).strip():0>6}"
    target_date = str(row['Date'])[:10]
    
    unique_key = f"{code}_{target_date}"
    
    # 중복 체크
    if unique_key in processed_keys: continue
    
    # 안전마진 (하루 24,500건)
    if api_call_count >= 24500:
        print("⛔ API 한도 소진 (카운터 기준)! 내일 이어서 하세요.")
        break

    try:
        stock_name = ticker_to_name.get(code, "")
        if not stock_name: continue
            
        query = stock_name
        
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {"X-Naver-Client-Id": CLIENT_ID, "X-Naver-Client-Secret": CLIENT_SECRET}
        params = {"query": query, "display": 100, "sort": "date"}
        
        res = requests.get(url, headers=headers, params=params, timeout=5)
        api_call_count += 1
        
        # 🚨 중요: 실제 API 한도 초과(429) 시 즉시 종료 (헛돌기 방지)
        if res.status_code == 429:
            print("⛔ 네이버 API 한도 초과 (429 Error)! 스크립트를 종료합니다.")
            break
        
        if res.status_code != 200: 
            time.sleep(0.1)
            continue
            
        items = res.json().get('items', [])
        
        best_grade = "None"
        best_keyword = ""
        news_title = ""
        
        for item in items:
            title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", "")
            
            # 악재 필터
            is_bad = False
            for k in KEYWORDS["BAD"]:
                if k in title:
                    is_bad = True
                    best_keyword = k
                    break
            
            if is_bad: 
                best_grade = "BAD"
                news_title = title
                break 

            # 호재 등급
            found = False
            for grade in ["S", "A", "B"]:
                for k in KEYWORDS[grade]:
                    if k in title:
                        best_grade = grade
                        best_keyword = k
                        news_title = title
                        found = True
                        break
                if found: break
            
            if found: break
            
        results.append({
            'Code': code, # 6자리 문자열로 저장
            'Name': stock_name,
            'Date': target_date,
            'Close': row['Close'],
            'Volume': row['Volume'],
            'Grade': best_grade,
            'Keyword': best_keyword,
            'Title': news_title
        })
        
        time.sleep(0.05)
        
        batch_count += 1
        if batch_count % 1000 == 0:
            mode = 'a' if os.path.exists(RESULT_FILE) else 'w'
            header = not os.path.exists(RESULT_FILE)
            pd.DataFrame(results).to_csv(RESULT_FILE, mode=mode, header=header, index=False)
            results = []
            print(f"💾 중간 저장 완료 ({batch_count}건)")

    except Exception as e:
        continue

# 남은 데이터 저장
if results:
    mode = 'a' if os.path.exists(RESULT_FILE) else 'w'
    header = not os.path.exists(RESULT_FILE)
    pd.DataFrame(results).to_csv(RESULT_FILE, mode=mode, header=header, index=False)

print(f"\n🎉 수집 완료! 결과 파일: {RESULT_FILE}")
print(f"총 API 호출 횟수: {api_call_count}회")