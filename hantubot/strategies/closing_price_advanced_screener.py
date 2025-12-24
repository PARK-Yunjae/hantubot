# hantubot_prod/hantubot/strategies/closing_price_advanced_screener.py
import datetime as dt
from typing import Dict, List, Any
import pandas as pd
from ta.trend import cci, sma_indicator

from .base_strategy import BaseStrategy
from ..core.portfolio import Portfolio
from ..core.clock import MarketClock
from ..execution.broker import Broker
from ..reporting.logger import get_logger
from ..reporting.notifier import Notifier

logger = get_logger(__name__)

from ta.trend import ADXIndicator

from .base_strategy import BaseStrategy
from ..core.portfolio import Portfolio
from ..core.clock import MarketClock
from ..execution.broker import Broker
from ..reporting.logger import get_logger
from ..reporting.notifier import Notifier
from ..utils.stock_filters import is_eligible_stock

logger = get_logger(__name__)

class ClosingPriceAdvancedScreener(BaseStrategy):
    """
    고급 종가매매 스크리너 전략. (v2: 종합 점수 모델)
    - 종합 점수 = (CCI 점수 x 40%) + (거래량 점수 x 30%) + (추세강도(ADX) 점수 x 30%)
    - 동작: 15:08 경에 조건에 맞는 상위 3개 종목을 점수와 함께 Discord로 알림
    """
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker: Broker, clock: MarketClock, notifier: Notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        self.run_time = dt.time(15, 3) # 실행 시간 15:03으로 변경
        # 지표 설정
        self.cci_period = self.config.get('cci_period', 14)
        self.sma_period = self.config.get('sma_period', 20)
        self.adx_period = self.config.get('adx_period', 14)
        self.volume_sma_period = self.config.get('volume_sma_period', 20)
        # 스크리닝 설정
        self.cci_target = self.config.get('cci_target', 180)
        self.cci_tolerance = self.config.get('cci_tolerance', 40)
        self.adx_min_threshold = self.config.get('adx_min_threshold', 20)
        self.top_n_volume = self.config.get('top_n_volume', 30)
        self.top_n_screen = self.config.get('top_n_screen', 3)
        # 자동 매수 설정
        self.auto_buy_enabled = self.config.get('auto_buy_enabled', True)
        self.buy_quantity = self.config.get('buy_quantity', 1)
        self.has_run_today = False

    async def generate_signal(self, data_payload: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        now = dt.datetime.now()
        
        # 하루 한 번, 지정된 시간에만 실행
        if now.time() < self.run_time or self.has_run_today:
            if now.hour > 16: self.has_run_today = False
            return signals

        logger.info(f"[{self.name}] 고급 스크리너 실행. 시간: {now.strftime('%H:%M:%S')}")
        self.has_run_today = True

        try:
            # KIS API를 통해 실시간 거래대금 상위 종목 조회
            top_volume_stocks_raw = self.broker.get_realtime_transaction_ranks(top_n=self.top_n_volume)
            if not top_volume_stocks_raw:
                logger.warning(f"[{self.name}] 실시간 거래대금 상위 종목 조회 실패.")
                return signals

            # [수정] ETF, 스팩 등 필터링
            top_volume_stocks = [
                item for item in top_volume_stocks_raw
                if is_eligible_stock(item.get('hts_kor_isnm', ''))
            ]
            logger.info(f"[{self.name}] 필터링 후 적격 종목 {len(top_volume_stocks)}개 발견.")

        except Exception as e:
            logger.error(f"[{self.name}] KIS API로 거래대금 상위 종목 조회 실패: {e}", exc_info=True)
            return signals

        screened_stocks = []
        for stock_data in top_volume_stocks:
            ticker = stock_data.get('mksc_shrn_iscd')
            stock_name = stock_data.get('hts_kor_isnm')
            if not ticker or not stock_name: continue

            try:
                hist_data = data_payload['historical_daily'].get(ticker)
                if not hist_data or len(hist_data) < self.sma_period: continue

                df = pd.DataFrame(hist_data)
                for col in ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol']:
                    df[col] = pd.to_numeric(df[col])
                df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
                
                # --- 조건 필터링 ---
                current_price = df['stck_clpr'].iloc[-1]
                sma20 = sma_indicator(df['stck_clpr'], window=self.sma_period).iloc[-1]
                if current_price <= sma20: continue

                current_cci = cci(df['stck_hgpr'], df['stck_lwpr'], df['stck_clpr'], window=self.cci_period).iloc[-1]
                if abs(current_cci - self.cci_target) > self.cci_tolerance: continue
                
                adx_indicator = ADXIndicator(df['stck_hgpr'], df['stck_lwpr'], df['stck_clpr'], window=self.adx_period)
                current_adx = adx_indicator.adx().iloc[-1]
                if current_adx < self.adx_min_threshold: continue

                # --- 점수 계산 ---
                score_cci = max(0, 100 - abs(current_cci - self.cci_target) * 2.5) # 거리가 0일때 100점, 40일때 0점
                
                vol_sma = sma_indicator(df['acml_vol'], window=self.volume_sma_period).iloc[-1]
                last_volume = df['acml_vol'].iloc[-1]
                score_volume = min(100, (last_volume / vol_sma) * 50) # 평균 거래량의 2배일 때 100점
                
                score_adx = min(100, current_adx * 2) # ADX 50일때 100점

                total_score = (score_cci * 0.4) + (score_volume * 0.3) + (score_adx * 0.3)
                
                screened_stocks.append({
                    'name': stock_name, 'ticker': ticker, 'price': current_price,
                    'score': round(total_score, 2),
                    'score_detail': f"CCI:{round(score_cci)}|거래량:{round(score_volume)}|ADX:{round(score_adx)}"
                })
            except Exception as e:
                logger.error(f"[{self.name}] {ticker} 분석 중 오류: {e}")

        if not screened_stocks:
            self.notifier.send_alert("종가매매 스크리너 결과, 조건에 맞는 종목이 없습니다.", level='info')
            return signals
            
        top_stocks = sorted(screened_stocks, key=lambda x: x['score'], reverse=True)[:self.top_n_screen]

        fields = []
        for i, stock in enumerate(top_stocks):
            fields.append({
                "name": f"{i+1}위: {stock['name']} ({stock['ticker']})",
                "value": f"**종합 점수: {stock['score']}점** ({stock['score_detail']})\n현재가: {stock['price']:,.0f}원",
                "inline": False
            })

        embed = {"title": f"🔔[Gemini Pick] 종가매매 후보 ({now.strftime('%H:%M')})", "description": "3가지 지표(모멘텀, 거래량, 추세강도)를 종합하여 선정한 후보입니다.", "color": 16705372, "fields": fields}
        self.notifier.send_alert("종가매매 후보 종목 알림", embed=embed)
        
        if self.auto_buy_enabled and top_stocks:
            # 최대 복리 테스트: 포트폴리오에 보유 종목이 없어야만 매수
            if portfolio.get_positions():
                logger.info(f"[{self.name}] 자동 매수 활성화 상태이나, 이미 보유 중인 종목이 있어 매수 신호를 생성하지 않습니다.")
                return signals

            top_stock = top_stocks[0]
            logger.info(f"[{self.name}] 자동 매수 활성화됨. 1위 종목 {top_stock['name']} 매수 신호를 생성합니다.")
            
            # 최대 복리 테스트: 가용 현금 95%로 주문 수량 계산
            available_cash = portfolio.get_cash()
            current_price = top_stock['price']
            if current_price <= 0:
                logger.warning(f"[{self.name}] {top_stock['name']}의 현재가가 0 이하여서 주문할 수 없습니다.")
                return signals
            
            order_amount = available_cash * 0.95
            quantity = int(order_amount // current_price)
            
            if quantity == 0:
                logger.warning(f"[{self.name}] 가용 현금이 부족하여 {top_stock['name']}를 1주도 매수할 수 없습니다.")
                return signals
            
            # ML 특징 추출
            features = {
                'total_score': top_stock.get('score'),
                'score_detail': top_stock.get('score_detail')
            }

            signals.append({
                'strategy_id': self.strategy_id, 'symbol': top_stock['ticker'], 'side': 'buy',
                'quantity': quantity, 'price': 0, 'order_type': 'market',
                'features': features
            })

        return signals

