# hantubot_prod/hantubot/providers/news_base.py
"""
뉴스 수집 Provider 추상 베이스 클래스
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime


class NewsProvider(ABC):
    """뉴스 수집 Provider의 추상 베이스 클래스"""
    
    def __init__(self, provider_name: str, max_items_per_ticker: int = 20):
        """
        Args:
            provider_name: Provider 이름 (예: 'naver', 'paid_news')
            max_items_per_ticker: 종목당 최대 수집 뉴스 개수
        """
        self.provider_name = provider_name
        self.max_items_per_ticker = max_items_per_ticker
    
    @abstractmethod
    def fetch_news(self, ticker: str, stock_name: str, 
                   date: Optional[str] = None) -> List[Dict]:
        """
        특정 종목의 뉴스를 수집합니다.
        
        Args:
            ticker: 종목코드
            stock_name: 종목명
            date: 검색 기준 날짜 (YYYYMMDD, None이면 오늘)
            
        Returns:
            뉴스 정보 딕셔너리 리스트
            [
                {
                    'provider': str,
                    'title': str,
                    'url': str,
                    'publisher': str (optional),
                    'published_at': str (optional, ISO format),
                    'snippet': str (optional),
                    'raw_text': str (optional)
                },
                ...
            ]
        """
        pass
    
    def _validate_news_item(self, news_item: Dict) -> bool:
        """
        뉴스 아이템의 필수 필드 검증
        
        Args:
            news_item: 뉴스 정보 딕셔너리
            
        Returns:
            유효성 여부
        """
        required_fields = ['title', 'url']
        return all(field in news_item and news_item[field] for field in required_fields)
    
    def _deduplicate_news(self, news_items: List[Dict]) -> List[Dict]:
        """
        중복 URL 제거
        
        Args:
            news_items: 뉴스 아이템 리스트
            
        Returns:
            중복 제거된 뉴스 아이템 리스트
        """
        seen_urls = set()
        deduplicated = []
        
        for item in news_items:
            url = item.get('url')
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(item)
        
        return deduplicated[:self.max_items_per_ticker]
