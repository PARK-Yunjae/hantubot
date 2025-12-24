# hantubot_prod/hantubot/optimization/analyzer.py
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

from ..reporting.logger import get_logger
from ..reporting.trade_logger import TRADE_LOG_DIR # Assuming TRADE_LOG_DIR is public

logger = get_logger(__name__)

DYNAMIC_PARAMS_FILE = os.path.join("configs", "dynamic_params.json")

def _load_trade_records(date_str: str) -> List[Dict[str, Any]]:
    """지정된 날짜의 거래 기록을 JSONL 파일에서 로드합니다."""
    filepath = os.path.join(TRADE_LOG_DIR, f"trades_{date_str}.jsonl")
    records = []
    if not os.path.exists(filepath):
        logger.info(f"거래 기록 파일이 없습니다: {filepath}")
        return records
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                records.append(json.loads(line))
    except Exception as e:
        logger.error(f"거래 기록 파일 로드 중 오류 발생: {filepath} - {e}", exc_info=True)
    return records

def _calculate_strategy_performance(records: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    거래 기록을 기반으로 각 전략의 총 실현 PnL을 계산합니다.
    :return: {strategy_id: total_realized_pnl_pct}
    """
    strategy_pnls: Dict[str, float] = {}
    
    for record in records:
        if record.get('event_type') == 'FILL' and record.get('side') == 'sell' and record.get('pnl_pct') is not None:
            strategy_id = record['strategy_id']
            # 현재는 단순히 PnL%를 합산하지만, 실제로는 금액 기반 PnL이 더 정확
            # 여기서는 예시로 PnL% 합산 사용
            strategy_pnls[strategy_id] = strategy_pnls.get(strategy_id, 0.0) + record['pnl_pct']
    return strategy_pnls

def _determine_capital_allocation_weights(strategy_pnls: Dict[str, float]) -> Dict[str, float]:
    """
    각 전략의 성과를 기반으로 자본 배분 가중치를 결정합니다.
    아주 단순한 로직: 수익 나면 가중치 증가, 손실 나면 감소.
    """
    weights: Dict[str, float] = {}
    for strategy_id, pnl in strategy_pnls.items():
        if pnl > 0:
            weights[strategy_id] = 1.1 # 10% 증액
        elif pnl < 0:
            weights[strategy_id] = 0.9 # 10% 감액
        else:
            weights[strategy_id] = 1.0 # 변화 없음
    return weights

def _save_dynamic_params(params: Dict[str, Dict[str, Any]]):
    """동적으로 조절된 파라미터를 JSON 파일에 저장합니다."""
    os.makedirs(os.path.dirname(DYNAMIC_PARAMS_FILE), exist_ok=True)
    try:
        with open(DYNAMIC_PARAMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(params, f, ensure_ascii=False, indent=4)
        logger.info(f"동적 파라미터 저장됨: {DYNAMIC_PARAMS_FILE}")
    except Exception as e:
        logger.error(f"동적 파라미터 저장 중 오류 발생: {e}", exc_info=True)

def run_daily_optimization():
    """
    장 마감 후 일일 거래 기록을 분석하여 다음 날 전략 파라미터를 최적화합니다.
    """
    logger.info("일일 전략 최적화 루틴 시작...")
    today_str = (datetime.now() - timedelta(days=0)).strftime("%Y-%m-%d") # 전일 기준으로 분석하려면 -1
    
    # 1. 일일 거래 기록 로드
    trade_records = _load_trade_records(today_str)
    if not trade_records:
        logger.info(f"오늘 ({today_str}) 기록된 거래가 없어 최적화를 건너뜀.")
        # 거래 기록이 없어도 기존 dynamic_params.json 파일은 유지해야 함
        return

    # 2. 전략별 성과 계산
    strategy_pnls = _calculate_strategy_performance(trade_records)
    logger.info(f"오늘의 전략별 총 실현 PnL: {strategy_pnls}")

    # 3. 자본 배분 가중치 결정
    capital_allocation_weights = _determine_capital_allocation_weights(strategy_pnls)
    
    # 4. 동적 파라미터 구조화 (기존 파라미터 로드 후 업데이트)
    dynamic_params: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(DYNAMIC_PARAMS_FILE):
        try:
            with open(DYNAMIC_PARAMS_FILE, 'r', encoding='utf-8') as f:
                dynamic_params = json.load(f)
        except Exception as e:
            logger.warning(f"기존 동적 파라미터 로드 중 오류 발생. 새로 생성: {e}")

    for strategy_id, weight in capital_allocation_weights.items():
        if strategy_id not in dynamic_params:
            dynamic_params[strategy_id] = {}
        dynamic_params[strategy_id]['capital_allocation_weight'] = weight
    
    # 5. 동적 파라미터 저장
    _save_dynamic_params(dynamic_params)
    logger.info("일일 전략 최적화 루틴 완료.")

if __name__ == '__main__':
    # 간단한 테스트
    # 실제 실행 시에는 reports/trades/trades_YYYY-MM-DD.jsonl 파일을 생성해야 함
    
    # 가상의 거래 기록 생성 (테스트용)
    test_date_str = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(os.path.join("reports", "trades"), exist_ok=True)
    with open(os.path.join("reports", "trades", f"trades_{test_date_str}.jsonl"), 'w', encoding='utf-8') as f:
        f.write(json.dumps({
            "timestamp": "...", "event_type": "FILL", "order_id": "...", "symbol": "A", "side": "sell",
            "quantity": 10, "price": 10000, "strategy_id": "strategy_X", "market_regime": "NEUTRAL", "pnl_pct": 5.0
        }, ensure_ascii=False) + '\n')
        f.write(json.dumps({
            "timestamp": "...", "event_type": "FILL", "order_id": "...", "symbol": "B", "side": "sell",
            "quantity": 5, "price": 20000, "strategy_id": "strategy_Y", "market_regime": "NEUTRAL", "pnl_pct": -2.0
        }, ensure_ascii=False) + '\n')
        f.write(json.dumps({
            "timestamp": "...", "event_type": "FILL", "order_id": "...", "symbol": "C", "side": "sell",
            "quantity": 3, "price": 30000, "strategy_id": "strategy_X", "market_regime": "NEUTRAL", "pnl_pct": 3.0
        }, ensure_ascii=False) + '\n')
    
    run_daily_optimization()
