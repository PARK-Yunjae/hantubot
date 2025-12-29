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
            # 검색어 조합 (기업 분석 중심 - 급등/급락 제거)
            keywords = [
                f"{stock_name}",           # 기본
                f"{stock_name} 실적",      # 실적 정보
                f"{stock_name} 신제품",    # 제품 출시
                f"{stock_name} 계약",      # 수주/계약
                f"{stock_name} 투자",      # 투자 유치
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
                
                # Rate limiting (네이버 API 권장) - 충분한 대기 시간 확보
                time.sleep(0.5)
                
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
        Naver 검색 API 호출 (공식) - 재시도 로직 포함
        
        Args:
            keyword: 검색 키워드
            display: 검색 결과 개수 (최대 100)
            
        Returns:
            뉴스 아이템 리스트
        """
        news_items = []
        max_retries = 3
        
        for attempt in range(max_retries):
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
                                'published_at': self._format_date_korean(item.get('pubDate', '')),
                                'snippet': description
                            }
                            
                            # 유효성 검사 + 저품질 필터링
                            if self._validate_news_item(news_item) and self._is_quality_news(news_item):
                                news_items.append(news_item)
                        
                        except Exception as e:
                            # 개별 뉴스 파싱 실패는 무시
                            # print(f"뉴스 파싱 실패: {e}") # 너무 시끄러워서 주석 처리
                            continue
                    
                    # 성공하면 루프 탈출
                    break
                
                elif response.status_code == 429:
                    # Rate Limit 걸리면 대기 후 재시도
                    wait_time = 2.0 * (attempt + 1)
                    if attempt < max_retries - 1:
                        # print(f"⚠️ API 호출 제한 (429) - {wait_time}초 대기 후 재시도 ({attempt+1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"⚠️ API 호출 제한 초과 (429) - 최대 재시도 횟수 도달. 건너뜀.")
                else:
                    print(f"⚠️ API 호출 실패 ({response.status_code}): {response.text}")
                    break
            
            except requests.exceptions.Timeout:
                print(f"⏱️ API 호출 타임아웃: {keyword}")
                break
            except Exception as e:
                print(f"❌ Naver API 검색 실패 '{keyword}': {e}")
                break
        
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
        
        # HTML 엔티티 디코딩 (" → ", & → & 등)
        text = html.unescape(text)
        
        return text.strip()
    
    def _format_date_korean(self, date_str: str) -> str:
        """
        영어 날짜를 한국식으로 변환
        
        Args:
            date_str: RFC 822 형식 날짜 (예: "Mon, 25 Dec 2024 14:30:00 +0900")
            
        Returns:
            한국식 날짜 (예: "2024년 12월 25일 14:30")
        """
        if not date_str:
            return ""
        
        try:
            from datetime import datetime
            
            # RFC 822 형식 파싱
            dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
            
            # 한국식으로 포맷팅
            return dt.strftime("%Y년 %m월 %d일 %H:%M")
        
        except Exception as e:
            # 파싱 실패 시 원본 반환
            return date_str
    
    def _is_quality_news(self, news_item: Dict) -> bool:
        """
        저품질 뉴스 필터링
        
        주가 변동만 다루는 기사나 테마주 뉴스 등 학습 가치가 낮은 뉴스 제외
        
        Args:
            news_item: 뉴스 아이템
            
        Returns:
            품질이 좋으면 True, 나쁘면 False
        """
        title = news_item.get('title', '')
        
        # 제외할 키워드 (주가 변동 중심 뉴스)
        exclude_keywords = [
            '급등', '급락', '폭등', '폭락',
            '상한가', '하한가',
            '마감', '시초가', '장중',
            '테마주', '관심주',
            '보유', '매수', '매도', '추천',
        ]
        
        # 제목에 제외 키워드가 있으면 거부
        for keyword in exclude_keywords:
            if keyword in title:
                return False
        
        # 기본적으로 허용 (너무 많이 거르지 않기)
        return True
    
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
