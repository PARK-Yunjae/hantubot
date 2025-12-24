# hantubot/utils/stock_filters.py

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

    # 제외할 키워드 목록
    # 대소문자 구분을 위해 일부는 원본, 일부는 대문자로 확인
    exclusion_keywords = [
        "스팩",
        "리츠",
        "인버스",
        "레버리지",
        "선물",
        " ETN", # ETN은 보통 'SOL ETN' 처럼 앞에 공백이 있음
    ]

    if "ETF" in name_upper:
        return False
    
    if name_upper.endswith("우"): # 우선주 (e.g., 삼성전자우)
        return False
        
    for keyword in exclusion_keywords:
        if keyword in stock_name:
            return False

    return True

if __name__ == '__main__':
    # --- 테스트 케이스 ---
    test_cases = {
        "삼성전자": True,
        "SK하이닉스": True,
        "KODEX 200": False,
        "TIGER 2차전지소재Fn": False,
        "NH스팩28호": False,
        "삼성전자우": False,
        "SK리츠": False,
        "SOL 미국배당다우존스(H)": False,
        "다른 ETN 상품": False,
        "하나금융25호스팩": False
    }

    for name, expected in test_cases.items():
        result = is_eligible_stock(name)
        print(f"Testing '{name}': Expected={expected}, Got={result} -> {'PASS' if result == expected else 'FAIL'}")

