# 유목민 공부법 배포 및 데이터 보존 가이드

## 📦 데이터 보존 (포맷 후에도 활용)

### SQLite DB 백업 전략

유목민 공부법의 모든 데이터는 `data/study.db` 파일에 저장됩니다. **이 파일만 백업하면 모든 데이터를 보존**할 수 있습니다!

#### 1. 수동 백업 (가장 간단)

**포맷 전:**
```bash
# 백업 폴더 생성
mkdir C:\Backup\hantubot_study

# DB 파일 복사
copy C:\Coding\hantubot_prod\data\study.db C:\Backup\hantubot_study\

# 또는 클라우드 드라이브에 복사
copy C:\Coding\hantubot_prod\data\study.db "C:\Users\PYJ\OneDrive\백업\study.db"
```

**포맷 후:**
```bash
# 프로젝트 재설치 후
copy C:\Backup\hantubot_study\study.db C:\Coding\hantubot_prod\data\

# 대시보드 실행하면 바로 이전 데이터 확인 가능
streamlit run dashboard/app.py
```

#### 2. 자동 백업 스크립트 (권장)

**backup_study_db.bat** 파일 생성:
```batch
@echo off
REM 유목민 공부법 DB 자동 백업
set BACKUP_DIR=C:\Backup\hantubot_study
set SOURCE_DB=C:\Coding\hantubot_prod\data\study.db

REM 백업 폴더가 없으면 생성
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM 날짜별 백업 (덮어쓰기 방지)
set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%
copy "%SOURCE_DB%" "%BACKUP_DIR%\study_%TIMESTAMP%.db"

echo 백업 완료: %BACKUP_DIR%\study_%TIMESTAMP%.db
pause
```

**사용법:**
- 백업하려면 `backup_study_db.bat` 더블클릭
- 또는 윈도우 작업 스케줄러로 자동화

#### 3. 클라우드 동기화 (추천)

**OneDrive/Google Drive/Dropbox 활용:**

1. **심볼릭 링크 생성** (관리자 권한 CMD):
   ```bash
   # data 폴더 전체를 OneDrive에 동기화
   mklink /D "C:\Coding\hantubot_prod\data" "C:\Users\PYJ\OneDrive\hantubot_data"
   ```

2. **장점:**
   - 실시간 자동 백업
   - 여러 PC에서 동일한 데이터 접근
   - 포맷 후에도 즉시 복구

3. **주의사항:**
   - SQLite WAL 파일 때문에 동시 쓰기는 피할 것
   - 한 PC에서만 봇 실행, 다른 PC에서는 읽기 전용

#### 4. 데이터 내보내기 (CSV/Excel)

완전히 독립적인 형태로 백업:

**export_study_data.py** (프로젝트 루트에 생성):
```python
import sqlite3
import pandas as pd
from pathlib import Path

# DB 연결
db_path = Path('data/study.db')
conn = sqlite3.connect(str(db_path))

# 각 테이블을 CSV로 내보내기
tables = ['study_runs', 'daily_candidates', 'news_items', 'summaries']

export_dir = Path('exports')
export_dir.mkdir(exist_ok=True)

for table in tables:
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    df.to_csv(f'exports/{table}.csv', index=False, encoding='utf-8-sig')
    print(f"✓ {table}.csv 생성")

conn.close()
print("\n✅ 모든 데이터를 exports/ 폴더에 CSV로 저장했습니다.")
```

**실행:**
```bash
python export_study_data.py
```

---

## 🌐 Streamlit 온라인 배포

Streamlit 대시보드를 온라인에 배포하면 **어디서나 웹 브라우저로 접근** 가능합니다!

### 방법 1: Streamlit Community Cloud (무료, 권장)

**장점:**
- 완전 무료
- GitHub 연동 자동 배포
- HTTPS 지원
- 간단한 설정

**단계:**

1. **GitHub에 프로젝트 업로드**
   ```bash
   # .gitignore에 추가 (민감한 정보 제외)
   echo "configs/.env" >> .gitignore
   echo "data/*.db" >> .gitignore
   
   # GitHub에 push
   git add .
   git commit -m "Add study dashboard"
   git push origin main
   ```

2. **Streamlit Cloud 가입**
   - https://share.streamlit.io 접속
   - GitHub 계정으로 로그인

