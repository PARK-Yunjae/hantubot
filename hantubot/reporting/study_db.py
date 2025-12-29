"""
유목민 공부법 SQLite 데이터베이스 관리 모듈 (Wrapper for hantubot.study.repository)
Backward compatibility layer.
"""
from hantubot.study.repository import StudyDatabase, get_study_db

__all__ = ['StudyDatabase', 'get_study_db']
