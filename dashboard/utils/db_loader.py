# dashboard/utils/db_loader.py
"""
Streamlit 대시보드용 DB 조회 헬퍼
"""
import sys
from pathlib import Path

# hantubot 모듈을 import할 수 있도록 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from hantubot.reporting.study_db import get_study_db


def load_study_data(run_date: str):
    """
    특정 날짜의 스터디 데이터 로드
    
    Args:
        run_date: YYYYMMDD 형식의 날짜
        
    Returns:
        dict: 스터디 데이터
    """
    db = get_study_db()
    return db.get_full_study_data(run_date)


def load_all_run_dates(limit: int = 100):
    """
    모든 run 날짜 조회
    
    Returns:
        list: 날짜 리스트 (YYYYMMDD)
    """
    db = get_study_db()
    return db.get_all_run_dates(limit)


def load_ticker_frequency(days: int = 100):
    """
    종목별 등장 빈도 조회
    
    Returns:
        list: [{'ticker': ..., 'name': ..., 'count': ...}, ...]
    """
    db = get_study_db()
    return db.get_ticker_frequency(days)
