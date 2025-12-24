# hantubot_prod/hantubot/optimization/analyzer.py
"""
동적 전략 최적화 모듈 v2
- 승률 기반 가중치 조절
- 연속 승리/패배 추적
- 손실 발생 시 손절 라인 강화
- 복리 전략에 최적화된 버퍼 동적 조정
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
from collections import defaultdict

from ..reporting.logger import get_logger
from ..reporting.trade_logger import TRADE_LOG_DIR

logger = get_logger(__name__)

DYNAMIC_PARAMS_FILE = os.path.join("configs", "dynamic_params.json")


def _load_trade_records(date_str: str) -> List[Dict[str, Any]]:
    """지정된 날짜의 거래 기록을 JSONL 파일에서 로드합니다."""
    filepath = os.path.join(TRADE_LOG_DIR, f"trades_{date_str}.jsonl")
    records = []
    if not os.path.exists(filepath):
        logger.debug(f"거래 기록 파일이 없습니다: {filepath}")
        return records
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    except Exception as e:
        logger.error(f"거래 기록 파일 로드 중 오류 발생: {filepath} - {e}", exc_info=True)
    return records


def _load_recent_trade_records(days: int = 7) -> List[Dict[str, Any]]:
    """최근 N일간의 거래 기록을 모두 로드합니다."""
    all_records = []
    for i in range(days):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        records = _load_trade_records(date_str)
        all_records.extend(records)
    return all_records


def _calculate_strategy_stats(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    거래 기록을 기반으로 각 전략의 상세 통계를 계산합니다.
    
    Returns:
        {strategy_id: {
            'total_pnl_krw': float,
            'total_pnl_pct': float,
            'win_count': int,
            'loss_count': int,
            'win_rate': float,
            'avg_win_pct': float,
            'avg_loss_pct': float,
            'max_loss_pct': float,
            'consecutive_wins': int,
            'consecutive_losses': int
        }}
    """
    stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        'total_pnl_krw': 0.0,
        'total_pnl_pct': 0.0,
        'wins': [],
        'losses': [],
        'all_pnls': []  # 순서 유지를 위해
    })
    
    # 매도 체결만 필터링 (실현 손익)
    sell_fills = [
        r for r in records 
        if r.get('event_type') == 'FILL' 
        and r.get('side') == 'sell'
        and r.get('pnl_pct') is not None
    ]
    
    # 시간순 정렬
    sell_fills.sort(key=lambda x: x.get('timestamp', ''))
    
    for record in sell_fills:
        strategy_id = record.get('strategy_id', 'unknown')
        pnl_pct = record.get('pnl_pct', 0)
        pnl_krw = record.get('pnl_krw', 0)
        
        stats[strategy_id]['total_pnl_krw'] += pnl_krw if pnl_krw else 0
        stats[strategy_id]['total_pnl_pct'] += pnl_pct
        stats[strategy_id]['all_pnls'].append(pnl_pct)
        
        if pnl_pct > 0:
            stats[strategy_id]['wins'].append(pnl_pct)
        else:
            stats[strategy_id]['losses'].append(pnl_pct)
    
    # 통계 계산
    result = {}
    for strategy_id, data in stats.items():
        wins = data['wins']
        losses = data['losses']
        all_pnls = data['all_pnls']
        total_trades = len(wins) + len(losses)
        
        # 연속 승리/패배 계산 (최근부터 역순으로)
        consecutive_wins = 0
        consecutive_losses = 0
        
        for pnl in reversed(all_pnls):
            if pnl > 0:
                if consecutive_losses == 0:
                    consecutive_wins += 1
                else:
                    break
            else:
                if consecutive_wins == 0:
                    consecutive_losses += 1
                else:
                    break
        
        result[strategy_id] = {
            'total_pnl_krw': data['total_pnl_krw'],
            'total_pnl_pct': data['total_pnl_pct'],
            'win_count': len(wins),
            'loss_count': len(losses),
            'win_rate': len(wins) / total_trades if total_trades > 0 else 0,
            'avg_win_pct': sum(wins) / len(wins) if wins else 0,
            'avg_loss_pct': sum(losses) / len(losses) if losses else 0,
            'max_loss_pct': min(losses) if losses else 0,
            'consecutive_wins': consecutive_wins,
            'consecutive_losses': consecutive_losses,
            'total_trades': total_trades
        }
    
    return result


