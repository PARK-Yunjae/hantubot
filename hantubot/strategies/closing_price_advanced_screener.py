# hantubot_prod/hantubot/strategies/closing_price_advanced_screener.py
"""
종가매매 고급 스크리너 전략 v3
- 매매일지 인사이트 반영: 양봉 필터, 윗꼬리 비율, 고가-종가 근접도
- 동적 파라미터 연동: 연속 승리 시 버퍼 축소 (복리 극대화)
- 점수 체계 개선: CCI(30%) + 거래량(25%) + ADX(20%) + 캔들패턴(25%)
"""
import datetime as dt
from typing import Dict, List, Any
import pandas as pd
from ta.trend import cci, sma_indicator, ADXIndicator

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
    고급 종가매매 스크리너 전략. (v3: 매매일지 인사이트 반영)
    
    점수 체계:
    - CCI 점수 (30%): CCI 180 근처일수록 고득점
    - 거래량 점수 (25%): 평균 대비 거래량 폭증
    - ADX 점수 (20%): 추세 강도
    - 캔들패턴 점수 (25%): 양봉 + 윗꼬리 짧음 + 고가-종가 근접
    
    동작: 15:03에 조건에 맞는 상위 3개 종목을 점수와 함께 Discord로 알림
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker: Broker, clock: MarketClock, notifier: Notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        self.run_time = dt.time(15, 3)  # 실행 시간 15:03
        
        # 지표 설정
        self.cci_period = self.config.get('cci_period', 14)
        self.sma_period = self.config.get('sma_period', 20)
        self.adx_period = self.config.get('adx_period', 14)
        self.volume_sma_period = self.config.get('volume_sma_period', 20)
        
        # 스크리닝 설정
        self.cci_target = self.config.get('cci_target', 180)
        self.cci_tolerance = self.config.get('cci_tolerance', 50)  # 조금 넓힘
        self.adx_min_threshold = self.config.get('adx_min_threshold', 18)  # 약간 낮춤
        self.top_n_volume = self.config.get('top_n_volume', 30)
        self.top_n_screen = self.config.get('top_n_screen', 3)
        
        # 자동 매수 설정
        self.auto_buy_enabled = self.config.get('auto_buy_enabled', True)
        self.buy_quantity = self.config.get('buy_quantity', 1)
        self.has_run_today = False
        
        # 연속 승리 카운터 (동적 파라미터에서 로드)
        self.consecutive_wins = self.dynamic_params.get('consecutive_wins', 0)

    def _calculate_candle_score(self, df: pd.DataFrame) -> tuple:
        """
        캔들 패턴 점수 계산 (매매일지 인사이트 반영)
        
        Returns:
            (score, is_bullish, details_str)
        """
        # 데이터 길이 검증
        if len(df) < 2:
            return 0, False, "데이터부족"
        
        # 당일 캔들 데이터
        try:
            today_open = float(df['stck_oprc'].iloc[-1]) if 'stck_oprc' in df.columns and len(df) >= 1 else float(df['stck_clpr'].iloc[-2]) if len(df) >= 2 else 0
            today_close = float(df['stck_clpr'].iloc[-1])
            today_high = float(df['stck_hgpr'].iloc[-1])
            today_low = float(df['stck_lwpr'].iloc[-1])
        except (IndexError, ValueError) as e:
            return 0, False, f"데이터오류:{e}"
        
        # 1. 양봉 여부 (필수 조건)
        is_bullish = today_close > today_open
        if not is_bullish:
            return 0, False, "음봉"
        
        # 2. 캔들 범위
        candle_range = today_high - today_low
        if candle_range == 0:
            return 0, False, "범위없음"
        
        body_size = today_close - today_open
        upper_shadow = today_high - today_close
        lower_shadow = today_open - today_low
        
        # 3. 윗꼬리 비율 (낮을수록 좋음) - 30% 미만이면 만점
        upper_shadow_ratio = upper_shadow / candle_range
        score_upper_shadow = max(0, 100 - (upper_shadow_ratio * 200))  # 0%->100점, 50%->0점
        
        # 4. 몸통 비율 (클수록 좋음) - 장대양봉 선호
        body_ratio = body_size / candle_range
        score_body = min(100, body_ratio * 150)  # 67% 이상이면 100점
        
        # 5. 고가-종가 근접도 (매매일지: "종가 고가가 근접함")
        high_close_gap = (today_high - today_close) / today_close * 100
        score_high_close = max(0, 100 - (high_close_gap * 50))  # 0%->100점, 2%->0점
        
        # 종합 점수 (가중 평균)
        total_score = (score_upper_shadow * 0.4) + (score_body * 0.3) + (score_high_close * 0.3)
        
        details = f"윗꼬리:{upper_shadow_ratio*100:.1f}%|몸통:{body_ratio*100:.1f}%|고종갭:{high_close_gap:.2f}%"
        
        return total_score, True, details

    def _get_buffer_ratio(self, stock_data: Dict[str, Any] = None) -> float:
        """
        연속 승리 횟수 + 거래대금에 따른 버퍼 비율 결정 (복리 극대화)
        
        Args:
            stock_data: 종목 데이터 (거래대금 정보 포함)
        
        Note: OrderManager가 시장가 주문 시 5% 슬리피지 버퍼를 추가하므로
        실제로는 여기서 설정한 비율보다 약간 더 보수적으로 작동함
        """
        consecutive_wins = self.dynamic_params.get('consecutive_wins', 0)
        
        # 기본 버퍼 (연속 승리 기반)
        if consecutive_wins >= 5:
            base_buffer = 0.93  # 7% 버퍼 (매우 공격적)
        elif consecutive_wins >= 3:
            base_buffer = 0.92  # 8% 버퍼
        elif consecutive_wins >= 2:
            base_buffer = 0.91  # 9% 버퍼
        else:
            base_buffer = 0.90  # 10% 버퍼 (기본)
        
        # 거래대금 기반 추가 조정 (보수적)
        if stock_data:
            try:
                # 거래대금 (단위: 원)
                trading_value_str = stock_data.get('data_rank', '0')
                trading_value = float(trading_value_str) if trading_value_str else 0
                
                # 거래대금 1000억 이상: +2% (대형 유동성)
                if trading_value >= 100_000_000_000:  # 1000억
                    base_buffer = min(0.95, base_buffer + 0.02)
                # 거래대금 100억 이상: +1% (중형)
                elif trading_value >= 10_000_000_000:  # 100억
                    base_buffer = min(0.94, base_buffer + 0.01)
                # 소형주는 그대로
            except (ValueError, TypeError):
                pass  # 오류 시 기본값 사용
        
        return base_buffer

    async def generate_signal(self, data_payload: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        now = dt.datetime.now()
        
        # 하루 한 번, 지정된 시간에만 실행
        if now.time() < self.run_time or self.has_run_today:
            if now.hour > 16:
                self.has_run_today = False
            return signals
        
        # 스크리너는 무조건 실행 (Discord 알림 + 학습 목적)
        logger.info(f"[{self.name}] 고급 스크리너 v3 실행. 시간: {now.strftime('%H:%M:%S')}")
        self.has_run_today = True
        
        # 포지션 체크는 나중에 (매수 신호 생성 시에만 체크)
        has_existing_positions = bool(portfolio.get_positions() or portfolio._open_orders)
        if has_existing_positions:
            logger.info(f"[{self.name}] 포지션이 있어 스크리닝 결과만 알림하고 매수는 건너뜁니다.")
            # ❌ return signals 제거! 스크리너는 계속 실행!

        try:
            # KIS API를 통해 실시간 거래대금 상위 종목 조회
            top_volume_stocks_raw = self.broker.get_realtime_transaction_ranks(top_n=self.top_n_volume)
            if not top_volume_stocks_raw:
                logger.warning(f"[{self.name}] 실시간 거래대금 상위 종목 조회 실패.")
                return signals

            # ETF, 스팩 등 필터링
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
            if not ticker or not stock_name:
                continue

            try:
                # 일봉 데이터 조회 (캐시 또는 API)
                hist_data = data_payload['historical_daily'].get(ticker)
                if not hist_data:
                    hist_data = self.broker.get_historical_daily_data(ticker, days=30)
                    if hist_data:
                        data_payload['historical_daily'][ticker] = hist_data
                
                if not hist_data or len(hist_data) < self.sma_period:
                    continue

                df = pd.DataFrame(hist_data)
                for col in ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # 시가 컬럼 처리
                if 'stck_oprc' in df.columns:
                    df['stck_oprc'] = pd.to_numeric(df['stck_oprc'], errors='coerce')
                
                df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
                
                # --- 1. 기본 데이터 추출 ---
                current_price = df['stck_clpr'].iloc[-1]
                sma20 = sma_indicator(df['stck_clpr'], window=self.sma_period).iloc[-1]
                
                # --- 2. CCI 계산 ---
                try:
                    current_cci = cci(df['stck_hgpr'], df['stck_lwpr'], df['stck_clpr'], window=self.cci_period).iloc[-1]
                    if pd.isna(current_cci):
                        current_cci = 0
                except (IndexError, ValueError):
                    current_cci = 0
                
                # ===== 필수 필터: 원칙에 맞지 않는 종목 사전 제거 =====
                # 필터 1: 20일 이평선 위에 있어야 함
                if pd.isna(sma20) or current_price <= sma20:
                    continue
                
                # 필터 2: CCI 100 이상 (과매도 영역 탈출)
                if current_cci < 100:
                    continue
                
                # --- 3. 캔들 패턴 점수 (양봉이면 가산, 음봉이면 감점) ---
                candle_score, is_bullish, candle_details = self._calculate_candle_score(df)
                
                # --- 4. ADX 계산 ---
                try:
                    adx_indicator = ADXIndicator(df['stck_hgpr'], df['stck_lwpr'], df['stck_clpr'], window=self.adx_period)
                    current_adx = adx_indicator.adx().iloc[-1]
                    if pd.isna(current_adx):
                        current_adx = 0
                except (IndexError, ValueError):
                    current_adx = 0

                # === 점수 계산 (필터링 대신 점수 반영) ===
                
                # CCI 점수 (25%) - 180 근처일수록 고득점
                score_cci = max(0, 100 - abs(current_cci - self.cci_target) * 1.5)
                
                # 거래량 점수 (25%) - 평균 대비 폭증
                vol_sma = sma_indicator(df['acml_vol'], window=self.volume_sma_period).iloc[-1]
                last_volume = df['acml_vol'].iloc[-1]
                if pd.isna(vol_sma) or vol_sma == 0:
                    score_volume = 50
                else:
                    score_volume = min(100, (last_volume / vol_sma) * 50)
                
                # ADX 점수 (15%) - 추세 강도
                score_adx = min(100, current_adx * 2.5)
                
                # 캔들 점수 (25%) - 양봉/음봉 반영
                if not is_bullish:
                    candle_score = 0  # 음봉은 캔들 점수 0점
                    candle_details = "음봉(감점)"
                
                # 이평선 점수 (10%) - 이평선 위면 가산
                if pd.isna(sma20) or sma20 == 0:
                    score_sma = 50
                    gap_from_sma = 0
                else:
                    gap_from_sma = ((current_price - sma20) / sma20) * 100
                    if current_price > sma20:
                        score_sma = min(100, 50 + gap_from_sma * 5)  # 이평선 위: 보너스
                    else:
                        score_sma = max(0, 50 + gap_from_sma * 5)  # 이평선 아래: 감점

                # 종합 점수 (가중 평균)
                total_score = (
                    (score_cci * 0.25) + 
                    (score_volume * 0.25) + 
                    (score_adx * 0.15) + 
                    (candle_score * 0.25) + 
                    (score_sma * 0.10)
                )
                
                # 양봉 보너스 (+10점)
                if is_bullish:
                    total_score += 10
                
                screened_stocks.append({
                    'name': stock_name,
                    'ticker': ticker,
                    'price': current_price,
                    'score': round(total_score, 2),
                    'cci': round(current_cci, 1),
                    'adx': round(current_adx, 1),
                    'is_bullish': is_bullish,
                    'score_detail': f"CCI:{round(score_cci)}|거래량:{round(score_volume)}|ADX:{round(score_adx)}|캔들:{round(candle_score)}|이평:{round(score_sma)}",
                    'candle_detail': candle_details
                })
                
            except Exception as e:
                logger.error(f"[{self.name}] {ticker} 분석 중 오류: {e}")

        if not screened_stocks:
            self.notifier.send_alert("종가매매 스크리너 결과, 조건에 맞는 종목이 없습니다.", level='info')
            return signals
        
        # 점수 순 정렬
        top_stocks = sorted(screened_stocks, key=lambda x: x['score'], reverse=True)[:self.top_n_screen]

        # Discord 알림 생성
        consecutive_wins = self.dynamic_params.get('consecutive_wins', 0)
        buffer_pct = int((1 - self._get_buffer_ratio()) * 100)
        
        fields = []
        for i, stock in enumerate(top_stocks):
            # 양봉/음봉 표시
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
            "title": f"🔔 종가매매 후보 TOP3 ({now.strftime('%H:%M')})",
            "description": (
                f"**양봉 + CCI 180 근처 + 추세강도 + 거래량 종합 분석**\n"
                f"연속 승리: {consecutive_wins}회 | 버퍼: {buffer_pct}%"
            ),
            "color": 16705372,  # 금색
            "fields": fields,
            "footer": {"text": "1위 종목 자동매수 활성화 시 15:03에 시장가 매수"}
        }
        self.notifier.send_alert("종가매매 후보 종목 알림", embed=embed)
        
        # 자동 매수 처리
        if self.auto_buy_enabled and top_stocks:
            # 이미 보유 중인 종목이 있으면 매수 안함
            if portfolio.get_positions():
                logger.info(f"[{self.name}] 자동 매수 활성화 상태이나, 이미 보유 중인 종목이 있어 매수 신호를 생성하지 않습니다.")
                return signals

            top_stock = top_stocks[0]
            logger.info(f"[{self.name}] 자동 매수 활성화됨. 1위 종목 {top_stock['name']} 매수 신호를 생성합니다.")
            
            # 복리 극대화를 위한 동적 버퍼
            available_cash = portfolio.get_cash()
            current_price = top_stock['price']
            
            if current_price <= 0:
                logger.warning(f"[{self.name}] {top_stock['name']}의 현재가가 0 이하여서 주문할 수 없습니다.")
                return signals
            
            # 거래대금 정보를 포함하여 버퍼 계산
            stock_data_for_buffer = next((s for s in top_volume_stocks if s.get('mksc_shrn_iscd') == top_stock['ticker']), None)
            buffer_ratio = self._get_buffer_ratio(stock_data_for_buffer)
            order_amount = available_cash * buffer_ratio
            quantity = int(order_amount // current_price)
            
            if quantity == 0:
                logger.warning(f"[{self.name}] 가용 현금이 부족하여 {top_stock['name']}를 1주도 매수할 수 없습니다.")
                return signals
            
            logger.info(f"[{self.name}] 주문 계산: 현금 {available_cash:,.0f}원 × {buffer_ratio:.0%} = {order_amount:,.0f}원 → {quantity}주")
            
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

        return signals
