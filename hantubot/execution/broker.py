import json
import time
import datetime as dt
from typing import Any, Dict, Optional, List

import requests
import yaml
from pykrx import stock

from ..reporting.logger import get_logger

logger = get_logger(__name__)

class Broker:
    """
    한국투자증권 OpenAPI 클라이언트 (국내주식)
    인증, API 요청, 응답 파싱 등 모든 KIS API 상호작용을 담당.
    모의투자 시, 지원되지 않는 API는 웹 스크레이핑으로 대체 데이터를 제공.
    """

    def __init__(self, config: dict, is_mock: bool):
        api_conf = config['api']
        self._APP_KEY = api_conf['app_key']
        self._APP_SECRET = api_conf['app_secret']
        self.ACCOUNT_NO = api_conf['account_no']
        self.IS_MOCK = is_mock
        self.BASE_URL = api_conf['base_url']['mock'] if is_mock else api_conf['base_url']['live']

        self._session = requests.Session()
        self._token_info: Dict[str, Any] = {}
        self._ensure_token()

        # pykrx 데이터 캐시용
        self._pykrx_cache: List[Dict] = []
        self._pykrx_cache_time: Optional[dt.datetime] = None
        
        # 모의투자용 가짜 체결 데이터 큐
        self._mock_fill_queue: List[Dict] = []

        logger.info(f"Broker initialized for {'MOCK' if is_mock else 'LIVE'} trading. Account: {self.ACCOUNT_NO}")

    # --- Authentication ---
    def _issue_new_token(self):
        """새로운 접근 토큰을 발급받습니다."""
        url = f"{self.BASE_URL}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self._APP_KEY,
            "appsecret": self._APP_SECRET,
        }
        try:
            res = self._session.post(url, headers=headers, data=json.dumps(body), timeout=10)
            res.raise_for_status()
            token_data = res.json()
            
            expires_in = token_data.get('expires_in', 86400)
            expire_time = dt.datetime.now() + dt.timedelta(seconds=expires_in - 300)
            
            token_data['expire_time'] = expire_time
            self._token_info = token_data
            logger.info(f"새 접근 토큰 발급. 만료: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
        except requests.exceptions.RequestException as e:
            logger.critical(f"[Broker] 토큰 발급 실패: {e}")
            raise RuntimeError("KIS API로부터 접근 토큰을 발급받지 못했습니다.")

    def _ensure_token(self):
        """토큰 유효성을 확인하고, 만료 시 갱신합니다."""
        now = dt.datetime.now()
        expire_time = self._token_info.get('expire_time')
        if not expire_time or expire_time <= now:
            logger.warning("접근 토큰이 만료되었거나 없습니다. 새로 발급합니다.")
            self._issue_new_token()

    def _get_hashkey(self, data: Dict) -> str:
        """POST 요청을 위한 hashkey를 생성합니다."""
        url = f"{self.BASE_URL}/uapi/hashkey"
        headers = {
            "content-type": "application/json",
            "appkey": self._APP_KEY,
            "appsecret": self._APP_SECRET,
        }
        try:
            res = self._session.post(url, headers=headers, data=json.dumps(data), timeout=10)
            res.raise_for_status()
            return res.json().get("HASH", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"Hashkey 생성 실패: {e}")
            return ""

    @property
    def _access_token(self) -> str:
        self._ensure_token()
        return self._token_info.get('access_token', '')

    def _get_headers(self, tr_id: str, hashkey: Optional[str] = None) -> Dict[str, str]:
        """API 요청을 위한 표준 헤더를 생성합니다."""
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token}",
            "appkey": self._APP_KEY,
            "appsecret": self._APP_SECRET,
            "tr_id": tr_id,
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def _request(self, method: str, url_path: str, tr_id: str, params: Optional[Dict] = None, body: Optional[Dict] = None, hashkey: Optional[str] = None, max_retries: int = 5) -> Dict:
        """API 요청 래퍼. 에러 처리 및 재시도를 수행합니다."""
        self._ensure_token()
        full_url = f"{self.BASE_URL}{url_path}"
        
        for attempt in range(max_retries):
            headers = self._get_headers(tr_id, hashkey=hashkey)
            try:
                if method.upper() == 'GET':
                    resp = self._session.get(full_url, headers=headers, params=params, timeout=10)
                elif method.upper() == 'POST':
                    resp = self._session.post(full_url, headers=headers, data=json.dumps(body), timeout=10)
                else:
                    raise ValueError("Unsupported HTTP method")

                resp.raise_for_status()
                data = resp.json()

                if str(data.get("rt_cd")) != "0":
                    if data.get("msg_cd") == "EGW00201":
                        time.sleep(0.2)
                        logger.warning(f"요청 한도 초과. 재시도... ({attempt + 1}/{max_retries})")
                        continue
                    if "token" in data.get("msg1", "").lower():
                        logger.warning("토큰 관련 오류 감지. 토큰 갱신 후 재시도.")
                        self._issue_new_token()
                        continue
                    logger.error(f"API 오류 (tr_id: {tr_id}): {data}")
                    return data
                
                return data
            except json.JSONDecodeError:
                logger.error(f"JSON 파싱 오류. 응답 상태: {resp.status_code}, 내용: {resp.text[:300]}")
                return {"rt_cd": "-1", "msg1": "JSON 파싱 오류"}
            except requests.exceptions.RequestException as e:
                # 404 에러는 재시도하지 않고 즉시 실패 처리
                if e.response is not None and e.response.status_code == 404:
                    logger.critical(f"API 경로를 찾을 수 없습니다 (404 Not Found): {full_url}")
                    break
                
                logger.error(f"HTTP 요청 실패: {e}. 재시도... ({attempt + 1}/{max_retries})")
                time.sleep(0.5)

        logger.critical(f"API 요청이 {max_retries}번의 재시도 후에도 최종 실패했습니다: {full_url}")
        return {}

    def get_current_price(self, symbol: str) -> float:
        """현재가를 조회합니다."""
        url_path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol}
        
        data = self._request("GET", url_path, tr_id, params=params)
        
        price_str = data.get('output', {}).get('stck_prpr', '0')
        return float(price_str) if price_str else 0.0

    def _get_volume_leaders_from_pykrx(self, top_n_each: int = 50) -> list:
        """[모의투자용] pykrx를 사용하여 KOSPI, KOSDAQ 각 시장별 거래량 상위 종목을 조회합니다."""
        now = dt.datetime.now()
        
        # 1. 캐시 확인: 1분 이내 재요청 시 캐시된 데이터 반환
        if self._pykrx_cache and self._pykrx_cache_time and (now - self._pykrx_cache_time).total_seconds() < 60:
            logger.debug("pykrx 거래량 상위 데이터 재사용 (캐시)")
            return self._pykrx_cache

        logger.info("모의투자 모드: pykrx를 사용하여 거래량 상위 데이터를 조회합니다.")
        
        try:
            today_str = now.strftime("%Y%m%d")
            all_leaders = []

            for market in ["KOSPI", "KOSDAQ"]:
                df = stock.get_market_ohlcv_by_ticker(today_str, market=market)
                if df is None or df.empty:
                    logger.warning(f"pykrx: {market} 시장의 ohlcv 데이터를 가져올 수 없습니다. (휴장일 가능성)")
                    continue

                df_sorted = df.sort_values("거래량", ascending=False).head(top_n_each)
                
                for code, row in df_sorted.iterrows():
                    # KIS API 응답 형식과 유사하게 맞춤
                    all_leaders.append({
                        "mksc_shrn_iscd": code, # 종목코드
                        "hts_kor_isnm": stock.get_market_ticker_name(code), # 종목명
                        "stck_prpr": row["종가"], # 현재가 (pykrx는 종가만 제공)
                        "acml_vol": row["거래량"] # 누적거래량
                    })
            
            if not all_leaders:
                logger.warning("pykrx: 거래량 상위 종목을 찾을 수 없습니다.")
                return []

            # 최종 결과를 거래량으로 다시 한번 정렬
            all_leaders.sort(key=lambda x: int(x['acml_vol']), reverse=True)
            
            # 캐시 저장
            self._pykrx_cache = all_leaders
            self._pykrx_cache_time = now
            logger.info(f"pykrx 조회 완료. 총 {len(all_leaders)}개의 종목을 찾았습니다.")
            return all_leaders

        except Exception as e:
            logger.error(f"pykrx 데이터 조회 중 오류 발생: {e}", exc_info=True)
            return []

    def get_volume_leaders(self, top_n: int = 100) -> list:
        """
        거래량 상위 종목 목록을 조회합니다.
        모의투자 시에는 pykrx로 대체합니다. top_n은 각 시장별 조회 수(top_n/2)로 변환됩니다.
        """
        if self.IS_MOCK:
            # KOSPI, KOSDAQ 각각 절반씩 조회하여 top_n에 근사하게 맞춤
            top_n_each = max(10, top_n // 2)
            return self._get_volume_leaders_from_pykrx(top_n_each)

        # --- 실전 투자용 API 호출 ---
        url_path = "/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_NO": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0", "FID_TRC_CLS_CODE": "0",
            "FID_ETC_CLS_CODE": "", "FID_VOL_CNT": str(top_n),
            "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "", "FID_INPUT_DATE_1": ""
        }
        data = self._request("GET", url_path, tr_id, params=params)
        
        if str(data.get("rt_cd")) == "0":
            return data.get('output', [])
            
        msg = data.get('msg1', '알 수 없는 오류')
        logger.error(f"거래량 상위 조회 실패: {msg}")
        return []

    def get_historical_daily_data(self, symbol: str, days: int = 60) -> list:
        """
        지정된 기간 동안의 일봉 데이터를 조회합니다.
        모의투자 시에는 pykrx로 대체합니다.
        """
        end_date = dt.datetime.now()
        start_date = end_date - dt.timedelta(days=days * 1.5) # 주말, 휴일 포함 넉넉하게

        # --- 모의투자용 pykrx 호출 ---
        if self.IS_MOCK:
            try:
                df = stock.get_market_ohlcv_by_date(
                    fromdate=start_date.strftime("%Y%m%d"),
                    todate=end_date.strftime("%Y%m%d"),
                    ticker=symbol
                )
                if df.empty:
                    return []
                
                # KIS API와 유사한 응답 형식으로 변환
                # 최신 날짜가 리스트의 맨 앞에 오도록 정렬
                df = df.sort_index(ascending=False).head(days)
                
                output = []
                for index, row in df.iterrows():
                    output.append({
                        "stck_bsop_date": index.strftime("%Y%m%d"), # 영업일자
                        "stck_oprc": str(row["시가"]),  # 시가
                        "stck_hgpr": str(row["고가"]),  # 고가
                        "stck_lwpr": str(row["저가"]),  # 저가
                        "stck_clpr": str(row["종가"]),  # 종가
                        "acml_vol": str(row["거래량"]), # 누적 거래량
                    })
                return output
            except Exception as e:
                logger.error(f"pykrx 일봉 데이터 조회 실패 ({symbol}): {e}")
                return []

        # --- 실전 투자용 API 호출 ---
        url_path = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        # 실제 KIS API는 end_date를 지원하지 않으므로, 최근 N일치 데이터를 요청하고 클라에서 필터링하는 방식이 더 안정적일 수 있음.
        # 여기서는 단순 기간 조회로 구현.
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_PERIOD_DIV_CODE": "D", # 일봉
            "FID_ORG_ADJ_PRC": "1", # 수정주가
        }
        data = self._request("GET", url_path, "FHKST01010400", params=params)

        if str(data.get("rt_cd")) == "0":
            # KIS API는 최신순으로 데이터를 반환합니다.
            return data.get('output', [])[:days]
        
        logger.error(f"일봉 데이터 조회 실패 ({symbol}): {data.get('msg1')}")
        return []

    def get_intraday_minute_data(self, symbol: str) -> list:
        """
        당일 분봉 데이터를 조회합니다.
        모의투자 시에는 pykrx로 대체합니다.
        """
        now = dt.datetime.now()
        
        # --- 모의투자용 pykrx 호출 ---
        if self.IS_MOCK:
            try:
                # pykrx는 전체 분봉을 반환하므로, 최근 데이터만 잘라서 사용
                df = stock.get_market_ohlcv_by_minute(now.strftime("%Y%m%d"), ticker=symbol)
                if df.empty: return []

                df = df.sort_index(ascending=False)
                output = []
                for index, row in df.iterrows():
                    output.append({
                        'stck_cntg_hour': index.strftime("%H%M%S"), # 체결 시각
                        'stck_oprc': str(row["시가"]),
                        'stck_hgpr': str(row["고가"]),
                        'stck_lwpr': str(row["저가"]),
                        'stck_prpr': str(row["종가"]), # 현재가
                        'cntg_vol': str(row["거래량"]), # 체결 거래량
                    })
                return output
            except Exception as e:
                logger.error(f"pykrx 분봉 데이터 조회 실패 ({symbol}): {e}")
                return []

        # --- 실전 투자용 API 호출 ---
        url_path = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_HOUR_1": now.strftime("%H%M%S"), # 현재 시간 기준
            "FID_PW_DATA_INCU_YN": "Y" # 금일 데이터만
        }
        data = self._request("GET", url_path, "FHKST01010200", params=params)

        if str(data.get("rt_cd")) == "0":
            return data.get('output1', [])
        
        logger.error(f"분봉 데이터 조회 실패 ({symbol}): {data.get('msg1')}")
        return []

    def _normalize_tick_price(self, price: int) -> int:
        """KRX 호가단위에 맞춰 가격을 정규화합니다."""
        if price < 2000: tick = 1
        elif price < 5000: tick = 5
        elif price < 20000: tick = 10
        elif price < 50000: tick = 50
        elif price < 200000: tick = 100
        elif price < 500000: tick = 500
        else: tick = 1000
        return (price // tick) * tick

    def place_order(self, symbol: str, side: str, quantity: int, price: float, order_type: str) -> Optional[Dict]:
        """매수/매도 주문을 전송합니다."""
        # --- 최종 방어: 수량 ---
        if quantity is None:
            logger.error(f"주문 거부: quantity is None ({symbol})")
            return None
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            logger.error(f"주문 거부: quantity 형식 오류 ({symbol}) qty={quantity}")
            return None
        if quantity <= 0:
            logger.error(f"주문 거부: 수량 0 이하 ({symbol}) qty={quantity}")
            return None
            
        if side.lower() not in ['buy', 'sell']:
            raise ValueError("side는 'buy' 또는 'sell'이어야 합니다.")
        
        if order_type.lower() == 'limit':
            if price <= 0:
                logger.error(f"지정가 주문({symbol})은 0원 이하일 수 없습니다. 주문 거부됨.")
                return None
            # --- 호가 단위 정규화 ---
            normalized_price = self._normalize_tick_price(int(price))
            if normalized_price != int(price):
                logger.warning(f"가격 정규화: {price} -> {normalized_price} (호가 단위 적용)")
            price = normalized_price
            ord_unpr = str(price)
            ord_dvsn = "00"
        else: # market
            ord_unpr = "0"
            ord_dvsn = "01"

        url_path = "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = ("TTTC0802U" if side.lower() == 'buy' else "TTTC0801U") if not self.IS_MOCK else \
                ("VTTC0802U" if side.lower() == 'buy' else "VTTC0801U")
            
        body = {
            "CANO": self.ACCOUNT_NO.split('-')[0],
            "ACNT_PRDT_CD": self.ACCOUNT_NO.split('-')[1] if '-' in self.ACCOUNT_NO else '01',
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": ord_unpr,
        }
        
        hashkey = self._get_hashkey(body)
        if not hashkey:
            logger.error("Hashkey 생성에 실패하여 주문을 중단합니다.")
            return None

        data = self._request("POST", url_path, tr_id, body=body, hashkey=hashkey)
        
        if str(data.get("rt_cd")) == "0":
            output = data.get("output")
            if not output:
                logger.error(f"주문 rt_cd=0 이지만 'output' 필드 없음. data={data}")
                return None
                
            order_id = output.get("ODNO")
            if not order_id:
                logger.error(f"주문 rt_cd=0 이지만 ODNO 없음. data={data}")
                return None

            logger.info(f"주문 성공: {side} {symbol} {quantity}주 @ {price if price > 0 else '시장가'}. 주문 ID: {order_id}")
            
            # 모의투자 모드일 경우, 즉시 체결을 시뮬레이션하고 큐에 추가
            if self.IS_MOCK:
                logger.info(f"[모의] 주문 ID {order_id}에 대한 즉시 체결을 시뮬레이션합니다.")
                # 시장가 주문이면 현재가를 가져와 체결가로 사용
                fill_price = price if price > 0 else self.get_current_price(symbol)
                
                fake_fill = {
                    "execution_id": f"{order_id}-01", # 가상 실행 ID
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "filled_quantity": quantity,
                    "fill_price": fill_price,
                    "timestamp": dt.datetime.now().strftime("%H%M%S"),
                }
                self._mock_fill_queue.append(fake_fill)

            return {'order_id': order_id, 'symbol': symbol, 'side': side, 'quantity': quantity, 'price': price, 'status': 'open'}
        
        logger.error(f"{symbol} 주문 실패: {data.get('msg1')}")
        return None

    def get_balance(self) -> Dict:
        """계좌 잔고 정보를 조회합니다."""
        url_path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "TTTC8434R" if not self.IS_MOCK else "VTTC8434R"
        
        params = {
            "CANO": self.ACCOUNT_NO.split('-')[0],
            "ACNT_PRDT_CD": self.ACCOUNT_NO.split('-')[1] if '-' in self.ACCOUNT_NO else '01',
            "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "01",
            "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            summary = (data.get("output2", []) or [{}])[0]
            positions = data.get("output1", [])
            
            def safe_float(val, default=0.0): return float(val) if val else default
            def safe_int(val, default=0): return int(val) if val else default

            return {
                'summary': {
                    'cash': safe_float(summary.get('prvs_rcdl_excc_amt')),
                    'total_asset_value': safe_float(summary.get('nass_amt')),
                    'total_eval_pl': safe_float(summary.get('evlu_pfls_amt')),
                },
                'positions': [{
                    'symbol': pos.get('pdno'), 'name': pos.get('prdt_name'),
                    'quantity': safe_int(pos.get('hldg_qty')),
                    'avg_price': safe_float(pos.get('pchs_avg_pric')),
                    'current_price': safe_float(pos.get('prpr')),
                    'eval_pl': safe_float(pos.get('evlu_pfls_amt')),
                } for pos in positions]
            }
        
        logger.error(f"잔고 조회 실패: {data.get('msg1')}")
        return {}

    def get_concluded_orders(self) -> list:
        """
        금일 체결 내역을 조회합니다.
        모의투자 시에는 내부 큐에서 시뮬레이션된 체결 내역을 반환합니다.
        """
        # --- 모의투자용 가짜 체결 데이터 반환 ---
        if self.IS_MOCK:
            if not self._mock_fill_queue:
                return []
            
            logger.info(f"[모의] {len(self._mock_fill_queue)}개의 시뮬레이션된 체결 내역을 반환합니다.")
            # 큐의 모든 내용을 복사하여 반환하고, 원래 큐는 비웁니다.
            fills_to_return = list(self._mock_fill_queue)
            self._mock_fill_queue.clear()
            return fills_to_return

        # --- 실전 투자용 API 호출 ---
        url_path = "/uapi/domestic-stock/v1/trading/inquire-not-concluded-account"
        tr_id = "TTTC8001R"
        params = {"CANO": self.ACCOUNT_NO.split('-')[0], "ACNT_PRDT_CD": self.ACCOUNT_NO.split('-')[1] if '-' in self.ACCOUNT_NO else '01', "UNPD_CSCN_DVSN": "01"}
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            fills = data.get('output1', [])
            standardized_fills = []
            
            def safe_float(val, default=0.0): return float(val) if val else default
            def safe_int(val, default=0): return int(val) if val else default
            
            for fill in fills:
                side = "buy" if fill.get('sll_buy_dvsn_cd') == "02" else "sell"
                standardized_fills.append({
                    "execution_id": f"{fill.get('odno')}-{fill.get('ord_no')}",
                    "order_id": fill.get('odno'), "symbol": fill.get('pdno'), "side": side,
                    "filled_quantity": safe_int(fill.get('tot_ccld_qty')),
                    "fill_price": safe_float(fill.get('avg_prvs')),
                    "timestamp": fill.get('ccld_time'),
                })
            return standardized_fills
        
        logger.error(f"체결 내역 조회 실패: {data.get('msg1')}")
        return []
    
    # --- Other public methods (get_historical_daily_data, etc.) are omitted for brevity ---
