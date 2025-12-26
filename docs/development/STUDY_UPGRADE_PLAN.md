# 유목민 공부법 업그레이드 계획서

## 📋 현재 코드 구조 분석

### 1. 기존 구현 위치
- **파일**: `hantubot/reporting/study.py`
- **호출 위치**: `hantubot/core/engine.py` → `_process_post_market_logic()` 메서드
- **함수 시그니처**: `run_daily_study(broker, notifier, force_run=False)`

### 2. 현재 동작 방식
```python
# 장 마감 후 실행 (engine.py 415줄)
try:
    now = dt.datetime.now()
    force_run = now.hour <= 16 and now.minute <= 30
    run_daily_study(broker=self.broker, notifier=self.notifier, force_run=force_run)
except Exception as e:
    logger.error(f"데일리 스터디 자료 생성 실패: {e}")
```

### 3. 현재 기능
- **데이터 수집**: pykrx로 상한가(29%+) 또는 거래량 천만주+ 종목 조회
- **필터링**: `is_eligible_stock()` 함수로 ETF, 스팩 제외
- **요약**: Gemini API (gemini-2.0-flash) 배치 요약
- **저장**: Google Sheets (DailyLog, Frequency_Analysis 시트)
- **알림**: Discord 웹훅으로 완료 알림

### 4. 현재 제약사항
- Google Sheets 의존성 (service_account.json 필요)
- 뉴스/재료 수집 없음 (왜 올랐는지 근거 부족)
- 요약 실패 시 "요약 생성 실패"로만 표시
- 중복 실행 방지만 있고, 부분 실패 처리 미흡

---

## 🎯 업그레이드 목표

### 1. 저장소 변경: Google Sheets → SQLite
- **경로**: `data/study.db`
- **WAL 모드**: 자동매매 봇과 병행 동작 안정성
- **Pathlib 기준**: 크로스 플랫폼 호환성

### 2. 뉴스/재료 수집 추가
- **Provider 패턴**: 확장 가능한 구조
- **초기 구현**: Naver 뉴스 크롤링
- **확장 가능**: 유료 API 추가 용이

### 3. LLM 요약 강화
- **배치 처리**: 이미 구현됨 (유지)
- **캐싱**: 이미 요약된 (ticker + date)는 재요약 안함
- **실패 내성**: 요약 실패해도 뉴스 링크는 저장

### 4. Streamlit 대시보드
- **날짜별 조회**: 과거 공부 자료 검색
- **종목 상세**: 시세 + 뉴스 + 요약 통합 뷰
- **필터링**: 상한가/거래량/시장/키워드

### 5. 실패 내성 강화
- 각 단계 독립적으로 try/except
- 시장 데이터는 항상 저장
- 뉴스 수집 실패 → 해당 종목만 실패 마킹
- LLM 요약 실패 → 원문 링크 유지

---

## 📊 데이터베이스 설계 (SQLite)

### 테이블 구조

