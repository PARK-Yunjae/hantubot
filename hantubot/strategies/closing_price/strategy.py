import datetime as dt
import json
import os
import time
from typing import Dict, List, Any
import pandas as pd
from pykrx import stock
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
    [ClosingPriceStrategy v6] Nomad Score V3 Implementation
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
        self.has_lunch_report_sent = False  # 점심 브리핑 발송 여부
        
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

    def _get_stock_status_kis(self, ticker: str) -> Dict[str, Any]:
        """KIS API를 통해 종목 상태(관리종목 등) 및 상세 정보 조회"""
        try:
            # Broker -> KisApi 접근
            if hasattr(self.broker, 'api'):
                url_path = "/uapi/domestic-stock/v1/quotations/inquire-price"
                tr_id = "FHKST01010100"
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": ticker
                }
                data = self.broker.api.request("GET", url_path, tr_id, params=params)
                if str(data.get('rt_cd')) == '0':
                    return data.get('output', {})
        except Exception:
            pass
        return {}

    def calculate_score(self, ticker: str, stock_info: Dict[str, Any], data_payload: Dict[str, Any], market_trend: str) -> Dict[str, Any]:
        """개별 종목 채점 (Nomad V3)"""
        result = {'valid': False, 'symbol': ticker, 'score': 0, 'features': {}, 'reason': ''}
        
        try:
            today_str = dt.datetime.now().strftime("%Y%m%d")
            
            # 1. Broker Data (Basic)
            # stock_info comes from get_realtime_transaction_ranks (FHPST01710000)
            # It has 'acml_tr_pbmn' (Trading Value), 'stck_prpr' (Price), etc.
            current_price = float(stock_info.get('stck_prpr', 0))
            trading_value = float(stock_info.get('acml_tr_pbmn', 0))
            change_rate = float(stock_info.get('prdy_ctrt', 0))
            
            # 2. Historical Data (MA, CCI, 52w)
            hist_data = data_payload['historical_daily'].get(ticker)
            if not hist_data:
                hist_data = self.broker.get_historical_daily_data(ticker, days=250) # Need 1 year for 52w high
                if hist_data: data_payload['historical_daily'][ticker] = hist_data
            
            if not hist_data or len(hist_data) < 60:
                result['reason'] = "데이터부족"
                return result

            df = pd.DataFrame(hist_data)
            for col in ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol', 'stck_oprc']:
                if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.sort_values(by='stck_bsop_date').reset_index(drop=True)
            
            # 3. Enhance Data (Fetch details if needed)
            # Admin Status (KIS) & Sector
            kis_detail = self._get_stock_status_kis(ticker)
            if kis_detail:
                stock_info['iscd_stat_cls_code'] = kis_detail.get('iscd_stat_cls_code', '')
                stock_info['bstp_kor_isnm'] = kis_detail.get('bstp_kor_isnm', stock_info.get('bstp_kor_isnm', 'Unknown'))
            
            # Foreigner Net Buy (Pykrx)
            # Try Pykrx if not in stock_info (FHPST01710000 likely doesn't have it)
            # Note: Frequent pykrx calls can be slow.
            if 'frgn_ntby_qty' not in stock_info or float(stock_info.get('frgn_ntby_qty', 0)) == 0:
                try:
                    inv_df = stock.get_market_investor_net_turnover_by_ticker(today_str, today_str, ticker)
                    if not inv_df.empty and '외국인' in inv_df.columns:
                        stock_info['frgn_ntby_qty'] = inv_df['외국인'].sum()
                except Exception:
                    pass
            
            # Shares Outstanding (Pykrx)
            # Needed for Turnover Ratio
            try:
                cap_df = stock.get_market_cap_by_date(today_str, today_str, ticker)
                if not cap_df.empty:
                    stock_info['lstn_stcn'] = cap_df.iloc[-1]['상장주식수']
            except Exception:
                pass

            # 4. Filter Check (Nomad V3 Hard Filters)
            is_valid, validation_reason = self.logic.is_valid_candidate(df, stock_info)
            if not is_valid:
                result['reason'] = validation_reason
                return result

            # 5. Score Calculation (Nomad V3)
            score, score_detail, features = self.logic.calculate_nomad_score_v3(df, stock_info, market_trend)
            
            # Additional feature storage
            features['change_rate'] = change_rate
            features['score_detail'] = score_detail
            
            sector_name = stock_info.get('bstp_kor_isnm', 'Unknown')
            
            result.update({
                'valid': True,
                'name': stock_info.get('hts_kor_isnm', ''),
                'ticker': ticker,
                'price': int(current_price),
                'score': score,
                'trading_value': trading_value,
                'sector': sector_name,
                'reason': score_detail,
                'features': features
            })
            
        except Exception as e:
            logger.error(f"[{self.name}] {ticker} 오류: {e}")
            result['reason'] = f"에러:{str(e)}"
            
        return result

    async def _perform_screening(self, data_payload: Dict[str, Any], top_volume_stocks: List[Dict]) -> List[Dict[str, Any]]:
        """스크리닝 실행 (공통 로직)"""
        candidates = []
        min_trading_value_cutoff = 100_000_000_000 # 1000억 (사전 필터링)
        
        market_trend = self.logic.get_market_trend()
        logger.info(f"[{self.name}] 시장 추세: {market_trend.upper()}")

        targets = []
        for stock_data in top_volume_stocks:
            ticker = stock_data.get('mksc_shrn_iscd')
            try: tv = float(stock_data.get('acml_tr_pbmn', 0))
            except: tv = 0
            
            # 1,000억 미만은 스코어링조차 할 필요 없음 (최적화)
            if tv < min_trading_value_cutoff: continue
            
            if ticker: targets.append((ticker, stock_data))

        # ThreadPoolExecutor로 병렬 스코어링
        with ThreadPoolExecutor(max_workers=5) as executor: # pykrx 호출 빈도 고려하여 워커 줄임
            future_to_info = {
                executor.submit(self.calculate_score, ticker, stock_info, data_payload, market_trend): ticker
                for ticker, stock_info in targets
            }
            for future in as_completed(future_to_info):
                try:
                    res = future.result()
                    if res.get('valid'): candidates.append(res)
                except Exception: pass

        # 최종 랭킹 및 등급 산정 (섹터 보너스 포함)
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
            self.has_lunch_report_sent = False
            self.top_stocks_today = []
            return signals
        
        # 🍱 [12:30] 점심 브리핑 (Nomad V3 적용)
        if dt.time(12, 30) <= now.time() < dt.time(12, 40):
            if self.has_lunch_report_sent: return signals
            self.has_lunch_report_sent = True

            dedup_key = f"MIDDAY_SCREENING:{today_str}:1230"
            
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
                                "value": f"**{stock['score']}점 ({stock.get('grade', '')})** | {stock['reason']}\n🏢 {sector} | 💰 {tv_billion:,.0f}억",
                                "inline": False
                            })
                        
                        embed = {
                            "title": f"🍱 Nomad V3 점심 점검 (12:30)",
                            "description": "**오후장 관전용**\nNomad Score V3 기준 상위 종목",
                            "color": 16776960, # 노란색
                            "fields": fields
                        }
                        self.notifier.send_alert("점심 브리핑", embed=embed, dedup_key=dedup_key)
            except Exception as e:
                logger.error(f"점심 스크리닝 오류: {e}")

        # ⏰ [15:03] 종가 스크리닝 (Nomad V3 적용)
        if self.strategy_config.webhook_time <= now.time() < self.strategy_config.buy_start_time:
            dedup_key = f"CLOSE_TOP3:{today_str}:1503"
            
            if not self.top_stocks_today:
                logger.info(f"[{self.name}] ===== 15:03 Nomad V3 Screening =====")
                try:
                    top_volume_stocks_raw = self.broker.get_realtime_transaction_ranks(top_n=100)
                    if top_volume_stocks_raw:
                        top_volume_stocks = [item for item in top_volume_stocks_raw if is_eligible_stock(item.get('hts_kor_isnm', ''))]
                        screened_stocks = await self._perform_screening(data_payload, top_volume_stocks)
                        
                        if screened_stocks:
                            self.top_stocks_today = screened_stocks
                            selection_type = self.top_stocks_today[0].get('selection_type', 'Nomad V3')
                            self._save_screening_results()

                            # 웹훅 발송
                            fields = []
                            for i, stock in enumerate(self.top_stocks_today):
                                rank_emoji = '🥇' if i==0 else '🥈' if i==1 else '🥉'
                                tv_billion = stock['trading_value'] / 100_000_000
                                sector = stock.get('sector', '-')
                                grade = stock.get('grade', '')
                                
                                fields.append({
                                    "name": f"{rank_emoji} {i+1}위: {stock['name']} ({stock['ticker']})",
                                    "value": (
                                        f"**{stock['score']}점 ({grade})**\n"
                                        f"└ {stock['reason']}\n"
                                        f"🏢 {sector} | 💰 {tv_billion:,.0f}억 | 💵 {stock['price']:,.0f}원"
                                    ),
                                    "inline": False
                                })
                            
                            embed = {
                                "title": f"🐳 Nomad V3 Whale Radar",
                                "description": f"**유형: {selection_type}**\n시장추세: {self.logic.get_market_trend().upper()}\n⏰ 15:15 1위 매수 예정",
                                "color": 0xFFD700, # Gold
                                "fields": fields
                            }
                            self.notifier.send_alert("Nomad V3 Signal", embed=embed, dedup_key=dedup_key)
                        else:
                            msg = "🚫 [Nomad V3] 조건 만족 종목(A-Class 이상) 없음"
                            self.notifier.send_alert(msg, level='info', dedup_key=dedup_key)
                except Exception as e:
                    logger.error(f"스크리닝 오류: {e}", exc_info=True)
            return signals
        
        # 15:15 매수 (Config 매수 비율 적용)
        if self.strategy_config.buy_start_time <= now.time() <= self.strategy_config.buy_end_time and not self.has_bought_today:
            
            policy = self.global_config.get('policy', {})
            priority = policy.get('position_priority', 'closing_over_intraday')
            
            if priority == 'intraday_over_closing' and portfolio.get_positions():
                logger.info(f"[{self.name}] intraday_over_closing 정책에 따라 보유 포지션이 있어 종가 매수를 스킵합니다.")
                self.has_bought_today = True 
                return signals

            if not self.top_stocks_today or not self.strategy_config.auto_buy_enabled: return signals
            
            self.has_bought_today = True
            top_stock = self.top_stocks_today[0]
            
            # S-Class/A-Class 필터 적용? 
            # Logic returns only S or A class (>=80). So top 1 is safe.
            
            avail_cash = portfolio.get_cash()
            price = self.broker.get_current_price(top_stock['ticker']) or top_stock['price']
            
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