def _determine_dynamic_params(stats: Dict[str, Dict[str, Any]], 
                              existing_params: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    전략 통계를 기반으로 동적 파라미터를 결정합니다.
    
    결정 항목:
    - capital_allocation_weight: 자본 배분 가중치 (0.7 ~ 1.2)
    - consecutive_wins: 연속 승리 횟수 (버퍼 결정에 사용)
    - stop_loss_override: 손절 라인 오버라이드 (큰 손실 후 강화)
    - take_profit_override: 익절 라인 오버라이드
    """
    params = existing_params.copy()
    
    for strategy_id, stat in stats.items():
        if strategy_id not in params:
            params[strategy_id] = {}
        
        win_rate = stat['win_rate']
        avg_win = stat['avg_win_pct']
        avg_loss = stat['avg_loss_pct']
        max_loss = stat['max_loss_pct']
        consecutive_wins = stat['consecutive_wins']
        consecutive_losses = stat['consecutive_losses']
        total_trades = stat['total_trades']
        
        # --- 1. 자본 배분 가중치 결정 ---
        # 승률 60% 이상 + 평균 수익 2% 이상 → 증액
        # 승률 40% 미만 또는 평균 손실 -3% 초과 → 감액
        if total_trades >= 3:  # 최소 3회 이상 거래해야 통계 의미 있음
            if win_rate >= 0.6 and avg_win >= 2.0:
                weight = 1.2  # 20% 증액
            elif win_rate >= 0.5 and (avg_win + avg_loss) > 0:
                weight = 1.1  # 10% 증액
            elif win_rate >= 0.5:
                weight = 1.0  # 유지
            elif win_rate < 0.4 or avg_loss < -3.0:
                weight = 0.7  # 30% 감액
            else:
                weight = 0.9  # 10% 감액
        else:
            weight = params[strategy_id].get('capital_allocation_weight', 1.0)
        
        params[strategy_id]['capital_allocation_weight'] = weight
        
        # --- 2. 연속 승리/패배 기록 ---
        params[strategy_id]['consecutive_wins'] = consecutive_wins
        params[strategy_id]['consecutive_losses'] = consecutive_losses
        
        # --- 3. 손절 라인 강화 (큰 손실 발생 시) ---
        # 최대 손실이 -5% 초과했으면 다음날 손절 라인 강화
        if max_loss < -5.0:
            params[strategy_id]['stop_loss_override'] = -1.5  # 1.5%로 강화
            logger.info(f"[{strategy_id}] 큰 손실({max_loss:.1f}%) 발생으로 손절 라인 강화: -1.5%")
        elif max_loss < -3.0:
            params[strategy_id]['stop_loss_override'] = -2.0  # 2%로 유지
        else:
            # 손실이 작으면 오버라이드 해제
            params[strategy_id].pop('stop_loss_override', None)
        
        # --- 4. 연속 패배 시 보수적 전환 ---
        if consecutive_losses >= 3:
            params[strategy_id]['capital_allocation_weight'] = 0.5  # 50% 감액
            params[strategy_id]['stop_loss_override'] = -1.0  # 1% 손절
            logger.warning(f"[{strategy_id}] 연속 {consecutive_losses}회 패배. 보수적 모드 전환.")
        
        # --- 5. 연속 승리 시 공격적 전환 (복리 극대화) ---
        if consecutive_wins >= 5:
            params[strategy_id]['capital_allocation_weight'] = min(1.3, weight + 0.1)
            logger.info(f"[{strategy_id}] 연속 {consecutive_wins}회 승리! 공격적 모드.")
        
        # 통계 로깅
        logger.info(
            f"[{strategy_id}] 통계: 승률 {win_rate*100:.1f}% ({stat['win_count']}승/{stat['loss_count']}패), "
            f"평균수익 {avg_win:.2f}%, 평균손실 {avg_loss:.2f}%, "
            f"연속승리 {consecutive_wins}, 가중치 {weight}"
        )
    
    return params


def _save_dynamic_params(params: Dict[str, Dict[str, Any]]):
    """동적으로 조절된 파라미터를 JSON 파일에 저장합니다."""
    os.makedirs(os.path.dirname(DYNAMIC_PARAMS_FILE), exist_ok=True)
    try:
        with open(DYNAMIC_PARAMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(params, f, ensure_ascii=False, indent=4)
        logger.info(f"동적 파라미터 저장됨: {DYNAMIC_PARAMS_FILE}")
    except Exception as e:
        logger.error(f"동적 파라미터 저장 중 오류 발생: {e}", exc_info=True)


def _load_existing_params() -> Dict[str, Dict[str, Any]]:
    """기존 동적 파라미터를 로드합니다."""
    if os.path.exists(DYNAMIC_PARAMS_FILE):
        try:
            with open(DYNAMIC_PARAMS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"기존 동적 파라미터 로드 중 오류 발생. 새로 생성: {e}")
    return {}


def run_daily_optimization():
    """
    장 마감 후 일일 거래 기록을 분석하여 다음 날 전략 파라미터를 최적화합니다.
    
    개선점:
    - 최근 7일간의 거래 기록을 종합 분석
    - 승률, 평균 수익/손실, 연속 승패를 고려한 가중치 결정
    - 큰 손실 후 손절 라인 자동 강화
    """
    logger.info("=" * 50)
    logger.info("일일 전략 최적화 루틴 시작 (v2)")
    logger.info("=" * 50)
    
    # 1. 최근 7일간의 거래 기록 로드
    all_records = _load_recent_trade_records(days=7)
    if not all_records:
        logger.info("최근 7일간 기록된 거래가 없어 최적화를 건너뜀.")
        return
    
    logger.info(f"최근 7일간 총 {len(all_records)}건의 거래 기록 로드됨.")
    
    # 2. 전략별 상세 통계 계산
    stats = _calculate_strategy_stats(all_records)
    
    if not stats:
        logger.info("분석할 매도 체결 기록이 없습니다.")
        return
    
    # 3. 기존 파라미터 로드
    existing_params = _load_existing_params()
    
    # 4. 동적 파라미터 결정
    new_params = _determine_dynamic_params(stats, existing_params)
    
    # 5. 저장
    _save_dynamic_params(new_params)
    
    # 6. 요약 로깅
    logger.info("-" * 50)
    logger.info("최적화 결과 요약:")
    for strategy_id, params in new_params.items():
        weight = params.get('capital_allocation_weight', 1.0)
        cons_wins = params.get('consecutive_wins', 0)
        cons_losses = params.get('consecutive_losses', 0)
        stop_override = params.get('stop_loss_override')
        
        logger.info(
            f"  [{strategy_id}] 가중치: {weight:.1f}, "
            f"연속승리: {cons_wins}, 연속패배: {cons_losses}, "
            f"손절오버라이드: {stop_override if stop_override else '없음'}"
        )
    
    logger.info("=" * 50)
    logger.info("일일 전략 최적화 루틴 완료.")


if __name__ == '__main__':
    # 테스트용 거래 기록 생성
    import os
    
    test_date_str = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(TRADE_LOG_DIR, exist_ok=True)
    
    test_records = [
        {"timestamp": "2025-01-01T10:00:00", "event_type": "FILL", "order_id": "1", 
         "symbol": "005930", "side": "sell", "quantity": 10, "price": 75000, 
         "strategy_id": "closing_price_advanced_screener", "market_regime": "NEUTRAL", 
         "pnl_pct": 2.5, "pnl_krw": 18750},
        {"timestamp": "2025-01-02T10:00:00", "event_type": "FILL", "order_id": "2", 
         "symbol": "000660", "side": "sell", "quantity": 5, "price": 130000, 
         "strategy_id": "closing_price_advanced_screener", "market_regime": "NEUTRAL", 
         "pnl_pct": -1.5, "pnl_krw": -9750},
        {"timestamp": "2025-01-03T10:00:00", "event_type": "FILL", "order_id": "3", 
         "symbol": "035720", "side": "sell", "quantity": 20, "price": 50000, 
         "strategy_id": "closing_price_advanced_screener", "market_regime": "NEUTRAL", 
         "pnl_pct": 3.2, "pnl_krw": 32000},
        {"timestamp": "2025-01-04T10:00:00", "event_type": "FILL", "order_id": "4", 
         "symbol": "005930", "side": "sell", "quantity": 10, "price": 76000, 
         "strategy_id": "volume_spike_strategy", "market_regime": "RISK_ON", 
         "pnl_pct": -6.5, "pnl_krw": -49400},  # 큰 손실
    ]
    
    with open(os.path.join(TRADE_LOG_DIR, f"trades_{test_date_str}.jsonl"), 'w', encoding='utf-8') as f:
        for record in test_records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    print(f"테스트 거래 기록 생성됨: {TRADE_LOG_DIR}/trades_{test_date_str}.jsonl")
    
    # 최적화 실행
    run_daily_optimization()
