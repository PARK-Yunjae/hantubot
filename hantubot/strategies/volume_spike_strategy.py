# hantubot_prod/hantubot/strategies/volume_spike_strategy.py
import datetime as dt
from typing import List, Dict, Any
import pandas as pd
import ta

from .base_strategy import BaseStrategy
from ..core.portfolio import Portfolio
from ..reporting.logger import get_logger

logger = get_logger(__name__)

class VolumeSpikeStrategy(BaseStrategy):
    """
    실시간 거래량 순위 급상승을 감지하여 추격 매수하는 전략.
    - 주기적으로 거래량 상위 종목을 스캔.
    - 순위권 밖에 있던 종목이 특정 순위 안으로 갑자기 진입하면 매수.
    - 목표 수익률 도달, 손절 라인 터치, 또는 순위 이탈 시 매도.
    """
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker, clock, notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        # 이전 순위를 저장하기 위한 상태 변수. {'symbol': rank}
        self.previous_ranks: Dict[str, int] = {}
        # 마지막으로 순위를 확인한 시간
        self.last_checked: dt.datetime = None
        self.trade_window_start = dt.time(9, 30)
        self.trade_window_end = dt.time(14, 50)
        logger.info(f"'{self.name}' initialized. Trade window: {self.trade_window_start}-{self.trade_window_end}")

    async def generate_signal(self, current_data: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        """
        거래량 순위 변화를 감지하여 매수/매도 신호를 생성합니다.
        """
        signals = []
        now = self.clock.get_current_time()

        # 1. 매매 시간 창인지 확인 (09:30 ~ 14:50)
        if not (self.trade_window_start <= now.time() < self.trade_window_end):
            return signals

        # 2. 1분에 한 번만 순위를 확인하도록 제한
        if self.last_checked and (now - self.last_checked).total_seconds() < 60:
            return signals
        self.last_checked = now
        
        logger.debug(f"[{self.name}] Running volume rank check...")

        # 3. 매수 로직: 순위 급상승 감지
        current_ranks: Dict[str, int] = {}
        try:
            leaders = self.broker.get_volume_leaders(top_n=100)
            if not leaders:
                logger.warning(f"[{self.name}] Could not retrieve volume leaders.")
                return signals

            for i, item in enumerate(leaders):
                current_ranks[item['mksc_shrn_iscd']] = i + 1
            
            # 순위 비교 및 신호 생성
            for symbol, rank in current_ranks.items():
                prev_rank = self.previous_ranks.get(symbol, 101) # 이전 순위 없으면 101위로 간주

                # 조건: 30위권 밖 -> 10위권 안으로 진입
                if prev_rank > 30 and rank <= 10:
                    # 안전장치 1: 이미 포지션을 보유하고 있는지 확인
                    if portfolio.get_position(symbol):
                        continue
                    
                    # 안전장치 2: 최소 가격 (동전주 제외)
                    current_price = self.broker.get_current_price(symbol)
                    if current_price < 1000:
                        continue

                    # ML 특징 계산
                    hist_data_raw = self.broker.get_historical_daily_data(symbol, days=30)
                    if not hist_data_raw or len(hist_data_raw) < 20: continue

                    df = pd.DataFrame(hist_data_raw)
                    df = df.iloc[::-1].reset_index(drop=True)
                    df['stck_clpr'] = pd.to_numeric(df['stck_clpr'])
                    
                    df['rsi_14'] = ta.momentum.rsi(df['stck_clpr'], window=14)
                    df['ma_5'] = ta.trend.sma_indicator(df['stck_clpr'], window=5)
                    ma_5_slope = (df['ma_5'].iloc[-1] / df['ma_5'].iloc[-2] - 1) * 100 if len(df['ma_5'].dropna()) > 1 else 0
                    bollinger = ta.volatility.BollingerBands(close=df['stck_clpr'], window=20, window_dev=2)
                    bollinger_width = ((bollinger.bollinger_hband() - bollinger.bollinger_lband()) / bollinger.bollinger_mavg()) * 100

                    features = {
                        "rank_previous": prev_rank,
                        "rank_current": rank,
                        "rsi_14_daily": round(df['rsi_14'].iloc[-1], 2),
                        "ma_5_slope_daily": round(ma_5_slope, 4),
                        "bollinger_width_daily": round(bollinger_width.iloc[-1], 2)
                    }

                    # 주문 수량 계산 (약 100만원)
                    order_amount = 1_000_000
                    quantity = int(order_amount // current_price)
                    if quantity == 0: continue

                    buy_signal = {
                        'strategy_id': self.strategy_id,
                        'symbol': symbol,
                        'side': 'buy',
                        'quantity': quantity,
                        'price': 0,
                        'order_type': 'market',
                        'features': features
                    }
                    signals.append(buy_signal)
                    self.notifier.send_alert(f"[{self.name}] 매수 신호: {symbol} (순위 급상승 {prev_rank}→{rank})", level='info')
            
            # 다음 조회를 위해 현재 순위를 이전 순위로 업데이트
            self.previous_ranks = current_ranks

        except Exception as e:
            logger.error(f"[{self.name}] Error during entry logic: {e}", exc_info=True)


        # 4. 매도 로직: 보유 종목 순위 이탈 또는 손익 감지
        # 매수 로직에서 순위가 업데이트 되었으므로, 보유 종목의 현재 순위를 알 수 있음
        positions = portfolio.get_positions()
        if not positions: # 보유 종목 없으면 바로 종료
             return signals

        for symbol, position in positions.items():
            if position.get('strategy_id') != self.strategy_id:
                continue
            
            try:
                should_sell = False
                reason = ""
                
                # 조건 1 & 2: 익절 또는 손절
                current_price = self.broker.get_current_price(symbol)
                if current_price > 0:
                    pnl = ((current_price / position['avg_price']) - 1) * 100
                    if pnl >= 2.0:
                        should_sell = True
                        reason = f"Profit-taking ({pnl:.2f}%)"
                    elif pnl <= -2.0:
                        should_sell = True
                        reason = f"Stop-loss ({pnl:.2f}%)"
                
                # 조건 3: 순위 이탈
                current_rank = self.previous_ranks.get(symbol, 101) # self.previous_ranks는 이미 현재 순위로 업데이트됨
                if not should_sell and current_rank > 30:
                    should_sell = True
                    reason = f"Rank drop ({current_rank})"
                
                if should_sell:
                    logger.info(f"[{self.name}] Exit signal for {symbol}. Reason: {reason}")
                    sell_signal = {
                        'strategy_id': self.strategy_id,
                        'symbol': symbol,
                        'side': 'sell',
                        'quantity': position['quantity'],
                        'price': 0,
                        'order_type': 'market'
                    }
                    signals.append(sell_signal)
                    self.notifier.send_alert(f"[{self.name}] 매도 신호: {symbol} ({position['quantity']}주) - {reason}", level='info')

            except Exception as e:
                logger.error(f"[{self.name}] Error during exit logic for {symbol}: {e}", exc_info=True)
            
        return signals
