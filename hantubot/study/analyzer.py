"""
LLM 기반 뉴스 요약 및 학습 메모 생성 모듈
"""
import os
import time
import json
from typing import List, Dict

import google.generativeai as genai

from datetime import datetime, timedelta
from hantubot.reporting.logger import get_logger
from hantubot.study.repository import StudyDatabase, get_study_db

logger = get_logger(__name__)


class StudyAnalyzer:
    """
    학습 및 성과 분석을 담당하는 클래스
    - 전일 종가매매 후보 성과 평가
    - 학습 데이터 분석
    """
    def __init__(self, broker):
        self.broker = broker
        self.db = get_study_db()

    def evaluate_closing_candidates(self):
        """
        전일 선정된 종가매매 후보군(TOP3)의 성과를 평가하고 DB에 저장
        """
        try:
            # 1. 평가 대상 날짜 (전일) 계산
            # 실제 거래일 기준으로 전일을 찾아야 함.
            # 여기서는 간단히 어제를 조회하지만, 휴일 고려가 필요할 수 있음.
            # 하지만 closing_candidates 테이블에 데이터가 있는 가장 최근 날짜를 찾는 것이 안전함.
            
            # 오늘 날짜
            today = datetime.now()
            
            # 최근 7일 중 데이터가 있는 날짜 검색 (역순)
            target_date = None
            candidates = []
            
            for i in range(1, 8):
                check_date = (today - timedelta(days=i)).strftime("%Y%m%d")
                candidates = self.db.get_closing_candidates(check_date)
                if candidates:
                    target_date = check_date
                    break
            
            if not target_date or not candidates:
                logger.info("평가할 전일 종가매매 후보 데이터가 없습니다.")
                return

            logger.info(f"전일({target_date}) 종가매매 후보 {len(candidates)}개 성과 평가 시작")

            # 2. 각 후보별 성과 계산
            for cand in candidates:
                try:
                    ticker = cand['ticker']
                    
                    # 일봉 데이터 조회 (전일, 금일 포함)
                    # 넉넉하게 5일치 조회
                    daily_data = self.broker.get_historical_daily_data(ticker, days=5)
                    
                    if not daily_data or len(daily_data) < 2:
                        logger.warning(f"{ticker} 데이터 부족으로 평가 스킵")
                        continue
                    
                    # 데이터 정렬 (날짜 오름차순)
                    # API 응답 구조에 따라 다를 수 있으므로 날짜 확인
                    # get_historical_daily_data는 보통 최신순(내림차순)일 가능성이 높음 -> 확인 필요
                    # KIS API는 보통 최신순으로 줌.
                    
                    # 날짜 기준 정렬 (과거 -> 최신)
                    daily_data.sort(key=lambda x: x['stck_bsop_date'])
                    
                    # 전일 데이터 찾기 (target_date)
                    prev_day_data = None
                    curr_day_data = None
                    
                    for i, day in enumerate(daily_data):
                        if day['stck_bsop_date'] == target_date:
                            prev_day_data = day
                            if i + 1 < len(daily_data):
                                curr_day_data = daily_data[i+1]
                            break
                    
                    if not prev_day_data or not curr_day_data:
                        logger.warning(f"{ticker}의 전일({target_date}) 또는 금일 데이터가 없습니다.")
                        continue

                    # 가격 데이터 추출
                    prev_close = float(prev_day_data['stck_clpr'])
                    curr_open = float(curr_day_data['stck_oprc'])
                    curr_close = float(curr_day_data['stck_clpr'])
                    curr_high = float(curr_day_data['stck_hgpr'])
                    curr_low = float(curr_day_data['stck_lwpr'])
                    
                    prev_vol = float(prev_day_data['acml_vol'])
                    curr_vol = float(curr_day_data['acml_vol'])

                    # 성과 지표 계산
                    # 1. 시가 수익률 (Next Open Return)
                    next_open_return_pct = ((curr_open - prev_close) / prev_close) * 100
                    
                    # 2. 종가 수익률 (Next Close Return)
                    next_close_return_pct = ((curr_close - prev_close) / prev_close) * 100
                    
                    # 3. 고가 기준 최대 수익률 (MFE)
                    next_day_mfe_pct = ((curr_high - prev_close) / prev_close) * 100
                    
                    # 4. 저가 기준 최대 손실률 (MAE)
                    next_day_mae_pct = ((curr_low - prev_close) / prev_close) * 100
                    
                    # 5. 거래량 비율
                    volume_ratio = (curr_vol / prev_vol * 100) if prev_vol > 0 else 0

                    # 3. 결과 저장
                    result = {
                        'candidate_id': cand['id'],
                        'ticker': ticker,
                        'eval_date': curr_day_data['stck_bsop_date'], # 평가 기준일 (오늘)
                        'next_open_return_pct': round(next_open_return_pct, 2),
                        'next_close_return_pct': round(next_close_return_pct, 2),
                        'next_day_mfe_pct': round(next_day_mfe_pct, 2),
                        'next_day_mae_pct': round(next_day_mae_pct, 2),
                        'volume_ratio': round(volume_ratio, 2)
                    }
                    
                    self.db.insert_closing_result(result)
                    logger.info(f"[{ticker}] 평가 완료: 시가 {next_open_return_pct:.2f}%, 종가 {next_close_return_pct:.2f}%")

                except Exception as e:
                    logger.error(f"{cand['ticker']} 평가 중 오류: {e}")

        except Exception as e:
            logger.error(f"종가매매 성과 평가 전체 오류: {e}", exc_info=True)


