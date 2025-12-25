# hantubot_prod/hantubot/providers/__init__.py
"""
뉴스/재료 수집 Provider 모듈
"""

from .news_base import NewsProvider
from .naver_news import NaverNewsProvider

__all__ = ['NewsProvider', 'NaverNewsProvider']