3. **앱 배포**
   - "New app" 클릭
   - Repository: `PARK-Yunjae/hantubot`
   - Branch: `main`
   - Main file path: `dashboard/app.py`
   - "Deploy!" 클릭

4. **환경 변수 설정**
   - Advanced settings → Secrets
   - `.env` 내용을 TOML 형식으로 입력:
   ```toml
   STUDY_DB_PATH = "data/study.db"
   ```

5. **데이터 업로드**
   - GitHub에 `data/study.db` 업로드 (public repo는 주의!)
   - 또는 S3/Google Cloud Storage 연동

**배포 URL 예시:**
```
https://your-username-hantubot-study.streamlit.app
```

**주의사항:**
- Public repo면 DB 파일이 공개됨 (민감한 정보 주의)
- Private repo 권장 (무료 플랜도 가능)
- DB 파일 크기 제한 (500MB)

### 방법 2: Heroku (유료/무료)

**특징:**
- 무료 티어 종료, 최소 $5/월
- 더 큰 리소스 사용 가능

**단계:**

1. **Procfile 생성**
   ```
   web: streamlit run dashboard/app.py --server.port=$PORT
   ```

2. **runtime.txt 생성**
   ```
   python-3.11.7
   ```

3. **Heroku 배포**
   ```bash
   heroku login
   heroku create your-app-name
   git push heroku main
   ```

### 방법 3: 로컬 네트워크 공유 (가장 간단)

**집안 네트워크에서 접근:**

```bash
# 외부 접근 허용 모드로 실행
streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8501
```

- 같은 WiFi의 다른 기기에서 접근 가능
- URL: `http://[내컴퓨터IP]:8501`
- IP 확인: `ipconfig` (Windows)

**외부 인터넷에서 접근 (고급):**

1. **ngrok 사용 (임시 터널)**
   ```bash
   # ngrok 설치: https://ngrok.com/download
   
   # Streamlit 실행 후
   ngrok http 8501
   ```
   
   - 임시 URL 생성 (예: `https://abc123.ngrok.io`)
   - 무료 플랜은 8시간 제한

2. **공유기 포트 포워딩 (영구)**
   - 공유기 설정에서 8501 포트 개방
   - DDNS 설정으로 고정 도메인 사용
   - 보안 주의 (비밀번호 설정 필수)

### 방법 4: 자체 서버 (VPS)

**AWS EC2, Azure VM, 또는 국내 호스팅:**

```bash
# Ubuntu 서버에서
sudo apt update
sudo apt install python3-pip
pip3 install streamlit plotly

# 백그라운드 실행
nohup streamlit run dashboard/app.py &

# 또는 systemd 서비스로 등록
```

---

## 📖 실행 전 체크리스트

### 필수 확인 사항

#### 1. 환경 설정 확인

```bash
# configs/.env 파일 확인
notepad configs\.env
```

**필수 항목:**
- [ ] `GEMINI_API_KEY` 설정됨
- [ ] `STUDY_MODE=sqlite` 설정됨
- [ ] `STUDY_DB_PATH=data/study.db` 설정됨

#### 2. 패키지 설치 확인

```bash
# 가상환경 활성화
venv\Scripts\activate

# 새 패키지 설치
pip install streamlit plotly

# 설치 확인
pip list | findstr "streamlit"
pip list | findstr "plotly"
```

#### 3. 디렉토리 구조 확인

```
hantubot_prod/
├── data/                    [생성됨]
│   └── study.db            [자동 생성됨]
├── dashboard/              [생성됨]
│   ├── app.py
│   └── utils/
│       └── db_loader.py
├── hantubot/
│   ├── providers/          [생성됨]
│   │   ├── __init__.py
│   │   ├── news_base.py
│   │   └── naver_news.py
│   └── reporting/
│       ├── study.py        [수정됨]
│       ├── study_db.py     [생성됨]
│       └── study_legacy.py [백업]
└── configs/
    └── .env                [수정됨]
```

#### 4. 첫 실행 테스트

**테스트 순서:**

1. **DB 초기화 테스트**
   ```bash
   python -c "from hantubot.reporting.study_db import get_study_db; db=get_study_db(); print('✓ DB 초기화 성공')"
   ```

