# 📘 Hantubot 통합 매뉴얼 (설치/설정/실행)

> **설치부터 실행까지, 이 문서 하나로 끝내세요!**

---

## 📋 목차

1. [설치 및 환경 설정](#1-설치-및-환경-설정)
2. [필수 설정 (API, 알림)](#2-필수-설정-api-알림)
3. [실행 및 운영](#3-실행-및-운영)
4. [배포 및 EXE 생성](#4-배포-및-exe-생성)

---

## 1. 설치 및 환경 설정

### 1.1 필수 요구사항
- **OS**: Windows 10/11 권장
- **Python**: 3.10 이상 (3.11 추천)
- **Editor**: Visual Studio Code (VS Code)

### 1.2 설치 순서

1. **프로젝트 다운로드** (Git Clone 또는 ZIP 다운로드)
   ```bash
   git clone https://github.com/PARK-Yunjae/hantubot.git
   cd hantubot
   ```

2. **가상환경 생성 및 활성화**
   ```bash
   # 가상환경 생성
   python -m venv venv

   # 가상환경 활성화 (Windows)
   venv\Scripts\activate
   ```

3. **라이브러리 설치**
   ```bash
   pip install -r requirements.txt
   ```

---

## 2. 필수 설정 (API, 알림)

### 2.1 환경변수 파일 생성
`configs` 폴더 안의 `.env.example` 파일을 복사하여 `.env` 파일로 이름을 변경합니다.

### 2.2 한국투자증권(KIS) API 설정
- **KIS_APP_KEY**: 한국투자증권 홈페이지에서 발급받은 App Key
- **KIS_APP_SECRET**: 발급받은 App Secret
- **KIS_ACCOUNT_NO**: 계좌번호 8자리 + 2자리 (예: `12345678-01`)
- **KIS_MODE**: `simulation` (모의투자) 또는 `real` (실전투자)

### 2.3 알림 설정 (Discord/Email)

#### Discord 알림
1. 디스코드 채널 설정 -> 연동 -> 웹후크 만들기
2. 웹후크 URL 복사
3. `.env` 파일의 `DISCORD_WEBHOOK_URL`에 붙여넣기

#### 이메일 알림 (Gmail)
1. 구글 계정 보안 설정 -> 2단계 인증 활성화 -> 앱 비밀번호 생성
2. `.env` 파일 설정:
   ```env
   EMAIL_SENDER=your.email@gmail.com
   EMAIL_PASSWORD=앱비밀번호(16자리)
   EMAIL_RECEIVER=받을이메일주소
   ```

### 2.4 VS Code 추천 설정

`.vscode/settings.json` 예시:
```json
{
  "python.defaultInterpreterPath": "./venv/Scripts/python.exe",
  "python.formatting.provider": "black",
  "editor.formatOnSave": true
}
```

---

## 3. 실행 및 운영

### 3.1 봇 실행

가장 간편한 방법은 `start_hantubot.bat` 파일을 더블클릭하는 것입니다.

터미널에서 직접 실행하려면:
```bash
python run.py
```

### 3.2 주요 기능
- **Start Engine**: 자동매매 엔진을 시작합니다.
- **Stop Engine**: 엔진을 중지합니다.
- **Log Viewer**: 실시간 로그를 확인합니다.

### 3.3 유목민 공부법 (장 마감 후)
장 마감 후(15:30~)에는 자동으로 데이터를 수집하고 AI 요약을 생성합니다. (자세한 내용은 `docs/NOMAD_STUDY.md` 참조)

---

## 4. 배포 및 EXE 생성

다른 PC에서 Python 설치 없이 실행하고 싶다면 EXE 파일로 만들 수 있습니다.

### 4.1 PyInstaller 설치
```bash
pip install pyinstaller
```

### 4.2 빌드 실행
프로젝트 루트에서 다음 명령어를 실행하거나, `build_exe.bat` 스크립트를 작성하여 실행하세요.

```bash
pyinstaller --name="Hantubot" --windowed --onefile --icon=icon.ico --add-data="configs;configs" run.py
```

생성된 파일은 `dist/Hantubot.exe`에 위치합니다.

### 4.3 배포 시 주의사항
- 배포 시 `configs/.env` 파일은 포함하지 않거나, 개인정보를 지우고 배포하세요.
- EXE 파일 실행 시 안티바이러스 경고가 뜰 수 있습니다. (서명되지 않은 프로그램)
