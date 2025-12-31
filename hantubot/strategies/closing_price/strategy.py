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
    [ClosingPriceStrategy v4] 2025년 유동성 기준 (1,000억 클럽) 적용
    
    1. 후보 수집: 1차 거래대금 필터(300억) 통과 종목 대상
    2. 점수 계산: 거래대금 + CCI + 등락률 (100점 만점)
    3. 최종 선발:
       - 1군: 거래대금 1,000억+, 양봉, 2,000원+ (점수순)
       - 2군(Plan B): 1군 없을 시 300억+, 양봉 (점수순)
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
        
        # 재시작 시 오늘 스크리닝 결과 복구
        self._load_screening_results()

    def _get_screening_file_path(self):
        """오늘 날짜의 스크리닝 결과 파일 경로"""
        today_str = dt.datetime.now().strftime("%Y%m%d")
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
                    self.has_webhook_sent_today = True 
            else:
                pass
        except Exception as e:
            logger.error(f"[{self.name}] 스크리닝 결과 로드 실패: {e}")

    def calculate_score(self, ticker: str, stock_info: Dict[str, Any], data_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        개별 종목 필터링 및 점수 계산 (CCI, 등락률, 거래대금 등)
        """
        result = {'valid': False, 'symbol': ticker, 'score': 0, 'features': {}, 'reason': ''}
        
        try:
            # 1. API 데이터 추출
            current_price = float(stock_info.get('stck_prpr', 0))
            trading_value = float(stock_info.get('acml_tr_pbmn', 0))
            change_rate = float(stock_info.get('prdy_ctrt', 0))
            
            # 2. 일봉 데이터 조회 (CCI 및 MA20 계산용)
            hist_data = data_payload['historical_daily'].get(ticker)
            if not hist_data:
                hist_data = self.broker.get_historical_daily_data(ticker, days=30)
                if hist_data:
                    data_payload['historical_daily'][ticker] = hist_data
            
            if not hist_data or len(hist_data) < 20:
                result['reason'] = "데이터부족"
                return result

            df = pd.DataFrame(hist_data)
            # 숫자형 변환
            for col in ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol', 'stck_oprc']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
            
            # 3. 기본 필터 검증 (MA20, 캔들 등)
            is_valid, validation_reason = self.logic.is_valid_candidate(df, stock_info)
            if not is_valid:
                result['reason'] = validation_reason
                return result

            # 4. 보조지표(CCI) 계산
            indicators = self.logic.get_indicators(df)
            cci_val = indicators.get('cci', 0.0)
            
            # 5. 점수 계산
            score, score_detail = self.logic.calculate_score(current_price, trading_value, change_rate, cci_val)
            
            result.update({
                'valid': True,
                'name': stock_info.get('hts_kor_isnm', ''),
                'ticker': ticker,
                'price': int(current_price),
                'score': score,
                'trading_value': trading_value,
                'reason': score_detail,
                'features': {
                    'cci': float(round(cci_val, 1)),
                    'change_rate': change_rate,
                    'score_detail': score_detail
                }
            })
            
        except Exception as e:
            logger.error(f"[{self.name}] {ticker} 계산 중 오류: {e}")
            result['reason'] = f"에러:{str(e)}"
            
        return result

    async def _perform_screening(self, data_payload: Dict[str, Any], top_volume_stocks: List[Dict]) -> List[Dict[str, Any]]:
        """스크리닝 실행 (후보 수집 -> 랭킹 선정) - 병렬 처리"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        candidates = []
        
        # 1차 대상: 거래대금 상위 종목 전체 (API에서 이미 정렬되어 옴)
        # 최소 거래대금 300억 (Plan B 기준) 이상인 종목만 계산 대상으로 삼음 (2025 기준)
        min_trading_value_cutoff = 30_000_000_000 

        targets = []
        for stock_data in top_volume_stocks:
            ticker = stock_data.get('mksc_shrn_iscd')
            stock_name = stock_data.get('hts_kor_isnm')
            
            try:
                trading_value = float(stock_data.get('acml_tr_pbmn', 0))
            except (ValueError, TypeError):
                trading_value = 0
            
            if trading_value < min_trading_value_cutoff:
                continue

            if not ticker or not stock_name:
                continue
            
            targets.append((ticker, stock_name, stock_data))

        # [Step 1] 점수 계산 및 필터링 (병렬 처리)
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_info = {
                executor.submit(self.calculate_score, ticker, stock_info, data_payload): (ticker, stock_name)
                for ticker, stock_name, stock_info in targets
            }
            
            for future in as_completed(future_to_info):
                try:
                    result = future.result()
                    if result.get('valid'):
                        candidates.append(result)
                except Exception as e:
                    logger.error(f"[{self.name}] 채점 중 에러: {e}")

        # [Step 2] 필터링 및 랭킹 (1군 -> 2군)
        selected_stocks, selection_type = self.logic.filter_and_rank(candidates)
        
        # 선택된 종목에 선정 유형 정보 추가
        for stock in selected_stocks:
            stock['selection_type'] = selection_type
            
        return selected_stocks

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
            logger.info(f"[{self.name}] ===== 15:03 유목민 스타일 스크리닝 실행 =====")
            self.has_webhook_sent_today = True
            
            try:
                # KIS API로 거래대금 상위 종목 조회 (충분히 많이 가져옴)
                top_volume_stocks_raw = self.broker.get_realtime_transaction_ranks(top_n=100)
                if not top_volume_stocks_raw:
                    logger.warning(f"[{self.name}] 거래대금 상위 종목 조회 실패")
                    return signals
                
                # ETF, 스팩 필터링
                top_volume_stocks = [
                    item for item in top_volume_stocks_raw
                    if is_eligible_stock(item.get('hts_kor_isnm', ''))
                ]
                logger.info(f"[{self.name}] 적격 종목 {len(top_volume_stocks)}개 발견 (필터링 전)")
                
                # 스크리닝 실행
                screened_stocks = await self._perform_screening(data_payload, top_volume_stocks)
                
                if not screened_stocks:
                    msg = "🚫 [2025 유목민 전략] 조건에 맞는 종목이 없습니다.\n(Plan B 최소 거래대금 300억 미달)"
                    logger.info(msg)
                    self.notifier.send_alert(msg, level='info')
                    return signals
                
                # [Step 3] 최종 선발
                self.top_stocks_today = screened_stocks # 이미 filter_and_rank에서 Top 3 반환
                selection_type = self.top_stocks_today[0].get('selection_type', '알수없음')
                
                # 💾 결과 파일 저장
                self._save_screening_results()

                # Discord 웹훅 발송
                fields = []
                for i, stock in enumerate(self.top_stocks_today):
                    rank_emoji = '🥇' if i==0 else '🥈' if i==1 else '🥉'
                    trading_val_billion = stock['trading_value'] / 100_000_000
                    change_rate = stock['features']['change_rate']
                    cci_val = stock['features']['cci']
                    score = stock['score']
                    
                    fields.append({
                        "name": f"{rank_emoji} {i+1}위: {stock['name']} ({stock['ticker']})",
                        "value": (
                            f"**점수: {score}점** ({stock['reason']})\n"
                            f"💰 대금: {trading_val_billion:,.0f}억\n"
                            f"📈 등락: {change_rate:+.2f}% | CCI: {cci_val:.1f}\n"
                            f"💵 현재가: {stock['price']:,.0f}원"
                        ),
                        "inline": False
                    })
                
                embed = {
                    "title": f"🐫 유목민 1,000억 클럽 TOP3 (15:03)",
                    "description": (
                        f"**선정 유형: {selection_type}**\n"
                        f"1군: 대금 1,000억/양봉/2,000원\n"
                        f"2군: 대금 300억/양봉 (Plan B)\n"
                        f"⏰ 15:15에 1위 종목 매수 예정"
                    ),
                    "color": 16705372,  # 금색
                    "fields": fields,
                    "footer": {"text": "자동 매수 활성화 시 1위 종목 매수"}
                }
                self.notifier.send_alert("종가매매 후보 알림", embed=embed)
                logger.info(f"[{self.name}] 웹훅 발송 완료. 선정 유형: {selection_type}")
                
            except Exception as e:
                logger.error(f"[{self.name}] 스크리닝 중 오류: {e}", exc_info=True)
            
            return signals
        
        # ========================================
        # 15:15-15:19: 저장된 1위 종목 매수
        # ========================================
        if self.strategy_config.buy_start_time <= now.time() <= self.strategy_config.buy_end_time and not self.has_bought_today:
            if not self.top_stocks_today:
                logger.warning(f"[{self.name}] 선정된 종목이 없어 매수를 건너뜁니다.")
                return signals
            
            if not self.strategy_config.auto_buy_enabled:
                logger.info(f"[{self.name}] 자동 매수 비활성화. 매수 건너뜀")
                return signals
            
            if portfolio.get_positions():
                logger.info(f"[{self.name}] 이미 보유 중인 종목이 있어 매수 건너뜀")
                self.has_bought_today = True
                return signals
            
            logger.info(f"[{self.name}] ===== 15:15 매수 실행 =====")
            self.has_bought_today = True
            
            top_stock = self.top_stocks_today[0]
            logger.info(f"[{self.name}] 🎯 1위 종목 매수 시도: {top_stock['name']} ({top_stock['ticker']})")
            
            current_price = self.broker.get_current_price(top_stock['ticker'])
            if current_price <= 0:
                current_price = top_stock['price']
            
            available_cash = portfolio.get_cash()
            order_amount = available_cash * 0.98
            quantity = int(order_amount // current_price)
            
            if quantity == 0:
                logger.warning(f"[{self.name}] 현금 부족으로 매수 불가 ({available_cash:,.0f}원)")
                return signals
            
            signals.append({
                'strategy_id': self.strategy_id,
                'symbol': top_stock['ticker'],
                'side': 'buy',
                'quantity': quantity,
                'price': 0,
                'order_type': 'market',
                'features': {
                    'score': top_stock['score'],
                    'selection_type': top_stock.get('selection_type', 'unknown')
                }
            })
            logger.info(f"[{self.name}] 매수 신호 생성 완료 ({quantity}주)")
            
            return signals
            
        return signals
