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
from ..utils.config_loader import load_config

logger = get_logger(__name__)


def backup_database():
    """
    study.db 자동 백업 (config.yaml 설정 기반)
    
    - 일요일마다 자동 백업
    - 설정된 기간(기본 30일) 이상 된 백업 자동 삭제
    """
    try:
        from pathlib import Path
        from datetime import datetime
        import shutil
        
        config = load_config()
        study_config = config.get('study', {})
        
        # 백업 활성화 체크
        if not study_config.get('enable_auto_backup', True):
            logger.debug("DB 자동 백업이 비활성화되어 있습니다.")
            return
        
        db_path = Path('data/study.db')
        if not db_path.exists():
            logger.warning("study.db 파일이 없어 백업을 건너뜁니다.")
            return
        
        backup_dir = Path('data/backups')
        backup_dir.mkdir(exist_ok=True)
        
        # 일요일(weekday=6)마다 백업
        now = datetime.now()
        if now.weekday() == 6:
            backup_file = backup_dir / f"study_backup_{now:%Y%m%d}.db"
            
            # 이미 오늘 백업이 있으면 건너뜀
            if backup_file.exists():
                logger.info(f"오늘 백업이 이미 존재합니다: {backup_file}")
                return
            
            shutil.copy(db_path, backup_file)
            logger.info(f"✅ DB 백업 완료: {backup_file}")
            
            # 오래된 백업 삭제
            retention_days = study_config.get('backup_retention_days', 30)
            deleted_count = 0
            for old_backup in backup_dir.glob("study_backup_*.db"):
                age_days = (now - datetime.fromtimestamp(old_backup.stat().st_mtime)).days
                if age_days > retention_days:
                    old_backup.unlink()
                    deleted_count += 1
                    logger.info(f"오래된 백업 삭제: {old_backup} ({age_days}일)")
            
            if deleted_count > 0:
                logger.info(f"총 {deleted_count}개의 오래된 백업 삭제 완료")
        else:
            logger.debug(f"백업 예정일이 아닙니다. (현재: {now.strftime('%A')}, 백업일: 일요일)")
    
    except Exception as e:
        logger.error(f"DB 백업 중 오류 발생: {e}", exc_info=True)


def get_latest_trading_date() -> str:
    """
    최근 거래일을 조회합니다 (오늘이 휴장일이면 이전 거래일 반환)
    
    Returns:
        YYYYMMDD 형식의 최근 거래일
    """
    from datetime import datetime, timedelta
    
    today = datetime.now()
    
    # 최대 10일 전까지 확인 (주말, 공휴일 고려)
    for i in range(10):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%Y%m%d")
        
        try:
            # pykrx로 해당 날짜에 시장 데이터가 있는지 확인
            df = stock.get_market_ohlcv_by_ticker(date_str, market="KOSPI")
            if not df.empty:
                logger.info(f"최근 거래일 확인: {date_str}")
                return date_str
        except:
            continue
    
    # 찾지 못하면 오늘 날짜 반환 (fallback)
    return today.strftime("%Y%m%d")


def run_daily_study(broker, notifier, force_run=False, target_date=None):
    """
    유목민 공부법 메인 함수 - SQLite 기반 데이터 수집 및 분석
    
    Args:
        broker: 브로커 인스턴스 (미사용, 시그니처 호환성 유지)
        notifier: 알림 인스턴스
        force_run: True면 중복 체크 무시하고 강제 실행
        target_date: 특정 날짜 지정 (YYYYMMDD), None이면 최근 거래일 자동 조회
    """
    logger.info("=" * 80)
    logger.info("유목민 공부법 (100일 공부) 시작 - SQLite + 뉴스 수집 버전")
    logger.info("=" * 80)
    
    # 환경 변수 확인
    study_mode = os.getenv('STUDY_MODE', 'sqlite')  # sqlite / gsheet / both
    
    # 날짜 설정 (최근 거래일 자동 조회)
    if target_date:
        today_str = target_date
    else:
        today_str = get_latest_trading_date()
        logger.info(f"자동 조회된 최근 거래일: {today_str}")
    
    today_date = datetime.strptime(today_str, "%Y%m%d").strftime("%Y-%m-%d")
    
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
        
        # ========== 단계 3.5: 백일공부 학습 메모 생성 (선택) ==========
        enable_study_notes = os.getenv('ENABLE_STUDY_NOTES', 'true').lower() == 'true'
        if enable_study_notes:
            logger.info("[3.5/4] 백일공부 학습 메모 생성 중...")
            note_stats = generate_study_notes(today_str, candidates, db)
            stats['study_notes_generated'] = note_stats['success_count']
            stats['errors'].extend(note_stats['errors'])
            logger.info(f"✅ {note_stats['success_count']}개 학습 메모 생성 완료 ({note_stats['failed_count']}개 실패)")
        else:
            logger.info("[3.5/4] 백일공부 학습 메모 건너뜀 (ENABLE_STUDY_NOTES=false)")
        
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
        
        # ========== DB 자동 백업 (옵션) ==========
        try:
            logger.info("[추가] DB 자동 백업 체크 중...")
            backup_database()
        except Exception as e:
            logger.warning(f"DB 자동 백업 중 오류 (무시됨): {e}")
        
        # ========== GitHub 자동 커밋 (옵션) ==========
        enable_auto_commit = os.getenv('ENABLE_GIT_AUTO_COMMIT', 'true').lower() == 'true'
        if enable_auto_commit:
            try:
                logger.info("[추가] GitHub 자동 커밋 중...")
                auto_commit_to_github(today_str, stats)
                logger.info("✅ GitHub 커밋 완료")
            except Exception as e:
                logger.warning(f"GitHub 자동 커밋 실패 (무시됨): {e}")
        
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
    후보 종목들의 뉴스 수집 (병렬 처리로 3배 빠름)
    
    Returns:
        {'total_news': int, 'failed_tickers': int, 'errors': []}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
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
    
    # Gemini API 설정 - 2.5 Pro로 업그레이드 (더 정확한 요약)
    try:
        genai.configure(api_key=api_key)
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-pro')
        model = genai.GenerativeModel(model_name)
        logger.info(f"Using Gemini model: {model_name}")
        
        # 배치 크기 설정 (Pro 모델은 더 느리므로 줄임)
        batch_size = int(os.getenv('LLM_BATCH_SIZE', '5'))
        
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


