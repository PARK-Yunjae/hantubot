import pandas as pd

# 설정
FILE_PATH = "data/final_ranking_v6.csv"
df = pd.read_csv(FILE_PATH)

results = []

print("🚀 매도 전략 시뮬레이션 중...")

for idx, row in df.iterrows():
    gap_profit = row['Gap_Profit']
    max_profit = row['Max_Profit']
    end_profit = row['End_Profit']
    grade = row['Grade']
    
    # === 전략 1: 기존 (반반 매도) ===
    # 시초가 50%, 나머지 고점-2% 매도 가정 (단, 고점이 시초가보다 낮으면 시초가 매도)
    real_max = max(gap_profit, max_profit)
    ts_exit = real_max - 2.0 # 고점 대비 -2%
    # 만약 종가가 TS가보다 높으면 종가 매도, 아니면 TS 매도
    exit_profit = max(end_profit, ts_exit) 
    
    profit_old = (gap_profit * 0.5) + (exit_profit * 0.5)
    
    # === 전략 2: Whale Tail (차등 매도) ===
    if "S-Class" in grade:
        # 시초가 30%, 나머지 고점 -4% TS
        ts_exit_whale = real_max - 4.0
        exit_profit_whale = max(end_profit, ts_exit_whale)
        profit_new = (gap_profit * 0.3) + (exit_profit_whale * 0.7)
    else:
        # B급은 시초가 100%
        profit_new = gap_profit

    results.append({
        'Grade': grade,
        'Old_Strategy': profit_old,
        'New_Strategy': profit_new
    })

df_res = pd.DataFrame(results)
print("\n[📊 전략별 평균 수익률 비교]")
print(df_res.groupby('Grade').mean())