#### 1. study_runs
```sql
CREATE TABLE study_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL UNIQUE,  -- YYYYMMDD
    started_at TEXT NOT NULL,       -- ISO datetime
    ended_at TEXT,                  -- ISO datetime
    status TEXT NOT NULL,           -- success / partial / fail
    error_message TEXT,
    stats_json TEXT,                -- JSON: {candidates: N, news: N, summaries: N}
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. daily_candidates
```sql
CREATE TABLE daily_candidates (
    run_date TEXT NOT NULL,         -- YYYYMMDD
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT,                    -- KOSPI / KOSDAQ
    close_price INTEGER,
    change_pct REAL,
    volume INTEGER,
    value_traded INTEGER,           -- 거래대금
    reason_flag TEXT,               -- limit_up / volume_10m / both
    data_collection_status TEXT DEFAULT 'pending',  -- pending / news_collected / summarized / failed
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_date, ticker)
);
```

#### 3. news_items
```sql
CREATE TABLE news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    provider TEXT NOT NULL,         -- naver / paid_news
    title TEXT NOT NULL,
    publisher TEXT,
    published_at TEXT,
    url TEXT NOT NULL,
    snippet TEXT,
    raw_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_date, ticker, url)
);
```

#### 4. summaries
```sql
CREATE TABLE summaries (
    run_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    key_points_json TEXT,           -- JSON array
    keywords_json TEXT,             -- JSON array
    llm_provider TEXT DEFAULT 'gemini',
    llm_model TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_date, ticker)
);
```

#### 5. ticker_notes (옵션)
```sql
CREATE TABLE ticker_notes (
    ticker TEXT PRIMARY KEY,
    note_text TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🗂️ 디렉토리 구조 (신규 추가)

```
hantubot_prod/
├── data/
│   └── study.db                    # SQLite 데이터베이스
├── hantubot/
│   ├── reporting/
│   │   ├── study.py                # [수정] 메인 로직 리팩토링
│   │   ├── study_db.py             # [신규] DB 관리
│   │   └── study_legacy.py         # [신규] 기존 Google Sheets 로직 백업
│   └── providers/
│       ├── __init__.py             # [신규]
│       ├── news_base.py            # [신규] 추상 베이스 클래스
│       └── naver_news.py           # [신규] Naver 뉴스 수집
└── dashboard/
    ├── app.py                      # [신규] Streamlit 메인
    ├── pages/
    │   ├── 1_종목_상세.py
    │   └── 2_Run_로그.py
    └── utils/
        └── db_loader.py            # [신규] DB 조회 헬퍼
```

---

## 🔄 마이그레이션 전략

### 단계별 전환
1. **Phase 1**: SQLite 구조 구현 + 병행 저장 (Google Sheets + SQLite)
2. **Phase 2**: 뉴스 수집 추가 (SQLite만 저장)
3. **Phase 3**: Streamlit 대시보드 구현
4. **Phase 4**: Google Sheets 의존성 제거 (옵션화)

### 호환성 유지
- `run_daily_study(broker, notifier, force_run=False)` 시그니처 유지
- 기존 로직은 `study_legacy.py`로 백업
- 환경 변수로 모드 전환 가능 (`STUDY_MODE=sqlite` or `gsheet`)

---

## ⚙️ 설정 업데이트

### .env 추가 항목
```bash
# 유목민 공부법 설정
STUDY_MODE=sqlite                    # sqlite / gsheet / both
STUDY_DB_PATH=data/study.db

# 뉴스 수집 설정 (선택)
NAVER_CLIENT_ID=                     # Naver Open API
NAVER_CLIENT_SECRET=

# LLM 설정
GEMINI_API_KEY=                      # 이미 존재
LLM_BATCH_SIZE=10                    # 한번에 요약할 종목 수
```

---

## 🚀 실행 방법

### 자동 실행 (기존과 동일)
```bash
python run.py
```
- 장 마감 후 자동으로 `run_daily_study()` 호출

### 수동 실행 (CLI)
```bash
# 오늘 날짜로 강제 실행
python -m hantubot.reporting.study --force

# 특정 날짜로 재실행
python -m hantubot.reporting.study --date 20250101

# 뉴스만 재수집
python -m hantubot.reporting.study --date 20250101 --news-only
```

### Streamlit 대시보드
```bash
streamlit run dashboard/app.py
```

---

## 🛡️ 실패 시나리오별 동작

| 단계 | 실패 시 동작 | 다음 단계 진행 여부 |
|------|-------------|-------------------|
| 시장 데이터 조회 (pykrx) | 전체 run 실패, 알림 발송 | ❌ 중단 |
| 특정 종목 뉴스 수집 | 해당 종목 `data_collection_status=failed`, 로그 기록 | ✅ 계속 |
| LLM 요약 생성 | 해당 종목 요약 없이 뉴스만 저장, 로그 기록 | ✅ 계속 |
| DB 저장 실패 | 재시도 3회, 실패 시 알림 발송 | ⚠️ 재시도 |
| Google Sheets 저장 실패 (병행 모드) | 로그 경고, SQLite는 성공 처리 | ✅ 계속 |

---

## 📈 성능 최적화

### 1. DB 최적화
- WAL 모드 활성화: 읽기/쓰기 동시 수행
- 인덱스: `(run_date, ticker)`, `(ticker, run_date)`

### 2. API 호출 최적화
- Gemini API: 배치 호출 (이미 구현됨)
- Naver 뉴스: 종목당 최대 20개 제한
- Rate Limiting: 요청 간 0.5초 대기

### 3. 캐싱
- 일봉 데이터: engine.py의 기존 캐시 활용
- LLM 요약: DB에 이미 있으면 재요약 안함

---

## ✅ 체크리스트

- [ ] SQLite 스키마 생성 (`study_db.py`)
- [ ] 뉴스 수집 provider 구현 (`providers/`)
- [ ] 메인 로직 리팩토링 (`study.py`)
- [ ] Streamlit 대시보드 구현 (`dashboard/`)
- [ ] 환경 변수 업데이트 (`.env.example`)
- [ ] CLI 인터페이스 구현
- [ ] 실패 내성 테스트
- [ ] 문서화 (README 업데이트)

---

## 📝 구현 우선순위

1. **P0 (필수)**: SQLite DB + 메인 로직 리팩토링
2. **P1 (높음)**: 뉴스 수집 (Naver)
3. **P2 (중간)**: Streamlit 대시보드
4. **P3 (낮음)**: CLI 수동 실행, 유료 뉴스 API

---

*작성일: 2025-12-25*
*작성자: Cline (AI Assistant)*