def generate_study_notes(run_date: str, candidates: List[Dict], 
                        db: StudyDatabase) -> Dict:
    """
    백일공부 학습 메모 생성 (사실 검증 → 학습 포인트 추출)
    
    Returns:
        {'success_count': int, 'failed_count': int, 'errors': []}
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.warning("GEMINI_API_KEY not found. Skipping study notes.")
        return {'success_count': 0, 'failed_count': 0, 'errors': ['No API key']}
    
    success_count = 0
    failed_count = 0
    errors = []
    
    # 학습 메모가 필요한 종목만 필터링
    stocks_to_note = []
    for candidate in candidates:
        ticker = candidate['ticker']
        
        # 이미 학습 메모가 있는지 확인
        if db.has_study_note(run_date, ticker):
            logger.debug(f"Study note already exists for {ticker}, skipping")
            continue
        
        # 뉴스가 있는 종목만 처리
        news_items = db.get_news_items(run_date, ticker)
        if not news_items:
            continue
        
        stocks_to_note.append({
            'ticker': ticker,
            'name': candidate['name'],
            'news_count': len(news_items)
        })
    
    if not stocks_to_note:
        logger.info("No new study notes needed")
        return {'success_count': 0, 'failed_count': 0, 'errors': []}
    
    # Gemini API 설정
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # 배치 크기 (학습 메모는 더 신중하게 3개씩)
        batch_size = 3
        
        # 배치 단위로 처리
        for i in range(0, len(stocks_to_note), batch_size):
            batch = stocks_to_note[i:i + batch_size]
            
            logger.info(f"배치 학습 메모 생성 중 ({i+1}-{i+len(batch)}/{len(stocks_to_note)})")
            
            try:
                notes = get_batch_study_notes_gemini(batch, model, run_date, db)
                
                for ticker, note_data in notes.items():
                    if note_data['success']:
                        success_count += 1
                        logger.info(f"✓ {ticker}: 학습 메모 생성 완료 (신뢰도: {note_data.get('confidence', 'unknown')})")
                    else:
                        failed_count += 1
                        errors.append(f"Study note failed for {ticker}")
                
                # Rate limiting (학습 메모는 더 보수적으로)
                time.sleep(3)
            
            except Exception as e:
                logger.error(f"Batch study note failed: {e}")
                failed_count += len(batch)
                errors.append(f"Batch study note error: {e}")
    
    except Exception as e:
        logger.error(f"Gemini API setup failed: {e}", exc_info=True)
        errors.append(f"Gemini setup failed: {e}")
    
    return {
        'success_count': success_count,
        'failed_count': failed_count,
        'errors': errors
    }


def get_batch_study_notes_gemini(stocks: List[Dict], model, run_date: str,
                                 db: StudyDatabase) -> Dict:
    """
    Gemini API로 백일공부 학습 메모 배치 생성
    
    백일공부 철학:
    1. 사실 수집 → 2. 사실 요약 → 3. 검증 → 4. 학습 메모 → 5. 신뢰도 평가
    
    Returns:
        {ticker: {'success': bool, 'confidence': str}, ...}
    """
    results = {}
    
    try:
        # 각 종목의 뉴스 데이터 수집
        stock_news_map = {}
        for stock in stocks:
            ticker = stock['ticker']
            news_items = db.get_news_items(run_date, ticker)
            
            # 뉴스 제목과 요약만 추출
            news_texts = []
            for news in news_items[:10]:  # 최대 10개만 사용
                news_texts.append(f"- [{news.get('publisher', '출처불명')}] {news['title']}: {news.get('snippet', '')}")
            
            stock_news_map[ticker] = {
                'name': stock['name'],
                'news_texts': '\n'.join(news_texts) if news_texts else '(뉴스 없음)'
            }
        
        # 프롬프트 구성 (백일공부 철학 반영)
        stock_sections = []
        for ticker, info in stock_news_map.items():
            stock_sections.append(
                f"### {info['name']} ({ticker})\n"
                f"관련 뉴스:\n{info['news_texts']}\n"
            )
        
        stocks_text = "\n".join(stock_sections)
        
        prompt = f"""당신은 "주식 공부용 학습 메모"를 작성하는 AI입니다. 
