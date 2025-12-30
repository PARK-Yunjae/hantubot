import datetime as dt
import json
import os
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
    
    [가산점 기반 랭킹 시스템 적용]
    1. 후보 수집: 거래대금 등 기본 필터 통과 종목 점수 계산
    2. 순위 선정: 점수(Score) 내림차순 -> 거래대금 내림차순
    3. 최종 선발: 상위 랭크 종목 선정
    
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

        # 재시작 시 오늘 스크리닝 결과 복구
        self._load_screening_results()

    def _get_screening_file_path(self):
        """오늘 날짜의 스크리닝 결과 파일 경로"""
        today_str = dt.datetime.now().strftime("%Y%m%d")
        # data 디렉토리가 없으면 생성
        if not os.path.exists('data'):
            os.makedirs('data')
        return os.path.join('data', f'closing_price_targets_{today_str}.json')

    def _save_screening_results(self):
        """스크리닝 결과를 JSON 파일로 저장"""
        try:
            file_path = self._get_screening_file_path()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.top_stocks_today, f, ensure_ascii=False, indent=2)
            logger.info(f"[{self.name}] 💾 스크리닝 결과 저장 완료: {file_path}")
        except Exception as e:
            logger.error(f"[{self.name}] 스크리닝 결과 저장 실패: {e}")

    def _load_screening_results(self):
        """저장된 스크리닝 결과 로드"""
        try:
            file_path = self._get_screening_file_path()
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.top_stocks_today = json.load(f)
                
                if self.top_stocks_today:
                    logger.info(f"[{self.name}] ♻️ 재시작 후 스크리닝 결과 복구 완료 ({len(self.top_stocks_today)}개)")
                    # 이미 데이터가 있다는 것은 스크리닝을 했다는 뜻
                    self.has_webhook_sent_today = True 
            else:
                pass
        except Exception as e:
            logger.error(f"[{self.name}] 스크리닝 결과 로드 실패: {e}")

    async def calculate_score(self, ticker: str, data_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        개별 종목에 대한 점수 계산 및 유효성 검증
        """
        result = {'valid': False, 'symbol': ticker, 'score': 0, 'reason': '', 'features': {}}
        
        try:
            # 일봉 데이터 조회 (기술적 지표 계산용)
            hist_data = data_payload['historical_daily'].get(ticker)
            if not hist_data:
                hist_data = self.broker.get_historical_daily_data(ticker, days=30)
                if hist_data:
                    data_payload['historical_daily'][ticker] = hist_data
            
            if not hist_data or len(hist_data) < self.strategy_config.sma_period:
                return result

            df = pd.DataFrame(hist_data)
            for col in ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol', 'stck_oprc']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
            
            # 1. [유목민 철학] 가격 지지 확인: 현재가가 시가 대비 +3% 이상인지 확인
            today_candle = df.iloc[-1]
            today_open = float(today_candle['stck_oprc'])
            current_price = float(today_candle['stck_clpr']) # 장중에는 현재가
            trading_value = float(today_candle.get('acml_tr_pbmn', 0)) if 'acml_tr_pbmn' in today_candle else 0
            # 만약 hist_data에 거래대금 정보가 없다면 실시간 데이터에서 가져와야 함 (상위 레벨에서 주입받거나 여기서 조회)
            
            if today_open > 0:
                change_from_open = ((current_price - today_open) / today_open) * 100
                if change_from_open < 3.0:
                    return result # 3% 이상 상승 유지하지 못하면 탈락
            
            # 2. 지표 계산
            indicators = self.logic.calculate_indicators(df)
            if 'error' in indicators:
                return result
                
            sma20 = indicators['sma20']
            
            # 3. 필수 필터 (20일선 위에 있어야 함)
            if pd.isna(sma20) or current_price <= sma20:
                return result
            
            # 4. 캔들 점수 및 종합 점수 계산
            candle_score, is_bullish, candle_details = self.logic.calculate_candle_score(df)
            
            # [유목민 철학] 캔들 패턴 필터 강화
            # A. 양봉 필수
            if not is_bullish: return result
            
            # B. 윗꼬리 제한 (몸통의 2배 이하)
            open_p = float(today_candle['stck_oprc'])
            high_p = float(today_candle['stck_hgpr'])
            close_p = float(today_candle['stck_clpr'])
            
            upper_shadow = high_p - close_p
            body = close_p - open_p
            if body > 0 and upper_shadow > body * 2: return result
            
            # C. 꽉 찬 종가 (고가 대비 -2% 이내)
            if close_p < high_p * 0.98: return result

            total_score, score_detail = self.logic.calculate_total_score(indicators, candle_score, is_bullish)
            
            # [유목민 철학] 거래대금 가산점 (150억: 0점, 500억: 10점, 1000억: 20점)
            # 여기서는 trading_value가 정확해야 함
            tv_score = 0
            if trading_value >= 100000000000: # 1000억
                tv_score = 20
                score_detail += "|대금(1000억+):+20"
            elif trading_value >= 50000000000: # 500억
                tv_score = 10
                score_detail += "|대금(500억+):+10"
            
            total_score += tv_score

            result.update({
                'valid': True,
                'price': int(current_price),
                'score': float(round(total_score, 2)),
                'trading_value': trading_value,
                'features': {
                    'cci': float(round(indicators['cci'], 1)),
                    'adx': float(round(indicators['adx'], 1)),
                    'is_bullish': bool(is_bullish),
                    'score_detail': str(score_detail),
                    'candle_detail': str(candle_details)
                },
                'reason': score_detail
            })
            
        except Exception as e:
            logger.error(f"[{self.name}] {ticker} 점수 계산 중 오류: {e}")
            
        return result

    async def _perform_screening(self, data_payload: Dict[str, Any], top_volume_stocks: List[Dict]) -> List[Dict[str, Any]]:
        """스크리닝 실행 (후보 수집 -> 정렬 -> 선발)"""
        candidates = []
        
        # 설정에서 최소 거래대금 가져오기 (없으면 기본 150억)
        min_trading_value = self.config.get('stock_filter', {}).get('min_trading_value_daily', 15000000000)

        # [Step 1] 후보 수집 (Collection)
        for stock_data in top_volume_stocks:
            ticker = stock_data.get('mksc_shrn_iscd')
            stock_name = stock_data.get('hts_kor_isnm')
            
            # 거래대금 1차 필터 (목록 조회 시 이미 포함된 정보 활용)
            try:
                trading_value = float(stock_data.get('acml_tr_pbmn', 0))
            except (ValueError, TypeError):
                trading_value = 0
            
            if trading_value < min_trading_value:
                continue

            if not ticker or not stock_name:
                continue

            # 점수 계산
            result = await self.calculate_score(ticker, data_payload)
            
            # 점수가 60점(Cut-off) 이상인 종목만 후보에 추가
            if result.get('valid') and result.get('score') >= 60:
                # API 데이터의 거래대금이 더 정확할 수 있으므로 업데이트
                if result.get('trading_value', 0) == 0:
                    result['trading_value'] = trading_value
                
                # 반환 포맷 맞추기
                features = result['features']
                candidates.append({
                    'name': str(stock_name),
                    'ticker': str(ticker),
                    'price': result['price'],
                    'score': result['score'],
                    'trading_value': result['trading_value'],
                    'cci': features['cci'],
                    'adx': features['adx'],
                    'is_bullish': features['is_bullish'],
                    'score_detail': features['score_detail'],
                    'candle_detail': features['candle_detail']
                })
        
        # [Step 2] 순위 선정 (Ranking)
        # 점수(score) 기준 내림차순, 동점 시 거래대금(trading_value) 내림차순
        candidates.sort(key=lambda x: (x['score'], x['trading_value']), reverse=True)
        
        return candidates

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
                
                # 스크리닝 실행 (랭킹 시스템 적용)
                screened_stocks = await self._perform_screening(data_payload, top_volume_stocks)
                
                if not screened_stocks:
                    self.notifier.send_alert("종가매매 스크리너 결과, 조건에 맞는 종목이 없습니다.", level='info')
                    return signals
                
                # [Step 3] 최종 선발 (Selection) - TOP 3 저장
                self.top_stocks_today = screened_stocks[:self.strategy_config.top_n_screen]
                
                # 💾 결과 파일 저장 (재시작 시 복구용)
                self._save_screening_results()

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
                            f"💰 대금: {stock['trading_value']/100000000:.0f}억\n"
                            f"📈 CCI: {stock['cci']} | ADX: {stock['adx']}\n"
                            f"🕯️ {stock['candle_detail']}\n"
                            f"💰 현재가: {stock['price']:,.0f}원"
                        ),
                        "inline": False
                    })
                
                embed = {
                    "title": f"🔔 종가매매 후보 TOP3 (15:03)",
                    "description": (
                        f"**가산점 기반 랭킹 시스템 적용**\n"
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
            
            # 최종 선발: 1위 종목
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
            
            consecutive_wins = self.dynamic_params.get('consecutive_wins', 0)
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
