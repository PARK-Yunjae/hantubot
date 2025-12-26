# -*- coding: utf-8 -*-
"""
잘못된 데이터 정리 및 재수집
"""
import sqlite3
from pathlib import Path

# DB 연결
db_path = Path('data/study.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 60)
print("데이터 정리 시작")
print("=" * 60)

# 1. 2024년 데이터 삭제 (20241220)
print("\n[1] 2024년 잘못된 데이터 삭제...")
dates_to_delete = ['20241220']

for date in dates_to_delete:
    cursor.execute('DELETE FROM study_runs WHERE run_date = ?', (date,))
    cursor.execute('DELETE FROM daily_candidates WHERE run_date = ?', (date,))
    cursor.execute('DELETE FROM news_items WHERE run_date = ?', (date,))
    cursor.execute('DELETE FROM summaries WHERE run_date = ?', (date,))
    cursor.execute('DELETE FROM study_notes WHERE run_date = ?', (date,))
    print(f"✓ {date} 데이터 삭제 완료")

# 2. 20251225 빈 데이터 삭제
print("\n[2] 빈 데이터 삭제 (20251225)...")
cursor.execute('DELETE FROM study_runs WHERE run_date = ?', ('20251225',))
cursor.execute('DELETE FROM daily_candidates WHERE run_date = ?', ('20251225',))
cursor.execute('DELETE FROM news_items WHERE run_date = ?', ('20251225',))
cursor.execute('DELETE FROM summaries WHERE run_date = ?', ('20251225',))
cursor.execute('DELETE FROM study_notes WHERE run_date = ?', ('20251225',))
print("✓ 20251225 빈 데이터 삭제 완료")

# 3. 20251223 데이터 정리 (뉴스가 없으므로 전체 재수집)
print("\n[3] 20251223 데이터 정리 (뉴스 재수집 위해)...")
cursor.execute('DELETE FROM study_runs WHERE run_date = ?', ('20251223',))
cursor.execute('DELETE FROM daily_candidates WHERE run_date = ?', ('20251223',))
cursor.execute('DELETE FROM news_items WHERE run_date = ?', ('20251223',))
cursor.execute('DELETE FROM summaries WHERE run_date = ?', ('20251223',))
cursor.execute('DELETE FROM study_notes WHERE run_date = ?', ('20251223',))
print("✓ 20251223 데이터 삭제 완료 (재수집 예정)")

conn.commit()
conn.close()

print("\n" + "=" * 60)
print("✅ 데이터 정리 완료!")
print("=" * 60)
print("\n다음 단계:")
print("1. 12월 23일(월) 데이터 수집")
print("2. 12월 24일(화) 데이터 수집")
print("\n명령어:")
print("python -m hantubot.reporting.study --date 20251223 --force")
print("python -m hantubot.reporting.study --date 20251224 --force")
