# 유목민 공부법 실행 가이드

## 📚 개요

**유목민 공부법 (100일 공부)**은 매일 장 마감 후 상한가 또는 거래량 천만주 이상 종목을 자동으로 수집하고, 뉴스와 AI 요약을 제공하여 "왜 이 종목이 올랐는가?"를 학습할 수 있도록 돕는 시스템입니다.

### 주요 기능

- ✅ **자동 데이터 수집**: 장 마감 후 자동으로 후보 종목 수집
- 📰 **뉴스 수집**: Naver 뉴스 자동 검색 및 저장
- 🤖 **AI 요약**: Gemini AI로 종목별 핵심 요약 생성
- 💾 **SQLite 저장**: 로컬 DB에 누적 저장 (검색 가능)
- 📊 **대시보드**: Streamlit으로 과거 데이터 조회 및 분석

---

## 🚀 빠른 시작

### 1단계: 환경 설정

#### 필수 패키지 설치
```bash
# 가상환경 활성화 (이미 설치된 경우)
cd C:\Coding\hantubot_prod
venv\Scripts\activate

# 새로운 패키지 설치
pip install streamlit plotly
```

#### 환경 변수 설정 (.env)
`configs/.env` 파일을 열어 다음 항목을 추가/수정하세요:

```bash
# Gemini API 키 (필수 - AI 요약 기능)
GEMINI_API_KEY="AIzaSy..."

# 유목민 공부법 설정
STUDY_MODE=sqlite          # sqlite / gsheet / both
STUDY_DB_PATH=data/study.db
LLM_BATCH_SIZE=10
```

**Gemini API 키 발급 방법:**
1. https://aistudio.google.com/app/apikey 접속
2. Google 계정으로 로그인
3. "Create API Key" 클릭
4. 생성된 키를 복사하여 `.env` 파일에 붙여넣기

### 2단계: 자동 실행 (봇과 함께)

유목민 공부법은 **자동매매 봇 실행 시 자동으로 작동**됩니다.

```bash
# 봇 실행 (기존 방식 그대로)
python run.py
```

- 장 마감 후 (15:30 이후) 자동으로 실행됨
- Discord로 완료 알림 수신
- `data/study.db`에 데이터 저장

### 3단계: 대시보드 실행

수집된 데이터를 확인하려면 Streamlit 대시보드를 실행하세요.

```bash
# 대시보드 실행
streamlit run dashboard/app.py
```

브라우저가 자동으로 열리며 `http://localhost:8501`에서 확인 가능합니다.

---

## 🛠️ 수동 실행

### 오늘 날짜로 강제 실행
```bash
python -m hantubot.reporting.study --force
```

### 특정 날짜 재실행 (향후 구현 예정)
```bash
python -m hantubot.reporting.study --date 20250101
```

---

## 📊 대시보드 사용법

### 메인 화면
1. **날짜 선택**: 사이드바에서 과거 날짜 선택 가능
2. **통계 요약**: 후보 종목, 뉴스, AI 요약 개수 확인
3. **필터링**: 시장, 선정 사유, 키워드로 종목 필터링
4. **후보 종목 테이블**: 전체 종목 리스트 확인

### 종목 상세 정보
- **시세 정보**: 종가, 등락률, 거래량 등
- **AI 요약**: Gemini가 생성한 핵심 요약
- **관련 뉴스**: 수집된 뉴스 리스트 (링크 포함)

### 빈도 분석
- 최근 100일간 가장 자주 등장한 종목 확인
- 반복적으로 관심받는 종목 파악 가능

---

## 🔧 문제 해결

### 1. "데이터가 없습니다" 오류
**원인**: 아직 유목민 공부법이 한 번도 실행되지 않았습니다.

**해결책**:
```bash
# 수동으로 강제 실행
python -m hantubot.reporting.study --force
```

### 2. Gemini API 오류
**증상**: "GEMINI_API_KEY not found" 또는 요약 생성 실패