2. **수동 실행 테스트**
   ```bash
   python -m hantubot.reporting.study --force
   ```
   
   **예상 출력:**
   ```
   ================================================================================
   유목민 공부법 (100일 공부) 시작 - SQLite + 뉴스 수집 버전
   ================================================================================
   [1/4] 시장 데이터 수집 중...
   ✅ X개 후보 종목 발견 및 DB 저장 완료
   [2/4] 뉴스 수집 중...
   ✅ X개 뉴스 수집 완료 (X개 종목 실패)
   [3/4] LLM 요약 생성 중...
   ✅ X개 요약 생성 완료 (X개 실패)
   [4/4] Google Sheets 백업 건너뜀
   ================================================================================
   유목민 공부법 완료: success
   ================================================================================
   ```

3. **대시보드 실행 테스트**
   ```bash
   streamlit run dashboard/app.py
   ```
   
   - 브라우저가 자동으로 열림
   - 데이터가 보이는지 확인

4. **Discord 알림 확인**
   - Discord에 완료 알림이 왔는지 확인
   - 에러 메시지가 없는지 확인

#### 5. 로그 확인

```bash
# 최근 로그 확인
type logs\hantubot.log | more

# 에러만 확인
findstr "ERROR" logs\hantubot.log
```

### 문제 해결 빠른 가이드

| 증상 | 원인 | 해결책 |
|------|------|--------|
| `ModuleNotFoundError: streamlit` | 패키지 미설치 | `pip install streamlit plotly` |
| `GEMINI_API_KEY not found` | 환경변수 미설정 | `.env` 파일에 API 키 추가 |
| `No such table: study_runs` | DB 초기화 실패 | `data/study.db` 삭제 후 재실행 |
| 뉴스 수집 0개 | 정상 (주말/공휴일) | 평일 장 마감 후 재시도 |
| 대시보드 빈 화면 | 데이터 없음 | 먼저 `--force` 옵션으로 수동 실행 |

---

## 🎯 권장 워크플로우

### 일일 루틴

```
09:00 - 봇 자동 시작
15:30 - 장 마감 후 자동 데이터 수집
16:00 - Discord 알림 확인
16:30 - 대시보드에서 오늘의 종목 확인
       → Streamlit 실행: streamlit run dashboard/app.py
17:00 - 관심 종목 상세 분석
```

### 주말 루틴

```
토요일 - 주간 빈도 분석
       - 반복 등장 종목 패턴 연구
       - DB 백업 실행
일요일 - 다음 주 전략 수립
```

### 포맷 전 체크리스트

```
[ ] data/study.db 백업 완료
[ ] configs/.env 백업 완료
[ ] GitHub에 최신 코드 push
[ ] (선택) CSV로 데이터 내보내기
[ ] 클라우드 동기화 확인
```

### 포맷 후 복구 절차

```
1. Python + Git 설치
2. 프로젝트 clone
3. 가상환경 생성 및 패키지 설치
4. study.db 파일 복원
5. .env 파일 복원
6. 대시보드 실행 확인
```

---

## 🔐 보안 주의사항

### 온라인 배포 시

1. **API 키 보호**
   - `.env` 파일은 절대 GitHub에 올리지 말 것
   - Streamlit Secrets 또는 환경변수 사용

2. **DB 파일 보호**
   - Public repo에 DB 업로드 주의
   - 민감한 데이터가 있다면 Private repo 사용

3. **접근 제한**
   - Streamlit Cloud의 경우 인증 설정 고려
   - 또는 VPN/IP 제한

### 백업 보안

1. **클라우드 백업**
   - OneDrive/Google Drive는 비공개 폴더 사용
   - 암호화 백업 고려

2. **외부 저장소**
   - USB/외장하드 백업은 암호화 권장
   - 정기적으로 백업 무결성 확인

---

## 📞 추가 지원

- **문서**: `STUDY_GUIDE.md` - 일반 사용 가이드
- **설계**: `STUDY_UPGRADE_PLAN.md` - 기술 문서
- **이슈**: GitHub Issues로 문의

---

**성공적인 100일 공부 되시길 바랍니다! 🚀**

*작성일: 2025-12-25*
*버전: 1.0.0*
