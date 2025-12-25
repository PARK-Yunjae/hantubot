# hantubot_prod/hantubot/reporting/study.py
"""
유목민 공부법 (100일 공부) - SQLite + 뉴스 수집 + LLM 요약 통합 버전
"""
import os
import time
import json
from datetime import datetime
from typing import List, Dict, Optional

from pykrx import stock
import google.generativeai as genai

from .logger import get_logger
from .study_db import get_study_db, StudyDatabase
from ..utils.stock_filters import is_eligible_stock
from ..providers import NaverNewsProvider

logger = get_logger(__name__)


def run_daily_study(broker, notifier, force_run=False):
    """
    유목민 공부법 메인 함수 - SQLite 기반 데이터 수집 및 분석
    
    Args:
        broker: 브로커 인스턴스 (미사용, 시그니처 호환성 유지)
        notifier: 알림 인스턴스
        force_run: True면 중복 체크 무시하고 강제 실행
    """
    logger.info("=" * 80)
    logger.info("유목민 공부법 (100일 공부) 시작 - SQLite + 뉴스 수집 버전")
    logger.info("=" * 80)
    
    # 환경 변수 확인
    study_mode = os.getenv('STUDY_MODE', 'sqlite')  # sqlite / gsheet / both
    
    # 날짜 설정
    today_str = datetime.now().strftime("%Y%m%d")
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # DB 초기화
    try:
        db = get_study_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        notifier.send_alert(f"❌ 유목민 공부법 DB 초기화 실패: {e}", level='error')
        return
    
    # 1. 중복 실행 체크
    if not force_run:
        existing_run = db.get_run(today_str)
        if existing_run and existing_run['status'] in ['success', 'partial']:
            logger.info(f"Today's study for {today_str} already completed. Skipping.")
            return
    
    # 2. Run 시작
    try:
        run_id = db.start_run(today_str)
        logger.info(f"Started new study run: {today_str} (run_id={run_id})")
    except Exception as e:
        logger.error(f"Failed to start run: {e}", exc_info=True)
        notifier.send_alert(f"❌ 유목민 공부법 시작 실패: {e}", level='error')
        return
    
    stats = {
        'candidates': 0,
        'news_collected': 0,
        'summaries_generated': 0,
        'errors': []
    }
    
    try:
        # ========== 단계 1: 시장 데이터 수집 ==========
        logger.info("[1/4] 시장 데이터 수집 중...")
        candidates = collect_market_data(today_str, db)
        stats['candidates'] = len(candidates)
        
        if not candidates:
            logger.info("No candidates found for today. Ending run.")
            db.end_run(today_str, 'success', stats=stats)
            return
        
        logger.info(f"✅ {len(candidates)}개 후보 종목 발견 및 DB 저장 완료")
        
        # ========== 단계 2: 뉴스 수집 ==========
        logger.info("[2/4] 뉴스 수집 중...")
        news_stats = collect_news_for_candidates(today_str, candidates, db)
        stats['news_collected'] = news_stats['total_news']
        stats['errors'].extend(news_stats['errors'])
        
        logger.info(f"✅ {news_stats['total_news']}개 뉴스 수집 완료 ({news_stats['failed_tickers']}개 종목 실패)")
        
        # ========== 단계 3: LLM 요약 생성 ==========
        logger.info("[3/4] LLM 요약 생성 중...")
        summary_stats = generate_summaries(today_str, candidates, db)
        stats['summaries_generated'] = summary_stats['success_count']
        stats['errors'].extend(summary_stats['errors'])
        
        logger.info(f"✅ {summary_stats['success_count']}개 요약 생성 완료 ({summary_stats['failed_count']}개 실패)")
        
        # ========== 단계 4: Google Sheets 백업 (옵션) ==========
        if study_mode in ['gsheet', 'both']:
            logger.info("[4/4] Google Sheets 백업 중...")
            try:
                backup_to_gsheet(today_str, db, notifier)
                logger.info("✅ Google Sheets 백업 완료")
            except Exception as e:
                logger.warning(f"Google Sheets 백업 실패 (무시됨): {e}")
                stats['errors'].append(f"GSheet backup failed: {e}")
        else:
            logger.info("[4/4] Google Sheets 백업 건너뜀 (STUDY_MODE={study_mode})")
        
        # Run 성공 종료
        final_status = 'success' if not stats['errors'] else 'partial'
        db.end_run(today_str, final_status, stats=stats)
        
        # 완료 알림
        send_completion_notification(today_str, stats, notifier, db)
        
        logger.info("=" * 80)
        logger.info(f"유목민 공부법 완료: {final_status}")
        logger.info("=" * 80)
    
    except Exception as e:
        logger.error(f"유목민 공부법 실행 중 치명적 오류: {e}", exc_info=True)
        db.end_run(today_str, 'fail', error_message=str(e), stats=stats)
        notifier.send_alert(f"❌ 유목민 공부법 실패: {e}", level='error')


