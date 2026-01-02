"""
시장 데이터 및 뉴스 수집 모듈
"""
import time
import json
import requests
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from pykrx import stock

from hantubot.reporting.logger import get_logger
from hantubot.utils.stock_filters import is_eligible_stock
from hantubot.providers import NaverNewsProvider
from hantubot.study.repository import StudyDatabase

logger = get_logger(__name__)


def collect_market_data(run_date: str, db: StudyDatabase) -> List[Dict]:
    """
    시장 데이터 수집 및 후보 종목 필터링
    
    Returns:
        후보 종목 리스트
    """
    candidates = []
    
    try:
        # pykrx로 전체 종목 조회
        try:
            df_all = stock.get_market_ohlcv_by_ticker(run_date, market="ALL")
        except (requests.exceptions.JSONDecodeError, json.JSONDecodeError):
            logger.warning("KRX 서버로부터 유효한 데이터를 받지 못했습니다. (JSON Decode Error) - 공부 단계를 건너뜁니다.")
            return candidates

        if df_all.empty:
            logger.warning("No market data available for today")
            return candidates
        
        # 필터: 거래량 천만주 OR 상한가(29%+)
        volume_filter = df_all['거래량'] >= 10_000_000
        price_ceil_filter = df_all['등락률'] >= 29.0
        interesting_df = df_all[volume_filter | price_ceil_filter]
        
        if interesting_df.empty:
            logger.info("No stocks met the criteria")
            return candidates
        
        # ETF, 스팩 등 제외
        unfiltered_tickers = interesting_df.index.tolist()
        eligible_tickers = [
            ticker for ticker in unfiltered_tickers
            if is_eligible_stock(stock.get_market_ticker_name(ticker))
        ]
        
        if not eligible_tickers:
            logger.info("No eligible stocks after filtering")
            return candidates
        
        # 거래대금 조회 (옵션)
        try:
            df_trading_value = stock.get_market_trading_value_by_ticker(run_date, market="ALL")
        except:
            df_trading_value = None
        
        # 후보 종목 정보 구성
        for ticker in eligible_tickers:
            try:
                stock_info = interesting_df.loc[ticker]
                stock_name = stock.get_market_ticker_name(ticker)
                
                # 시장 구분 (KOSPI/KOSDAQ)
                market = stock.get_market_ticker_list(run_date, market="KOSPI")
                market_type = "KOSPI" if ticker in market else "KOSDAQ"
                
                # 선정 사유
                reasons = []
                if stock_info['등락률'] >= 29.0:
                    reasons.append('limit_up')
                if stock_info['거래량'] >= 10_000_000:
                    reasons.append('volume_10m')
                reason_flag = ' / '.join(reasons) if reasons else 'both'
                
                # 거래대금
                value_traded = None
                if df_trading_value is not None and ticker in df_trading_value.index:
                    value_traded = int(df_trading_value.loc[ticker, '거래대금'])
                
                candidate = {
                    'run_date': run_date,
                    'ticker': ticker,
                    'name': stock_name,
                    'market': market_type,
                    'close_price': int(stock_info['종가']),
                    'change_pct': float(stock_info['등락률']),
                    'volume': int(stock_info['거래량']),
                    'value_traded': value_traded,
                    'reason_flag': reason_flag
                }
                
                candidates.append(candidate)
            
            except Exception as e:
                logger.error(f"Failed to process ticker {ticker}: {e}")
                continue
        
        # DB에 일괄 저장
        if candidates:
            db.insert_candidates(candidates)
            logger.info(f"Inserted {len(candidates)} candidates into database")
    
    except Exception as e:
        logger.error(f"Market data collection failed: {e}", exc_info=True)
        raise  # 시장 데이터 실패는 전체 run 중단
    
    return candidates


def collect_news_for_candidates(run_date: str, candidates: List[Dict], 
                                 db: StudyDatabase) -> Dict:
    """
    후보 종목들의 뉴스 수집 (병렬 처리로 3배 빠름)
    
    Returns:
        {'total_news': int, 'failed_tickers': int, 'errors': []}
    """
    
    news_provider = NaverNewsProvider(max_items_per_ticker=20)
    
    total_news = 0
    failed_tickers = 0
    errors = []
    
    def fetch_single_news(candidate):
        """단일 종목 뉴스 수집 (스레드 내에서 실행)"""
        ticker = candidate['ticker']
        stock_name = candidate['name']
        
        try:
            logger.info(f"뉴스 수집 중: {stock_name} ({ticker})")
            
            # 뉴스 수집
            news_items = news_provider.fetch_news(ticker, stock_name, run_date)
            
            if news_items:
                # run_date 및 ticker 추가
                for item in news_items:
                    item['run_date'] = run_date
                    item['ticker'] = ticker
                
                return {
                    'success': True,
                    'ticker': ticker,
                    'news_items': news_items,
                    'count': len(news_items)
                }
            else:
                return {
                    'success': True,
                    'ticker': ticker,
                    'news_items': [],
                    'count': 0
                }
        
        except Exception as e:
            logger.error(f"뉴스 수집 실패: {ticker} - {e}")
            return {
                'success': False,
                'ticker': ticker,
                'error': str(e)
            }
    
    # 병렬 처리 (최대 5개 스레드 동시 실행)
    with ThreadPoolExecutor(max_workers=5) as executor:
        # 모든 종목에 대해 비동기 작업 제출
        future_to_candidate = {
            executor.submit(fetch_single_news, candidate): candidate 
            for candidate in candidates
        }
        
        # 완료된 작업부터 순서대로 처리
        for future in as_completed(future_to_candidate):
            result = future.result()
            
            if result['success']:
                ticker = result['ticker']
                news_items = result.get('news_items', [])
                
                if news_items:
                    # DB 저장 (메인 스레드에서 안전하게)
                    db.insert_news_items(news_items)
                    total_news += result['count']
                    db.update_candidate_status(run_date, ticker, 'news_collected')
                    logger.debug(f"✓ {ticker}: {result['count']}개 뉴스 수집")
                else:
                    logger.warning(f"✗ {ticker}: 뉴스 없음")
                    db.update_candidate_status(run_date, ticker, 'no_news')
            else:
                ticker = result['ticker']
                db.update_candidate_status(run_date, ticker, 'news_failed')
                failed_tickers += 1
                errors.append(f"News collection failed for {ticker}: {result.get('error', 'Unknown')}")
            
            # Rate limiting (전체적으로)
            time.sleep(0.1)
    
    return {
        'total_news': total_news,
        'failed_tickers': failed_tickers,
        'errors': errors
    }
