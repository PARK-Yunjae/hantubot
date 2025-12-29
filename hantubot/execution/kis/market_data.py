import datetime as dt
from typing import List, Optional, Dict
from pykrx import stock
from ...reporting.logger import get_logger
from .api import KisApi

logger = get_logger(__name__)

class KisMarketData:
    """
    KIS API를 사용한 시세 데이터 조회 클래스.
    현재가, 호가, 거래량 상위, 차트 데이터 등을 조회합니다.
    """
    def __init__(self, api: KisApi):
        self.api = api
        self._pykrx_cache: List[Dict] = []
        self._pykrx_cache_time: Optional[dt.datetime] = None

    def get_current_price(self, symbol: str) -> float:
        """현재가를 조회합니다."""
        url_path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol}
        
        data = self.api.request("GET", url_path, tr_id, params=params)
        
        price_str = data.get('output', {}).get('stck_prpr', '0')
        return float(price_str) if price_str else 0.0

    def _get_volume_leaders_from_pykrx(self, top_n_each: int = 50) -> list:
        """[모의투자용] pykrx를 사용하여 KOSPI, KOSDAQ 각 시장별 거래량 상위 종목을 조회합니다."""
        now = dt.datetime.now()
        
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
                    all_leaders.append({
                        "mksc_shrn_iscd": code,
                        "hts_kor_isnm": stock.get_market_ticker_name(code),
                        "stck_prpr": row["종가"],
                        "acml_vol": row["거래량"]
                    })
            
            if not all_leaders:
                logger.warning("pykrx: 거래량 상위 종목을 찾을 수 없습니다.")
                return []

            all_leaders.sort(key=lambda x: int(x['acml_vol']), reverse=True)
            
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
        모의투자 시에는 pykrx로 대체합니다.
        """
        if self.api.IS_MOCK:
            top_n_each = max(10, top_n // 2)
            return self._get_volume_leaders_from_pykrx(top_n_each)

        url_path = "/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0",
            "FID_INPUT_DATE_1": "0"
        }
        data = self.api.request("GET", url_path, tr_id, params=params)
        
        if str(data.get("rt_cd")) == "0":
            return data.get('output', [])
            
        msg = data.get('msg1', '알 수 없는 오류')
        logger.error(f"거래량 상위 조회 실패: {msg}")
        return []

    def get_historical_daily_data(self, symbol: str, days: int = 60) -> list:
        """지정된 기간 동안의 일봉 데이터를 조회합니다."""
        end_date = dt.datetime.now()
        start_date = end_date - dt.timedelta(days=days * 1.5)

        if self.api.IS_MOCK:
            try:
                df = stock.get_market_ohlcv_by_date(
                    fromdate=start_date.strftime("%Y%m%d"),
                    todate=end_date.strftime("%Y%m%d"),
                    ticker=symbol
                )
                if df.empty:
                    return []
                
                df = df.sort_index(ascending=False).head(days)
                
                output = []
                for index, row in df.iterrows():
                    output.append({
                        "stck_bsop_date": index.strftime("%Y%m%d"),
                        "stck_oprc": str(row["시가"]),
                        "stck_hgpr": str(row["고가"]),
                        "stck_lwpr": str(row["저가"]),
                        "stck_clpr": str(row["종가"]),
                        "acml_vol": str(row["거래량"]),
                    })
                return output
            except Exception as e:
                logger.error(f"pykrx 일봉 데이터 조회 실패 ({symbol}): {e}")
                return []

        url_path = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1",
        }
        data = self.api.request("GET", url_path, "FHKST01010400", params=params)

        if str(data.get("rt_cd")) == "0":
            return data.get('output', [])[:days]
        
        logger.error(f"일봉 데이터 조회 실패 ({symbol}): {data.get('msg1')}")
        return []

    def get_intraday_minute_data(self, symbol: str) -> list:
        """당일 분봉 데이터를 조회합니다."""
        now = dt.datetime.now()
        
        if self.api.IS_MOCK:
            try:
                df = stock.get_market_ohlcv_by_minute(now.strftime("%Y%m%d"), ticker=symbol)
                if df.empty: return []

                df = df.sort_index(ascending=False)
                output = []
                for index, row in df.iterrows():
                    output.append({
                        'stck_cntg_hour': index.strftime("%H%M%S"),
                        'stck_oprc': str(row["시가"]),
                        'stck_hgpr': str(row["고가"]),
                        'stck_lwpr': str(row["저가"]),
                        'stck_prpr': str(row["종가"]),
                        'cntg_vol': str(row["거래량"]),
                    })
                return output
            except Exception as e:
                logger.error(f"pykrx 분봉 데이터 조회 실패 ({symbol}): {e}")
                return []

        url_path = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_HOUR_1": now.strftime("%H%M%S"),
            "FID_PW_DATA_INCU_YN": "Y"
        }
        data = self.api.request("GET", url_path, "FHKST01010200", params=params)

        if str(data.get("rt_cd")) == "0":
            return data.get('output1', [])
        
        logger.error(f"분봉 데이터 조회 실패 ({symbol}): {data.get('msg1')}")
        return []
