"""
데이터 백업 및 알림 발송 모듈
"""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from hantubot.reporting.logger import get_logger
from hantubot.study.repository import StudyDatabase
from hantubot.utils.config_loader import load_config_with_env

logger = get_logger(__name__)


def backup_database():
    """
    study.db 자동 백업 (config.yaml 설정 기반)
    
    - 일요일마다 자동 백업
    - 설정된 기간(기본 30일) 이상 된 백업 자동 삭제
    """
    try:
        config = load_config_with_env('configs/config.yaml')
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


def backup_to_gsheet(run_date: str, db: StudyDatabase, notifier):
    """Google Sheets 백업 (옵션)"""
    try:
        from hantubot.reporting.study_legacy import get_gsheet_client, get_worksheet_or_create
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
