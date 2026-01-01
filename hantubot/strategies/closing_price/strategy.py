import datetime as dt
import json
import os
from typing import Dict, List, Any
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from ...strategies.base_strategy import BaseStrategy
from ...core.portfolio import Portfolio
from ...core.clock import MarketClock
from ...execution.broker import Broker
from ...reporting.logger import get_logger
from ...reporting.notifier import Notifier
from ...utils.stock_filters import is_eligible_stock
from ...reporting.study_db import get_study_db  # DB 연동
from .config import ClosingPriceConfig
from .logic import ClosingPriceLogic

logger = get_logger(__name__)

class ClosingPriceStrategy(BaseStrategy):
    """
    [ClosingPriceStrategy v5.2] 유목민 전략 (데이터화 및 고도화)
    - 12:30 점심 중간 점검 알림 (Dedup 적용)
    - 15:03 종가 배팅 알림 (DB 저장 및 Dedup 적용)
    - 15:15 자동 매수 (Config 매수 비율 적용)
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any], broker: Broker, clock: MarketClock, notifier: Notifier):
        super().__init__(strategy_id, config, broker, clock, notifier)
        
        self.strategy_config = ClosingPriceConfig.from_dict(self.config)
        self.logic = ClosingPriceLogic(self.strategy_config)
        
        # 플래그 관리
        self.has_bought_today = False
        
        self.top_stocks_today = []
        self._load_screening_results()

    def _get_screening_file_path(self):
        today_str = dt.datetime.now().strftime("%Y%m%d")
        if not os.path.exists('data'): os.makedirs('data')
        return os.path.join('data', f'closing_price_targets_{today_str}.json')

    def _save_screening_results(self):
        try:
            # 1. 파일 저장 (기존 유지)
            file_path = self._get_screening_file_path()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.top_stocks_today, f, ensure_ascii=False, indent=2)
            logger.info(f"[{self.name}] 💾 스크리닝 결과 파일 저장 완료")
            
            # 2. DB 저장 (추가)
            db = get_study_db()
            today_str = dt.datetime.now().strftime("%Y%m%d")
            generated_at = dt.datetime.now().isoformat()
            
            for i, stock in enumerate(self.top_stocks_today):
                candidate = {
                    'trade_date': today_str,
                    'generated_at': generated_at,
                    'rank': i + 1,
                    'ticker': stock['ticker'],
                    'name': stock['name'],
                    'score': stock.get('score'),
                    'reason': stock.get('reason'),
                    'selection_type': stock.get('selection_type'),
                    'market_trend': self.logic.get_market_trend(), # 현재 로직에서 가져옴
                    'price_at_signal': stock.get('price'),
                    'trading_value': stock.get('trading_value'),
                    'sector': stock.get('sector'),
                    'raw_payload_json': stock
                }
                db.insert_closing_candidate(candidate)
            logger.info(f"[{self.name}] 💾 스크리닝 결과 DB 저장 완료")
            
        except Exception as e:
            logger.error(f"[{self.name}] 저장 실패: {e}")

    def _load_screening_results(self):
        try:
            file_path = self._get_screening_file_path()
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.top_stocks_today = json.load(f)
                if self.top_stocks_today:
                    self.has_webhook_sent_today = True 
        except Exception:
            pass

    def calculate_score(self, ticker: str, stock_info: Dict[str, Any], data_payload: Dict[str, Any], market_trend: str) -> Dict[str, Any]:
        """개별 종목 채점 (시장 지수 반영)"""
        result = {'valid': False, 'symbol': ticker, 'score': 0, 'features': {}, 'reason': ''}
        
        try:
            # 1. API 데이터 추출
            current_price = float(stock_info.get('stck_prpr', 0))
            trading_value = float(stock_info.get('acml_tr_pbmn', 0))
            change_rate = float(stock_info.get('prdy_ctrt', 0))
            sector_name = stock_info.get('bstp_kor_isnm', 'Unknown')
            
            # 🔥 외국인 수급 확인
            frgn_net_buy = float(stock_info.get('frgn_ntby_qty', 0))
            is_foreigner_buy = frgn_net_buy > 0
            
            # 2. 일봉 데이터 (MA20, CCI)
            hist_data = data_payload['historical_daily'].get(ticker)
            if not hist_data:
                hist_data = self.broker.get_historical_daily_data(ticker, days=30)
                if hist_data: data_payload['historical_daily'][ticker] = hist_data
            
            if not hist_data or len(hist_data) < 20:
                result['reason'] = "데이터부족"
                return result

            df = pd.DataFrame(hist_data)
            for col in ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol', 'stck_oprc']:
                if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
            
            # 3. 기본 필터
            is_valid, validation_reason = self.logic.is_valid_candidate(df, stock_info)
            if not is_valid:
                result['reason'] = validation_reason
                return result

            # 4. 점수 계산
            indicators = self.logic.get_indicators(df)
            cci_val = indicators.get('cci', 0.0)
            
            score, score_detail = self.logic.calculate_base_score(
                current_price, trading_value, change_rate, cci_val, 
                market_trend, is_foreigner_buy
            )
            
            result.update({
                'valid': True,
                'name': stock_info.get('hts_kor_isnm', ''),
                'ticker': ticker,
                'price': int(current_price),
                'score': score,
                'trading_value': trading_value,
                'sector': sector_name,
                'reason': score_detail,
                'features': {
                    'cci': float(round(cci_val, 1)),
                    'change_rate': change_rate,
                    'score_detail': score_detail,
                    'is_foreigner': is_foreigner_buy
                }
            })
            
        except Exception as e:
            logger.error(f"[{self.name}] {ticker} 오류: {e}")
            result['reason'] = f"에러:{str(e)}"
            
        return result

    async def _perform_screening(self, data_payload: Dict[str, Any], top_volume_stocks: List[Dict]) -> List[Dict[str, Any]]:
        """스크리닝 실행 (공통 로직)"""
        candidates = []
        min_trading_value_cutoff = 30_000_000_000 
        
        market_trend = self.logic.get_market_trend()
        logger.info(f"[{self.name}] 시장 추세: {market_trend.upper()}")

        targets = []
        for stock_data in top_volume_stocks:
            ticker = stock_data.get('mksc_shrn_iscd')
            try: tv = float(stock_data.get('acml_tr_pbmn', 0))
            except: tv = 0
            if tv < min_trading_value_cutoff: continue
            if ticker: targets.append((ticker, stock_data))

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_info = {
                executor.submit(self.calculate_score, ticker, stock_info, data_payload, market_trend): ticker
                for ticker, stock_info in targets
            }
            for future in as_completed(future_to_info):
                try:
                    res = future.result()
                    if res.get('valid'): candidates.append(res)
                except Exception: pass

        selected_stocks, selection_type = self.logic.filter_and_rank(candidates)
        for stock in selected_stocks:
            stock['selection_type'] = selection_type
            
        return selected_stocks

    async def generate_signal(self, data_payload: Dict[str, Any], portfolio: Portfolio) -> List[Dict[str, Any]]:
        signals = []
        now = dt.datetime.now()
        today_str = now.strftime("%Y%m%d")
        
        # 리셋 (다음날을 위해)
        if now.hour >= 16:
            self.has_bought_today = False
            self.top_stocks_today = []
            return signals
        
        # 🍱 [12:30] 점심 브리핑 (Dedup Key 사용)
        if dt.time(12, 30) <= now.time() < dt.time(12, 40):
            dedup_key = f"MIDDAY_SCREENING:{today_str}:1230"
            # Notifier 내부 캐시가 아니라, 여기서 먼저 확인하고 로직을 태우는게 효율적일 수 있으나
            # Notifier에 로직을 위임하려면 일단 계산 후 보내야 함.
            # 하지만 계산 비용이 크므로, 로컬 플래그 대신 Notifier의 캐시를 확인하는게 좋지만 Notifier는 private함.
            # 따라서 기존처럼 로컬 플래그를 쓰되, Notifier의 dedup도 활용.
            
            # 여기서는 로컬 플래그 대신 DB나 메모리 상태를 확인하여 중복 실행 방지
            # (간단하게 Notifier 전송 시점에 처리)
            
            try:
                top_volume_stocks_raw = self.broker.get_realtime_transaction_ranks(top_n=100)
                if top_volume_stocks_raw:
                    top_volume_stocks = [item for item in top_volume_stocks_raw if is_eligible_stock(item.get('hts_kor_isnm', ''))]
                    lunch_stocks = await self._perform_screening(data_payload, top_volume_stocks)
                    
                    if lunch_stocks:
                        fields = []
                        for i, stock in enumerate(lunch_stocks):
                            tv_billion = stock['trading_value'] / 100_000_000
                            sector = stock.get('sector', '-')
                            fields.append({
                                "name": f"{i+1}위: {stock['name']} ({stock['ticker']})",
                                "value": f"**{stock['score']}점** | {stock['reason']}\n🏢 {sector} | 💰 {tv_billion:,.0f}억",
                                "inline": False
                            })
                        
                        embed = {
                            "title": f"🍱 점심 중간 점검 (12:30)",
                            "description": "**[Plan B] 오후장 매수 참고용**\n현재 시점 1,000억 클럽/주도주 현황입니다.",
                            "color": 16776960, # 노란색
                            "fields": fields
                        }
                        self.notifier.send_alert("점심 브리핑", embed=embed, dedup_key=dedup_key)
            except Exception as e:
                logger.error(f"점심 스크리닝 오류: {e}")

        # ⏰ [15:03] 종가 스크리닝 (Dedup Key 사용)
        if self.strategy_config.webhook_time <= now.time() < self.strategy_config.buy_start_time:
            dedup_key = f"CLOSE_TOP3:{today_str}:1503"
            
            # 이미 전송했는지 확인 (로컬 캐시) -> API 호출 절약
            # 하지만 정확한 Dedup을 위해 매번 실행하되 Notifier에서 막는 방식도 가능.
            # 여기서는 비용 절감을 위해 self.top_stocks_today가 비어있을 때만 실행
            if not self.top_stocks_today:
                logger.info(f"[{self.name}] ===== 15:03 종가 배팅 스크리닝 =====")
                try:
                    top_volume_stocks_raw = self.broker.get_realtime_transaction_ranks(top_n=100)
                    if top_volume_stocks_raw:
                        top_volume_stocks = [item for item in top_volume_stocks_raw if is_eligible_stock(item.get('hts_kor_isnm', ''))]
                        screened_stocks = await self._perform_screening(data_payload, top_volume_stocks)
                        
                        if screened_stocks:
                            self.top_stocks_today = screened_stocks
                            selection_type = self.top_stocks_today[0].get('selection_type', '알수없음')
                            self._save_screening_results() # DB 및 파일 저장

                            # 웹훅 발송
                            fields = []
                            for i, stock in enumerate(self.top_stocks_today):
                                rank_emoji = '🥇' if i==0 else '🥈' if i==1 else '🥉'
                                tv_billion = stock['trading_value'] / 100_000_000
                                sector = stock.get('sector', '-')
                                
                                fields.append({
                                    "name": f"{rank_emoji} {i+1}위: {stock['name']} ({stock['ticker']})",
                                    "value": (
                                        f"**점수: {stock['score']}점**\n"
                                        f"└ {stock['reason']}\n"
                                        f"🏢 업종: {sector} | 💰 {tv_billion:,.0f}억\n"
                                        f"💵 현재가: {stock['price']:,.0f}원"
                                    ),
                                    "inline": False
                                })
                            
                            embed = {
                                "title": f"🐫 유목민 1,000억 클럽 TOP3",
                                "description": f"**유형: {selection_type}**\n시장추세 반영 완료\n⏰ 15:15 1위 매수 예정",
                                "color": 16705372,
                                "fields": fields
                            }
                            self.notifier.send_alert("종가매매 후보 알림", embed=embed, dedup_key=dedup_key)
                        else:
                            msg = "🚫 [유목민 전략] 조건 만족 종목 없음"
                            self.notifier.send_alert(msg, level='info', dedup_key=dedup_key)
                except Exception as e:
                    logger.error(f"스크리닝 오류: {e}", exc_info=True)
            return signals
        
        # 15:15 매수 (Config 매수 비율 적용)
        if self.strategy_config.buy_start_time <= now.time() <= self.strategy_config.buy_end_time and not self.has_bought_today:
            
            # [정책 확인] intraday_over_closing 정책일 경우, 포지션이 있으면 스킵
            # 하지만 이는 OrderManager 레벨에서 처리하는게 더 좋지만, 여기서 미리 확인하여 로그를 남김
            policy = self.global_config.get('policy', {})
            priority = policy.get('position_priority', 'closing_over_intraday')
            
            if priority == 'intraday_over_closing' and portfolio.get_positions():
                logger.info(f"[{self.name}] intraday_over_closing 정책에 따라 보유 포지션이 있어 종가 매수를 스킵합니다.")
                self.has_bought_today = True 
                return signals

            if not self.top_stocks_today or not self.strategy_config.auto_buy_enabled: return signals
            
            self.has_bought_today = True
            top_stock = self.top_stocks_today[0]
            
            avail_cash = portfolio.get_cash()
            price = self.broker.get_current_price(top_stock['ticker']) or top_stock['price']
            
            # [변경] 공통 매수 수량 계산 메서드 사용 (Config 비율 적용)
            qty = self.calculate_buy_quantity(price, avail_cash)
            
            if qty > 0:
                signals.append({
                    'strategy_id': self.strategy_id,
                    'symbol': top_stock['ticker'],
                    'side': 'buy',
                    'quantity': qty,
                    'price': 0,
                    'order_type': 'market',
                    'features': {'score': top_stock['score']}
                })
                logger.info(f"[{self.name}] 🎯 매수 신호: {top_stock['name']} {qty}주")
            return signals
            
        return signals
