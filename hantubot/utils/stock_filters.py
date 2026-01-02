# hantubot/utils/stock_filters.py

# 제외할 키워드 목록
# 대소문자 구분을 위해 일부는 원본, 일부는 대문자로 확인
# [전수조사 수정] 채권 관련 키워드 추가
EXCLUSION_KEYWORDS = [
    "스팩",
    "리츠",
    "인버스",
    "레버리지",
    "선물",
    " ETN", # ETN은 보통 'SOL ETN' 처럼 앞에 공백이 있음
    "채권",
    "국고채",
    "회사채",
    "전환사채",
    "신주인수권",
]

def is_eligible_stock(stock_name: str) -> bool:
    """
    주어진 종목명이 투자 대상에 적합한 일반 주식인지 확인합니다.
    ETF, 스팩, 우선주, 리츠 등을 제외합니다.

    :param stock_name: 확인할 종목의 이름
    :return: 적합하면 True, 아니면 False
    """
    if not stock_name:
        return False

    name_upper = stock_name.upper()

    if "ETF" in name_upper:
        return False
    
    if name_upper.endswith("우"): # 우선주 (e.g., 삼성전자우)
        return False
        
    for keyword in EXCLUSION_KEYWORDS:
        if keyword in stock_name:
            return False

    return True
