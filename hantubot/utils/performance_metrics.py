# hantubot_prod/hantubot/utils/performance_metrics.py
"""
트레이딩 성과 지표 계산
- Sharpe Ratio: 위험 대비 수익률
- Max Drawdown: 최대 낙폭
- Calmar Ratio: 연간 수익률 / 최대 낙폭
- Win Rate, Profit Factor 등
"""
import sqlite3
import os
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import math


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
    """
    Sharpe Ratio 계산
    
    공식: (평균 수익률 - 무위험 수익률) / 수익률 표준편차
    
    Args:
        returns: 일별 수익률 리스트 (예: [0.01, -0.02, 0.03])
        risk_free_rate: 무위험 수익률 (연 2% = 0.02)
    
    Returns:
        Sharpe Ratio (높을수록 좋음, 1.0 이상 양호, 2.0 이상 우수)
    """
    if not returns or len(returns) < 2:
        return 0.0
    
    # 평균 수익률
    avg_return = sum(returns) / len(returns)
    
    # 표준편차
    variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance)
    
    if std_dev == 0:
        return 0.0
    
    # 일일 무위험 수익률 (연간 → 일일)
    daily_risk_free = risk_free_rate / 252
    
    # Sharpe Ratio
    sharpe = (avg_return - daily_risk_free) / std_dev
    
    # 연율화 (√252)
    return sharpe * math.sqrt(252)


