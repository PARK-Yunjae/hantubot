import datetime as dt
from typing import Optional, Dict
from ...reporting.logger import get_logger
from .api import KisApi
from .market_data import KisMarketData

logger = get_logger(__name__)

class KisTrading:
    """
    KIS API를 사용한 주문 및 잔고 관리 클래스.
    주문 실행, 잔고 조회, 체결 내역 조회, 리스크 관리(주문 한도 등)를 담당합니다.
    """
    def __init__(self, api: KisApi, market_data: KisMarketData, config: dict):
        self.api = api
        self.market_data = market_data
        
        # 리스크 관리 설정
        self._risk_config = config.get('risk_management', {})
        self._daily_order_value_krw = 0.0 # 금일 누적 매수 금액
        self._daily_realized_loss_krw = 0.0 # 금일 누적 실현 손실
        self._last_reset_date = dt.date.today()
        
    def _check_and_reset_daily_metrics(self):
        """매일 자정마다 일일 누적 지표들을 초기화합니다."""
        today = dt.date.today()
        if today > self._last_reset_date:
            logger.info(f"일일 지표 초기화 (이전 날짜: {self._last_reset_date}, 오늘 날짜: {today})")
            self._daily_order_value_krw = 0.0
            self._daily_realized_loss_krw = 0.0
            self._last_reset_date = today
            # 에러 플래그는 Api 클래스에서 관리하므로 여기서는 패스
            
    def register_realized_pnl(self, pnl_krw: float):
        """매도 체결 시 발생한 실현 손익을 기록하고 일일 손실 한도를 확인합니다."""
        self._check_and_reset_daily_metrics()
        
        self._daily_realized_loss_krw += pnl_krw
        max_daily_loss = self._risk_config.get('max_daily_realized_loss_krw')

        if max_daily_loss is not None and self._daily_realized_loss_krw < -max_daily_loss:
            logger.critical(f"일일 누적 실현 손실이 한도를 초과했습니다! ({self._daily_realized_loss_krw:,}원 < -{max_daily_loss:,}원)")
            logger.critical("긴급 정지 스위치를 강제로 활성화합니다. 모든 거래가 중단됩니다.")
            self._risk_config['emergency_stop'] = True 

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
        
        # --- 리스크 관리 ---
        if self._risk_config.get('emergency_stop', False):
            logger.warning(f"긴급 정지 스위치 활성화로 인해 주문 거부됨 ({side} {symbol} {quantity}주)")
            return None

        if self._risk_config.get('halt_on_error', False) and self.api.has_error:
            logger.warning(f"이전 에러 발생으로 인해 주문 거부됨 (halt_on_error 활성화) ({side} {symbol} {quantity}주)")
            return None

        if side.lower() == 'buy':
            if order_type.lower() == 'limit':
                if price <= 0:
                    logger.error(f"지정가 매수 주문({symbol})은 0원 이하일 수 없습니다. 주문 거부됨.")
                    return None
                order_value = price * quantity
            else: # market order
                current_price = self.market_data.get_current_price(symbol)
                if current_price <= 0:
                    logger.error(f"시장가 매수 주문({symbol})의 현재가를 가져올 수 없어 주문 거부됨.")
                    return None
                order_value = current_price * quantity
            
            max_order_value = self._risk_config.get('max_order_value_krw')
            if max_order_value and order_value > max_order_value:
                logger.warning(f"1회 주문 최대 금액 초과로 주문 거부됨 ({symbol}, 주문 금액: {order_value:,}원, 최대: {max_order_value:,}원)")
                return None
            
            max_daily_order_value = self._risk_config.get('max_daily_order_value_krw')
            if max_daily_order_value:
                self._check_and_reset_daily_metrics()
                if (self._daily_order_value_krw + order_value) > max_daily_order_value:
                    logger.warning(f"일일 누적 매수 금액 초과로 주문 거부됨 ({symbol}, 예상 누적: {self._daily_order_value_krw + order_value:,}원, 최대: {max_daily_order_value:,}원)")
                    return None
                    
        if side.lower() not in ['buy', 'sell']:
            raise ValueError("side는 'buy' 또는 'sell'이어야 합니다.")
        
        if order_type.lower() == 'limit':
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
        tr_id = ("TTTC0802U" if side.lower() == 'buy' else "TTTC0801U") if not self.api.IS_MOCK else \
                ("VTTC0802U" if side.lower() == 'buy' else "VTTC0801U")
            
        body = {
            "CANO": self.api.ACCOUNT_NO.split('-')[0],
            "ACNT_PRDT_CD": self.api.ACCOUNT_NO.split('-')[1] if '-' in self.api.ACCOUNT_NO else '01',
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": ord_unpr,
        }
        
        hashkey = self.api.get_hashkey(body)
        if not hashkey:
            logger.error("Hashkey 생성에 실패하여 주문을 중단합니다.")
            return None

        data = self.api.request("POST", url_path, tr_id, body=body, hashkey=hashkey)
        
        if str(data.get("rt_cd")) == "0":
            output = data.get("output")
            if not output:
                logger.error(f"주문 rt_cd=0 이지만 'output' 필드 없음. data={data}")
                return None
                
            order_id = output.get("ODNO")
            if not order_id:
                logger.error(f"주문 rt_cd=0 이지만 ODNO 없음. data={data}")
                return None
            
            # 매수 주문 성공 시 누적 금액 업데이트
            if side.lower() == 'buy':
                 if order_type.lower() == 'limit':
                     self._daily_order_value_krw += (price * quantity)
                 else:
                     pass

            logger.info(f"주문 성공: {side} {symbol} {quantity}주 @ {price if price > 0 else '시장가'}. 주문 ID: {order_id}")
            
            return {'order_id': order_id, 'symbol': symbol, 'side': side, 'quantity': quantity, 'price': price, 'status': 'open'}
        
        logger.error(f"{symbol} 주문 실패: {data.get('msg1')}")
        return None

    def get_balance(self) -> Dict:
        """계좌 잔고 정보를 조회합니다."""
        url_path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "TTTC8434R" if not self.api.IS_MOCK else "VTTC8434R"
        
        params = {
            "CANO": self.api.ACCOUNT_NO.split('-')[0],
            "ACNT_PRDT_CD": self.api.ACCOUNT_NO.split('-')[1] if '-' in self.api.ACCOUNT_NO else '01',
            "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "01",
            "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        data = self.api.request("GET", url_path, tr_id, params=params)

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
        """금일 체결 내역을 조회합니다."""
        url_path = "/uapi/domestic-stock/v1/trading/inquire-not-concluded-account"
        tr_id = "TTTC8001R"
        params = {"CANO": self.api.ACCOUNT_NO.split('-')[0], "ACNT_PRDT_CD": self.api.ACCOUNT_NO.split('-')[1] if '-' in self.api.ACCOUNT_NO else '01', "UNPD_CSCN_DVSN": "01"}
        data = self.api.request("GET", url_path, tr_id, params=params)

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
