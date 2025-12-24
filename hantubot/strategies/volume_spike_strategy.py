# hantubot_prod/hantubot/strategies/volume_spike_strategy.py
import datetime as dt
from typing import List, Dict, Any
import pandas as pd
import ta

from .base_strategy import BaseStrategy
from ..core.portfolio import Portfolio
from ..reporting.logger import get_logger
from ..utils.stock_filters import is_eligible_stock

logger = get_logger(__name__)

class VolumeSpikeStrategy(BaseStrategy):
    """
    실시간 거래량 순위 급상승을 감지하여 추격 매수하는 전략.
    - 시장 레짐(Regime)에 따라 매매 강도와 기준을 동적으로 조절.
    - 주기적으로 거래량 상위 종목을 스캔.
    - 순위권 밖에 있던 종목이 특정 순위 안으로 갑자기 진입하면 매수.
    - 목표 수익률 도달, 손절 라인 터치, 또는 순위 이탈 시 매도.
    """
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker, clock, notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        self.previous_ranks: Dict[str, int] = {}
        self.last_checked: dt.datetime = None
        self.trade_window_start = dt.time(9, 30)
        self.trade_window_end = dt.time(14, 50)
        
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
        if not params or not params.get('trade_enabled', False):
            # logger.debug(f"[{self.name}] 현재 레짐 '{regime}'({params.get('name')})에서는 거래가 비활성화되어 있습니다.")
            return signals

        # 1. 매매 시간 창 및 실행 주기 확인
        if not (self.trade_window_start <= now.time() < self.trade_window_end):
            return signals
        if self.last_checked and (now - self.last_checked).total_seconds() < 60:
            return signals
        
        # 2. API를 통해 현재 순위 조회 및 필터링
        try:
            leaders_raw = self.broker.get_volume_leaders(top_n=100)
            if not leaders_raw:
                logger.warning(f"[{self.name}] 거래량 상위 종목을 조회할 수 없습니다.")
                return signals
            
            volume_leaders = [item for item in leaders_raw if is_eligible_stock(item.get('hts_kor_isnm', ''))]
            current_ranks: Dict[str, int] = {item['mksc_shrn_iscd']: i + 1 for i, item in enumerate(volume_leaders)}
        except Exception as e:
            logger.error(f"[{self.name}] 거래량 순위 조회 중 오류 발생: {e}", exc_info=True)
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
                
                current_rank = current_ranks.get(symbol, 101)
                if not should_sell and current_rank > params['rank_sell_threshold']:
                    should_sell, reason = True, f"순위 이탈 ({current_rank}위)"
                
                if should_sell:
                    logger.info(f"[{self.name}] {symbol} 매도 신호. 사유: {reason}")
                    signals.append({
                        'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'sell',
                        'quantity': position['quantity'], 'price': 0, 'order_type': 'market'
                    })
                    self.notifier.send_alert(f"[{self.name}/{regime}] 매도: {symbol} ({position['quantity']}주) - {reason}", level='info')
            
            # 3-2. 매수 로직
            num_positions = len(positions)
            if num_positions < params['max_positions'] and self.previous_ranks:
                logger.debug(f"[{self.name}/{regime}] 신규 진입 탐색 (현재 보유: {num_positions}, 최대: {params['max_positions']})")
                
                for symbol, rank in current_ranks.items():
                    # 이미 보유 중인 종목은 건너뛰기
                    if symbol in positions:
                        continue
                        
                    prev_rank = self.previous_ranks.get(symbol, 101)
                    logger.debug(f"[{self.name}/{regime}] 종목 {symbol}: 이전 순위 {prev_rank}, 현재 순위 {rank}")

                    if prev_rank > params['rank_jump_prev_threshold'] and rank <= params['rank_jump_buy_threshold']:
                        current_price = self.broker.get_current_price(symbol)
                        if current_price < 1000: continue
                        
                        available_cash = portfolio.get_cash()
                        
                        # 동적 파라미터에서 자본 배분 가중치 가져오기 (기본값 1.0)
                        allocation_weight = self.dynamic_params.get('capital_allocation_weight', 1.0)
                        
                        # 전체 현금의 95%를 최대 포지션 수로 나눈 금액에 가중치 적용
                        buy_amount = (available_cash * 0.95 * allocation_weight) / params['max_positions']
                        quantity = int(buy_amount // current_price)

                        if quantity == 0: continue

                        reason = f"순위 급상승 {prev_rank}→{rank}"
                        logger.info(f"[{self.name}/{regime}] 매수 신호: {symbol} {quantity}주 ({reason})")
                        signals.append({
                            'strategy_id': self.strategy_id, 'symbol': symbol, 'side': 'buy',
                            'quantity': quantity, 'price': 0, 'order_type': 'market',
                        })
                        self.notifier.send_alert(f"[{self.name}/{regime}] 매수: {symbol} {quantity}주 ({reason})", level='info')
                        # 매수 신호 발생 후 다음 신호 탐색을 위해 break. 한 번에 하나씩만 매수.
                        break
        
        except Exception as e:
            logger.error(f"[{self.name}] 신호 생성 로직 중 오류 발생: {e}", exc_info=True)

        # 4. 다음 조회를 위해 현재 상태를 업데이트
        self.last_checked = now
        self.previous_ranks = current_ranks
            
        return signals