아래 종목들에 대해 뉴스를 분석하고, 각 종목마다 다음 형식의 JSON을 생성하세요:

**백일공부 원칙:**
1. 사실만 추출 (추측/예측 금지)
2. 여러 기사에서 공통으로 반복되는 내용만 요약
3. 학습 메모는 "이 종목에서 배울 점"을 일반화된 문장으로 작성
4. 신뢰도 평가: high(3개 이상 기사 일치), mid(2개 기사 일치), low(단일 기사 또는 불명확)

**출력 형식 (JSON):**
```json
{{
  "종목코드": {{
    "factual_summary": "여러 기사에서 공통으로 언급된 사실만 2-3문장으로 요약. 단일 기사 주장은 제외.",
    "ai_learning_note": "이 종목에서 배울 수 있는 일반화된 교훈. 특정 종목명 언급 금지. 다음에 비슷한 패턴을 만났을 때 체크할 조건 포함. 감정/예측/권유 금지.",
    "ai_confidence": "high 또는 mid 또는 low",
    "verification_status": "기사 간 내용 일치 여부 또는 '확인 필요' 메시지"
  }}
}}
```

**예시:**
```json
{{
  "123456": {{
    "factual_summary": "복수의 언론사가 A사와의 계약 체결을 보도. 계약 규모는 100억원으로 일치.",
    "ai_learning_note": "주요 고객사와의 대규모 계약 체결 시 단기 급등 가능성. 계약 규모, 고객사 신뢰도, 기존 매출 대비 비중 확인 필요.",
    "ai_confidence": "high",
    "verification_status": "3개 언론사 보도 내용 일치"
  }}
}}
```

**분석할 종목:**
{stocks_text}

**중요:** JSON만 출력하세요. 다른 설명은 불필요합니다.
"""
        
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
            for ticker, note_data in json_response.items():
                try:
                    db.insert_study_note({
                        'run_date': run_date,
                        'ticker': ticker,
                        'factual_summary': note_data.get('factual_summary'),
                        'ai_learning_note': note_data.get('ai_learning_note'),
                        'ai_confidence': note_data.get('ai_confidence', 'low'),
                        'verification_status': note_data.get('verification_status')
                    })
                    
                    results[ticker] = {
                        'success': True, 
                        'confidence': note_data.get('ai_confidence', 'unknown')
                    }
                
                except Exception as e:
                    logger.error(f"Failed to save study note for {ticker}: {e}")
                    results[ticker] = {'success': False}
        else:
            logger.warning("Gemini 응답에서 JSON을 찾을 수 없습니다")
            for stock in stocks:
                results[stock['ticker']] = {'success': False}
    
    except Exception as e:
        logger.error(f"Batch study note generation failed: {e}", exc_info=True)
        for stock in stocks:
            results[stock['ticker']] = {'success': False}
    
    return results


def get_batch_summaries_gemini(stocks: List[Dict], model, run_date: str, 
                               db: StudyDatabase) -> Dict:
    """
    Gemini API로 배치 요약 생성 (뉴스 기반 - 환각 방지)
    
    Returns:
        {ticker: {'success': bool, 'summary': str}, ...}
    """
    results = {}
    
    try:
        # 각 종목의 뉴스 데이터 수집 (환각 방지)
        stock_news_map = {}
        for stock in stocks:
            ticker = stock['ticker']
            news_items = db.get_news_items(run_date, ticker)
            
            # 뉴스 제목과 요약만 추출 (최대 5개)
            news_texts = []
            for news in news_items[:5]:
                news_texts.append(f"- [{news.get('publisher', '')}] {news['title']}")
                if news.get('snippet'):
                    news_texts.append(f"  {news.get('snippet')}")
            
            stock_news_map[ticker] = {
                'name': stock['name'],
                'news_texts': '\n'.join(news_texts) if news_texts else '(뉴스 없음)'
            }
        
        # 프롬프트 구성 (뉴스 기반)
        stock_sections = []
        for ticker, info in stock_news_map.items():
            stock_sections.append(
                f"### {info['name']} ({ticker})\n"
                f"관련 뉴스:\n{info['news_texts']}\n"
            )
        
        stocks_text = "\n".join(stock_sections)
        
        prompt = f"""아래 종목들을 **수집된 뉴스 내용만을 근거로** 요약하세요.

