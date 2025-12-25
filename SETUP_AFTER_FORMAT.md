# 💻 포맷 후 Hantubot 재설치 가이드

> **컴퓨터 포맷 후 처음부터 다시 설정하는 완전한 가이드**

---

## 📋 목차

1. [Git 상태 확인](#1-git-상태-확인)
2. [필수 프로그램 설치](#2-필수-프로그램-설치)
3. [프로젝트 클론 및 복구](#3-프로젝트-클론-및-복구)
4. [Python 환경 설정](#4-python-환경-설정)
5. [API 키 재설정](#5-api-키-재설정)
6. [Cline 설치 및 사용법](#6-cline-설치-및-사용법)
7. [프로젝트 실행 확인](#7-프로젝트-실행-확인)

---

## ✅ 1. Git 상태 확인

### 현재 상태 (포맷 전 체크)

**✅ 커밋 상태:**
```bash
git status
# On branch main
# Your branch is up to date with 'origin/main'.
# nothing to commit, working tree clean
```

**✅ 리모트 저장소:**
```bash
git remote -v
# origin  https://github.com/PARK-Yunjae/hantubot.git (fetch)
# origin  https://github.com/PARK-Yunjae/hantubot.git (push)
```

**✅ 최신 커밋:**
```bash
# 커밋 해시: 747dca921049de904d37446b721a8ce26093bb9d
# 모든 변경사항이 GitHub에 안전하게 백업되었습니다!
```

**결론:** 🎉 **모든 코드가 GitHub에 안전하게 저장되어 있습니다!**

---

## 💻 2. 필수 프로그램 설치

### 2-1. Python 설치

#### Windows

1. **[Python 공식 사이트](https://www.python.org/downloads/)** 접속
2. **Python 3.11** 또는 **Python 3.12** 다운로드
3. **설치 시 주의사항:**
   - ✅ **"Add Python to PATH"** 반드시 체크! (가장 중요!)
   - ✅ "Install launcher for all users" 체크 (선택)
   - 기본 경로에 설치: `C:\Users\사용자명\AppData\Local\Programs\Python\Python311`

4. **설치 확인:**
```bash
# Windows CMD 또는 PowerShell에서
python --version
# Python 3.11.x 또는 3.12.x 출력되면 성공!

pip --version
# pip 23.x.x 출력되면 성공!
```

**문제 해결:**
- "python이(가) 내부 또는 외부 명령으로 인식되지 않습니다" 에러 발생 시:
  - Python 재설치 (Add to PATH 체크!)
  - 또는 환경변수에 수동으로 추가

---

### 2-2. Git 설치

1. **[Git 공식 사이트](https://git-scm.com/downloads)** 접속
2. Windows용 Git 다운로드 및 설치
3. 기본 옵션으로 설치 (Next 연타!)

4. **설치 확인:**
```bash
git --version
# git version 2.x.x 출력되면 성공!
```

---

### 2-3. Visual Studio Code 설치

1. **[VS Code 공식 사이트](https://code.visualstudio.com/)** 접속
2. Windows용 다운로드 및 설치
3. 설치 옵션:
   - ✅ "Code(으)로 열기" 작업을 Windows 탐색기 상황에 추가
   - ✅ PATH에 추가

---

## 📦 3. 프로젝트 클론 및 복구

### 3-1. 작업 폴더 생성

```bash
# Windows CMD 또는 PowerShell에서
# C 드라이브에 Coding 폴더 생성
cd C:\
mkdir Coding
cd Coding
```

---

### 3-2. GitHub에서 프로젝트 클론

```bash
# Hantubot 프로젝트 클론
git clone https://github.com/PARK-Yunjae/hantubot.git hantubot_prod

# 프로젝트 폴더로 이동
cd hantubot_prod
```

**확인:**
```bash
dir
# .gitignore, README.md, requirements.txt 등이 보이면 성공!
```

---

### 3-3. VS Code에서 프로젝트 열기

**방법 1: 탐색기에서**
- `C:\Coding\hantubot_prod` 폴더 우클릭
- "Code(으)로 열기" 선택

**방법 2: VS Code에서**
- VS Code 실행
- File → Open Folder
- `C:\Coding\hantubot_prod` 선택

---

## 🐍 4. Python 환경 설정

### 4-1. VS Code 터미널 설정

**중요:** Windows에서는 **CMD** 터미널이 가장 안정적입니다!

1. VS Code에서 **Ctrl + Shift + P**
2. `Terminal: Select Default Profile` 검색
3. **Command Prompt** 선택
4. 새 터미널 열기: **Ctrl + `** (백틱)

---

### 4-2. 가상환경 생성

```bash
# VS Code 터미널 (CMD)에서
python -m venv venv
```

**확인:**
```bash
dir
# venv 폴더가 생성되었는지 확인
```

---

### 4-3. 가상환경 활성화

```bash
# Windows CMD
venv\Scripts\activate

# 프롬프트 앞에 (venv) 표시되면 성공!
(venv) C:\Coding\hantubot_prod>
```

**문제 해결 (PowerShell):**
```powershell
# PowerShell에서 권한 오류 발생 시
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
venv\Scripts\Activate.ps1
```

**권장:** 문제 발생 시 **CMD** 터미널 사용!

---

### 4-4. 필수 패키지 설치

```bash
# pip 업그레이드
pip install --upgrade pip

# requirements.txt에서 모든 패키지 설치
pip install -r requirements.txt
```

**설치 시간:** 약 2-5분 소요

**설치 확인:**
```bash
pip list
# PySide6, pandas, requests, PyYAML 등이 보이면 성공!
```

**패키지 목록:**
- **Core**: setuptools, python-dotenv, PyYAML, requests
- **Scheduling**: holidays
- **GUI**: PySide6
- **Data**: pandas, openpyxl, ta, pykrx
- **Web**: beautifulsoup4
- **Google**: gspread, gspread-dataframe, google-auth-oauthlib, google-genai, google-generativeai

---

## 🔑 5. API 키 재설정

### 5-1. `.env` 파일 생성

```bash
# configs/.env.example을 복사하여 .env 생성
copy configs\.env.example configs\.env
```

---

### 5-2. API 키 입력

**configs/.env 파일 편집:**

```env
# ========================================
# 한국투자증권 API 키
# ========================================
KIS_APP_KEY="발급받은_APP_KEY를_여기에"
KIS_APP_SECRET="발급받은_APP_SECRET을_여기에"
KIS_ACCOUNT_NO="계좌번호-01"

# ========================================
# Discord 웹훅 (선택사항)
# ========================================
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# ========================================
# Gemini API (유목민 공부법용, 선택사항)
# ========================================
GEMINI_API_KEY="발급받은_Gemini_API_키"
```

**주의사항:**
- **모의투자**: 한국투자증권 → KIS Developers → 모의투자 APP_KEY 발급
- **실전투자**: 실전투자 APP_KEY 발급 (별도)
- `config.yaml`의 `mode` 설정과 일치해야 함!

---

### 5-3. 한국투자증권 API 키 발급 방법

1. **[한국투자증권 KIS Developers](https://apiportal.koreainvestment.com/)** 접속
2. 로그인
3. **모의투자** 또는 **실전투자** 선택
4. "앱 등록" → `APP_KEY`, `APP_SECRET` 발급
5. 계좌번호 확인 (형식: `12345678-01`)

---

### 5-4. Discord 웹훅 생성 (선택)

1. Discord 서버 설정 → 연동 → 웹훅
2. "새 웹훅" 클릭
3. 이름: Hantubot
4. 웹훅 URL 복사 → `.env`에 붙여넣기

---

### 5-5. Gemini API 발급 (선택)

1. **[Google AI Studio](https://aistudio.google.com/app/apikey)** 접속
2. "Get API Key" 클릭
3. API 키 복사 → `.env`에 붙여넣기

---

## 🤖 6. VS Code Cline 확장 (선택사항)

**Cline**은 VS Code에서 사용하는 AI 코딩 어시스턴트입니다.

### 설치 방법

1. VS Code 확장 프로그램 탭 (**Ctrl + Shift + X**)
2. `Cline` 검색 후 설치
3. API 키 설정 (Claude, OpenAI GPT-4 등)

### 주요 기능

- 💬 자연어로 코드 작성 및 수정
- 🔍 코드 분석 및 설명
- 🐛 버그 수정 및 리팩토링
- 📝 문서 자동 생성

### 사용 예시

```
"README.md 파일 내용을 설명해줘"
"새로운 전략 파일을 만들어줘"
"이 에러를 찾아서 고쳐줘"
```

**참고:** Cline 사용이 필수는 아니며, VS Code의 일반 편집 기능만으로도 충분합니다.

---

## ✅ 7. 프로젝트 실행 확인

### 7-1. 전체 체크리스트

```bash
# 1. Python 확인
python --version
# ✅ Python 3.11.x 이상

# 2. 가상환경 활성화 확인
# ✅ 프롬프트에 (venv) 표시

# 3. 패키지 설치 확인
pip list
# ✅ PySide6, pandas, requests 등

# 4. .env 파일 확인
type configs\.env
# ✅ API 키가 제대로 입력되었는지 확인
```

---

### 7-2. Hantubot 실행

**방법 1: GUI 모드 (권장)**
```bash
python run.py
```

**방법 2: 배치 파일**
```bash
start_hantubot.bat
```

**성공 확인:**
- 🎨 GUI 창이 열림
- ✅ 로그에 "Trading Engine initialized" 표시
- 🟢 "Start Engine" 버튼 클릭 가능

---

### 7-3. 테스트 실행

#### 모의투자 모드로 테스트

**configs/config.yaml 확인:**
```yaml
mode: mock  # 모의투자 모드
```

**실행:**
```bash
python run.py
```

**확인 사항:**
- 접근 토큰 발급 성공
- Discord 알림 수신 (설정한 경우)
- GUI에서 로그 출력

---

### 7-4. 문제 해결

#### 문제 1: "ModuleNotFoundError"

**원인:** 패키지 미설치

**해결:**
```bash
pip install -r requirements.txt
```

---

#### 문제 2: "접근 토큰 발급 실패"

**원인:** API 키 오류

**해결:**
1. `.env` 파일의 API 키 재확인
2. 한국투자증권에서 키 재발급
3. `mode`(모의/실전)와 API 키 일치 확인

---

#### 문제 3: GUI가 안 열림

**원인:** PySide6 오류

**해결:**
```bash
pip uninstall PySide6
pip install PySide6
```

---

## 🎯 빠른 복구 체크리스트

포맷 후 빠르게 복구하려면:

- [ ] Python 3.11+ 설치 (Add to PATH 체크!)
- [ ] Git 설치
- [ ] VS Code 설치
- [ ] 프로젝트 클론: `git clone https://github.com/PARK-Yunjae/hantubot.git hantubot_prod`
- [ ] VS Code에서 프로젝트 열기
- [ ] 터미널을 CMD로 설정
- [ ] 가상환경 생성: `python -m venv venv`
- [ ] 가상환경 활성화: `venv\Scripts\activate`
- [ ] 패키지 설치: `pip install -r requirements.txt`
- [ ] `.env` 파일 생성 및 API 키 입력
- [ ] Cline 설치 (선택)
- [ ] 실행 테스트: `python run.py`

---

## 📚 추가 참고 자료

| 문서 | 내용 |
|------|------|
| **README.md** | 프로젝트 전체 소개 및 사용법 |
| **VSCODE_SETUP.md** | VS Code 터미널 설정 상세 가이드 |
| **LEARNING_GUIDE.md** | Python 기초부터 전략 개발까지 |
| **DEPLOYMENT_GUIDE.md** | 배포 및 운영 가이드 |
| **PYTHON_VERSION_GUIDE.md** | Python 버전 관리 가이드 |

---

## 🔗 중요 링크

- **GitHub 저장소**: https://github.com/PARK-Yunjae/hantubot.git
- **Python 다운로드**: https://www.python.org/downloads/
- **Git 다운로드**: https://git-scm.com/downloads
- **VS Code 다운로드**: https://code.visualstudio.com/
- **한국투자증권 API**: https://apiportal.koreainvestment.com/

---

## 💡 핵심 요약

### 포맷 전 확인
✅ **모든 코드가 GitHub에 백업되었습니다!**
- 저장소: `https://github.com/PARK-Yunjae/hantubot.git`
- 브랜치: `main`
- 최신 커밋: `747dca921049de904d37446b721a8ce26093bb9d`

### 포맷 후 복구 (30분 내 완료!)
1. Python 설치 (5분)
2. Git 설치 (3분)
3. VS Code 설치 (5분)
4. 프로젝트 클론 (2분)
5. 가상환경 설정 (3분)
6. 패키지 설치 (5분)
7. API 키 설정 (5분)
8. Cline 설치 (2분, 선택)
9. 실행 테스트 (3분)

**총 소요 시간: 약 30분**

---

## 📞 도움이 필요하면?

- **GitHub Issues**: [이슈 등록](https://github.com/PARK-Yunjae/hantubot/issues)
- **Cline에게 질문**: VS Code에서 Cline 패널 열고 질문!
- **Email**: dbswoql0712@gmail.com

---

<div align="center">

**🎉 포맷 후에도 걱정 없이 빠르게 복구하세요! 🎉**

Made with ❤️ by [PARK-Yunjae](https://github.com/PARK-Yunjae)

</div>
