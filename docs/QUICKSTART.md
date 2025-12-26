# 🚀 Hantubot 빠른 시작 가이드

**최종 업데이트**: 2025-12-26

---

## 📋 목차

1. [필수 준비물](#필수-준비물)
2. [10분 설치](#10분-설치)
3. [환경 설정](#환경-설정)
4. [첫 실행](#첫-실행)
5. [자동 시작 설정](#자동-시작-설정)
6. [문제 해결](#문제-해결)

---

## ✅ 필수 준비물

- [ ] Python 3.11 이상
- [ ] 한국투자증권 계좌 (모의/실전)
- [ ] Discord 계정 (선택)
- [ ] Gmail 계정 (알림용, 선택)

---

## ⚡ 10분 설치

### 1단계: Python 설치

**Windows:**
1. https://www.python.org/downloads/ 접속
2. "Download Python 3.12" 클릭
3. **"Add Python to PATH" 체크** ✅ 필수!
4. Install Now

**확인:**
```bash
python --version
# Python 3.12.x 출력되면 성공
```

**macOS/Linux:**
```bash
# Homebrew (macOS)
brew install python@3.12

# apt (Ubuntu/Debian)
sudo apt install python3.12 python3.12-venv
```

### 2단계: 프로젝트 설치

```bash
# 1. 클론
git clone https://github.com/PARK-Yunjae/hantubot.git
cd hantubot_prod

# 2. 가상환경 생성
python -m venv venv

# 3. 가상환경 활성화
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# 4. 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
```

### 3단계: API 키 발급

**한국투자증권:**
1. https://apiportal.koreainvestment.com 로그인
2. 모의투자 또는 실전투자 선택
3. APP_KEY, APP_SECRET 발급
4. 계좌번호 확인

**Discord (선택):**
1. Discord 서버 설정 → 연동 → 웹훅
2. 새 웹훅 생성 → URL 복사

**Gemini AI (선택):**
1. https://aistudio.google.com/apikey
2. API 키 생성

---

## ⚙️ 환경 설정

### .env 파일 생성

```bash
# Windows
copy configs\.env.example configs\.env

# macOS/Linux
cp configs/.env.example configs/.env
```

### configs/.env 편집

```env
# ===== 한국투자증권 API =====
APP_KEY=발급받은_APP_KEY
APP_SECRET=발급받은_APP_SECRET
CANO=12345678  # 계좌번호 (하이픈 제외)
ACNT_PRDT_CD=01

# ===== Discord 웹훅 (선택) =====
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# ===== 자동 시작/종료 =====
AUTO_START_ENGINE=true
AUTO_SHUTDOWN_ENABLED=true
AUTO_SHUTDOWN_TIME=15:40

# ===== 이메일 알림 (선택) =====
EMAIL_ENABLED=true
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=앱_비밀번호
EMAIL_RECEIVER=dbswoql0712@gmail.com

# ===== Gemini AI (선택) =====
GEMINI_API_KEY=발급받은_키
```

### configs/config.yaml 확인

```yaml
# 거래 모드
mode: mock  # 'mock' (모의) 또는 'live' (실전)

# 활성 전략
active_strategies:
  - closing_price_advanced_screener  # 15:03 종가 매매

# 전략별 설정
strategy_settings:
  closing_price_advanced_screener:
    enabled: true
    auto_buy_enabled: true  # 자동 매수
```

---

## 🎮 첫 실행

### GUI 모드 (권장)

```bash
# 가상환경 활성화 확인
python run.py
```

**GUI 컨트롤:**
- 🟢 **Start Engine**: 시스템 시작
- 🔴 **Stop Engine**: 안전 정지
- 📊 실시간 로그 확인

### 테스트 확인 사항

1. **로그 확인**
   ```
   logs/hantubot.log 생성 확인
   ```

2. **Discord 알림**
   - "Hantubot 시스템이 시작되었습니다" 메시지 확인

3. **이메일 알림** (설정 시)
   - 테스트 이메일 수신 확인

4. **전략 로드**
   - GUI에 "closing_price_advanced_screener" 표시 확인

---

## 🤖 자동 시작 설정

### Windows 작업 스케줄러

**1단계: 배치 파일 생성**

`start_hantubot.bat` 생성 (이미 존재):
```batch
@echo off
cd /d C:\Coding\hantubot_prod
call venv\Scripts\activate
python run.py
pause
```

**2단계: 작업 스케줄러 설정**

1. `작업 스케줄러` 실행 (Win + R → `taskschd.msc`)
2. "작업 만들기" 클릭
3. **일반 탭**
   - 이름: `Hantubot 자동 시작`
   - ⚠️ **비밀번호 없는 계정**: "로그온할 때만 실행" 선택 (추천!)
   - ⚠️ **비밀번호 있는 계정**: "사용자 로그온 여부에 관계없이 실행" 선택
   - "가장 높은 수준의 권한으로 실행" 체크

4. **트리거 탭**
   - "새로 만들기" 클릭
   - 작업 시작: `일정에 따라`
   - 설정: `매일` / `월요일~금요일`
   - 시작: `08:50`
   - "사용" 체크

5. **동작 탭**
   - "새로 만들기" 클릭
   - 프로그램/스크립트: `C:\Coding\hantubot_prod\start_hantubot.bat`
   - 시작 위치: `C:\Coding\hantubot_prod`

6. **조건 탭**
   - "컴퓨터의 전원이 AC일 때만 작업 시작" 해제
   - "작업을 실행하기 위해 절전 모드 종료" 체크

7. **설정 탭**
   - "작업이 요청 시 실행되지 않으면 가능한 빨리 시작" 체크
   - "작업 실패 시 다시 시작 간격": `1분`
   - "다시 시작 시도 횟수": `3회`

8. **확인** 클릭 → Windows 비밀번호 입력
   - **비밀번호 없이 사용 중이라면**: 그냥 Enter (비밀번호 생성되지 않음!)
   - **비밀번호 사용 중이라면**: Windows 로그인 비밀번호 입력

**💡 TIP**: 비밀번호 입력이 싫다면
- **일반 탭**에서 "로그온할 때만 실행" 선택
- 이 경우 PC 켜져 있을 때만 작동 (추천!)

**테스트:**
- 작업 목록에서 "Hantubot 자동 시작" 우클릭 → "실행"
- 프로그램이 정상 실행되는지 확인

### macOS launchd

`~/Library/LaunchAgents/com.hantubot.autostart.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hantubot.autostart</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/hantubot_prod/venv/bin/python</string>
        <string>/path/to/hantubot_prod/run.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1-5</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>50</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

```bash
# 등록
launchctl load ~/Library/LaunchAgents/com.hantubot.autostart.plist

# 확인
launchctl list | grep hantubot
```

---

## 🔧 문제 해결

### 문제 1: ModuleNotFoundError

```bash
# 해결
pip install -r requirements.txt
```

### 문제 2: 한투 API 연결 실패

1. `.env`의 API 키 확인
2. 모의/실전 모드 일치 확인
3. 한투 API 포털에서 키 재발급

### 문제 3: GUI가 안 열림

```bash
# PySide6 재설치
pip uninstall PySide6
pip install PySide6
```

### 문제 4: 가상환경 활성화 안됨

**Windows PowerShell 실행 정책 오류:**
```powershell
# 관리자 권한으로 PowerShell 실행
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 문제 5: 이메일 알림 안 옴

**Gmail 앱 비밀번호 생성:**
1. Google 계정 → 보안
2. 2단계 인증 활성화
3. 앱 비밀번호 생성
4. 생성된 16자리 비밀번호를 `.env`에 입력

---

## 🎯 다음 단계

1. ✅ 설치 완료
2. ✅ 모의투자로 1주일 테스트
3. ✅ Discord/이메일 알림 확인
4. ✅ 로그 파일 모니터링
5. ✅ 실전투자 전환 (신중하게!)

**상세 가이드:**
- [OPTIMIZATION_GUIDE.md](guides/OPTIMIZATION_GUIDE.md) - 전체 시스템 이해
- [EMAIL_SETUP.md](setup/EMAIL_SETUP.md) - 이메일 알림 상세 설정

---

**🚀 설치 완료! 행복한 트레이딩 되세요!**