# ==================== 단계별 함수 ====================

def collect_market_data(run_date: str, db: StudyDatabase) -> List[Dict]:
    """
    시장 데이터 수집 및 후보 종목 필터링
    
    Returns:
        후보 종목 리스트
    """
    candidates = []
    
    try:
        # pykrx로 전체 종목 조회
        df_all = stock.get_market_ohlcv_by_ticker(run_date, market="ALL")
        
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
    후보 종목들의 뉴스 수집
    
    Returns:
        {'total_news': int, 'failed_tickers': int, 'errors': []}
    """
    news_provider = NaverNewsProvider(max_items_per_ticker=20)
    
    total_news = 0
    failed_tickers = 0
    errors = []
    
    for candidate in candidates:
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
                
                # DB 저장
                db.insert_news_items(news_items)
                total_news += len(news_items)
                
                # 상태 업데이트
                db.update_candidate_status(run_date, ticker, 'news_collected')
                logger.debug(f"✓ {ticker}: {len(news_items)}개 뉴스 수집")
            else:
                logger.warning(f"✗ {ticker}: 뉴스 없음")
                db.update_candidate_status(run_date, ticker, 'no_news')
            
            # Rate limiting
            time.sleep(0.3)
        
        except Exception as e:
            logger.error(f"뉴스 수집 실패: {ticker} - {e}")
            db.update_candidate_status(run_date, ticker, 'news_failed')
            failed_tickers += 1
            errors.append(f"News collection failed for {ticker}: {e}")
    
    return {
        'total_news': total_news,
        'failed_tickers': failed_tickers,
        'errors': errors
    }


def generate_summaries(run_date: str, candidates: List[Dict], 
                      db: StudyDatabase) -> Dict:
    """
    LLM으로 종목 요약 생성 (배치 처리)
    
    Returns:
        {'success_count': int, 'failed_count': int, 'errors': []}
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.warning("GEMINI_API_KEY not found. Skipping summaries.")
        return {'success_count': 0, 'failed_count': 0, 'errors': ['No API key']}
    
    success_count = 0
    failed_count = 0
    errors = []
    
    # 요약이 필요한 종목만 필터링 (캐싱)
    stocks_to_summarize = []
    for candidate in candidates:
        ticker = candidate['ticker']
        
        # 이미 요약이 있는지 확인
        if db.has_summary(run_date, ticker):
            logger.debug(f"Summary already exists for {ticker}, skipping")
            continue
        
        stocks_to_summarize.append({
            'ticker': ticker,
            'name': candidate['name']
        })
    
    if not stocks_to_summarize:
        logger.info("No new summaries needed (all cached)")
        return {'success_count': 0, 'failed_count': 0, 'errors': []}
    
    # Gemini API 설정
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # 배치 크기 설정
        batch_size = int(os.getenv('LLM_BATCH_SIZE', '10'))
        
        # 배치 단위로 처리
        for i in range(0, len(stocks_to_summarize), batch_size):
            batch = stocks_to_summarize[i:i + batch_size]
            
            logger.info(f"배치 요약 생성 중 ({i+1}-{i+len(batch)}/{len(stocks_to_summarize)})")
            
            try:
                summaries = get_batch_summaries_gemini(batch, model, run_date, db)
                
                for ticker, summary_data in summaries.items():
                    if summary_data['success']:
                        success_count += 1
                        db.update_candidate_status(run_date, ticker, 'summarized')
                    else:
                        failed_count += 1
                        errors.append(f"Summary failed for {ticker}")
                
                # Rate limiting
                time.sleep(2)
            
            except Exception as e:
                logger.error(f"Batch summary failed: {e}")
                failed_count += len(batch)
                errors.append(f"Batch summary error: {e}")
    
    except Exception as e:
        logger.error(f"Gemini API setup failed: {e}", exc_info=True)
        errors.append(f"Gemini setup failed: {e}")
    
    return {
        'success_count': success_count,
        'failed_count': failed_count,
        'errors': errors
    }


