# 📊 Streamlit Cloud 배포 가이드

> 유목민 공부법 대시보드를 Streamlit Cloud에 배포하여 웹에서 볼 수 있게 만들기

---

## 🎯 배포 전 준비사항

### 1. requirements.txt에 Streamlit 추가 확인

`requirements.txt` 파일에 다음 패키지들이 있는지 확인:

```txt
streamlit
pandas
plotly
```

### 2. GitHub에 코드 푸시

```bash
# 변경사항 커밋
git add .
git commit -m "Add 100-day study system with Streamlit dashboard"
git push origin main
```

---

## 🚀 Streamlit Cloud 배포 단계별 가이드

### STEP 1: Streamlit Cloud 가입

1. **https://streamlit.io/** 접속
2. 우측 상단 **Sign up** 클릭
3. **Continue with GitHub** 선택
4. GitHub 계정으로 로그인 및 권한 승인

### STEP 2: 새 앱 배포

1. 로그인 후 **Create app** 버튼 클릭
2. 배포 설정 입력:

```
Repository: PARK-Yunjae/hantubot
Branch: main
Main file path: dashboard/app.py
App URL (optional): hantubot-study (원하는 이름)
```

3. **Advanced settings** 클릭 (중요!)

### STEP 3: 환경 설정 (매우 중요!)

**Secrets 설정:**

```toml
# 아래 내용을 그대로 복사하여 Secrets에 입력
# (실제 값은 입력하지 마세요 - DB 경로만 지정)

STUDY_DB_PATH = "data/study.db"
STUDY_MODE = "sqlite"
```

**Python version:** `3.11` 선택

### STEP 4: 배포 실행

**Deploy!** 버튼 클릭 → 약 2-5분 대기

배포 완료되면 자동으로 URL 생성:
- 예: `https://hantubot-study.streamlit.app`

---

## ⚠️ 중요: 데이터 업로드 방법

Streamlit Cloud는 **읽기 전용**입니다. 따라서 다음 두 가지 방법 중 선택:

### 방법 1: GitHub에 DB 파일 커밋 (추천)

```bash
# .gitignore에서 data/study.db 제외
# 현재 .gitignore 확인 후 수정 필요 시:
# data/study.db 라인 삭제 또는 주석 처리

# DB 파일 커밋
git add data/study.db
git commit -m "Add study database"
git push origin main
```

**장점:**
- 간단하고 자동 동기화
- 매일 장 종료 후 자동 커밋하면 자동 업데이트

**단점:**
- DB 파일이 커지면 GitHub 용량 제한

### 방법 2: Google Drive 또는 Dropbox 연동 (고급)

나중에 DB가 커지면 클라우드 스토리지 사용

---

## 🔄 자동 업데이트 시스템 구축

### GitHub Actions 워크플로우 생성

`.github/workflows/update-study-db.yml` 파일 생성:

```yaml
name: Update Study Database

on:
  schedule:
    # 매일 오후 4시 (장 마감 후) 실행
    - cron: '0 7 * * 1-5'  # UTC 7시 = KST 16시
  workflow_dispatch:  # 수동 실행 가능

jobs:
  update-db:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run study collection
      env:
        GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      run: |
        python -m hantubot.reporting.study --force
    
    - name: Commit and push if changed
      run: |
        git config --global user.name 'GitHub Actions'
        git config --global user.email 'actions@github.com'
        git add data/study.db
        git diff --quiet && git diff --staged --quiet || git commit -m "Auto-update study database"
        git push
```

**GitHub Secrets 설정:**
1. GitHub 저장소 → Settings → Secrets and variables → Actions
2. **New repository secret** 클릭
3. Name: `GEMINI_API_KEY`, Value: (당신의 Gemini API 키)

---

## 📱 배포 후 확인사항

### 1. 대시보드 작동 확인

- URL 접속: `https://your-app-name.streamlit.app`
- 날짜 선택 기능 확인
- 종목 상세 정보 확인
- 뉴스 링크 클릭 테스트

### 2. 자동 업데이트 확인

- 다음날 오후 4시 이후 대시보드 새로고침
- 새로운 날짜 데이터가 나타나는지 확인

---

## 🐛 문제 해결

### 문제 1: "No module named 'streamlit'"

**해결:**
```bash
# requirements.txt에 streamlit 추가 확인
echo "streamlit" >> requirements.txt
git add requirements.txt
git commit -m "Add streamlit to requirements"
git push
```

### 문제 2: 데이터가 보이지 않음

**해결:**
```bash
# data/study.db 파일이 GitHub에 있는지 확인
git add data/study.db
git commit -m "Add study database"
git push

# Streamlit Cloud에서 앱 재시작 (Manage app → Reboot)
```

### 문제 3: "File not found: data/study.db"

**해결:**
- GitHub 저장소에서 `data/` 폴더 확인
- `.gitignore`에서 `data/study.db` 제외 확인
- 로컬에서 테스트 실행 후 DB 생성 확인

---

## 🎓 테스트 실행 방법

### 로컬에서 대시보드 테스트

```bash
# Streamlit 설치 (없는 경우)
pip install streamlit

# 대시보드 실행
streamlit run dashboard/app.py

# 브라우저에서 자동으로 열림 (http://localhost:8501)
```

### 과거 데이터로 테스트

```bash
# 24일 데이터 강제 생성 (테스트용)
python -m hantubot.reporting.study --force

# 대시보드에서 확인
streamlit run dashboard/app.py
```

---

## 📞 추가 도움

**Streamlit 공식 문서:**
- https://docs.streamlit.io/streamlit-community-cloud/get-started

**GitHub Actions 문서:**
- https://docs.github.com/en/actions

---

## ✅ 최종 체크리스트

배포 전 확인:

- [ ] `requirements.txt`에 streamlit 추가 확인
- [ ] `data/study.db` 파일 생성 및 GitHub 커밋
- [ ] `.gitignore`에서 `data/study.db` 제외 확인
- [ ] GitHub에 모든 변경사항 푸시
- [ ] Streamlit Cloud 가입 및 앱 생성
- [ ] 배포 완료 및 URL 접속 테스트

배포 후 확인:

- [ ] 대시보드 정상 작동
- [ ] 데이터 표시 확인
- [ ] 뉴스 링크 작동 확인
- [ ] (선택) GitHub Actions 자동 업데이트 설정

---

**🎉 이제 전 세계 어디서나 당신의 백일공부 대시보드를 볼 수 있습니다!**
