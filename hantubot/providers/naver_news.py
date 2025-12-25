# hantubot_prod/hantubot/providers/naver_news.py
"""
Naver 뉴스 수집 Provider
"""
import time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from urllib.parse import quote

from .news_base import NewsProvider


class NaverNewsProvider(NewsProvider):
    """Naver 뉴스 검색 및 수집 Provider"""
    
    def __init__(self, max_items_per_ticker: int = 20):
        super().__init__('naver', max_items_per_ticker)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.base_search_url = 'https://search.naver.com/search.naver'
    
    def fetch_news(self, ticker: str, stock_name: str, 
                   date: Optional[str] = None) -> List[Dict]:
        """
        Naver 뉴스 검색으로 종목 관련 뉴스 수집
        
        Args:
            ticker: 종목코드
            stock_name: 종목명
            date: 검색 기준 날짜 (YYYYMMDD)
            
        Returns:
            뉴스 정보 딕셔너리 리스트
        """
        news_items = []
        
        try:
            # 검색어: 종목명 + 주가/상승/상한가 등 키워드
            keywords = [
                f"{stock_name}",
                f"{stock_name} 주가",
                f"{stock_name} 상승",
            ]
            
            for keyword in keywords:
                items = self._search_news(keyword, date)
                news_items.extend(items)
                
                # Rate limiting
                time.sleep(0.5)
            
            # 중복 제거 및 최대 개수 제한
            news_items = self._deduplicate_news(news_items)
            
            # Provider 정보 추가
            for item in news_items:
                item['provider'] = self.provider_name
            
            return news_items
        
        except Exception as e:
            # 실패해도 빈 리스트 반환 (실패 내성)
            print(f"Naver news fetch failed for {stock_name}: {e}")
            return []
    
    def _search_news(self, keyword: str, date: Optional[str] = None) -> List[Dict]:
        """
        Naver 뉴스 검색 API 호출
        
        Args:
            keyword: 검색 키워드
            date: 검색 기준 날짜 (YYYYMMDD)
            
        Returns:
            뉴스 아이템 리스트
        """
        news_items = []
        
        try:
            # 날짜 필터 (최근 1개월로 확장 - 백일공부용)
            if date:
                target_date = datetime.strptime(date, '%Y%m%d')
            else:
                target_date = datetime.now()
            
            start_date = (target_date - timedelta(days=30)).strftime('%Y.%m.%d')
            end_date = target_date.strftime('%Y.%m.%d')
            
            # Naver 뉴스 검색 URL (모바일 버전이 더 파싱하기 쉬움)
            params = {
                'where': 'news',
                'query': keyword,
                'sm': 'tab_opt',
                'sort': '1',  # 최신순
                'photo': '0',
                'field': '0',
                'pd': '3',  # 기간 설정
                'ds': start_date,
                'de': end_date,
                'start': '1',
                'refresh_start': '0'
            }
            
            response = requests.get(
                self.base_search_url,
                params=params,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            # HTML 파싱
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 뉴스 항목 추출
            news_area = soup.find('ul', {'class': 'list_news'})
            
            if news_area:
                items = news_area.find_all('li', limit=10)
                
                for item in items:
                    try:
                        # 제목 및 링크
                        title_tag = item.find('a', {'class': 'news_tit'})
                        if not title_tag:
                            continue
                        
                        title = title_tag.get('title', title_tag.text.strip())
                        url = title_tag.get('href', '')
                        
                        # 발행처
                        publisher_tag = item.find('a', {'class': 'info press'})
                        publisher = publisher_tag.text.strip() if publisher_tag else ''
                        
                        # 본문 미리보기
                        snippet_tag = item.find('div', {'class': 'news_dsc'})
                        snippet = snippet_tag.text.strip() if snippet_tag else ''
                        
                        # 발행 시간
                        time_tag = item.find('span', {'class': 'info'})
                        published_at = time_tag.text.strip() if time_tag else ''
                        
                        # 유효성 검사
                        news_item = {
                            'title': title,
                            'url': url,
                            'publisher': publisher,
                            'published_at': published_at,
                            'snippet': snippet
                        }
                        
                        if self._validate_news_item(news_item):
                            news_items.append(news_item)
                    
                    except Exception as e:
                        # 개별 뉴스 파싱 실패는 무시
                        continue
        
        except Exception as e:
            print(f"Naver news search failed for '{keyword}': {e}")
        
        return news_items
    
    def fetch_news_detail(self, url: str) -> Optional[str]:
        """
        뉴스 상세 페이지에서 본문 추출 (옵션)
        
        Args:
            url: 뉴스 URL
            
        Returns:
            본문 텍스트 (실패 시 None)
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Naver 뉴스 본문 영역 (여러 패턴 시도)
            article_body = None
            
            # 패턴 1: 네이버 뉴스 본문
            article_body = soup.find('article', {'id': 'dic_area'})
            
            # 패턴 2: 일반 뉴스 본문
            if not article_body:
                article_body = soup.find('div', {'class': 'article_body'})
            
            # 패턴 3: 기타
            if not article_body:
                article_body = soup.find('div', {'id': 'articleBodyContents'})
            
            if article_body:
                # 불필요한 태그 제거
                for tag in article_body.find_all(['script', 'style', 'iframe']):
                    tag.decompose()
                
                return article_body.get_text(strip=True, separator='\n')
            
            return None
        
        except Exception as e:
            print(f"Failed to fetch news detail from {url}: {e}")
            return None


# 테스트 코드
if __name__ == '__main__':
    provider = NaverNewsProvider(max_items_per_ticker=5)
    
    # 삼성전자 뉴스 검색
    news = provider.fetch_news('005930', '삼성전자', '20250101')
    
    print(f"Found {len(news)} news items:")
    for item in news:
        print(f"- {item['title']}")
        print(f"  {item['url']}")
        print(f"  발행: {item['publisher']} | {item['published_at']}")
        print()
