import json
import time
import datetime as dt
from typing import Any, Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ...reporting.logger import get_logger

logger = get_logger(__name__)

class KisApi:
    """
    KIS API 통신을 전담하는 클래스.
    인증(토큰 관리), 요청 전송, 응답 처리, 에러 핸들링을 담당합니다.
    """
    def __init__(self, config: dict, is_mock: bool):
        api_conf = config['api']
        self._APP_KEY = api_conf['app_key']
        self._APP_SECRET = api_conf['app_secret']
        self.ACCOUNT_NO = api_conf['account_no']
        self.IS_MOCK = is_mock
        self.BASE_URL = api_conf['base_url']['mock'] if is_mock else api_conf['base_url']['live']

        self._session = requests.Session()
        # Retry 로직 강화: backoff_factor를 늘려 천천히 재시도, 500번대 에러에 대해 재시도 설정
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self._session.mount('https://', HTTPAdapter(max_retries=retries))
        self._session.mount('http://', HTTPAdapter(max_retries=retries))

        self._token_info: Dict[str, Any] = {}
        self._has_error_occurred = False
        
        self._ensure_token()

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

    def get_hashkey(self, data: Dict) -> str:
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
    def access_token(self) -> str:
        self._ensure_token()
        return self._token_info.get('access_token', '')

    def _get_headers(self, tr_id: str, hashkey: Optional[str] = None) -> Dict[str, str]:
        """API 요청을 위한 표준 헤더를 생성합니다."""
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self._APP_KEY,
            "appsecret": self._APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def request(self, method: str, url_path: str, tr_id: str, params: Optional[Dict] = None, body: Optional[Dict] = None, hashkey: Optional[str] = None, max_retries: int = 5) -> Dict:
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
                    
                    masked_headers = headers.copy()
                    if 'authorization' in masked_headers:
                        masked_headers['authorization'] = 'Bearer ***MASKED***'
                    if 'appsecret' in masked_headers:
                        masked_headers['appsecret'] = '***MASKED***'
                    
                    logger.error(f"API 오류 (tr_id: {tr_id}): {data}\n"
                                 f"  응답 상태 코드: {resp.status_code}\n"
                                 f"  응답 본문: {resp.text}\n"
                                 f"  요청 URL: {full_url}\n"
                                 f"  요청 헤더: {masked_headers}")
                    return data
                
                return data
            except json.JSONDecodeError:
                logger.error(f"JSON 파싱 오류. 응답 상태: {resp.status_code}, 내용: {resp.text[:300]}")
                return {"rt_cd": "-1", "msg1": "JSON 파싱 오류"}
            except requests.exceptions.RequestException as e:
                # 500 에러 처리 강화
                if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and 500 <= e.response.status_code < 600:
                    logger.warning(f"서버 에러({e.response.status_code}) 발생. 1초 대기 후 재시도... ({attempt + 1}/{max_retries})")
                    time.sleep(1.0)
                    continue

                if e.response is not None and e.response.status_code == 404:
                    logger.critical(f"API 경로를 찾을 수 없습니다 (404 Not Found): {full_url}")
                    self._has_error_occurred = True
                    break
                
                logger.error(f"HTTP 요청 실패: {e}. 재시도... ({attempt + 1}/{max_retries})", exc_info=True)
                time.sleep(0.5)

        logger.critical(f"API 요청이 {max_retries}번의 재시도 후에도 최종 실패했습니다: {full_url}")
        self._has_error_occurred = True
        return {}
    
    @property
    def has_error(self) -> bool:
        return self._has_error_occurred
