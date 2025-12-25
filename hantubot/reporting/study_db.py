# hantubot_prod/hantubot/reporting/study_db.py
"""
유목민 공부법 SQLite 데이터베이스 관리 모듈
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

from .logger import get_logger

logger = get_logger(__name__)


class StudyDatabase:
    """유목민 공부법 데이터를 관리하는 SQLite 데이터베이스 클래스"""
    
    def __init__(self, db_path: str = "data/study.db"):
        """
        Args:
            db_path: 데이터베이스 파일 경로 (기본: data/study.db)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # WAL 모드로 초기화
        self._initialize_database()
        logger.info(f"StudyDatabase initialized at {self.db_path}")
    
    @contextmanager
    def get_connection(self):
        """DB 연결 컨텍스트 매니저 (자동 commit/rollback)"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 딕셔너리처럼 접근 가능
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction failed: {e}")
            raise
        finally:
            conn.close()
    
    def _initialize_database(self):
        """데이터베이스 스키마 생성 및 WAL 모드 활성화"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # WAL 모드 활성화 (읽기/쓰기 동시 수행)
            cursor.execute("PRAGMA journal_mode=WAL")
            
            # 1. study_runs 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL UNIQUE,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    stats_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. daily_candidates 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_candidates (
                    run_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    market TEXT,
                    close_price INTEGER,
                    change_pct REAL,
                    volume INTEGER,
                    value_traded INTEGER,
                    reason_flag TEXT,
                    data_collection_status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_date, ticker)
                )
            """)
            
            # 3. news_items 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    title TEXT NOT NULL,
                    publisher TEXT,
                    published_at TEXT,
                    url TEXT NOT NULL,
                    snippet TEXT,
                    raw_text TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(run_date, ticker, url)
                )
            """)
            
            # 4. summaries 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS summaries (
                    run_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    key_points_json TEXT,
                    keywords_json TEXT,
                    llm_provider TEXT DEFAULT 'gemini',
                    llm_model TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_date, ticker)
                )
            """)
            
            # 5. ticker_notes 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticker_notes (
                    ticker TEXT PRIMARY KEY,
                    note_text TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 인덱스 생성
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_candidates_date 
                ON daily_candidates(run_date)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_news_ticker 
                ON news_items(ticker, run_date)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_summaries_date 
                ON summaries(run_date)
            """)
            
            logger.info("Database schema initialized successfully")
    
    # ==================== Run 관리 ====================
    
    def start_run(self, run_date: str) -> int:
        """
        새로운 스터디 run 시작
        
        Args:
            run_date: YYYYMMDD 형식의 날짜
            
        Returns:
            run_id
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 기존 run 확인
            cursor.execute(
                "SELECT run_id FROM study_runs WHERE run_date = ?",
                (run_date,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # 기존 run 삭제 (재실행)
                logger.warning(f"Deleting existing run for {run_date}")
                self.delete_run(run_date)
            
            # 새 run 생성
            cursor.execute("""
                INSERT INTO study_runs (run_date, started_at, status)
                VALUES (?, ?, 'running')
            """, (run_date, datetime.now().isoformat()))
            
            run_id = cursor.lastrowid
            logger.info(f"Started new study run: {run_date} (run_id={run_id})")
            return run_id
    
    def end_run(self, run_date: str, status: str, error_message: Optional[str] = None,
                stats: Optional[Dict] = None):
        """
        스터디 run 종료
        
        Args:
            run_date: YYYYMMDD 형식의 날짜
            status: 'success' / 'partial' / 'fail'
            error_message: 에러 메시지 (옵션)
            stats: 통계 정보 딕셔너리 (옵션)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE study_runs
                SET ended_at = ?, status = ?, error_message = ?, stats_json = ?
                WHERE run_date = ?
            """, (
                datetime.now().isoformat(),
                status,
                error_message,
                json.dumps(stats) if stats else None,
                run_date
            ))
            logger.info(f"Ended study run: {run_date} with status '{status}'")
    
    def get_run(self, run_date: str) -> Optional[Dict]:
        """특정 날짜의 run 정보 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM study_runs WHERE run_date = ?",
                (run_date,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def delete_run(self, run_date: str):
        """특정 날짜의 모든 데이터 삭제"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM daily_candidates WHERE run_date = ?", (run_date,))
            cursor.execute("DELETE FROM news_items WHERE run_date = ?", (run_date,))
            cursor.execute("DELETE FROM summaries WHERE run_date = ?", (run_date,))
            cursor.execute("DELETE FROM study_runs WHERE run_date = ?", (run_date,))
            logger.info(f"Deleted all data for run_date: {run_date}")
    
    # ==================== Candidates 관리 ====================
    
    def insert_candidates(self, candidates: List[Dict]):
        """
        후보 종목 일괄 삽입
        
        Args:
            candidates: 종목 정보 딕셔너리 리스트
                required keys: run_date, ticker, name
                optional keys: market, close_price, change_pct, volume, 
                              value_traded, reason_flag
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for candidate in candidates:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO daily_candidates 
                        (run_date, ticker, name, market, close_price, change_pct, 
                         volume, value_traded, reason_flag, data_collection_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    """, (
                        candidate['run_date'],
                        candidate['ticker'],
                        candidate['name'],
                        candidate.get('market'),
                        candidate.get('close_price'),
                        candidate.get('change_pct'),
                        candidate.get('volume'),
                        candidate.get('value_traded'),
                        candidate.get('reason_flag')
                    ))
                except Exception as e:
                    logger.error(f"Failed to insert candidate {candidate.get('ticker')}: {e}")
            
            logger.info(f"Inserted {len(candidates)} candidates")
    
    def update_candidate_status(self, run_date: str, ticker: str, status: str):
        """후보 종목의 데이터 수집 상태 업데이트"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE daily_candidates
                SET data_collection_status = ?
                WHERE run_date = ? AND ticker = ?
            """, (status, run_date, ticker))
    
    def get_candidates(self, run_date: str, status: Optional[str] = None) -> List[Dict]:
        """
        특정 날짜의 후보 종목 조회
        
        Args:
            run_date: YYYYMMDD 형식의 날짜
            status: 필터링할 상태 (옵션)
            
        Returns:
            종목 정보 딕셔너리 리스트
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT * FROM daily_candidates
                    WHERE run_date = ? AND data_collection_status = ?
                    ORDER BY change_pct DESC
                """, (run_date, status))
            else:
                cursor.execute("""
                    SELECT * FROM daily_candidates
                    WHERE run_date = ?
                    ORDER BY change_pct DESC
                """, (run_date,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== News 관리 ====================
    
    def insert_news_items(self, news_items: List[Dict]):
        """
        뉴스 아이템 일괄 삽입
        
        Args:
            news_items: 뉴스 정보 딕셔너리 리스트
                required keys: run_date, ticker, provider, title, url
                optional keys: publisher, published_at, snippet, raw_text
        """
        inserted_count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for news in news_items:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO news_items
                        (run_date, ticker, provider, title, publisher, 
                         published_at, url, snippet, raw_text)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        news['run_date'],
                        news['ticker'],
                        news['provider'],
                        news['title'],
                        news.get('publisher'),
                        news.get('published_at'),
                        news['url'],
                        news.get('snippet'),
                        news.get('raw_text')
                    ))
                    if cursor.rowcount > 0:
                        inserted_count += 1
                except Exception as e:
                    logger.error(f"Failed to insert news for {news.get('ticker')}: {e}")
            
            logger.info(f"Inserted {inserted_count} news items (duplicates ignored)")
    
    def get_news_items(self, run_date: str, ticker: Optional[str] = None) -> List[Dict]:
        """
        뉴스 아이템 조회
        
        Args:
            run_date: YYYYMMDD 형식의 날짜
            ticker: 종목코드 (옵션, 없으면 전체)
            
        Returns:
            뉴스 정보 딕셔너리 리스트
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if ticker:
                cursor.execute("""
                    SELECT * FROM news_items
                    WHERE run_date = ? AND ticker = ?
                    ORDER BY published_at DESC
                """, (run_date, ticker))
            else:
                cursor.execute("""
                    SELECT * FROM news_items
                    WHERE run_date = ?
                    ORDER BY ticker, published_at DESC
                """, (run_date,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== Summaries 관리 ====================
    
    def insert_summary(self, summary: Dict):
        """
        LLM 요약 삽입
        
        Args:
            summary: 요약 정보 딕셔너리
                required keys: run_date, ticker, summary_text
                optional keys: key_points_json, keywords_json, llm_provider, llm_model
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO summaries
                (run_date, ticker, summary_text, key_points_json, 
                 keywords_json, llm_provider, llm_model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                summary['run_date'],
                summary['ticker'],
                summary['summary_text'],
                summary.get('key_points_json'),
                summary.get('keywords_json'),
                summary.get('llm_provider', 'gemini'),
                summary.get('llm_model')
            ))
            logger.debug(f"Inserted summary for {summary['ticker']}")
    
    def get_summary(self, run_date: str, ticker: str) -> Optional[Dict]:
        """특정 종목의 요약 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM summaries
                WHERE run_date = ? AND ticker = ?
            """, (run_date, ticker))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def has_summary(self, run_date: str, ticker: str) -> bool:
        """요약 존재 여부 확인 (캐싱용)"""
        return self.get_summary(run_date, ticker) is not None
    
    # ==================== Notes 관리 ====================
    
    def save_note(self, ticker: str, note_text: str):
        """종목 메모 저장"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO ticker_notes (ticker, note_text, updated_at)
                VALUES (?, ?, ?)
            """, (ticker, note_text, datetime.now().isoformat()))
            logger.info(f"Saved note for {ticker}")
    
    def get_note(self, ticker: str) -> Optional[str]:
        """종목 메모 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT note_text FROM ticker_notes WHERE ticker = ?",
                (ticker,)
            )
            row = cursor.fetchone()
            return row['note_text'] if row else None
    
    # ==================== 통합 조회 ====================
    
    def get_full_study_data(self, run_date: str) -> Dict[str, Any]:
        """
        특정 날짜의 모든 스터디 데이터 조회 (대시보드용)
        
        Returns:
            {
                'run_info': {...},
                'candidates': [...],
                'news': {...},  # ticker를 키로 하는 딕셔너리
                'summaries': {...}  # ticker를 키로 하는 딕셔너리
            }
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Run 정보
            cursor.execute("SELECT * FROM study_runs WHERE run_date = ?", (run_date,))
            run_row = cursor.fetchone()
            run_info = dict(run_row) if run_row else None
            
            # 후보 종목
            cursor.execute("""
                SELECT * FROM daily_candidates WHERE run_date = ?
                ORDER BY change_pct DESC
            """, (run_date,))
            candidates = [dict(row) for row in cursor.fetchall()]
            
            # 뉴스 (ticker별로 그룹화)
            cursor.execute("""
                SELECT * FROM news_items WHERE run_date = ?
                ORDER BY ticker, published_at DESC
            """, (run_date,))
            news_rows = cursor.fetchall()
            news_by_ticker = {}
            for row in news_rows:
                ticker = row['ticker']
                if ticker not in news_by_ticker:
                    news_by_ticker[ticker] = []
                news_by_ticker[ticker].append(dict(row))
            
            # 요약 (ticker별로 그룹화)
            cursor.execute("""
                SELECT * FROM summaries WHERE run_date = ?
            """, (run_date,))
            summary_rows = cursor.fetchall()
            summaries_by_ticker = {row['ticker']: dict(row) for row in summary_rows}
            
            return {
                'run_info': run_info,
                'candidates': candidates,
                'news': news_by_ticker,
                'summaries': summaries_by_ticker
            }
    
    def get_all_run_dates(self, limit: int = 100) -> List[str]:
        """모든 run 날짜 조회 (최신순)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT run_date FROM study_runs
                ORDER BY run_date DESC
                LIMIT ?
            """, (limit,))
            return [row['run_date'] for row in cursor.fetchall()]
    
    def get_ticker_frequency(self, days: int = 100) -> List[Dict]:
        """
        종목별 등장 빈도 분석 (최근 N일)
        
        Returns:
            [{'ticker': '...', 'name': '...', 'count': N}, ...]
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticker, name, COUNT(*) as count
                FROM daily_candidates
                WHERE run_date IN (
                    SELECT run_date FROM study_runs
                    ORDER BY run_date DESC
                    LIMIT ?
                )
                GROUP BY ticker
                ORDER BY count DESC
            """, (days,))
            return [dict(row) for row in cursor.fetchall()]


# ==================== 헬퍼 함수 ====================

def get_study_db() -> StudyDatabase:
    """StudyDatabase 싱글톤 인스턴스 반환"""
    import os
    db_path = os.getenv('STUDY_DB_PATH', 'data/study.db')
    return StudyDatabase(db_path)


if __name__ == '__main__':
    # 테스트 코드
    db = StudyDatabase('data/test_study.db')
    
    # Run 시작
    run_id = db.start_run('20250101')
    print(f"Started run: {run_id}")
    
    # 후보 종목 삽입
    candidates = [
        {
            'run_date': '20250101',
            'ticker': '005930',
            'name': '삼성전자',
            'market': 'KOSPI',
            'close_price': 70000,
            'change_pct': 5.2,
            'volume': 15000000,
            'reason_flag': 'volume_10m'
        }
    ]
    db.insert_candidates(candidates)
    
    # Run 종료
    db.end_run('20250101', 'success', stats={'candidates': 1})
    
    # 조회
    data = db.get_full_study_data('20250101')
    print(json.dumps(data, indent=2, ensure_ascii=False))
