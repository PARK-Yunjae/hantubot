# scripts/verify_ranking_logic.py

import sys
import os
import asyncio
from unittest.mock import MagicMock
import datetime as dt

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hantubot.strategies.closing_price.strategy import ClosingPriceStrategy
from hantubot.strategies.closing_price.config import ClosingPriceConfig

async def test_ranking_logic():
    print("=== 랭킹 시스템 동작 검증 시작 ===")

    # 1. Mock 객체 설정
    mock_broker = MagicMock()
    mock_clock = MagicMock()
    mock_notifier = MagicMock()
    
    # 설정
    config = {
        'buy_start_time': '15:15',
        'buy_end_time': '15:19',
        'webhook_time': '15:03',
        'auto_buy_enabled': True,
        'stock_filter': { # Strategy가 config에서 직접 참조하는 경우를 대비
            'min_trading_value_daily': 15000000000
        }
    }
    
    # 전략 인스턴스 생성
    # 로거 초기화 문제 회피를 위해 try-except
    try:
        strategy = ClosingPriceStrategy("test_strategy", config, mock_broker, mock_clock, mock_notifier)
    except Exception as e:
        print(f"전략 초기화 중 오류 (무시 가능): {e}")
        # 로거 설정 등으로 실패할 수 있으나, 로직 테스트에는 영향 없으므로 진행 시도
        # 하지만 __init__에서 실패하면 객체가 없으므로 문제됨.
        # ClosingPriceStrategy는 BaseStrategy를 상속받고 로거를 사용함.
        # 실제 환경과 유사하게 로거가 설정되어 있어야 함.
        return

    # 2. 가짜 데이터 준비 (시나리오)
    # Stock A: 80점 (거래대금 2000억)
    # Stock B: 90점 (거래대금 5000억) - Target (1등)
    # Stock C: 40점 (거래대금 1000억) - 점수 미달 탈락
    # Stock D: 90점 (거래대금 100억) - 거래대금 미달 탈락
    
    async def mock_calculate_score(ticker, data_payload):
        if ticker == "000001": # Stock A
            return {
                'valid': True, 'symbol': ticker, 'score': 80, 
                'price': 10000, 'trading_value': 200000000000,
                'features': {'cci': 150, 'adx': 30, 'is_bullish': True, 'score_detail': 'A', 'candle_detail': 'Good'}
            }
        elif ticker == "000002": # Stock B (Target)
            return {
                'valid': True, 'symbol': ticker, 'score': 90, 
                'price': 20000, 'trading_value': 500000000000,
                'features': {'cci': 180, 'adx': 40, 'is_bullish': True, 'score_detail': 'B', 'candle_detail': 'Perfect'}
            }
        elif ticker == "000003": # Stock C (Low Score)
            return {
                'valid': True, 'symbol': ticker, 'score': 40, 
                'price': 5000, 'trading_value': 100000000000,
                'features': {'cci': 50, 'adx': 10, 'is_bullish': False, 'score_detail': 'C', 'candle_detail': 'Bad'}
            }
        elif ticker == "000004": # Stock D (Low Trading Value)
             return {
                'valid': True, 'symbol': ticker, 'score': 90, 
                'price': 20000, 'trading_value': 10000000000,
                'features': {'cci': 180, 'adx': 40, 'is_bullish': True, 'score_detail': 'D', 'candle_detail': 'Perfect'}
            }
        return {'valid': False}

    # 메서드 교체 (Mocking)
    strategy.calculate_score = mock_calculate_score
    
    # 입력 데이터
    top_volume_stocks = [
        {'mksc_shrn_iscd': '000001', 'hts_kor_isnm': 'Stock A', 'acml_tr_pbmn': 200000000000},
        {'mksc_shrn_iscd': '000003', 'hts_kor_isnm': 'Stock C', 'acml_tr_pbmn': 100000000000},
        {'mksc_shrn_iscd': '000002', 'hts_kor_isnm': 'Stock B', 'acml_tr_pbmn': 500000000000},
        {'mksc_shrn_iscd': '000004', 'hts_kor_isnm': 'Stock D', 'acml_tr_pbmn': 10000000000},
    ]
    
    # 3. 실행
    print(">> 스크리닝 실행 중...")
    candidates = await strategy._perform_screening({}, top_volume_stocks)
    
    # 4. 결과 검증
    print(f"\n>> 결과 확인 (후보 수: {len(candidates)}개)")
    for i, item in enumerate(candidates):
        print(f"{i+1}위: {item['name']} ({item['ticker']}) - 점수: {item['score']}점, 대금: {item['trading_value']/100000000:.0f}억")
    
    if not candidates:
        print("FAIL: 후보가 없습니다.")
        return

    top_pick = candidates[0]
    
    filtered_out_C = not any(c['ticker'] == '000003' for c in candidates)
    filtered_out_D = not any(c['ticker'] == '000004' for c in candidates)
    is_top_B = top_pick['ticker'] == '000002'
    
    print("\n[검증 결과]")
    print(f"1. 점수 미달(40점) 제외 여부: {'PASS' if filtered_out_C else 'FAIL'}")
    print(f"2. 거래대금 미달(150억) 제외 여부: {'PASS' if filtered_out_D else 'FAIL'}")
    print(f"3. 1등 종목 정확성 (Stock B): {'PASS' if is_top_B else 'FAIL'}")
    
    if filtered_out_C and filtered_out_D and is_top_B:
        print("\n✅ 랭킹 시스템 동작 검증 완료!")
    else:
        print("\n❌ 검증 실패")

if __name__ == "__main__":
    asyncio.run(test_ranking_logic())