def calculate_max_drawdown(equity_curve: List[float]) -> Tuple[float, int, int]:
    """
    최대 낙폭 (Max Drawdown) 계산
    
    Args:
        equity_curve: 자산 가치 변화 (예: [100000, 105000, 98000, 110000])
    
    Returns:
        (max_drawdown_pct, peak_idx, trough_idx)
        - max_drawdown_pct: 최대 낙폭 % (음수)
        - peak_idx: 고점 인덱스
        - trough_idx: 저점 인덱스
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0, 0, 0
    
    max_drawdown = 0.0
    peak = equity_curve[0]
    peak_idx = 0
    trough_idx = 0
    max_dd_peak_idx = 0
    max_dd_trough_idx = 0
    
    for i, value in enumerate(equity_curve):
        if value > peak:
            peak = value
            peak_idx = i
            trough_idx = i
        
        drawdown = (value - peak) / peak
        
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_dd_peak_idx = peak_idx
            max_dd_trough_idx = i
    
    return max_drawdown * 100, max_dd_peak_idx, max_dd_trough_idx


def calculate_calmar_ratio(annual_return: float, max_drawdown: float) -> float:
    """
    Calmar Ratio 계산
    
    공식: 연간 수익률 / |최대 낙폭|
    
    Args:
        annual_return: 연간 수익률 % (예: 20.5)
        max_drawdown: 최대 낙폭 % (예: -15.2)
    
    Returns:
        Calmar Ratio (높을수록 좋음, 3.0 이상 우수)
    """
    if max_drawdown >= 0:
        return 0.0
    
    return annual_return / abs(max_drawdown)


def calculate_profit_factor(wins: List[float], losses: List[float]) -> float:
    """
    Profit Factor 계산
    
    공식: 총 수익 / 총 손실
    
    Args:
        wins: 수익 거래 리스트
        losses: 손실 거래 리스트
    
    Returns:
        Profit Factor (1.0 이상 수익, 2.0 이상 우수)
    """
    total_profit = sum(wins) if wins else 0
    total_loss = abs(sum(losses)) if losses else 0
    
    if total_loss == 0:
        return float('inf') if total_profit > 0 else 0.0
    
    return total_profit / total_loss


def get_performance_summary(days: int = 90) -> Dict[str, any]:
    """
    전체 성과 요약 조회
    
    Args:
        days: 분석 기간 (일)
    
    Returns:
        성과 지표 딕셔너리
    """
    db_path = os.path.join('data', 'trading_performance.db')
    
    if not os.path.exists(db_path):
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_profit': 0.0,
            'avg_loss': 0.0,
            'profit_factor': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'calmar_ratio': 0.0
        }
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # 전체 거래 조회
        cursor.execute("""
            SELECT pnl_pct, pnl_krw, timestamp
            FROM trades
            WHERE timestamp >= ? AND pnl_pct IS NOT NULL
            ORDER BY timestamp
        """, (start_date,))
        
        trades = cursor.fetchall()
        conn.close()
        
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'calmar_ratio': 0.0
            }
        
        # 데이터 분류
        pnl_pcts = [t[0] for t in trades]
        pnl_krws = [t[1] for t in trades]
        
        wins = [p for p in pnl_pcts if p > 0]
        losses = [p for p in pnl_pcts if p < 0]
        
        # 기본 지표
        total_trades = len(trades)
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
        avg_profit = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        # Profit Factor
        profit_factor = calculate_profit_factor(wins, losses)
        
        # Sharpe Ratio (일별 수익률 가정)
        returns = [p / 100 for p in pnl_pcts]  # % -> 소수
        sharpe_ratio = calculate_sharpe_ratio(returns)
        
        # Max Drawdown (누적 자산 곡선)
        initial_capital = 1000000  # 가정
        equity_curve = [initial_capital]
        for pnl_krw in pnl_krws:
            equity_curve.append(equity_curve[-1] + pnl_krw)
        
        max_dd, _, _ = calculate_max_drawdown(equity_curve)
        
        # Calmar Ratio (연간 수익률 가정)
        total_return_pct = ((equity_curve[-1] - initial_capital) / initial_capital) * 100
        annual_return = (total_return_pct / days) * 365
        calmar_ratio = calculate_calmar_ratio(annual_return, max_dd)
        
        return {
            'total_trades': total_trades,
            'win_rate': round(win_rate * 100, 2),
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_drawdown': round(max_dd, 2),
            'calmar_ratio': round(calmar_ratio, 2),
            'total_return_pct': round(total_return_pct, 2),
            'annual_return': round(annual_return, 2)
        }
    
    except Exception as e:
        print(f"성과 조회 오류: {e}")
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_profit': 0.0,
            'avg_loss': 0.0,
            'profit_factor': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'calmar_ratio': 0.0
        }


def print_performance_report(days: int = 90):
    """성과 리포트 출력"""
    metrics = get_performance_summary(days)
    
    print("=" * 60)
    print(f"📊 트레이딩 성과 리포트 (최근 {days}일)")
    print("=" * 60)
    print(f"총 거래 횟수: {metrics['total_trades']}회")
    print(f"승률: {metrics['win_rate']:.2f}%")
    print(f"평균 수익: {metrics['avg_profit']:.2f}%")
    print(f"평균 손실: {metrics['avg_loss']:.2f}%")
    print(f"Profit Factor: {metrics['profit_factor']:.2f}")
    print("-" * 60)
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f} {'🟢 우수' if metrics['sharpe_ratio'] >= 2.0 else '🟡 양호' if metrics['sharpe_ratio'] >= 1.0 else '🔴 개선 필요'}")
    print(f"Max Drawdown: {metrics['max_drawdown']:.2f}% {'🟢 우수' if metrics['max_drawdown'] > -10 else '🟡 주의' if metrics['max_drawdown'] > -20 else '🔴 위험'}")
    print(f"Calmar Ratio: {metrics['calmar_ratio']:.2f} {'🟢 우수' if metrics['calmar_ratio'] >= 3.0 else '🟡 양호' if metrics['calmar_ratio'] >= 1.0 else '🔴 개선 필요'}")
    
    if 'total_return_pct' in metrics:
        print("-" * 60)
        print(f"총 수익률: {metrics['total_return_pct']:.2f}%")
        print(f"연간 수익률 (추정): {metrics['annual_return']:.2f}%")
    
    print("=" * 60)


if __name__ == '__main__':
    # 테스트
    print("=== 성능 지표 계산기 테스트 ===\n")
    
    # 테스트 1: Sharpe Ratio
    returns = [0.01, -0.005, 0.02, 0.015, -0.01, 0.03, -0.002, 0.01]
    sharpe = calculate_sharpe_ratio(returns)
    print(f"Sharpe Ratio: {sharpe:.2f}")
    
    # 테스트 2: Max Drawdown
    equity = [100000, 105000, 103000, 108000, 95000, 98000, 110000]
    max_dd, peak, trough = calculate_max_drawdown(equity)
    print(f"Max Drawdown: {max_dd:.2f}% (고점: {peak}, 저점: {trough})")
    
    # 테스트 3: Profit Factor
    wins = [2.5, 3.0, 1.5, 4.0]
    losses = [-1.0, -2.0, -1.5]
    pf = calculate_profit_factor(wins, losses)
    print(f"Profit Factor: {pf:.2f}")
    
    # 테스트 4: Calmar Ratio
    annual_ret = 25.0
    max_dd_pct = -12.5
    calmar = calculate_calmar_ratio(annual_ret, max_dd_pct)
    print(f"Calmar Ratio: {calmar:.2f}")
    
    # 테스트 5: 전체 성과 요약
    print("\n=== 실제 데이터 기반 성과 요약 ===")
    print_performance_report(90)