def generate_summaries(run_date: str, candidates: List[Dict], 
                      db: StudyDatabase) -> Dict:
    """
    LLM으로 종목 요약 생성 (배치 처리)
    
    Returns:
        {'success_count': int, 'failed_count': int, 'errors': []}
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.warning("GEMINI_API_KEY not found. Skipping summaries.")
        return {'success_count': 0, 'failed_count': 0, 'errors': ['No API key']}
    
    success_count = 0
    failed_count = 0
    errors = []
    
    # 요약이 필요한 종목만 필터링 (캐싱)
    stocks_to_summarize = []
    for candidate in candidates:
        ticker = candidate['ticker']
        
        # 이미 요약이 있는지 확인
        if db.has_summary(run_date, ticker):
            logger.debug(f"Summary already exists for {ticker}, skipping")
            continue
        
        stocks_to_summarize.append({
            'ticker': ticker,
            'name': candidate['name']
        })
    
    if not stocks_to_summarize:
        logger.info("No new summaries needed (all cached)")
        return {'success_count': 0, 'failed_count': 0, 'errors': []}
    
    # Gemini API 설정 - 2.5 Pro로 업그레이드 (더 정확한 요약)
    try:
        genai.configure(api_key=api_key)
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-pro')
        model = genai.GenerativeModel(model_name)
        logger.info(f"Using Gemini model: {model_name}")
        
        # 배치 크기 설정 (Pro 모델은 더 느리므로 줄임)
        batch_size = int(os.getenv('LLM_BATCH_SIZE', '5'))
        
        # 배치 단위로 처리
        for i in range(0, len(stocks_to_summarize), batch_size):
            batch = stocks_to_summarize[i:i + batch_size]
            
            logger.info(f"배치 요약 생성 중 ({i+1}-{i+len(batch)}/{len(stocks_to_summarize)})")
            
            try:
                summaries = get_batch_summaries_gemini(batch, model, run_date, db)
                
                for ticker, summary_data in summaries.items():
                    if summary_data['success']:
                        success_count += 1
                        db.update_candidate_status(run_date, ticker, 'summarized')
                    else:
                        failed_count += 1
                        errors.append(f"Summary failed for {ticker}")
                
                # Rate limiting
                time.sleep(2)
            
            except Exception as e:
                logger.error(f"Batch summary failed: {e}")
                failed_count += len(batch)
                errors.append(f"Batch summary error: {e}")
    
    except Exception as e:
        logger.error(f"Gemini API setup failed: {e}", exc_info=True)
        errors.append(f"Gemini setup failed: {e}")
    
    return {
        'success_count': success_count,
        'failed_count': failed_count,
        'errors': errors
    }


def generate_study_notes(run_date: str, candidates: List[Dict], 
                        db: StudyDatabase) -> Dict:
    """
    백일공부 학습 메모 생성 (사실 검증 → 학습 포인트 추출)
    
    Returns:
        {'success_count': int, 'failed_count': int, 'errors': []}
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.warning("GEMINI_API_KEY not found. Skipping study notes.")
        return {'success_count': 0, 'failed_count': 0, 'errors': ['No API key']}
    
    success_count = 0
    failed_count = 0
    errors = []
    
    # 학습 메모가 필요한 종목만 필터링
    stocks_to_note = []
    for candidate in candidates:
        ticker = candidate['ticker']
        
        # 이미 학습 메모가 있는지 확인
        if db.has_study_note(run_date, ticker):
            logger.debug(f"Study note already exists for {ticker}, skipping")
            continue
        
        # 뉴스가 있는 종목만 처리
        news_items = db.get_news_items(run_date, ticker)
        if not news_items:
            continue
        
        stocks_to_note.append({
            'ticker': ticker,
            'name': candidate['name'],
            'news_count': len(news_items)
        })
    
    if not stocks_to_note:
        logger.info("No new study notes needed")
        return {'success_count': 0, 'failed_count': 0, 'errors': []}
    
    # Gemini API 설정
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # 배치 크기 (학습 메모는 더 신중하게 3개씩)
        batch_size = 3
        
        # 배치 단위로 처리
        for i in range(0, len(stocks_to_note), batch_size):
            batch = stocks_to_note[i:i + batch_size]
            
            logger.info(f"배치 학습 메모 생성 중 ({i+1}-{i+len(batch)}/{len(stocks_to_note)})")
            
            try:
                notes = get_batch_study_notes_gemini(batch, model, run_date, db)
                
                for ticker, note_data in notes.items():
                    if note_data['success']:
                        success_count += 1
                        logger.info(f"✓ {ticker}: 학습 메모 생성 완료 (신뢰도: {note_data.get('confidence', 'unknown')})")
                    else:
                        failed_count += 1
                        errors.append(f"Study note failed for {ticker}")
                
                # Rate limiting (학습 메모는 더 보수적으로)
                time.sleep(3)
            
            except Exception as e:
                logger.error(f"Batch study note failed: {e}")
                failed_count += len(batch)
                errors.append(f"Batch study note error: {e}")
    
    except Exception as e:
        logger.error(f"Gemini API setup failed: {e}", exc_info=True)
        errors.append(f"Gemini setup failed: {e}")
    
    return {
        'success_count': success_count,
        'failed_count': failed_count,
        'errors': errors
    }