**해결책**:
1. `.env` 파일에 `GEMINI_API_KEY` 확인
2. API 키가 올바른지 확인 (https://aistudio.google.com)
3. API 할당량 초과 여부 확인

### 3. 뉴스 수집 실패
**증상**: "뉴스 없음" 또는 특정 종목만 실패

**해결책**:
- 정상 동작입니다 (실패 내성 설계)
- 뉴스가 없는 종목은 `no_news` 상태로 저장됨
- 로그 확인: `logs/` 디렉토리

### 4. SQLite DB 손상
**증상**: "database is locked" 또는 데이터 읽기 실패

**해결책**:
```bash
# DB 백업
copy data\study.db data\study_backup.db

# DB 재생성 (기존 데이터 삭제 주의!)
del data\study.db
python -m hantubot.reporting.study --force
```

### 5. Streamlit 실행 오류
**증상**: `ModuleNotFoundError: No module named 'streamlit'`

**해결책**:
```bash
# 가상환경 활성화 확인
venv\Scripts\activate

# Streamlit 설치
pip install streamlit plotly
```

---

## 📂 데이터 구조

### SQLite DB 위치
```
C:\Coding\hantubot_prod\data\study.db
```

### 테이블 구조
- `study_runs`: 실행 이력
- `daily_candidates`: 후보 종목
- `news_items`: 뉴스 데이터
- `summaries`: AI 요약
- `ticker_notes`: 사용자 메모 (옵션)

### DB 직접 조회 (고급)
```bash
# SQLite 명령줄 도구 사용
sqlite3 data/study.db

# 테이블 목록
.tables

# 최근 데이터 조회
SELECT * FROM study_runs ORDER BY run_date DESC LIMIT 5;
```

---

## ⚙️ 고급 설정

### Google Sheets 병행 저장
기존 Google Sheets도 계속 사용하려면:

```bash
# .env 파일
STUDY_MODE=both
```

### LLM 배치 크기 조정
한 번에 요약할 종목 수를 조절하여 API 사용량 최적화:

```bash
# .env 파일
LLM_BATCH_SIZE=5   # 기본값: 10
```

### 뉴스 Provider 추가 (향후)
`hantubot/providers/` 디렉토리에 새로운 Provider 추가 가능:

```python
# 예: paid_news.py
from .news_base import NewsProvider

class PaidNewsProvider(NewsProvider):
    def fetch_news(self, ticker, stock_name, date):
        # 유료 API 연동
        pass
```

---

## 📖 참고 자료

### 관련 문서
- [프로젝트 전체 README](./README.md)
- [업그레이드 계획서](./STUDY_UPGRADE_PLAN.md)
- [배포 가이드](./DEPLOYMENT_GUIDE.md)

### 코드 위치
- **메인 로직**: `hantubot/reporting/study.py`
- **DB 관리**: `hantubot/reporting/study_db.py`
- **뉴스 수집**: `hantubot/providers/naver_news.py`
- **대시보드**: `dashboard/app.py`
- **레거시 코드**: `hantubot/reporting/study_legacy.py` (백업)

---

## 💡 활용 팁

### 1. 매일 루틴
1. 장 마감 후 Discord 알림 확인
2. 대시보드에서 오늘의 종목 확인
3. 관심 종목의 뉴스와 AI 요약 읽기
4. 차트와 함께 분석 (별도 툴 사용)

### 2. 주간 리뷰
- 빈도 분석으로 반복 등장 종목 파악
- 패턴 발견 및 전략 수립

### 3. 100일 챌린지
- 매일 최소 5개 종목 상세 분석
- 왜 올랐는지 이유를 자신의 언어로 정리
- 메모 기능 활용 (향후 구현 예정)

---

## 🆘 지원

### 문제 보고
- GitHub Issues: https://github.com/PARK-Yunjae/hantubot/issues
- Discord 알림으로 에러 로그 자동 전송됨

### 기여
- Pull Requests 환영합니다
- 새로운 뉴스 Provider 추가
- 대시보드 기능 개선

---

**행운을 빕니다! 📈**

*작성일: 2025-12-25*
*버전: 1.0.0*
