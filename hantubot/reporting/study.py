"""
유목민 공부법 (Wrapper for hantubot.study.manager)
Backward compatibility layer.
"""
from hantubot.study.manager import run_daily_study, get_latest_trading_date
from hantubot.study.exporter import backup_database
from hantubot.study.analyzer import generate_summaries, generate_study_notes
from hantubot.study.collector import collect_market_data, collect_news_for_candidates

# Re-export necessary functions
__all__ = [
    'run_daily_study',
    'get_latest_trading_date',
    'backup_database',
    'collect_market_data',
    'collect_news_for_candidates',
    'generate_summaries',
    'generate_study_notes'
]

if __name__ == '__main__':
    # CLI execution
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
    
    args = parser.parse_args()
    
    # Notifier 초기화
    notifier = Notifier()
    
    if args.date:
        # 특정 날짜로 실행
        run_daily_study(None, notifier, force_run=args.force, target_date=args.date)
    else:
        # 최근 거래일로 실행
        run_daily_study(None, notifier, force_run=args.force)