def get_batch_study_notes_gemini(stocks: List[Dict], model, run_date: str,
                                 db: StudyDatabase) -> Dict:
    """
    Gemini API로 백일공부 학습 메모 배치 생성
    
    백일공부 철학:
    1. 사실 수집 → 2. 사실 요약 → 3. 검증 → 4. 학습 메모 → 5. 신뢰도 평가
    
    Returns:
        {ticker: {'success': bool, 'confidence': str}, ...}
    """
    results = {}
    
    try:
        # 각 종목의 뉴스 데이터 수집
        stock_news_map = {}
        for stock in stocks:
            ticker = stock['ticker']
            news_items = db.get_news_items(run_date, ticker)
            
            # 뉴스 제목과 요약만 추출
            news_texts = []
            for news in news_items[:10]:  # 최대 10개만 사용
                news_texts.append(f"- [{news.get('publisher', '출처불명')}] {news['title']}: {news.get('snippet', '')}")
            
            stock_news_map[ticker] = {
                'name': stock['name'],
                'news_texts': '\n'.join(news_texts) if news_texts else '(뉴스 없음)'
            }
        
        # 프롬프트 구성 (백일공부 철학 반영)
        stock_sections = []
        for ticker, info in stock_news_map.items():
            stock_sections.append(
                f"### {info['name']} ({ticker})\n"
                f"관련 뉴스:\n{info['news_texts']}\n"
            )
        
        stocks_text = "\n".join(stock_sections)
        
        prompt = f"""당신은 "주식 공부용 학습 메모"를 작성하는 AI입니다. 
아래 종목들에 대해 뉴스를 분석하고, 각 종목마다 다음 형식의 JSON을 생성하세요:

**백일공부 원칙:**
1. 사실만 추출 (추측/예측 금지)
2. 여러 기사에서 공통으로 반복되는 내용만 요약
3. 학습 메모는 "이 종목에서 배울 점"을 일반화된 문장으로 작성
4. 신뢰도 평가: high(3개 이상 기사 일치), mid(2개 기사 일치), low(단일 기사 또는 불명확)

**출력 형식 (JSON):**
```json
{{
  "종목코드": {{
    "factual_summary": "여러 기사에서 공통으로 언급된 사실만 2-3문장으로 요약. 단일 기사 주장은 제외.",
    "ai_learning_note": "이 종목에서 배울 수 있는 일반화된 교훈. 특정 종목명 언급 금지. 다음에 비슷한 패턴을 만났을 때 체크할 조건 포함. 감정/예측/권유 금지.",
    "ai_confidence": "high 또는 mid 또는 low",
    "verification_status": "기사 간 내용 일치 여부 또는 '확인 필요' 메시지"
  }}
}}
```

**예시:**
```json
{{
  "123456": {{
    "factual_summary": "복수의 언론사가 A사와의 계약 체결을 보도. 계약 규모는 100억원으로 일치.",
    "ai_learning_note": "주요 고객사와의 대규모 계약 체결 시 단기 급등 가능성. 계약 규모, 고객사 신뢰도, 기존 매출 대비 비중 확인 필요.",
    "ai_confidence": "high",
    "verification_status": "3개 언론사 보도 내용 일치"
  }}
}}
```

**분석할 종목:**
{stocks_text}

**중요:** JSON만 출력하세요. 다른 설명은 불필요합니다.
"""
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # JSON 파싱
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            json_text = response_text[start_idx:end_idx+1]
            json_response = json.loads(json_text)
            
            # DB에 저장
            for ticker, note_data in json_response.items():
                try:
                    db.insert_study_note({
                        'run_date': run_date,
                        'ticker': ticker,
                        'factual_summary': note_data.get('factual_summary'),
                        'ai_learning_note': note_data.get('ai_learning_note'),
                        'ai_confidence': note_data.get('ai_confidence', 'low'),
                        'verification_status': note_data.get('verification_status')
                    })
                    
                    results[ticker] = {
                        'success': True, 
                        'confidence': note_data.get('ai_confidence', 'unknown')
                    }
                
                except Exception as e:
                    logger.error(f"Failed to save study note for {ticker}: {e}")
                    results[ticker] = {'success': False}
        else:
            logger.warning("Gemini 응답에서 JSON을 찾을 수 없습니다")
            for stock in stocks:
                results[stock['ticker']] = {'success': False}
    
    except Exception as e:
        logger.error(f"Batch study note generation failed: {e}", exc_info=True)
        for stock in stocks:
            results[stock['ticker']] = {'success': False}
    
    return results


