# hantubot_prod/hantubot/strategies/opening_breakout_strategy.py
import datetime as dt
from typing import List, Dict, Any
import pandas as pd
import ta

from .base_strategy import BaseStrategy
from ..core.portfolio import Portfolio
from ..reporting.logger import get_logger
from ..utils.stock_filters import is_eligible_stock

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
        logger.info(f"'{self.name}' 초기화 완료. 거래 시간: {self.trade_window_start}-{self.trade_window_end}")

    async def _pre_market_screen(self):
        """
        장 시작 전 (e.g., 08:50)에 실행될 스크리닝 로직.
        - 전일 거래대금 상위 40개 종목을 필터링.
        - 전일 양봉, 윗꼬리가 짧은 종목 등의 조건 추가.
        """
        today = dt.datetime.now().date()
        if self.screened_at == today and self.target_symbols:
            return  # 이미 오늘 스크리닝 완료

        logger.info(f"[{self.name}] 장전 스크리닝 실행 중...")
        self.target_symbols = [] # Reset target list for the day
        
        try:
            # 1. 전일 거래량 상위 종목 조회
            volume_leaders_raw = self.broker.get_volume_leaders(top_n=40)
            if not volume_leaders_raw:
                logger.warning("거래량 상위 종목을 조회할 수 없습니다. 스크리닝을 중단합니다.")
                return

            # [수정] ETF, 스팩 등 필터링
            volume_leaders = [
                item for item in volume_leaders_raw 
                if is_eligible_stock(item.get('hts_kor_isnm', ''))
            ]
            logger.info(f"Found {len(volume_leaders)} eligible volume leaders after filtering. Now analyzing...")

            # 2. 각 종목 필터링
            for item in volume_leaders:
                symbol = item['mksc_shrn_iscd']
                
                # 일봉 데이터 조회 (최근 2일치만 필요)
                hist_data = self.broker.get_historical_daily_data(symbol, days=2)
                if not hist_data or len(hist_data) < 2: # 전일 데이터 비교를 위해 최소 2개 필요
                    logger.debug(f"[{symbol}] Not enough historical data to analyze.")
                    continue
                
                # API 응답은 최신순이므로 첫 번째 데이터가 전일 데이터
                prev_day = hist_data[1] # 전전일 데이터가 아닌 전일 데이터 사용
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
                logger.debug(f"[{symbol}] 스크리닝 조건 통과.")

        except Exception as e:
            logger.error(f"장전 스크리닝 중 오류 발생: {e}", exc_info=True)
            self.notifier.send_alert(f"[{self.name}] 스크리닝 중 오류 발생", level='error')
        
        self.screened_at = today
        if self.target_symbols:
            logger.info(f"Screening complete. {len(self.target_symbols)} target(s) for today: {self.target_symbols}")
            self.notifier.send_alert(f"금일의 시초가 돌파 전략 대상 종목: {len(self.target_symbols)}개", level='info')
        else:
            logger.warning("금일 스크리닝 조건에 맞는 종목이 없습니다.")

    async def generate_signal(self, current_data: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        """
        매수/매도 신호를 생성합니다. 매수 로직은 09:00-09:15 사이에만 실행됩니다.
        매도 로직은 장중 항상 실행되어 시간 기반 청산 등을 처리합니다.
        """
        now = dt.datetime.now()
        signals = []
        my_positions = portfolio.get_positions_by_strategy(self.strategy_id)

        # --- 1. 매도 로직 (보유 종목이 있을 경우, 항상 실행) ---
        if my_positions:
            for symbol, position in my_positions.items():
                try:
                    current_price = self.broker.get_current_price(symbol)
                    if current_price == 0: continue

                    pnl = ((current_price / position['avg_price']) - 1) * 100
                    should_sell, reason = False, ""

                    if pnl >= 3.0:
                        should_sell, reason = True, f"익절 ({pnl:.2f}%)"
                    elif pnl <= -2.0:
                        should_sell, reason = True, f"손절 ({pnl:.2f}%)"
                    elif now.time() > dt.time(9, 30) and pnl < 1.0:
                        should_sell, reason = True, f"시간 기반 청산 ({now.strftime('%H:%M:%S')})"
                    
                    if should_sell:
                        logger.info(f"[{self.name}] {symbol} 매도 신호. 사유: {reason}")
                        signals.append({
                            'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'sell',
                            'quantity': position['quantity'], 'order_type': 'market', 'price': 0,
                        })
                        self.notifier.send_alert(f"[{self.name}] 매도 신호: {symbol} ({position['quantity']}주) - {reason}", level='info')
                        return signals # 매도 신호 발생 시 즉시 반환
                except Exception as e:
                    logger.error(f"[{self.name}] 매도 신호 처리 중 오류 발생: {e}", exc_info=True)
            
            # 보유 포지션이 있으므로, 신규 매수 로직은 실행하지 않고 종료
            return signals

        # --- 2. 매수 로직 (보유 종목이 없고, 지정된 시간일 때만 실행) ---
        if not (self.trade_window_start <= now.time() < self.trade_window_end):
            return [] # 매수 시간이 아니면 아무것도 안함

        # 매수 시간이 맞으면, 스크리닝 및 매수 신호 생성 로직 실행
        try:
            # 오늘 스크리닝을 아직 안했다면 실행
            if self.screened_at != now.date():
                await self._pre_market_screen()

            if not self.target_symbols:
                return [] # 대상 종목이 없으면 종료

            for symbol in self.target_symbols:
                # API 호출 최소화를 위해 루프 안에서 필요한 데이터만 조회
                hist_data = self.broker.get_historical_daily_data(symbol, days=2)
                if not hist_data or len(hist_data) < 2: continue
                
                prev_day = hist_data[1]
                today_open = float(self.broker.get_current_price(symbol)) # 시초가 대신 현재가로 로직 단순화
                
                prev_close = float(prev_day['stck_clpr'])
                if prev_close == 0: continue

                gap = ((today_open / prev_close) - 1) * 100
                if not (2.0 <= gap <= 7.0): continue

                current_price = self.broker.get_current_price(symbol)
                if current_price == 0 or current_price <= today_open_or_current: continue
                
                # 분봉 거래량 급증 확인
                prev_day_volume = float(prev_day['acml_vol'])
                if prev_day_volume == 0: continue
                
                # 전일 평균 1분 거래량
                avg_1m_volume = prev_day_volume / 390 
                
                minute_data = self.broker.get_intraday_minute_data(symbol)
                if not minute_data: continue
                
                current_1m_volume = float(minute_data[0]['cntg_vol'])
                volume_spike_ratio = current_1m_volume / avg_1m_volume if avg_1m_volume > 0 else 0
                
                # 첫 1분봉 거래량이 전일 평균 분당 거래량의 3배 이상일 때
                if volume_spike_ratio <= 3.0: continue

                logger.info(f"[{self.name}] 진입 신호: {symbol}. 갭: {gap:.2f}%, 거래량 비율: {volume_spike_ratio:.1f}")
                
                available_cash = portfolio.get_cash()
                order_amount = available_cash * 0.95
                quantity = int(order_amount // current_price)
                if quantity == 0: continue

                signals.append({
                    'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'buy',
                    'quantity': quantity, 'price': 0, 'order_type': 'market',
                })
                self.notifier.send_alert(f"[{self.name}] 매수 신호 (최대): {symbol} {quantity}주", level='info')
                return signals # 한 종목만 매수하고 종료
        
        except Exception as e:
            logger.error(f"[{self.name}] 매수 신호 생성 중 오류 발생: {e}", exc_info=True)

        return signals
