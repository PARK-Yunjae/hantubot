# hantubot_prod/hantubot/utils/kelly_calculator.py
"""
Kelly Criterion 계산기
- 과거 매매 성과를 기반으로 최적 포지션 크기 계산
- Half-Kelly 적용으로 안정성 확보
"""
import sqlite3
from typing import Tuple, Optional
from datetime import datetime, timedelta
import os


def calculate_kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly Criterion 계산 (Half-Kelly 적용)
    
    공식: f* = (p*b - q) / b
    
    Args:
        win_rate: 승률 (0~1)
        avg_win: 평균 수익률 (양수)
        avg_loss: 평균 손실률 (음수)
    
    Returns:
        Kelly 비율 (0~1), Half-Kelly 적용
    """
    if win_rate <= 0 or win_rate >= 1:
        return 0.0
    
    if avg_win <= 0 or avg_loss >= 0:
        return 0.0
    
    q = 1 - win_rate
    b = avg_win / abs(avg_loss)  # 승률 대비 손익비
    
    kelly = (win_rate * b - q) / b
    
    # Half-Kelly (안정성)
    half_kelly = kelly * 0.5
    
    # 0~1 사이로 제한
    return max(0.0, min(half_kelly, 1.0))


def get_historical_performance(symbol: Optional[str] = None, 
                               strategy_id: Optional[str] = None,
                               days: int = 90) -> Tuple[float, float, float]:
    """
    과거 매매 성과 분석
    
    Args:
        symbol: 종목 코드 (None이면 전체)
        strategy_id: 전략 ID (None이면 전체)
        days: 분석 기간 (일)
    
    Returns:
        (win_rate, avg_win, avg_loss)
    """
    db_path = os.path.join('data', 'trading_performance.db')
    
    if not os.path.exists(db_path):
        # DB 없으면 기본값 반환
        return 0.5, 0.02, -0.02
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 날짜 필터
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # WHERE 절 구성
        where_clauses = ["timestamp >= ?"]
        params = [start_date]
        
        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol)
        
        if strategy_id:
            where_clauses.append("strategy_name = ?")
            params.append(strategy_id)
        
        where_sql = " AND ".join(where_clauses)
        
        # 전체 거래 조회
        query = f"""
        SELECT pnl_pct 
        FROM trades 
        WHERE {where_sql} AND pnl_pct IS NOT NULL
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        if not results or len(results) < 5:
            # 데이터 부족 시 기본값
            return 0.5, 0.02, -0.02
        
        pnl_list = [row[0] for row in results]
        
        # 승/패 분류
        wins = [pnl for pnl in pnl_list if pnl > 0]
        losses = [pnl for pnl in pnl_list if pnl < 0]
        
        if not wins or not losses:
            # 승 또는 패만 있으면 기본값
            return 0.5, 0.02, -0.02
        
        # 승률
        win_rate = len(wins) / len(pnl_list)
        
        # 평균 수익률 / 손실률
        avg_win = sum(wins) / len(wins) / 100  # % -> 소수
        avg_loss = sum(losses) / len(losses) / 100
        
        return win_rate, avg_win, avg_loss
    
    except Exception as e:
        print(f"성과 분석 오류: {e}")
        return 0.5, 0.02, -0.02


def calculate_position_size_kelly(cash: float, 
                                  current_price: float,
                                  symbol: Optional[str] = None,
                                  strategy_id: Optional[str] = None) -> int:
    """
    Kelly 기준 포지션 크기 계산
    
    Args:
        cash: 가용 현금
        current_price: 현재가
        symbol: 종목 코드 (선택)
        strategy_id: 전략 ID (선택)
    
    Returns:
        매수 수량
    """
    # 과거 성과 조회
    win_rate, avg_win, avg_loss = get_historical_performance(symbol, strategy_id)
    
    # Kelly 비율 계산
    kelly = calculate_kelly_fraction(win_rate, avg_win, avg_loss)
    
    # 포지션 크기
    position_value = cash * kelly
    quantity = int(position_value // current_price)
    
    return max(1, quantity)  # 최소 1주


if __name__ == '__main__':
    # 테스트
    print("=== Kelly Criterion 계산기 테스트 ===\n")
    
    # 예시 1: 승률 60%, 평균 수익 3%, 평균 손실 -2%
    win_rate = 0.6
    avg_win = 0.03
    avg_loss = -0.02
    kelly = calculate_kelly_fraction(win_rate, avg_win, avg_loss)
    
    print(f"승률: {win_rate*100:.1f}%")
    print(f"평균 수익: {avg_win*100:.1f}%")
    print(f"평균 손실: {avg_loss*100:.1f}%")
    print(f"Kelly 비율 (Half): {kelly*100:.1f}%")
    print(f"→ 100만원 중 {kelly*1000000:,.0f}원 투자 권장\n")
    
    # 예시 2: 과거 성과 기반
    print("=== 과거 성과 기반 계산 ===")
    hist_win_rate, hist_avg_win, hist_avg_loss = get_historical_performance()
    hist_kelly = calculate_kelly_fraction(hist_win_rate, hist_avg_win, hist_avg_loss)
    
    print(f"과거 승률: {hist_win_rate*100:.1f}%")
    print(f"과거 평균 수익: {hist_avg_win*100:.2f}%")
    print(f"과거 평균 손실: {hist_avg_loss*100:.2f}%")
    print(f"Kelly 비율 (Half): {hist_kelly*100:.1f}%")
    
    # 예시 3: 포지션 크기 계산
    cash = 100000
    price = 50000
    quantity = calculate_position_size_kelly(cash, price)
    print(f"\n현금 {cash:,}원, 주가 {price:,}원")
    print(f"→ 권장 매수 수량: {quantity}주 ({quantity * price:,}원)")