def get_batch_summaries_gemini(stocks: List[Dict], model, run_date: str, 
                               db: StudyDatabase) -> Dict:
    """
    Gemini API로 배치 요약 생성
    
    Returns:
        {ticker: {'success': bool, 'summary': str}, ...}
    """
    results = {}
    
    try:
        # 프롬프트 구성
        stock_list_str = "\n".join([f"- {s['name']} ({s['ticker']})" for s in stocks])
        
        prompt = (
            "아래 주식 종목들에 대해, 각각을 **한국어로 3~5문장**으로 요약해줘.\n"
            "각 종목마다:\n"
            "1) 핵심 사업 분야\n"
            "2) 최근 주가 상승/주목받는 이유 (있다면)\n"
            "3) 주요 고객사 또는 경쟁력\n\n"
            "결과는 **반드시 아래 JSON 형식**으로만 응답해줘:\n"
            "```json\n"
            "{\n"
            '  "종목코드": "요약 내용 (줄바꿈 포함)",\n'
            "  ...\n"
            "}\n"
            "```\n\n"
            f"요약할 종목:\n{stock_list_str}"
        )
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # JSON 파싱
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            json_text = response_text[start_idx:end_idx+1]
            json_response = json.loads(json_text)
            
            # DB에 저장
            for ticker, summary_text in json_response.items():
                try:
                    db.insert_summary({
                        'run_date': run_date,
                        'ticker': ticker,
                        'summary_text': summary_text,
                        'llm_provider': 'gemini',
                        'llm_model': 'gemini-2.0-flash-exp'
                    })
                    
                    results[ticker] = {'success': True, 'summary': summary_text}
                
                except Exception as e:
                    logger.error(f"Failed to save summary for {ticker}: {e}")
                    results[ticker] = {'success': False}
        else:
            logger.warning("Gemini 응답에서 JSON을 찾을 수 없습니다")
            for stock in stocks:
                results[stock['ticker']] = {'success': False}
    
    except Exception as e:
        logger.error(f"Batch summary generation failed: {e}", exc_info=True)
        for stock in stocks:
            results[stock['ticker']] = {'success': False}
    
    return results


def backup_to_gsheet(run_date: str, db: StudyDatabase, notifier):
    """Google Sheets 백업 (옵션)"""
    try:
        from .study_legacy import get_gsheet_client, get_worksheet_or_create
        from gspread_dataframe import set_with_dataframe
        import pandas as pd
        
        # 데이터 조회
        data = db.get_full_study_data(run_date)
        candidates = data['candidates']
        summaries = data['summaries']
        
        if not candidates:
            return
        
        # DataFrame 구성
        records = []
        for candidate in candidates:
            ticker = candidate['ticker']
            summary = summaries.get(ticker, {})
            
            records.append({
                '날짜': run_date,
                '종목코드': ticker,
                '종목명': candidate['name'],
                '선정사유': candidate['reason_flag'],
                '종가': f"{candidate['close_price']:,}",
                '등락률': f"{candidate['change_pct']:.2f}%",
                '거래량': f"{candidate['volume']:,}",
                '기업개요': summary.get('summary_text', '요약 없음')
            })
        
        # Google Sheets 업데이트
        gsheet_client = get_gsheet_client()
        spreadsheet = gsheet_client.open("시장 관심주 추적")
        log_ws = get_worksheet_or_create(spreadsheet, "DailyLog")
        
        # 기존 데이터와 병합
        existing_df = pd.DataFrame(log_ws.get_all_records())
        new_df = pd.DataFrame(records).astype(str)
        
        if not existing_df.empty:
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        
        set_with_dataframe(log_ws, combined_df, include_index=False, resize=True)
        logger.info(f"Backed up {len(records)} records to Google Sheets")
    
    except Exception as e:
        raise Exception(f"GSheet backup failed: {e}")


def send_completion_notification(run_date: str, stats: Dict, notifier, db: StudyDatabase):
    """완료 알림 발송"""
    try:
        # 상위 5개 종목 정보
        candidates = db.get_candidates(run_date)[:5]
        
        fields = []
        for candidate in candidates:
            fields.append({
                "name": f"📊 {candidate['name']} ({candidate['ticker']})",
                "value": f"등락률: {candidate['change_pct']:.2f}% | 사유: {candidate['reason_flag']}",
                "inline": False
            })
        
        embed = {
            "title": f"📚 유목민 공부법 완료 ({run_date})",
            "description": (
                f"✅ 후보 종목: **{stats['candidates']}개**\n"
                f"📰 뉴스 수집: **{stats['news_collected']}개**\n"
                f"🤖 AI 요약: **{stats['summaries_generated']}개**\n"
                f"⚠️ 오류: **{len(stats['errors'])}건**"
            ),
            "color": 5814783,
            "fields": fields,
            "footer": {"text": f"SQLite DB 저장 완료 | 대시보드에서 확인 가능"}
        }
        
        notifier.send_alert("유목민 공부법 완료", embed=embed)
    
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


# ==================== CLI 인터페이스 ====================

if __name__ == '__main__':
    import argparse
    from .notifier import Notifier
    
    parser = argparse.ArgumentParser(description='유목민 공부법 수동 실행')
    parser.add_argument('--force', action='store_true', help='강제 실행 (중복 무시)')
    parser.add_argument('--date', type=str, help='특정 날짜 실행 (YYYYMMDD)')
    parser.add_argument('--news-only', action='store_true', help='뉴스만 재수집')
    
    args = parser.parse_args()
    
    # Notifier 초기화
    notifier = Notifier()
    
    if args.date:
        # 특정 날짜로 실행 (미구현 - 향후 확장 가능)
        print(f"특정 날짜 실행 기능은 향후 구현 예정: {args.date}")
    else:
        # 오늘 날짜로 실행
        run_daily_study(None, notifier, force_run=args.force)
