# Hantubot 설정 가이드

**통합 문서**: EMAIL_SETUP.md + VSCODE_SETUP.md를 하나로 통합

---

## 📧 이메일 알림 설정

### Gmail 설정

1. **Gmail 계정에서 2단계 인증 활성화**
   - Google 계정 설정 → 보안 → 2단계 인증 활성화

2. **앱 비밀번호 생성**
   - Google 계정 → 보안 → 앱 비밀번호
   - "메일" 앱, "Windows 컴퓨터" 선택
   - 생성된 16자리 비밀번호 복사

3. **.env 파일에 추가**
   ```env
   EMAIL_SENDER=your.email@gmail.com
   EMAIL_PASSWORD=abcd efgh ijkl mnop  # 앱 비밀번호 (공백 포함)
   EMAIL_RECEIVER=receiver@example.com
   ```

### 테스트

```bash
python test_email.py
```

---

## 💻 VS Code 설정

### 1. 필수 확장 프로그램

- **Python** (Microsoft)
- **Pylance** (Microsoft)
- **GitLens** (자동 Git 히스토리)
- **YAML** (Red Hat)

### 2. workspace 설정 (.vscode/settings.json)

```json
{
  "python.defaultInterpreterPath": "./venv/Scripts/python.exe",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "venv/": true
  }
}
```

### 3. 디버깅 설정 (.vscode/launch.json)

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Hantubot GUI",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/run.py",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/configs/.env"
    }
  ]
}
```

### 4. 단축키 추천

- `Ctrl+Shift+P`: 명령 팔레트
- `Ctrl+B`: 사이드바 토글
- `F5`: 디버깅 시작
- `Ctrl+Shift+F`: 전체 검색

---

## 🔑 환경변수 설정 (.env)

### 필수 항목

```env
# KIS API 인증
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01

# Discord 알림
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# 이메일 알림 (선택)
EMAIL_SENDER=your.email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=receiver@example.com

# Gemini AI (유목민 공부법)
GEMINI_API_KEY=your_gemini_api_key

# Naver News API (선택)
NaverAPI_Client_ID=your_client_id
NaverAPI_Client_Secret=your_client_secret
```

### 선택 항목

```env
# 유목민 공부법
STUDY_MODE=sqlite
ENABLE_STUDY_NOTES=true
ENABLE_GIT_AUTO_COMMIT=true

# 자동 종료
AUTO_SHUTDOWN_ENABLED=true
AUTO_SHUTDOWN_TIME=15:40
```

---

## 🛠️ 문제 해결

### 이메일 전송 실패
- 앱 비밀번호 확인
- 2단계 인증 활성화 여부
- 방화벽 설정 (SMTP 포트 587)

### VS Code Python 인터프리터 인식 안됨
```bash
# 가상환경 재생성
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### .env 파일 로드 안됨
- 파일 위치: `configs/.env`
- 파일명 정확히 `.env` (확장자 없음)
- UTF-8 인코딩 확인

---

**참고**: 이 문서는 EMAIL_SETUP.md와 VSCODE_SETUP.md를 통합한 것입니다.
