# hantubot_prod/hantubot/providers/naver_news.py
"""
Naver 뉴스 수집 Provider - 공식 API 버전
"""
import os
import time
import requests
from typing import List, Dict, Optional
from datetime import datetime
import html

from .news_base import NewsProvider


class NaverNewsProvider(NewsProvider):
    """Naver 검색 API를 사용한 뉴스 수집 Provider"""
    
    def __init__(self, max_items_per_ticker: int = 20):
        super().__init__('naver', max_items_per_ticker)
        
        # 환경변수에서 API 키 로드
        self.client_id = os.getenv('NaverAPI_Client_ID')
        self.client_secret = os.getenv('NaverAPI_Client_Secret')
        
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "네이버 API 키가 설정되지 않았습니다. "
                ".env 파일에 NaverAPI_Client_ID와 NaverAPI_Client_Secret를 설정하세요."
            )
        
        self.api_url = "https://openapi.naver.com/v1/search/news.json"
    
    def fetch_news(self, ticker: str, stock_name: str, 
                   date: Optional[str] = None) -> List[Dict]:
        """
        Naver 검색 API로 종목 관련 뉴스 수집
        
        Args:
            ticker: 종목코드
            stock_name: 종목명
            date: 검색 기준 날짜 (YYYYMMDD) - API에서는 정렬 순서만 제공
            
        Returns:
            뉴스 정보 딕셔너리 리스트
        """
        news_items = []
        
        try:
            # 검색어 조합 (종목명 중심)
            keywords = [
                f"{stock_name}",
                f"{stock_name} 주가",
                f"{stock_name} 급등",
            ]
            
            # 중복 제거를 위한 URL 세트
            seen_urls = set()
            
            for keyword in keywords:
                items = self._search_news_api(keyword)
                
                # 중복 제거하면서 추가
                for item in items:
                    url = item.get('url', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        news_items.append(item)
                
                # Rate limiting (네이버 API 권장)
                time.sleep(0.1)
                
                # 충분한 뉴스를 수집했으면 중단
                if len(news_items) >= self.max_items_per_ticker:
                    break
            
            # 최대 개수 제한
            news_items = news_items[:self.max_items_per_ticker]
            
            # Provider 정보 추가
            for item in news_items:
                item['provider'] = self.provider_name
            
            return news_items
        
        except Exception as e:
            # 실패해도 빈 리스트 반환 (실패 내성)
            print(f"Naver API news fetch failed for {stock_name}: {e}")
            return []
    
    def _search_news_api(self, keyword: str, display: int = 10) -> List[Dict]:
        """
        Naver 검색 API 호출 (공식)
        
        Args:
            keyword: 검색 키워드
            display: 검색 결과 개수 (최대 100)
            
        Returns:
            뉴스 아이템 리스트
        """
        news_items = []
        
        try:
            # API 요청 헤더
            headers = {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret
            }
            
            # API 요청 파라미터
            params = {
                "query": keyword,
                "display": min(display, 100),  # 최대 100개
                "sort": "date"  # 최신순 (또는 "sim" - 정확도순)
            }
            
            # API 호출
            response = requests.get(
                self.api_url,
                headers=headers,
                params=params,
                timeout=10
            )
            
            # 상태 코드 확인
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                # 데이터 변환 (API 응답 → 내부 형식)
                for item in items:
                    try:
                        # HTML 태그 제거 (<b>, </b> 등)
                        title = self._clean_html(item.get('title', ''))
                        description = self._clean_html(item.get('description', ''))
                        
                        # 뉴스 아이템 구성
                        news_item = {
                            'title': title,
                            'url': item.get('link', ''),
                            'publisher': item.get('originallink', '').split('/')[2] if item.get('originallink') else 'Naver',
                            'published_at': item.get('pubDate', ''),
                            'snippet': description
                        }
                        
                        # 유효성 검사
                        if self._validate_news_item(news_item):
                            news_items.append(news_item)
                    
                    except Exception as e:
                        # 개별 뉴스 파싱 실패는 무시
                        print(f"뉴스 파싱 실패: {e}")
                        continue
            
            elif response.status_code == 429:
                print(f"⚠️ API 호출 제한 초과 (429) - 잠시 대기 필요")
            else:
                print(f"⚠️ API 호출 실패 ({response.status_code}): {response.text}")
        
        except requests.exceptions.Timeout:
            print(f"⏱️ API 호출 타임아웃: {keyword}")
        except Exception as e:
            print(f"❌ Naver API 검색 실패 '{keyword}': {e}")
        
        return news_items
    
    def _clean_html(self, text: str) -> str:
        """
        HTML 태그 및 엔티티 제거
        
        Args:
            text: 원본 텍스트
            
        Returns:
            정제된 텍스트
        """
        # HTML 태그 제거
        text = text.replace('<b>', '').replace('</b>', '')
        text = text.replace('<strong>', '').replace('</strong>', '')
        
        # HTML 엔티티 디코딩 (&quot; → ", &amp; → & 등)
        text = html.unescape(text)
        
        return text.strip()
    
    def fetch_news_detail(self, url: str) -> Optional[str]:
        """
        뉴스 상세 페이지에서 본문 추출 (옵션)
        
        ⚠️ 참고: 네이버 검색 API는 본문을 제공하지 않으므로,
        상세 본문이 필요하면 별도로 크롤링해야 합니다.
        (하지만 이는 불안정하므로 description으로 충분)
        
        Args:
            url: 뉴스 URL
            
        Returns:
            본문 텍스트 (미구현 - None 반환)
        """
        # 네이버 API의 description이 충분히 길므로 별도 본문 크롤링은 불필요
        return None


# ==================== 테스트 코드 ====================

if __name__ == '__main__':
    from pathlib import Path
    from dotenv import load_dotenv
    
    # .env 파일 로드
    env_path = Path(__file__).parent.parent.parent / 'configs' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ .env 파일 로드: {env_path}\n")
    else:
        print(f"⚠️ .env 파일을 찾을 수 없습니다: {env_path}\n")
    
    # Provider 생성
    try:
        provider = NaverNewsProvider(max_items_per_ticker=5)
        print("✅ NaverNewsProvider 초기화 성공\n")
        
        # 삼성전자 뉴스 검색 테스트
        print("=" * 60)
        print("테스트: 삼성전자 뉴스 검색")
        print("=" * 60)
        
        news = provider.fetch_news('005930', '삼성전자')
        
        print(f"\n📰 총 {len(news)}개 뉴스 발견:\n")
        
        for i, item in enumerate(news, 1):
            print(f"{i}. {item['title']}")
            print(f"   출처: {item['publisher']}")
            print(f"   URL: {item['url'][:60]}...")
            print(f"   날짜: {item['published_at']}")
            if item.get('snippet'):
                snippet = item['snippet'][:80]
                print(f"   요약: {snippet}...")
            print()
        
        print("=" * 60)
        print("✅ 테스트 완료!")
        print("=" * 60)
    
    except ValueError as e:
        print(f"❌ 초기화 실패: {e}")
        print("\n💡 .env 파일에 다음 항목을 추가하세요:")
        print("   NaverAPI_Client_ID = \"your_client_id\"")
        print("   NaverAPI_Client_Secret = \"your_client_secret\"")
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