**중요:**
- 뉴스가 없으면 "관련 뉴스 없음"이라고만 적으세요
- 추측하지 말고 뉴스에 명시된 사실만 요약
- 각 종목당 2-4문장

**출력 형식 (JSON):**
```json
{{
  "종목코드": "뉴스 기반 요약 내용"
}}
```

**종목 및 뉴스:**
{stocks_text}

**JSON만 출력:**
"""
        
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


def auto_commit_to_github(run_date: str, stats: Dict):
    """
    GitHub 자동 커밋 및 푸시
    
    Args:
        run_date: 실행 날짜 (YYYYMMDD)
        stats: 실행 통계
    """
    import subprocess
    from pathlib import Path
    
    try:
        # Git 저장소 루트 경로
        repo_root = Path(__file__).parent.parent.parent
        
        # Git lock 파일 체크 (동시 Git 작업 방지)
        lock_file = repo_root / '.git' / 'index.lock'
        if lock_file.exists():
            logger.warning("Git lock 파일 감지됨. 다른 Git 작업이 진행 중입니다. 커밋을 건너뜁니다.")
            return
        
        # data/study.db 파일이 있는지 확인
        db_file = repo_root / 'data' / 'study.db'
        if not db_file.exists():
            logger.warning("study.db 파일이 없어 커밋 건너뜀")
            return
        
        # Git add (Windows 인코딩 문제 해결)
        result = subprocess.run(
            ['git', 'add', 'data/study.db'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',  # 디코딩 오류 무시
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"Git add 실패: {result.stderr}")
            return
        
        # 변경사항이 있는지 확인 (Windows 인코딩 문제 해결)
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=repo_root,
            capture_output=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10
        )
        
        # returncode가 1이면 변경사항 있음, 0이면 변경사항 없음
        if result.returncode == 0:
            logger.info("변경사항이 없어 커밋 건너뜀")
            return
        
        # Git commit (Windows 인코딩 문제 해결)
        commit_message = (
            f"📚 유목민 공부법 자동 업데이트 ({run_date})\n\n"
            f"- 후보 종목: {stats['candidates']}개\n"
            f"- 뉴스 수집: {stats['news_collected']}개\n"
            f"- AI 요약: {stats['summaries_generated']}개"
        )
        
        result = subprocess.run(
            ['git', 'commit', '-m', commit_message],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"Git commit 실패: {result.stderr}")
            return
        
        logger.info(f"✓ Git commit 완료: {commit_message.split()[0]}")
        
        # Git push (실패해도 무시 - 네트워크 이슈 등, Windows 인코딩 문제 해결)
        result = subprocess.run(
            ['git', 'push'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info("✓ Git push 완료 → GitHub 업데이트됨")
        else:
            logger.warning(f"Git push 실패 (무시됨): {result.stderr}")
    
    except subprocess.TimeoutExpired:
        logger.warning("Git 명령 타임아웃")
    except Exception as e:
        logger.warning(f"Git 자동 커밋 중 오류: {e}")


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
    from pathlib import Path
    from dotenv import load_dotenv
    from .notifier import Notifier
    
    # .env 파일 명시적 로드
    env_path = Path(__file__).parent.parent.parent / 'configs' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ .env 파일 로드 완료: {env_path}")
    else:
        print(f"⚠️ .env 파일을 찾을 수 없습니다: {env_path}")
    
    parser = argparse.ArgumentParser(description='유목민 공부법 수동 실행')
    parser.add_argument('--force', action='store_true', help='강제 실행 (중복 무시)')
    parser.add_argument('--date', type=str, help='특정 날짜 실행 (YYYYMMDD)')
    parser.add_argument('--news-only', action='store_true', help='뉴스만 재수집')
    
    args = parser.parse_args()
    
    # Notifier 초기화
    notifier = Notifier()
    
    if args.date:
        # 특정 날짜로 실행
        run_daily_study(None, notifier, force_run=args.force, target_date=args.date)
    else:
        # 최근 거래일로 실행
        run_daily_study(None, notifier, force_run=args.force)
