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
        장 시작 전 스크리닝 로직 - 유목민 철학 적용
        - 전일 거래대금 500억 이상인 '확신 신호' 종목만 타겟팅.
        """
        today = dt.datetime.now().date()
        if self.screened_at == today and self.target_symbols:
            return

        logger.info(f"[{self.name}] 장전 스크리닝 실행 중 (유목민 철학: 500억 봉)")
        self.target_symbols = []
        
        try:
            # 1. 전일 거래대금 상위 종목 조회 (넉넉하게 50개)
            # get_volume_leaders는 거래량 기준이지만, 거래대금 필터를 위해 사용
            volume_leaders_raw = self.broker.get_volume_leaders(top_n=50)
            if not volume_leaders_raw:
                return

            volume_leaders = [
                item for item in volume_leaders_raw 
                if is_eligible_stock(item.get('hts_kor_isnm', ''))
            ]
            
            # 2. 각 종목 필터링
            for item in volume_leaders:
                symbol = item['mksc_shrn_iscd']
                
                # 거래대금 확인 (API 응답에 acml_tr_pbmn 필드가 있다고 가정)
                try:
                    trading_value = float(item.get('acml_tr_pbmn', 0))
                except (ValueError, TypeError):
                    trading_value = 0
                
                # [유목민 철학] 500억 봉 법칙: 전일 거래대금 500억 이상
                if trading_value < 50000000000:
                    continue

                # 일봉 데이터 확인 (양봉 조건)
                hist_data = self.broker.get_historical_daily_data(symbol, days=2)
                if not hist_data or len(hist_data) < 2:
                    continue
                
                prev_day = hist_data[1]
                prev_open = float(prev_day['stck_oprc'])
                prev_close = float(prev_day['stck_clpr'])

                # 전일 양봉 조건
                if prev_close <= prev_open:
                    continue
                
                self.target_symbols.append(symbol)
                logger.debug(f"[{symbol}] 스크리닝 통과 (거래대금: {trading_value/100000000:.1f}억)")

        except Exception as e:
            logger.error(f"장전 스크리닝 중 오류 발생: {e}", exc_info=True)
        
        self.screened_at = today
        if self.target_symbols:
            logger.info(f"Screening complete. {len(self.target_symbols)} target(s): {self.target_symbols}")
            self.notifier.send_alert(f"금일 시초가 돌파 대상(500억↑): {len(self.target_symbols)}개", level='info')

    async def generate_signal(self, current_data: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        """
        매수 신호 생성 로직 - 유목민 철학 적용
        - 시가 갭 3~7%
        - 초반 화력 집중 (거래대금 폭발)
        """
        now = dt.datetime.now()
        signals = []
        my_positions = portfolio.get_positions_by_strategy(self.strategy_id)

        # 1. 매도 로직 (기존 유지)
        if my_positions:
            for symbol, position in my_positions.items():
                try:
                    current_price = self.broker.get_current_price(symbol)
                    if current_price == 0: continue

                    pnl = ((current_price / position['avg_price']) - 1) * 100
                    should_sell, reason = False, ""

                    if pnl >= 5.0: # 유목민 스타일: 슈팅 나오면 크게 먹기 위해 목표 상향 (3% -> 5%)
                        should_sell, reason = True, f"익절 ({pnl:.2f}%)"
                    elif pnl <= -2.0:
                        should_sell, reason = True, f"손절 ({pnl:.2f}%)"
                    
                    if should_sell:
                        logger.info(f"[{self.name}] {symbol} 매도 신호. 사유: {reason}")
                        signals.append({
                            'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'sell',
                            'quantity': position['quantity'], 'order_type': 'market', 'price': 0,
                        })
                        self.notifier.send_alert(f"[{self.name}] 매도: {symbol} - {reason}", level='info')
                        return signals
                except Exception as e:
                    logger.error(f"매도 처리 중 오류: {e}")
            return signals

        # 2. 매수 로직
        if not (self.trade_window_start <= now.time() < self.trade_window_end):
            return []

        try:
            if self.screened_at != now.date():
                await self._pre_market_screen()

            if not self.target_symbols:
                return []

            for symbol in self.target_symbols:
                hist_data = self.broker.get_historical_daily_data(symbol, days=2)
                if not hist_data or len(hist_data) < 2: continue
                
                prev_day = hist_data[1]
                prev_close = float(prev_day['stck_clpr'])
                prev_trading_value = float(prev_day.get('acml_tr_pbmn', 0)) # 전일 거래대금
                if prev_trading_value == 0: continue

                # 실시간 시가/현재가 조회
                current_price_info = self.broker.get_current_price_detail(symbol) # 상세 정보 필요 (시가 등)
                if not current_price_info: continue
                
                today_open = float(current_price_info.get('stck_oprc', 0))
                current_price = float(current_price_info.get('stck_prpr', 0))
                
                if today_open == 0: continue

                # [유목민 철학] 갭 보정: 3~7% 사이
                gap = ((today_open / prev_close) - 1) * 100
                if not (3.0 <= gap <= 7.0):
                    continue

                if current_price <= today_open: # 시가 아래로 밀리면 패스
                    continue
                
                # [유목민 철학] 초반 화력: 3분간 거래대금 확인
                # 전일 분당 평균 거래대금 = 전일 거래대금 / 390분
                avg_1m_trading_value = prev_trading_value / 390
                
                minute_data = self.broker.get_intraday_minute_data(symbol)
                if not minute_data or not isinstance(minute_data, list) or len(minute_data) == 0:
                    continue
                
                # 현재 1분 거래대금 (acml_tr_pbmn 필드 사용 가정)
                # KIS API 분봉 조회 시 acml_tr_pbmn 필드가 있음
                current_1m_value = float(minute_data[0].get('acml_tr_pbmn', 0))
                
                # 전일 분당 평균 대비 5배 이상 터졌는지 확인
                if current_1m_value < (avg_1m_trading_value * 5):
                    continue

                logger.info(f"[{self.name}] 진입: {symbol}. 갭:{gap:.1f}%, 화력:{current_1m_value/100000000:.1f}억")
                
                available_cash = portfolio.get_cash()
                order_amount = available_cash * 0.90
                quantity = int(order_amount // current_price)
                if quantity == 0: continue

                signals.append({
                    'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'buy',
                    'quantity': quantity, 'price': 0, 'order_type': 'market',
                })
                self.notifier.send_alert(f"[{self.name}] 강력 매수(500억봉+화력): {symbol} {quantity}주", level='info')
                return signals
        
        except Exception as e:
            logger.error(f"[{self.name}] 매수 로직 오류: {e}", exc_info=True)

        return signals
