import datetime as dt
from typing import Dict, List, Any
import pandas as pd

from ...strategies.base_strategy import BaseStrategy
from ...core.portfolio import Portfolio
from ...core.clock import MarketClock
from ...execution.broker import Broker
from ...reporting.logger import get_logger
from ...reporting.notifier import Notifier
from ...utils.stock_filters import is_eligible_stock
from .config import ClosingPriceConfig
from .logic import ClosingPriceLogic

logger = get_logger(__name__)

class ClosingPriceStrategy(BaseStrategy):
    """
    고급 종가매매 스크리너 전략. (v3 리팩토링 버전)
    
    점수 체계:
    - CCI 점수 (30%): CCI 180 근처일수록 고득점
    - 거래량 점수 (25%): 평균 대비 거래량 폭증
    - ADX 점수 (20%): 추세 강도
    - 캔들패턴 점수 (25%): 양봉 + 윗꼬리 짧음 + 고가-종가 근접
    
    동작: 15:03에 조건에 맞는 상위 3개 종목을 점수와 함께 Discord로 알림
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker: Broker, clock: MarketClock, notifier: Notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        
        # 설정 로드
        self.strategy_config = ClosingPriceConfig.from_dict(self.config)
        self.logic = ClosingPriceLogic(self.strategy_config)
        
        # 상태 변수
        self.has_webhook_sent_today = False
        self.has_bought_today = False
        self.top_stocks_today = []
        
        # 연속 승리 카운터 (동적 파라미터에서 로드)
        self.consecutive_wins = self.dynamic_params.get('consecutive_wins', 0)

    async def _perform_screening(self, data_payload: Dict[str, Any], top_volume_stocks: List[Dict]) -> List[Dict[str, Any]]:
        """스크리닝 실행 (15:03에 호출)"""
        screened_stocks = []
        
        for stock_data in top_volume_stocks:
            ticker = stock_data.get('mksc_shrn_iscd')
            stock_name = stock_data.get('hts_kor_isnm')
            if not ticker or not stock_name:
                continue

            try:
                # 일봉 데이터 조회
                hist_data = data_payload['historical_daily'].get(ticker)
                if not hist_data:
                    hist_data = self.broker.get_historical_daily_data(ticker, days=30)
                    if hist_data:
                        data_payload['historical_daily'][ticker] = hist_data
                
                if not hist_data or len(hist_data) < self.strategy_config.sma_period:
                    continue

                df = pd.DataFrame(hist_data)
                for col in ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                if 'stck_oprc' in df.columns:
                    df['stck_oprc'] = pd.to_numeric(df['stck_oprc'], errors='coerce')
                
                df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
                
                # 1. 지표 계산
                indicators = self.logic.calculate_indicators(df)
                if 'error' in indicators:
                    continue
                    
                current_price = indicators['price']
                sma20 = indicators['sma20']
                current_cci = indicators['cci']
                
                # 2. 필수 필터
                if pd.isna(sma20) or current_price <= sma20:
                    continue
                if current_cci < 100:
                    continue
                
                # 3. 캔들 점수 계산
                candle_score, is_bullish, candle_details = self.logic.calculate_candle_score(df)
                
                # 4. 종합 점수 계산
                total_score, score_detail = self.logic.calculate_total_score(indicators, candle_score, is_bullish)
                
                screened_stocks.append({
                    'name': stock_name,
                    'ticker': ticker,
                    'price': current_price,
                    'score': round(total_score, 2),
                    'cci': round(indicators['cci'], 1),
                    'adx': round(indicators['adx'], 1),
                    'is_bullish': is_bullish,
                    'score_detail': score_detail,
                    'candle_detail': candle_details
                })
                
            except Exception as e:
                logger.error(f"[{self.name}] {ticker} 분석 중 오류: {e}")
        
        return sorted(screened_stocks, key=lambda x: x['score'], reverse=True)

    async def generate_signal(self, data_payload: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        now = dt.datetime.now()
        
        # 16시 이후 플래그 리셋
        if now.hour >= 16:
            self.has_webhook_sent_today = False
            self.has_bought_today = False
            self.top_stocks_today = []
            return signals
        
        # ========================================
        # 15:03-15:15: 스크리닝 + 웹훅 발송 (매수 X)
        # ========================================
        if self.strategy_config.webhook_time <= now.time() < self.strategy_config.buy_start_time and not self.has_webhook_sent_today:
            logger.info(f"[{self.name}] ===== 15:03 스크리닝 실행 (웹훅만, 매수 안함) =====")
            self.has_webhook_sent_today = True
            
            try:
                # KIS API로 거래대금 상위 종목 조회
                top_volume_stocks_raw = self.broker.get_realtime_transaction_ranks(top_n=self.strategy_config.top_n_volume)
                if not top_volume_stocks_raw:
                    logger.warning(f"[{self.name}] 거래대금 상위 종목 조회 실패")
                    return signals
                
                # ETF, 스팩 필터링
                top_volume_stocks = [
                    item for item in top_volume_stocks_raw
                    if is_eligible_stock(item.get('hts_kor_isnm', ''))
                ]
                logger.info(f"[{self.name}] 적격 종목 {len(top_volume_stocks)}개 발견")
                
                # 스크리닝 실행
                screened_stocks = await self._perform_screening(data_payload, top_volume_stocks)
                
                if not screened_stocks:
                    self.notifier.send_alert("종가매매 스크리너 결과, 조건에 맞는 종목이 없습니다.", level='info')
                    return signals
                
                # TOP3 추출 및 저장
                self.top_stocks_today = screened_stocks[:self.strategy_config.top_n_screen]
                
                # Discord 웹훅 발송
                consecutive_wins = self.dynamic_params.get('consecutive_wins', 0)
                buffer_pct = int((1 - self.logic.get_buffer_ratio(consecutive_wins)) * 100)
                
                fields = []
                for i, stock in enumerate(self.top_stocks_today):
                    candle_emoji = "🟢" if stock.get('is_bullish', False) else "🔴"
                    rank_emoji = '🥇' if i==0 else '🥈' if i==1 else '🥉'
                    
                    fields.append({
                        "name": f"{rank_emoji} {i+1}위: {stock['name']} ({stock['ticker']}) {candle_emoji}",
                        "value": (
                            f"**종합 점수: {stock['score']}점**\n"
                            f"📊 {stock['score_detail']}\n"
                            f"📈 CCI: {stock['cci']} | ADX: {stock['adx']}\n"
                            f"🕯️ {stock['candle_detail']}\n"
                            f"💰 현재가: {stock['price']:,.0f}원"
                        ),
                        "inline": False
                    })
                
                embed = {
                    "title": f"🔔 종가매매 후보 TOP3 (15:03)",
                    "description": (
                        f"**양봉 + CCI 180 근처 + 추세강도 + 거래량 종합 분석**\n"
                        f"연속 승리: {consecutive_wins}회 | 버퍼: {buffer_pct}%\n"
                        f"⏰ 15:15-15:19에 1위 종목 자동 매수 예정"
                    ),
                    "color": 16705372,  # 금색
                    "fields": fields,
                    "footer": {"text": "자동 매수 활성화 시 15:15에 1위 종목 시장가 매수"}
                }
                self.notifier.send_alert("종가매매 후보 종목 알림 (15:03)", embed=embed)
                logger.info(f"[{self.name}] 웹훅 발송 완료. 15:15-15:19 매수 대기 중...")
                
            except Exception as e:
                logger.error(f"[{self.name}] 15:03 스크리닝 중 오류: {e}", exc_info=True)
            
            return signals
        
        # ========================================
        # 15:15-15:19: 저장된 1위 종목 매수
        # ========================================
        if self.strategy_config.buy_start_time <= now.time() <= self.strategy_config.buy_end_time and not self.has_bought_today:
            if not self.top_stocks_today:
                logger.warning(f"[{self.name}] 15:03 스크리닝 결과가 없습니다. 매수 건너뜀")
                return signals
            
            if not self.strategy_config.auto_buy_enabled:
                logger.info(f"[{self.name}] 자동 매수 비활성화 상태. 매수 건너뜀")
                return signals
            
            # 포지션 체크
            if portfolio.get_positions():
                logger.info(f"[{self.name}] 이미 보유 중인 종목이 있어 매수 건너뜀")
                self.has_bought_today = True
                return signals
            
            logger.info(f"[{self.name}] ===== 15:15-15:19 매수 실행 =====")
            self.has_bought_today = True
            
            top_stock = self.top_stocks_today[0]
            logger.info(f"[{self.name}] 1위 종목 {top_stock['name']} ({top_stock['ticker']}) 매수 신호 생성")
            
            # 현재가 재조회
            current_price = self.broker.get_current_price(top_stock['ticker'])
            if current_price <= 0:
                logger.warning(f"[{self.name}] 현재가 조회 실패. 15:03 가격 사용: {top_stock['price']}원")
                current_price = top_stock['price']
            else:
                logger.info(f"[{self.name}] 현재가 업데이트: {top_stock['price']}원 → {current_price}원")
                top_stock['price'] = current_price
            
            # 매수 수량 계산
            available_cash = portfolio.get_cash()
            
            # 거래대금 정보 가져오기 (이미 메모리에 없을 수 있으므로 다시 조회하거나 저장된 정보 사용)
            # 여기서는 top_stock 정보에는 거래대금 정보가 없으므로 다시 조회하거나 보수적으로 접근
            # Logic의 get_buffer_ratio는 거래대금 정보가 없으면 기본값 사용
            consecutive_wins = self.dynamic_params.get('consecutive_wins', 0)
            
            # top_stocks_today는 simple dict이므로 거래대금 정보가 누락되었을 수 있음
            # 정확성을 위해 다시 조회하거나, 이전 단계에서 저장했어야 함.
            # 일단 여기서는 기본 버퍼 사용 (safe)
            buffer_ratio = self.logic.get_buffer_ratio(consecutive_wins, None)
            
            order_amount = available_cash * buffer_ratio
            quantity = int(order_amount // current_price)
            
            if quantity == 0:
                logger.warning(f"[{self.name}] 가용 현금 부족. 매수 불가")
                return signals
            
            logger.info(f"[{self.name}] 매수 계산: {available_cash:,.0f}원 × {buffer_ratio:.0%} = {order_amount:,.0f}원 → {quantity}주")
            
            # 매수 신호 생성
            signals.append({
                'strategy_id': self.strategy_id,
                'symbol': top_stock['ticker'],
                'side': 'buy',
                'quantity': quantity,
                'price': 0,
                'order_type': 'market',
                'features': {
                    'total_score': top_stock['score'],
                    'cci': top_stock['cci'],
                    'adx': top_stock['adx'],
                    'score_detail': top_stock['score_detail'],
                    'candle_detail': top_stock['candle_detail']
                }
            })
            logger.info(f"[{self.name}] ✅ 매수 신호 생성 완료")
            
            return signals
            
        return signals