def get_batch_summaries_gemini(stocks: List[Dict], model, run_date: str, 
                               db: StudyDatabase) -> Dict:
    """
    Gemini API로 배치 요약 생성 (뉴스 기반 - 환각 방지)
    
    Returns:
        {ticker: {'success': bool, 'summary': str}, ...}
    """
    results = {}
    
    try:
        # 각 종목의 뉴스 데이터 수집 (환각 방지)
        stock_news_map = {}
        for stock in stocks:
            ticker = stock['ticker']
            news_items = db.get_news_items(run_date, ticker)
            
            # 뉴스 제목과 요약만 추출 (최대 5개)
            news_texts = []
            for news in news_items[:5]:
                news_texts.append(f"- [{news.get('publisher', '')}] {news['title']}")
                if news.get('snippet'):
                    news_texts.append(f"  {news.get('snippet')}")
            
            stock_news_map[ticker] = {
                'name': stock['name'],
                'news_texts': '\n'.join(news_texts) if news_texts else '(뉴스 없음)'
            }
        
        # 프롬프트 구성 (뉴스 기반)
        stock_sections = []
        for ticker, info in stock_news_map.items():
            stock_sections.append(
                f"### {info['name']} ({ticker})\n"
                f"관련 뉴스:\n{info['news_texts']}\n"
            )
        
        stocks_text = "\n".join(stock_sections)
        
        prompt = f"""아래 종목들을 **수집된 뉴스 내용만을 근거로** 요약하세요.

**중요:**
- 뉴스가 없으면 "관련 뉴스 없음"이라고만 적으세요
- 추측하지 말고 뉴스에 명시된 사실만 요약
- 각 종목당 2-4문장

**출력 형식 (JSON):**
```json
{{
  "종목코드": "뉴스 기반 요약 내용"
}}
```

**종목 및 뉴스:**
{stocks_text}

**JSON만 출력:**
"""
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # JSON 파싱
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            json_text = response_text[start_idx:end_idx+1]
            json_response = json.loads(json_text)
            
            # DB에 저장
            for ticker, summary_text in json_response.items():
                try:
                    db.insert_summary({
                        'run_date': run_date,
                        'ticker': ticker,
                        'summary_text': summary_text,
                        'llm_provider': 'gemini',
                        'llm_model': 'gemini-2.0-flash-exp'
                    })
                    
                    results[ticker] = {'success': True, 'summary': summary_text}
                
                except Exception as e:
                    logger.error(f"Failed to save summary for {ticker}: {e}")
                    results[ticker] = {'success': False}
        else:
            logger.warning("Gemini 응답에서 JSON을 찾을 수 없습니다")
            for stock in stocks:
                results[stock['ticker']] = {'success': False}
    
    except Exception as e:
        logger.error(f"Batch summary generation failed: {e}", exc_info=True)
        for stock in stocks:
            results[stock['ticker']] = {'success': False}
    
    return results
