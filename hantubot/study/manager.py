"""
유목민 공부법 메인 매니저 (오케스트레이션)
"""
import os
from datetime import datetime
from pykrx import stock

from hantubot.reporting.logger import get_logger
from hantubot.study.repository import get_study_db
from hantubot.study.collector import collect_market_data, collect_news_for_candidates
from hantubot.study.analyzer import generate_summaries, generate_study_notes
from hantubot.study.exporter import (
    backup_to_gsheet, 
    send_completion_notification, 
    backup_database, 
    auto_commit_to_github
)

logger = get_logger(__name__)


def get_latest_trading_date() -> str:
    """
    최근 거래일을 조회합니다 (오늘이 휴장일이면 이전 거래일 반환)
    
    Returns:
        YYYYMMDD 형식의 최근 거래일
    """
    from datetime import timedelta
    
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
