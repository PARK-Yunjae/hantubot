# hantubot_prod/hantubot/reporting/trade_logger.py
import os
import json
from datetime import datetime
from typing import Dict, Any

from .logger import get_logger

logger = get_logger(__name__)

TRADE_LOG_DIR = os.path.join("reports", "trades") # 프로젝트 루트 기준

def _get_trade_log_filepath() -> str:
    """오늘 날짜의 거래 기록 파일 경로를 반환합니다."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(TRADE_LOG_DIR, exist_ok=True) # 디렉토리가 없으면 생성
    return os.path.join(TRADE_LOG_DIR, f"trades_{today_str}.jsonl")

def log_trade_record(record: Dict[str, Any]):
    """
    거래 체결 기록을 JSON Lines 형식으로 파일에 추가합니다.
    :param record: 기록할 거래 정보 딕셔너리
    """
    filepath = _get_trade_log_filepath()
    try:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        logger.debug(f"거래 기록 저장됨: {record}")
    except Exception as e:
        logger.error(f"거래 기록 저장 중 오류 발생: {e}", exc_info=True)

if __name__ == '__main__':
    # 테스트 코드
    print(f"Trade log file path: {_get_trade_log_filepath()}")
    
    test_record_buy = {
        "timestamp": datetime.now().isoformat(),
        "strategy_id": "test_strategy_ob",
        "symbol": "005930",
        "side": "buy",
        "quantity": 10,
        "price": 75000,
        "market_regime": "NEUTRAL"
    }
    log_trade_record(test_record_buy)

    test_record_sell = {
        "timestamp": datetime.now().isoformat(),
        "strategy_id": "test_strategy_ob",
        "symbol": "005930",
        "side": "sell",
        "quantity": 10,
        "price": 75500,
        "pnl_pct": 0.66,
        "market_regime": "NEUTRAL"
    }
    log_trade_record(test_record_sell)
    print("Test records logged.")
