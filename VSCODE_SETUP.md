# 🔧 VS Code 터미널 설정 가이드

> **"Python을 찾을 수 없습니다" 에러 해결하기**

---

## 🎯 문제 상황

VS Code 터미널에서:
```
python --version
# Python was not found
```

**원인:** Python이 PATH에 등록되지 않았거나, 터미널 설정 문제

---

## ✅ 해결 방법

### 방법 1: VS Code 터미널을 CMD로 변경 ⭐ 가장 쉬움!

#### Step 1: 터미널 프로필 변경

1. VS Code에서 **Ctrl + Shift + P** (명령 팔레트)
2. `Terminal: Select Default Profile` 검색
3. **Command Prompt** 선택

#### Step 2: 새 터미널 열기

1. 기존 터미널 닫기 (휴지통 아이콘)
2. **Ctrl + `** (백틱) 또는 메뉴: Terminal → New Terminal
3. 이제 CMD로 열림!

#### Step 3: venv 가상환경 활성화

```bash
venv\Scripts\activate

# 프롬프트에 (venv) 표시되면 성공
(venv) C:\Coding\hantubot_prod>

# Python 확인
python --version
```

---

### 방법 2: Python 재설치 (PATH 등록 필수)

Python이 설치되지 않았거나 PATH에 없는 경우:

#### Step 1: Python 설치

1. [Python 공식 사이트](https://www.python.org/downloads/) 접속
2. Python 3.11 또는 3.12 다운로드
3. 설치 시 **"Add Python to PATH"** 반드시 체크 ✅ (중요!)
4. Install Now

#### Step 2: VS Code 완전 재시작

**터미널만 새로 여는 게 아니라 VS Code를 완전히 종료 후 재시작!**

#### Step 3: 확인

```bash
python --version
# Python 3.11.x 출력되면 성공!
```

---

### 방법 3: 배치 파일 사용 (가장 간단!) ⭐⭐⭐

VS Code 터미널 설정 없이도 바로 실행:

```bash
# VS Code 터미널에서
start_hantubot.bat
```

또는 파일 탐색기에서 `start_hantubot.bat` 더블클릭!

---

## 📊 터미널 비교

| 터미널 | venv 지원 | 추천도 |
|--------|----------|--------|
| **CMD** | ✅ 완벽 | ⭐⭐⭐ |
| **PowerShell** | ✅ 가능 (설정 필요) | ⭐⭐ |
| **Git Bash** | ⚠️ 경로 문제 가능 | ⭐ |

**결론:** Windows에서는 **CMD가 가장 무난합니다!**

---

## 💡 VS Code 터미널 단축키

| 단축키 | 기능 |
|--------|------|
| **Ctrl + `** | 터미널 열기/닫기 |
| **Ctrl + Shift + `** | 새 터미널 열기 |
| **Ctrl + Shift + 5** | 터미널 분할 |

---

## 🔍 문제 해결

### Q1: CMD로 바꿨는데도 Python을 못 찾아요

**해결:**

1. Python 재설치 (Add to PATH 체크!)
2. 또는 PATH 수동 등록:
   - 시작 → "환경 변수" 검색
   - 시스템 변수 → Path → 편집
   - 추가: `C:\Users\PYJ\AppData\Local\Programs\Python\Python311`
   - 추가: `C:\Users\PYJ\AppData\Local\Programs\Python\Python311\Scripts`
3. **VS Code 완전 재시작** 또는 시스템 재부팅

---

### Q2: venv 활성화가 안 됨 (PowerShell)

**증상:**
```powershell
venv\Scripts\activate
# 실행되지만 (venv) 표시가 안 나옴
```

**해결 (PowerShell):**
```powershell
# 실행 정책 변경
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 다시 시도
venv\Scripts\Activate.ps1
```

**권장:** PowerShell 대신 **CMD** 사용!

---

### Q3: Git Bash에서는 안 되나요?

Windows에서 Git Bash는 Python 가상환경과 궁합이 좋지 않습니다:
- 경로 변환 문제 (Windows 경로 vs Unix 경로)
- venv 활성화 방식이 다름

**강력 권장:** **CMD 사용!**

---

## 🎬 빠른 시작 (추천 워크플로우)

### 1️⃣ VS Code 터미널 사용

```bash
# VS Code에서 Ctrl + `
# 터미널이 CMD인지 확인

cd C:\Coding\hantubot_prod
venv\Scripts\activate
python run.py
```

### 2️⃣ 배치 파일 사용 (가장 쉬움!)

```bash
# VS Code 터미널에서
start_hantubot.bat

# 또는 탐색기에서 더블클릭
```

---

## 🎯 최종 권장 설정

### VS Code 설정 (settings.json)

**Ctrl + Shift + P** → `Preferences: Open User Settings (JSON)`

```json
{
  "terminal.integrated.defaultProfile.windows": "Command Prompt",
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/Scripts/python.exe"
}
```

이렇게 설정하면:
- 터미널이 자동으로 CMD로 열림
- Python 경로 자동 인식
- 프로젝트마다 venv 자동 감지

---

## 🚀 실전 테스트

### 테스트 1: Python 확인

```bash
python --version
# Python 3.11.x 나오면 성공
```

### 테스트 2: venv 활성화

```bash
venv\Scripts\activate

# 프롬프트에 (venv) 표시되면 성공
(venv) C:\Coding\hantubot_prod>
```

### 테스트 3: 한투봇 실행

```bash
python run.py
# GUI 열리면 완료!
```

---

## 📞 여전히 안 되면?

### 가장 쉬운 방법

**1. Windows CMD 직접 사용**
   - 시작 → `cmd` 검색
   - 명령 프롬프트 실행
   - `cd C:\Coding\hantubot_prod`
   - `start_hantubot.bat` 실행

**2. 배치 파일로 실행**
   - 파일 탐색기에서 `start_hantubot.bat` 더블클릭
   - VS Code 없이도 완벽하게 작동!

---

## ✨ 핵심 정리

1. **VS Code 터미널: CMD 사용 권장**
2. **Python 설치 시: "Add to PATH" 필수 체크**
3. **가장 간편: start_hantubot.bat 더블클릭**

Happy Coding! 🎉
