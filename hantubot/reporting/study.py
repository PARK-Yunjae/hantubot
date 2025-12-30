"""
유목민 공부법 및 자동 오답노트 생성 모듈
"""
import os
import json
import datetime as dt
from typing import List, Dict
import pandas as pd

from hantubot.study.manager import run_daily_study, get_latest_trading_date
from hantubot.study.exporter import backup_database
from hantubot.study.analyzer import generate_summaries, generate_study_notes
from hantubot.study.collector import collect_market_data, collect_news_for_candidates
from hantubot.reporting.logger import get_logger

logger = get_logger(__name__)

# Re-export necessary functions
__all__ = [
    'run_daily_study',
    'get_latest_trading_date',
    'backup_database',
    'collect_market_data',
    'collect_news_for_candidates',
    'generate_summaries',
    'generate_study_notes',
    'generate_daily_retrospective'
]

def generate_daily_retrospective(target_date: str = None):
    """
    당일 매매 내역을 분석하여 오답노트(Markdown)를 생성합니다.
    
    Args:
        target_date (str): 대상 날짜 (YYYYMMDD). 기본값은 오늘.
    """
    if not target_date:
        target_date = dt.datetime.now().strftime("%Y%m%d")
    
    log_dir = 'logs'
    formatted_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"
    trade_file = os.path.join(log_dir, f"trades_{formatted_date}.jsonl")
    
    logger.info(f"오답노트 생성 시작: {trade_file}")
    
    if not os.path.exists(trade_file):
        logger.warning(f"매매 로그 파일이 없습니다: {trade_file}")
        return

    trades = []
    try:
        with open(trade_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    trades.append(json.loads(line))
    except Exception as e:
        logger.error(f"매매 로그 파일 읽기 실패: {e}")
        return

    if not trades:
        logger.info("매매 내역이 없습니다.")
        return

    # 매매 내역 정리 (종목별 그룹화)
    trades_by_symbol = {}
    for trade in trades:
        symbol = trade.get('symbol')
        if not symbol: continue
        if symbol not in trades_by_symbol:
            trades_by_symbol[symbol] = []
        trades_by_symbol[symbol].append(trade)

    # Markdown 리포트 생성
    report_lines = [f"# 📅 {formatted_date} 매매 복기\n"]
    
    for i, (symbol, symbol_trades) in enumerate(trades_by_symbol.items(), 1):
        # 수익률 계산 (약식: 매도 평균가 / 매수 평균가 - 1)
        buy_trades = [t for t in symbol_trades if t.get('side') == 'buy']
        sell_trades = [t for t in symbol_trades if t.get('side') == 'sell']
        
        avg_buy_price = 0
        avg_sell_price = 0
        
        if buy_trades:
            total_qty = sum(t.get('filled_quantity', 0) for t in buy_trades)
            total_amt = sum(t.get('filled_quantity', 0) * t.get('fill_price', 0) for t in buy_trades)
            avg_buy_price = total_amt / total_qty if total_qty > 0 else 0
            
        if sell_trades:
            total_qty = sum(t.get('filled_quantity', 0) for t in sell_trades)
            total_amt = sum(t.get('filled_quantity', 0) * t.get('fill_price', 0) for t in sell_trades)
            avg_sell_price = total_amt / total_qty if total_qty > 0 else 0
            
        pnl_str = ""
        if avg_buy_price > 0 and avg_sell_price > 0:
            pnl = ((avg_sell_price / avg_buy_price) - 1) * 100
            pnl_str = f"(수익: {pnl:+.2f}%)"
        elif avg_buy_price > 0:
             pnl_str = "(보유 중)"
        
        # 종목명 가져오기 (API나 DB 필요하지만 여기선 생략하거나 trades에 포함되어 있다면 사용)
        stock_name = symbol # 이름 정보가 없으면 코드로 대체
        
        report_lines.append(f"### {i}. {stock_name} ({symbol}) {pnl_str}")
        
        # 매수/매도 이유
        buy_reason = "정보 없음"
        sell_reason = "정보 없음"
        
        # trades 로그에 reason이 있다면 사용
        for t in buy_trades:
            if t.get('reason'): buy_reason = t.get('reason')
        for t in sell_trades:
            if t.get('reason'): sell_reason = t.get('reason')
            
        report_lines.append(f"- **매수 이유:** {buy_reason}")
        if sell_trades:
            report_lines.append(f"- **매도 이유:** {sell_reason}")
        
        # 특이사항 (메모 등 - 현재는 공란)
        report_lines.append("- **특이사항:** ")
        report_lines.append("")

    # 파일 저장
    output_file = os.path.join(log_dir, f"study_note_{target_date}.md")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
        logger.info(f"오답노트 저장 완료: {output_file}")
    except Exception as e:
        logger.error(f"오답노트 저장 실패: {e}")

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
    
    parser = argparse.ArgumentParser(description='유목민 공부법 및 오답노트 실행')
    parser.add_argument('--force', action='store_true', help='강제 실행 (중복 무시)')
    parser.add_argument('--date', type=str, help='특정 날짜 실행 (YYYYMMDD)')
    parser.add_argument('--retro', action='store_true', help='오답노트 생성만 실행')
    
    args = parser.parse_args()
    
    # Notifier 초기화
    notifier = Notifier()
    
    target_date = args.date if args.date else dt.datetime.now().strftime("%Y%m%d")

    if args.retro:
        generate_daily_retrospective(target_date)
    else:
        # 기존 공부법 실행
        run_daily_study(None, notifier, force_run=args.force, target_date=target_date)
        # 오답노트도 같이 생성
        generate_daily_retrospective(target_date)
