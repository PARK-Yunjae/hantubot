# hantubot_prod/hantubot/strategies/opening_breakout_strategy.py
import datetime as dt
from typing import List, Dict, Any
import pandas as pd
import ta

from .base_strategy import BaseStrategy
from ..core.portfolio import Portfolio
from ..reporting.logger import get_logger

logger = get_logger(__name__)

class OpeningBreakoutStrategy(BaseStrategy):
    """
    시초가 갭 상승 및 거래량 돌파 전략.
    - 전일 특정 조건(거래대금, 양봉 등)을 만족한 종목을 선정.
    - 당일 시초가가 갭 상승하고, 장 초반(09:00~09:15) 거래량이 급증할 때 매수.
    - 목표 수익률 또는 손절 라인 도달 시 매도.
    """
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker, clock, notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        self.target_symbols: List[str] = []
        self.screened_at: dt.date = None
        self.trade_window_start = dt.time(9, 0)
        self.trade_window_end = dt.time(9, 15)
        logger.info(f"'{self.name}' initialized. Trade window: {self.trade_window_start}-{self.trade_window_end}")

    async def _pre_market_screen(self):
        """
        장 시작 전 (e.g., 08:50)에 실행될 스크리닝 로직.
        - 전일 거래대금 상위 40개 종목을 필터링.
        - 전일 양봉, 윗꼬리가 짧은 종목 등의 조건 추가.
        """
        today = self.clock.get_current_time().date()
        if self.screened_at == today and self.target_symbols:
            return  # 이미 오늘 스크리닝 완료

        logger.info(f"[{self.name}] Running pre-market screening...")
        self.target_symbols = [] # Reset target list for the day
        
        try:
            # 1. 전일 거래량 상위 종목 조회
            volume_leaders = self.broker.get_volume_leaders(top_n=40)
            if not volume_leaders:
                logger.warning("Could not retrieve volume leaders. Screening aborted.")
                return

            candidate_symbols = [item['hts_kor_isnm'] for item in volume_leaders]
            logger.info(f"Found {len(candidate_symbols)} volume leaders. Now filtering...")

            # 2. 각 종목 필터링
            for item in volume_leaders:
                symbol = item['mksc_shrn_iscd']
                
                # 일봉 데이터 조회 (최근 2일치만 필요)
                hist_data = self.broker.get_historical_daily_data(symbol, days=2)
                if not hist_data or len(hist_data) < 1:
                    logger.debug(f"[{symbol}] Not enough historical data to analyze.")
                    continue

                # API 응답은 최신순이므로 첫 번째 데이터가 전일 데이터
                prev_day = hist_data[0]
                prev_open = float(prev_day['stck_oprc'])
                prev_close = float(prev_day['stck_clpr'])
                prev_high = float(prev_day['stck_hgpr'])
                prev_low = float(prev_day['stck_lwpr'])

                # 조건 1: 전일 양봉 (종가 > 시가)
                if prev_close <= prev_open:
                    continue
                
                # 조건 2: 윗꼬리가 짧음 (주관적 기준: 윗꼬리가 전체 캔들 길이의 30% 미만)
                candle_range = prev_high - prev_low
                upper_shadow = prev_high - prev_close
                if candle_range > 0 and (upper_shadow / candle_range) >= 0.3:
                    continue
                
                # 모든 필터 통과
                self.target_symbols.append(symbol)
                logger.debug(f"[{symbol}] Passed screening criteria.")

        except Exception as e:
            logger.error(f"Error during pre-market screening: {e}", exc_info=True)
            self.notifier.send_alert(f"[{self.name}] 스크리닝 중 오류 발생", level='error')
        
        self.screened_at = today
        if self.target_symbols:
            logger.info(f"Screening complete. {len(self.target_symbols)} target(s) for today: {self.target_symbols}")
            self.notifier.send_alert(f"금일의 시초가 돌파 전략 대상 종목: {len(self.target_symbols)}개", level='info')
        else:
            logger.warning("No symbols passed the screening criteria for today.")

    async def generate_signal(self, current_data: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        """
        장 중(09:00~09:15)에 매수 신호를 생성하고, 보유 종목의 청산 신호를 생성합니다.
        """
        signals = []
        now = self.clock.get_current_time()

        # 1. 장 시작 전 스크리닝 실행
        await self._pre_market_screen()

        # 2. 매수 로직: 매매 시간 창인지 확인 (09:00 ~ 09:15)
        if self.trade_window_start <= now.time() < self.trade_window_end:
            for symbol in self.target_symbols:
                # 이미 이 전략으로 포지션을 보유하고 있다면 매수하지 않음
                if portfolio.get_position(symbol, self.strategy_id):
                    continue

                try:
                    # 데이터 조회 (지표 계산을 위해 30일치 데이터 요청)
                    hist_data_raw = self.broker.get_historical_daily_data(symbol, days=30)
                    if not hist_data_raw or len(hist_data_raw) < 20: continue # 최소 20일 데이터 확보
                    
                    # Pandas DataFrame으로 변환
                    df = pd.DataFrame(hist_data_raw)
                    df = df.iloc[::-1].reset_index(drop=True) # 역순 정렬 (과거 -> 현재)
                    df['stck_clpr'] = pd.to_numeric(df['stck_clpr'])

                    # 전일, 금일 데이터 추출
                    prev_day = hist_data_raw[1]
                    today_candle_info = hist_data_raw[0]
                    
                    prev_close = float(prev_day['stck_clpr'])
                    today_open = float(today_candle_info['stck_oprc'])
                    current_price = self.broker.get_current_price(symbol)
                    if prev_close == 0 or today_open == 0 or current_price == 0: continue

                    # 조건 1: 시초가 갭 (+2% ~ +7%)
                    gap = ((today_open / prev_close) - 1) * 100
                    if not (2.0 <= gap <= 7.0):
                        continue

                    # 조건 2: 1분 거래량 > 전일 평균 1분 거래량의 3배
                    prev_day_volume = float(prev_day['acml_vol'])
                    avg_1m_volume = prev_day_volume / 390 if prev_day_volume > 0 else 1
                    
                    minute_data = self.broker.get_intraday_minute_data(symbol)
                    if not minute_data: continue
                    
                    current_1m_volume = float(minute_data[0]['cntg_vol'])
                    volume_spike_ratio = current_1m_volume / avg_1m_volume if avg_1m_volume > 0 else 0
                    if volume_spike_ratio <= 3.0:
                        continue

                    # 조건 3: 시초가 돌파
                    if current_price <= today_open:
                        continue

                    # 모든 조건 충족: 매수 신호 생성
                    logger.info(f"[{self.name}] Entry signal for {symbol}. Gap: {gap:.2f}%, Vol Ratio: {volume_spike_ratio:.1f}")
                    
                    # ML 특징 계산
                    df['rsi_14'] = ta.momentum.rsi(df['stck_clpr'], window=14)
                    df['ma_5'] = ta.trend.sma_indicator(df['stck_clpr'], window=5)
                    ma_5_slope = (df['ma_5'].iloc[-1] / df['ma_5'].iloc[-2] - 1) * 100 if len(df['ma_5'].dropna()) > 1 else 0
                    bollinger = ta.volatility.BollingerBands(close=df['stck_clpr'], window=20, window_dev=2)
                    bollinger_width = ((bollinger.bollinger_hband() - bollinger.bollinger_lband()) / bollinger.bollinger_mavg()) * 100

                    features = {
                        "gap_percent": round(gap, 2),
                        "volume_spike_ratio": round(volume_spike_ratio, 2),
                        "rsi_14_daily": round(df['rsi_14'].iloc[-2], 2), # 신호 시점은 전일 RSI가 유효
                        "ma_5_slope_daily": round(ma_5_slope, 4),
                        "bollinger_width_daily": round(bollinger_width.iloc[-2], 2)
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
                        'price': 0, # 시장가 주문
                        'order_type': 'market',
                        'features': features
                    }
                    signals.append(buy_signal)
                    self.notifier.send_alert(f"[{self.name}] 매수 신호: {symbol} ({quantity}주)", level='info')
                    
                except Exception as e:
                    logger.error(f"Error processing entry signal for {symbol}: {e}", exc_info=True)

        # 3. 매도 로직
        for symbol, position in portfolio.get_positions().items():
            if position.get('strategy_id') != self.strategy_id:
                continue

            try:
                current_price = self.broker.get_current_price(symbol)
                if current_price == 0: continue

                purchase_price = position['avg_price']
                pnl = ((current_price / purchase_price) - 1) * 100
                should_sell = False
                reason = ""

                # 조건 1: 익절 (+3%)
                if pnl >= 3.0:
                    should_sell = True
                    reason = f"Profit-taking ({pnl:.2f}%)"
                
                # 조건 2: 손절 (-2%)
                elif pnl <= -2.0:
                    should_sell = True
                    reason = f"Stop-loss ({pnl:.2f}%)"

                # 조건 3: 시간 기반 청산 (09:30 이후, 수익률 1% 미만)
                elif now.time() > dt.time(9, 30) and pnl < 1.0:
                    should_sell = True
                    reason = f"Time-based exit ({now.strftime('%H:%M:%S')})"
                
                if should_sell:
                    logger.info(f"[{self.name}] Exit signal for {symbol}. Reason: {reason}")
                    sell_signal = {
                        'strategy_id': self.strategy_id,
                        'symbol': symbol,
                        'side': 'sell',
                        'quantity': position['quantity'],
                        'price': 0, # 시장가 주문
                        'order_type': 'market'
                    }
                    signals.append(sell_signal)
                    self.notifier.send_alert(f"[{self.name}] 매도 신호: {symbol} ({position['quantity']}주) - {reason}", level='info')

            except Exception as e:
                logger.error(f"Error processing exit signal for {symbol}: {e}", exc_info=True)
            
        return signals
