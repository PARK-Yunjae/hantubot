# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect('data/study.db')
cursor = conn.cursor()

print("\n=== 최근 실행 기록 ===")
cursor.execute('SELECT run_date, status, created_at FROM study_runs ORDER BY run_date DESC LIMIT 10')
for row in cursor.fetchall():
    print(f'{row[0]} | {row[1]} | {row[2]}')

print("\n=== 후보 종목 수 (날짜별) ===")
cursor.execute('SELECT run_date, COUNT(*) FROM daily_candidates GROUP BY run_date ORDER BY run_date DESC LIMIT 10')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]}개 종목')

print("\n=== 뉴스 수 (날짜별) ===")
cursor.execute('SELECT run_date, COUNT(*) FROM news_items GROUP BY run_date ORDER BY run_date DESC LIMIT 10')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]}개 뉴스')

print("\n=== 요약 수 (날짜별) ===")
cursor.execute('SELECT run_date, COUNT(*) FROM summaries GROUP BY run_date ORDER BY run_date DESC LIMIT 10')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]}개 요약')

conn.close()
