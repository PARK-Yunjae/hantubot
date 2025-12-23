# hantubot_prod/hantubot/execution/broker.py
import json
import time
import datetime as dt
from typing import Any, Dict, Optional, Tuple

import requests
import yaml

from ..reporting.logger import get_logger

logger = get_logger(__name__)

class Broker:
    """
    한국투자증권 OpenAPI 클라이언트 (국내주식)
    인증, API 요청, 응답 파싱 등 모든 KIS API 상호작용을 담당.
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
            
            # 토큰 만료 시간 계산 (API 응답의 `expires_in`은 초 단위)
            expires_in = token_data.get('expires_in', 86400) # 기본 24시간
            expire_time = dt.datetime.now() + dt.timedelta(seconds=expires_in - 300) # 5분 여유
            
            token_data['expire_time'] = expire_time
            self._token_info = token_data
            logger.info(f"New access token issued. Expires at: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
        except requests.exceptions.RequestException as e:
            logger.critical(f"[Broker._issue_new_token] Failed to issue token: {e}")
            raise RuntimeError("Failed to issue access token from KIS API.")

    def _ensure_token(self):
        """토큰이 유효한지 확인하고, 만료되었거나 임박했다면 갱신합니다."""
        now = dt.datetime.now()
        expire_time = self._token_info.get('expire_time')
        if not expire_time or expire_time <= now:
            logger.warning("Access token is expired or missing. Issuing a new one.")
            self._issue_new_token()

    @property
    def _access_token(self) -> str:
        """유효한 토큰을 반환하는 프로퍼티."""
        self._ensure_token()
        return self._token_info.get('access_token', '')

    def _get_headers(self, tr_id: str, tr_cont: str = "N") -> Dict[str, str]:
        """API 요청을 위한 표준 헤더를 생성합니다."""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token}",
            "appkey": self._APP_KEY,
            "appsecret": self._APP_SECRET,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
        }

    # --- Request Wrapper ---
    def _request(self, method: str, url_path: str, tr_id: str, params: Optional[Dict] = None, body: Optional[Dict] = None, max_retries: int = 5) -> Dict:
        """API 요청을 감싸고, 에러 처리, 재시도 등을 수행합니다."""
        self._ensure_token() # 요청 전 토큰 유효성 검사
        
        full_url = f"{self.BASE_URL}{url_path}"
        
        for attempt in range(max_retries):
            headers = self._get_headers(tr_id)
            try:
                if method.upper() == 'GET':
                    resp = self._session.get(full_url, headers=headers, params=params, timeout=10)
                elif method.upper() == 'POST':
                    resp = self._session.post(full_url, headers=headers, data=json.dumps(body), timeout=10)
                else:
                    raise ValueError("Unsupported HTTP method")

                data = resp.json()

                # API 레벨 에러 체크 (rt_cd가 0이 아닌 경우)
                if str(data.get("rt_cd")) != "0":
                    msg_cd = data.get("msg_cd", "")
                    # 재시도 가능한 에러 처리
                    if msg_cd == "EGW00201": # 초당 거래건수 초과
                        time.sleep(0.2)
                        logger.warning(f"Rate limit exceeded. Retrying... ({attempt + 1}/{max_retries})")
                        continue
                    if "token" in data.get("msg1", "").lower(): # 토큰 관련 문제
                        logger.warning("Token-related error detected. Refreshing token and retrying.")
                        self._issue_new_token()
                        continue
                    # 그 외 API 에러는 즉시 실패 처리
                    logger.error(f"API Error: {data}")
                    return data # 에러 응답 반환
                
                # 성공 시 데이터 반환
                return data

            except requests.exceptions.RequestException as e:
                logger.error(f"HTTP Request failed: {e}. Retrying... ({attempt + 1}/{max_retries})")
                time.sleep(0.5)

        raise RuntimeError(f"API request failed after {max_retries} retries for url: {full_url}")

    # --- Public API Methods ---

    def get_current_price(self, symbol: str) -> float:
        """현재가를 조회합니다."""
        url_path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol}
        
        data = self._request("GET", url_path, tr_id, params=params)
        
        if str(data.get("rt_cd")) == "0":
            price_str = data.get('output', {}).get('stck_prpr', '0')
            return float(price_str)
        return 0.0

    def place_order(self, symbol: str, side: str, quantity: int, price: float, order_type: str) -> Optional[Dict]:
        """
        매수/매도 주문을 전송합니다. OrderManager의 호출을 받습니다.
        :return: {'order_id': '주문번호', ...} 또는 실패 시 None
        """
        if side.lower() not in ['buy', 'sell']:
            raise ValueError("side must be 'buy' or 'sell'")
        
        url_path = "/uapi/domestic-stock/v1/trading/order-cash"
        
        if order_type.lower() == 'market':
            ord_dvsn = "01" # 시장가
            ord_unpr = "0"
        else: # limit
            ord_dvsn = "00" # 지정가
            ord_unpr = str(int(price))
        
        # TR_ID 설정
        if side.lower() == 'buy':
            tr_id = "TTTC0802U" if not self.IS_MOCK else "VTTC0802U"
        else: # sell
            tr_id = "TTTC0801U" if not self.IS_MOCK else "VTTC0801U"
            
        body = {
            "CANO": self.ACCOUNT_NO.split('-')[0],
            "ACNT_PRDT_CD": self.ACCOUNT_NO.split('-')[1] if '-' in self.ACCOUNT_NO else '01',
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": ord_unpr,
        }
        
        data = self._request("POST", url_path, tr_id, body=body)
        
        if str(data.get("rt_cd")) == "0":
            output = data.get('output', {})
            order_id = output.get('ODNO')
            if order_id:
                logger.info(f"Order successful: {side} {symbol} {quantity} @ {price if price > 0 else 'market'}. Order ID: {order_id}")
                return {
                    'order_id': order_id,
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'price': price,
                    'status': 'open',
                }
        
        logger.error(f"Order failed for {symbol}: {data.get('msg1')}")
        return None
        
    def get_balance(self) -> Dict:
        """
        계좌 잔고 정보를 조회합니다. (예수금, 총자산, 보유 주식 목록 등)
        """
        url_path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "TTTC8434R" if not self.IS_MOCK else "VTTC8434R"
        
        params = {
            "CANO": self.ACCOUNT_NO.split('-')[0],
            "ACNT_PRDT_CD": self.ACCOUNT_NO.split('-')[1] if '-' in self.ACCOUNT_NO else '01',
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "01", # 총 평가손익
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00", # 처리구분 (00: 전일매매포함)
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            summary = (data.get("output2", []) or [{}])[0]
            positions = data.get("output1", [])
            
            # 필요한 데이터만 추출하여 반환
            return {
                'summary': {
                    'cash': float(summary.get('prvs_rcdl_excc_amt', 0)),
                    'total_asset_value': float(summary.get('nass_amt', 0)),
                    'total_eval_pl': float(summary.get('evlu_pfls_amt', 0)),
                },
                'positions': [
                    {
                        'symbol': pos.get('pdno'),
                        'name': pos.get('prdt_name'),
                        'quantity': int(pos.get('hldg_qty', 0)),
                        'avg_price': float(pos.get('pchs_avg_pric', 0)),
                        'current_price': float(pos.get('prpr', 0)),
                        'eval_pl': float(pos.get('evlu_pfls_amt', 0)),
                    }
                    for pos in positions
                ]
            }
        
        logger.error(f"Failed to get balance: {data.get('msg1')}")
        return {}

    def get_historical_daily_data(self, symbol: str, days: int = 100) -> list:
        """
        과거 일봉 데이터를 조회합니다.
        :param symbol: 종목 코드
        :param days: 조회할 기간 (최근 N일)
        :return: 일봉 데이터 딕셔너리 리스트
        """
        url_path = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        tr_id = "FHKST01010400"
        
        # KIS API는 '기간'으로 조회하므로 오늘 날짜와 N일 전 날짜를 계산
        end_date = dt.datetime.now().strftime('%Y%m%d')
        start_date = (dt.datetime.now() - dt.timedelta(days=days)).strftime('%Y%m%d')
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D", # 일봉
            "FID_ORG_ADJ_PRC": "1" # 수정주가
        }
        
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            return data.get('output', [])
        
        logger.error(f"Failed to get historical data for {symbol}: {data.get('msg1')}")
        return []

    def get_unclosed_orders(self) -> list:
        """미체결 주문 내역을 조회합니다."""
        url_path = "/uapi/domestic-stock/v1/trading/inquire-not-concluded-account"
        tr_id = "TTTC8001R" if not self.IS_MOCK else "VTTC8001R"
        
        params = {
            "CANO": self.ACCOUNT_NO.split('-')[0],
            "ACNT_PRDT_CD": self.ACCOUNT_NO.split('-')[1] if '-' in self.ACCOUNT_NO else '01',
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "0", # 주문일자, 주문번호
            "INQR_DVSN_2": "0", # 전체
            "UNPD_CSCN_DVSN": "00", # 미체결
            "FUND_ORD_TP_CODE": "0", # 전체
            "FNCG_AMT_AUTO_RDPT_YN": "",
            "ORD_GBN": "00", # 전체
            "ORD_SNO_DVSN_ORD": "00", # 정렬순서
            "INQR_COND": "0", # 전체
            "COMP_YN": "",
        }
        
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            return data.get('output1', [])
        
        logger.error(f"Failed to get unclosed orders: {data.get('msg1')}")
        return []

    def get_volume_leaders(self, top_n: int = 40) -> list:
        """
        전일 기준 거래량 상위 종목 목록을 조회합니다. (FHKST01010300)
        :param top_n: 조회할 상위 종목 수
        :return: 거래량 상위 종목 정보 딕셔너리 리스트
        """
        url_path = "/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHKST01010300"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 주식
            "FID_COND_SCR_DIV_CODE": "20171", # 거래량상위
            "FID_INPUT_ISCD": "0000", # 전체
            "FID_DIV_CLS_CODE": "0", # 분류 구분 코드(0:전체)
            "FID_BLNG_CLS_CODE": "0", # 소속 구분 코드(0:전체)
            "FID_TRGT_CLS_CODE": "111111111", # 대상구분코드
            "FID_TRGT_EXLS_CLS_CODE": "000000", # 제외대상구분코드
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": str(top_n), # 조회할 거래량 (상위 N개)
            "FID_INPUT_DATE_1": "",
        }
        
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            return data.get('output', [])
        
        logger.error(f"Failed to get volume leaders: {data.get('msg1')}")
        return []

    def get_realtime_transaction_ranks(self, top_n: int = 40) -> list:
        """
        당일 기준 거래대금 상위 종목 목록을 실시간으로 조회합니다. (FHPST01210000)
        :param top_n: 조회할 상위 종목 수
        :return: 거래대금 상위 종목 정보 딕셔너리 리스트
        """
        url_path = "/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01210000" # 실시간 거래대금 상위 TR_ID
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 주식
            "FID_COND_SCR_DIV_CODE": "20170", # 거래대금상위
            "FID_INPUT_ISCD": "0000", # 전체
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": str(top_n),
            "FID_INPUT_DATE_1": "",
        }
        
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            return data.get('output', [])
        
        logger.error(f"Failed to get realtime transaction ranks: {data.get('msg1')}")
        return []

    def get_intraday_minute_data(self, symbol: str) -> list:
        """
        당일 분봉 데이터를 조회합니다. (FHKST01010200)
        :param symbol: 종목 코드
        :return: 분봉 데이터 딕셔너리 리스트
        """
        url_path = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        tr_id = "FHKST01010200"
        now = dt.datetime.now()
        
        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_HOUR_1": now.strftime('%H%M%S'), # 현재 시간 기준
            "FID_PW_DATA_INCU_YN": "N", # 과거 데이터 미포함
        }
        
        data = self._request("GET", url_path, tr_id, params=params)

        if str(data.get("rt_cd")) == "0":
            # API는 시간 역순으로 데이터를 반환합니다.
            return data.get('output2', [])
        
        logger.error(f"Failed to get intraday minute data for {symbol}: {data.get('msg1')}")
        return []


if __name__ == '__main__':
    # 테스트 코드
    # .env 파일과 config.yaml 파일이 올바르게 설정되어 있어야 함
    # python -m hantubot.execution.broker
    from dotenv import load_dotenv
    import os
    
    load_dotenv(dotenv_path='../../configs/.env')

    with open("../../configs/config.yaml", "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
        config_data['api']['app_key'] = os.getenv('KIS_APP_KEY')
        config_data['api']['app_secret'] = os.getenv('KIS_APP_SECRET')
        config_data['api']['account_no'] = os.getenv('KIS_ACCOUNT_NO')

    broker = Broker(config=config_data, is_mock=True)
    
    # 1. 현재가 조회 테스트
    price = broker.get_current_price("005930")
    print(f"삼성전자 현재가: {price}")

    # 2. 잔고 조회 테스트
    balance = broker.get_balance()
    print(f"계좌 잔고: {balance}")

    # 3. 미체결 주문 조회 테스트
    unclosed_orders = broker.get_unclosed_orders()
    print(f"미체결 주문: {unclosed_orders}")

    # 4. 주문 테스트 (모의투자 환경에서만 실행!)
    if broker.IS_MOCK and price > 0:
        buy_order_result = broker.place_order(symbol="005930", side="buy", quantity=1, price=price, order_type="limit")
        print(f"지정가 매수 주문 결과: {buy_order_result}")

    logger.info("Broker test finished.")
