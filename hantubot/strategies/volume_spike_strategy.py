# hantubot_prod/hantubot/strategies/volume_spike_strategy.py
import datetime as dt
from typing import List, Dict, Any
import pandas as pd
import ta

from .base_strategy import BaseStrategy
from ..core.portfolio import Portfolio
from ..reporting.logger import get_logger
from ..utils.stock_filters import is_eligible_stock
from ..providers.naver_news import NaverNewsProvider

logger = get_logger(__name__)

class VolumeSpikeStrategy(BaseStrategy):
    """
    급등주 포착 전략 (유목민 철학 적용)
    - 기존: 거래량 순위 급상승
    - 변경: 
      1. 거래대금 우선 (일 150억 이상만 대상)
      2. 순간 화력 (1분 거래대금 10억 돌파)
      3. 뉴스 연동 (특징주, 공시 등 재료 확인)
    """
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker, clock, notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        self.previous_ranks: Dict[str, int] = {}
        self.last_checked: dt.datetime = None
        self.trade_window_start = dt.time(9, 30)
        self.trade_window_end = dt.time(14, 50)
        
        # 뉴스 프로바이더 초기화
        try:
            self.news_provider = NaverNewsProvider(max_items_per_ticker=5)
        except Exception as e:
            logger.warning(f"[{self.name}] 뉴스 프로바이더 초기화 실패: {e}")
            self.news_provider = None
        
        # 레짐별 파라미터 로드
        self.params_by_regime = self.config.get('params_by_regime', {})
        if not self.params_by_regime:
            logger.warning(f"[{self.name}] 레짐별 설정(params_by_regime)이 없습니다. 전략이 올바르게 동작하지 않을 수 있습니다.")
        
        logger.info(f"'{self.name}' 초기화 완료. 거래 시간: {self.trade_window_start}-{self.trade_window_end}")

    def _get_current_params(self, regime: str) -> Dict[str, Any]:
        """
        현재 레짐에 맞는 파라미터를 반환합니다.
        계층적으로 폴백(fallback)합니다: 현재 레짐 설정 -> NEUTRAL 설정 -> 코드 내 기본값
        """
        # 1. 코드에 내장된 가장 안전한 기본값 (최후의 보루)
        hardcoded_defaults = {
            'name': "기본 모드",
            'take_profit_pct': 2.0,
            'stop_loss_pct': -2.0,
            'rank_jump_buy_threshold': 10,
            'rank_jump_prev_threshold': 30,
            'rank_sell_threshold': 30,
            'max_positions': 1,
            'trade_enabled': False  # 기본적으로 거래 비활성화
        }
        
        # 2. config.yaml에 정의된 NEUTRAL 설정 (사용자 정의 기본값)
        neutral_params = self.params_by_regime.get('NEUTRAL', {})
        
        # 3. 현재 레짐의 특정 설정
        regime_params = self.params_by_regime.get(regime, {})

        # 4. 계층적으로 설정을 병합 (오른쪽 값이 왼쪽 값을 덮어씀)
        # 최종 파라미터 = (코드 기본값 < NEUTRAL 설정 < 현재 레짐 설정)
        final_params = {**hardcoded_defaults, **neutral_params, **regime_params}
        
        return final_params

    async def generate_signal(self, current_data: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        """
        거래량 순위 변화를 감지하여 매수/매도 신호를 생성합니다.
        (수정: 레짐 기반 동적 파라미터 적용 및 안정성 강화)
        """
        signals = []
        now = dt.datetime.now()
        
        # 0. 현재 레짐과 파라미터 가져오기
        regime = current_data.get("regime", "NEUTRAL") # 엔진으로부터 레짐 정보 수신
        params = self._get_current_params(regime)
        
        # [변경] 거래 활성화 체크 (전역 설정 force_trade_enabled 우선 적용)
        is_trade_enabled = params.get('trade_enabled', False)
        if self.global_config.get('force_trade_enabled', False):
            is_trade_enabled = True
            
        if not params or not is_trade_enabled:
            # logger.debug(f"[{self.name}] 현재 레짐 '{regime}'({params.get('name')})에서는 거래가 비활성화되어 있습니다.")
            return signals

        # 1. 매매 시간 창 및 실행 주기 확인
        if not (self.trade_window_start <= now.time() < self.trade_window_end):
            return signals
        if self.last_checked and (now - self.last_checked).total_seconds() < 60:
            return signals
        
        # 2. API를 통해 현재 순위 조회 및 필터링 (거래대금 기준)
        try:
            # 거래량 상위 100개 중 필터링
            leaders_raw = self.broker.get_volume_leaders(top_n=100)
            if not leaders_raw:
                return signals
            
            # [유목민 철학] 잡주 제외: 거래대금 150억 미만은 쳐다보지도 않는다.
            # 하지만 장중에는 누적 거래대금이 150억을 향해 가는 중일 수 있으므로, 
            # 일단 100억 이상이면 후보로 둠.
            volume_leaders = []
            for item in leaders_raw:
                if not is_eligible_stock(item.get('hts_kor_isnm', '')):
                    continue
                try:
                    tv = float(item.get('acml_tr_pbmn', 0))
                    if tv >= 10000000000: # 100억 이상
                        volume_leaders.append(item)
                except:
                    pass

            current_ranks: Dict[str, int] = {item['mksc_shrn_iscd']: i + 1 for i, item in enumerate(volume_leaders)}
        except Exception as e:
            logger.error(f"[{self.name}] 순위 조회 오류: {e}")
            return signals

        # 3. 로직 실행 (매도 또는 매수)
        positions = portfolio.get_positions_by_strategy(self.strategy_id)
        try:
            # 3-1. 매도 로직
            for symbol, position in positions.items():
                should_sell = False
                reason = ""
                current_price = self.broker.get_current_price(symbol)
                
                if current_price > 0:
                    pnl = ((current_price / position['avg_price']) - 1) * 100
                    if pnl >= params['take_profit_pct']:
                        should_sell, reason = True, f"익절 ({pnl:.2f}%)"
                    elif pnl <= params['stop_loss_pct']:
                        should_sell, reason = True, f"손절 ({pnl:.2f}%)"
                
                # 순위 이탈 로직은 거래대금 순위로 대체되었으므로, 너무 밀리면 매도
                current_rank = current_ranks.get(symbol, 101)
                if not should_sell and current_rank > params['rank_sell_threshold']:
                    should_sell, reason = True, f"관심권 이탈 ({current_rank}위)"
                
                if should_sell:
                    signals.append({
                        'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'sell',
                        'quantity': position['quantity'], 'price': 0, 'order_type': 'market',
                        'reason': reason
                    })
                    self.notifier.send_alert(f"[{self.name}] 매도: {symbol} - {reason}", level='info')
            
            # 3-2. 매수 로직
            num_positions = len(positions)
            if num_positions < params['max_positions'] and self.previous_ranks:
                for symbol, rank in current_ranks.items():
                    if symbol in positions: continue
                        
                    prev_rank = self.previous_ranks.get(symbol, 101)
                    
                    # [유목민 철학] 순위 급상승 + 순간 화력 체크
                    if prev_rank > params['rank_jump_prev_threshold'] and rank <= params['rank_jump_buy_threshold']:
                        # 1분봉 데이터 조회하여 순간 거래대금 확인
                        minute_data = self.broker.get_intraday_minute_data(symbol)
                        if not minute_data: continue
                        
                        if not isinstance(minute_data, list):
                            # logger.debug(f"[{self.name}] 분봉 데이터 형식 오류 ({symbol}): {type(minute_data)} - {minute_data}")
                            continue

                        try:
                            # 최근 1분 거래대금
                            current_1m_value = float(minute_data[0].get('acml_tr_pbmn', 0))
                            
                            # [유목민 철학 1] 1분 거래대금 10억 돌파 (강력한 매수세) - 1차 필터
                            if current_1m_value < 1000000000:
                                continue

                            # [유목민 철학 2] 기술적 분석 필터 (캔들, 거래량, 추세) - 2차 필터
                            # API 호출 비용이 크므로 1차 필터 통과한 놈만 검사
                            hist_data = self.broker.get_historical_daily_data(symbol, days=120)
                            if not hist_data or len(hist_data) < 20: continue
                            
                            df = pd.DataFrame(hist_data)
                            for col in ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'acml_vol']:
                                if col in df.columns:
                                    df[col] = pd.to_numeric(df[col], errors='coerce')
                            
                            # 데이터 정렬 및 MA 계산
                            df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
                            df['ma20'] = ta.trend.sma_indicator(df['stck_clpr'], window=20)
                            
                            today_candle = df.iloc[-1] # 현재(오늘) 캔들
                            prev_candle = df.iloc[-2]  # 전일 캔들
                            
                            current_price = float(today_candle['stck_clpr'])
                            open_price = float(today_candle['stck_oprc'])
                            high_price = float(today_candle['stck_hgpr'])
                            
                            # A. 캔들 패턴 필터
                            # 양봉 필수
                            if current_price <= open_price: continue
                            # 윗꼬리 제한 (High - Close) <= (Close - Open) * 2
                            upper_shadow = high_price - current_price
                            body = current_price - open_price
                            if body > 0 and upper_shadow > body * 2: continue

                            # B. 거래량 분석 필터
                            # 당일 거래량 > 전일 거래량 * 2 (200% 이상 급증)
                            current_vol = float(today_candle['acml_vol'])
                            prev_vol = float(prev_candle['acml_vol'])
                            if prev_vol > 0 and current_vol < prev_vol * 2:
                                continue # 거래량 폭발력 부족

                            # C. 추세 필터
                            # MA20 지지 (현재가 > 20일선)
                            ma20 = float(today_candle['ma20'])
                            if not pd.isna(ma20) and current_price <= ma20:
                                continue

                            # D. 뉴스 확인 (재료가 있는가?)
                            news_score = 0
                            news_title = ""
                            if self.news_provider:
                                news_items = self.news_provider.fetch_news(symbol, symbol)
                                for news in news_items:
                                    if '특징주' in news['title'] or '공시' in news['title']:
                                        news_score = 1
                                        news_title = news['title']
                                        break
                            
                            # 뉴스가 없으면 진입 기준을 더 높임 (1분 20억)
                            if news_score == 0 and current_1m_value < 2000000000:
                                continue

                            available_cash = portfolio.get_cash()
                            
                            # [변경] 공통 매수 수량 계산 메서드 사용
                            # max_positions는 이미 params에서 1로 고정되도록 권고됨 (Config 참조)
                            # 하지만 안전을 위해 max_positions로 나누는 로직은 유지하되, buy_cash_ratio는 calculate_buy_quantity 내부에서 적용됨
                            # calculate_buy_quantity는 전체 가용 현금 기준이므로, max_positions 고려하여 현금 배분
                            allocated_cash = available_cash / params['max_positions']
                            quantity = self.calculate_buy_quantity(current_price, allocated_cash)

                            if quantity == 0: continue

                            reason = f"화력(1분 {current_1m_value/100000000:.1f}억) + 거래량200% + MA20지지"
                            if news_title:
                                reason += f" + 뉴스({news_title[:10]}...)"

                            logger.info(f"[{self.name}] 매수 신호: {symbol} {quantity}주 ({reason})")
                            signals.append({
                                'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'buy',
                                'quantity': quantity, 'price': 0, 'order_type': 'market',
                                'reason': reason
                            })
                            self.notifier.send_alert(f"[{self.name}] 강력 매수: {symbol} {quantity}주 ({reason})", level='info')
                            break # 한 번에 하나만
                            
                        except Exception as e:
                            logger.error(f"매수 로직 상세 오류 ({symbol}): {type(e).__name__} - {e}")
                            continue

        except Exception as e:
            logger.error(f"[{self.name}] 신호 생성 로직 중 오류 발생: {e}", exc_info=True)

        # 4. 다음 조회를 위해 현재 상태를 업데이트
        self.last_checked = now
        self.previous_ranks = current_ranks
            
        return signals
