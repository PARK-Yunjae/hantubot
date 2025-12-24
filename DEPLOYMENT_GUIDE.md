# 🚀 Hantubot 배포 가이드

> **간편 실행부터 EXE 배포까지**

---

## 📋 목차

1. [빠른 실행 (배치 파일)](#1-빠른-실행-배치-파일)
2. [바탕화면 바로가기 만들기](#2-바탕화면-바로가기-만들기)
3. [EXE 파일 생성 (배포용)](#3-exe-파일-생성-배포용)
4. [배포 패키지 만들기](#4-배포-패키지-만들기)
5. [문제 해결](#5-문제-해결)

---

## 1. 빠른 실행 (배치 파일) ⭐ 가장 쉬움!

### ✅ 사용 방법

**방법 1: 더블클릭**
```
📁 hantubot_prod/
└── start_hantubot.bat  ← 이 파일 더블클릭!
```

**방법 2: 파일 탐색기에서**
1. `C:\Coding\hantubot_prod` 폴더 열기
2. `start_hantubot.bat` 더블클릭
3. GUI 자동 실행!

### 🎯 장점
- ✅ 설치 불필요
- ✅ 가상환경 자동 감지
- ✅ 에러 발생 시 창 유지
- ✅ 수정 간편

---

## 2. 바탕화면 바로가기 만들기

### Step 1: 바로가기 생성

1. **start_hantubot.bat** 파일 우클릭
2. **바로가기 만들기** 클릭
3. 생성된 바로가기를 **바탕화면으로 드래그**

### Step 2: 아이콘 변경 (선택)

1. 바로가기 우클릭 → **속성**
2. **바로가기** 탭 → **아이콘 변경**
3. 원하는 아이콘 선택

### Step 3: 이름 변경

```
start_hantubot.bat - 바로가기
     ↓
🤖 Hantubot 자동매매
```

### 🎯 결과

바탕화면에서 **더블클릭만으로 실행!** 🎉

---

## 3. EXE 파일 생성 (배포용)

### 🤔 EXE가 필요한 경우

- 다른 사람에게 배포
- Python 없는 PC에서 실행
- 프로페셔널한 느낌

### ⚠️ 주의사항

**EXE의 단점:**
- 파일 크기 큼 (100~300MB)
- 빌드 시간 오래 걸림
- 안티바이러스 오탐 가능
- 코드 수정 시 재빌드 필요

**추천:** 대부분의 경우 **배치 파일이 더 좋습니다!**

### Step 1: PyInstaller 설치

```bash
# venv 환경 활성화
venv\Scripts\activate

# PyInstaller 설치
pip install pyinstaller
```

### Step 2: 빌드 스크립트 생성

`build_exe.bat` 파일 생성:

```batch
@echo off
chcp 65001 > nul
echo ========================================
echo   🔨 Hantubot EXE 빌드 중...
echo ========================================

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM venv 환경 활성화
if exist "venv\Scripts\activate.bat" (
    echo [INFO] venv 가상환경 활성화 중...
    call venv\Scripts\activate.bat
) else (
    echo [ERROR] venv 가상환경을 찾을 수 없습니다!
    echo [INFO] 먼저 'python -m venv venv' 명령으로 가상환경을 생성하세요.
    pause
    exit /b 1
)

REM 이전 빌드 삭제
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

REM PyInstaller 실행
pyinstaller ^
  --name="Hantubot" ^
  --windowed ^
  --onefile ^
  --icon=icon.ico ^
  --add-data="configs;configs" ^
  --hidden-import=PySide6 ^
  --hidden-import=pandas ^
  --hidden-import=requests ^
  run.py

echo.
echo ========================================
echo   ✅ 빌드 완료!
echo   📁 실행 파일: dist\Hantubot.exe
echo ========================================
pause
```

### Step 3: 빌드 실행

```bash
build_exe.bat
```

**결과:**
```
dist/
└── Hantubot.exe  ← 생성된 실행 파일
```

### Step 4: 테스트

```bash
dist\Hantubot.exe
```

---

## 4. 배포 패키지 만들기

### 🎁 배포 패키지 구성

```
Hantubot_Release_v1.0/
├── Hantubot.exe              # 실행 파일
├── configs/
│   ├── .env.example          # 설정 템플릿
│   └── config.yaml           # 전략 설정
├── README.md                 # 사용 설명서
├── LEARNING_GUIDE.md         # 학습 가이드
└── 설치_가이드.txt            # 빠른 시작 가이드
```

### Step 1: 배포 폴더 생성

```bash
# PowerShell에서
mkdir Hantubot_Release_v1.0
cd Hantubot_Release_v1.0
```

### Step 2: 필요한 파일 복사

```bash
# 실행 파일
copy ..\dist\Hantubot.exe .

# 설정 파일
mkdir configs
copy ..\configs\.env.example configs\
copy ..\configs\config.yaml configs\

# 문서
copy ..\README.md .
copy ..\LEARNING_GUIDE.md .
```

### Step 3: 빠른 시작 가이드 작성

`설치_가이드.txt`:

```
═══════════════════════════════════
   Hantubot 자동매매 시스템 v1.0
═══════════════════════════════════

📌 빠른 시작 (3분)

1. configs/.env.example을 configs/.env로 복사
2. configs/.env 파일 열어서 API 키 입력
3. Hantubot.exe 더블클릭
4. GUI에서 "Start Engine" 클릭!

📖 자세한 설명: README.md 참고
📚 파이썬 학습: LEARNING_GUIDE.md 참고

⚠️ 주의사항
- 반드시 모의투자로 먼저 테스트!
- 실전 투자 전 충분한 학습 필요
- 투자 손실 책임은 본인에게 있음

💬 문의
GitHub: https://github.com/PARK-Yunjae/hantubot
```

### Step 4: 압축

```bash
# 7-Zip, WinRAR 등으로 압축
Hantubot_Release_v1.0.zip
```

### 🎯 배포 완료!

친구에게 `.zip` 파일만 보내면 끝!

---

## 5. 문제 해결

### Q1: PyInstaller 설치 안 됨

**해결:**
```bash
# pip 업그레이드
python -m pip install --upgrade pip

# 재시도
pip install pyinstaller
```

### Q2: EXE 실행 시 "Windows에서 보호함" 경고

**원인:** 서명되지 않은 실행 파일

**해결:**
1. "추가 정보" 클릭
2. "실행" 클릭

**영구 해결:** 코드 서명 인증서 구매 (비용 발생)

### Q3: EXE가 너무 큼 (300MB+)

**원인:** 모든 라이브러리 포함

**해결:**
```bash
# --onefile 대신 --onedir 사용 (폴더로 배포)
pyinstaller --windowed --onedir run.py
```

### Q4: 안티바이러스가 차단함

**원인:** 오탐 (False Positive)

**해결:**
1. 배치 파일 사용 (EXE 대신)
2. 또는 안티바이러스 예외 등록

### Q5: 실행 시 모듈 없다는 에러

**원인:** 숨겨진 import 누락

**해결:**
```bash
pyinstaller ^
  --hidden-import=모듈명 ^
  run.py
```

---

## 📊 방법 비교

| 방법 | 난이도 | 파일 크기 | 배포 | 추천 |
|------|--------|-----------|------|------|
| **배치 파일** | ⭐ | 1KB | Python 필요 | ✅ 일반 사용 |
| **바로가기** | ⭐ | 1KB | Python 필요 | ✅ 개인 사용 |
| **EXE 파일** | ⭐⭐⭐ | 100~300MB | 독립 실행 | ⚠️ 배포용만 |

---

## 🎯 추천 사항

### 개인 사용
```
start_hantubot.bat ← 이거면 충분!
```

### 친구에게 공유
```
1. 배치 파일 + 설명서
2. 또는 GitHub 링크
```

### 상용 배포
```
1. EXE + 코드 서명
2. 설치 프로그램 (NSIS 등)
3. 자동 업데이트 기능
```

---

## ✨ 마무리

**대부분의 경우:**
- ✅ `start_hantubot.bat` 더블클릭으로 충분!
- ✅ 바탕화면 바로가기만 만들면 끝!

**EXE는:**
- ⚠️ 꼭 필요할 때만 사용
- ⚠️ 배포 목적으로만 권장

**Happy Trading!** 🚀📈
