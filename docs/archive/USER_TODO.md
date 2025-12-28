# 📝 사용자 할 일 목록 (월요일 실전 전)

**마지막 업데이트**: 2025-12-26  
**완료 기한**: 월요일 장 시작 전

---

## 🎯 우선순위 1: 즉시 완료 (30분)

### 1. 환경 변수 설정 (.env 파일) ⭐ 이메일만 추가!

**파일**: `configs/.env`

**✅ 기존 설정 확인만** (이미 설정되어 있음):
```env
# 한투 API (기존 설정 확인)
APP_KEY=...
APP_SECRET=...
CANO=...

# Discord (기존 설정 확인)
DISCORD_WEBHOOK_URL=...
```

**🆕 configs/.env 파일 맨 아래에 추가하세요!**:
```env
# ===== 자동 시작/종료 (NEW!) =====
AUTO_START_ENGINE=true
AUTO_SHUTDOWN_ENABLED=true
AUTO_SHUTDOWN_TIME=15:40
MAX_AUTO_RESTARTS=3

# ===== 이메일 알림 (NEW!) =====
EMAIL_ENABLED=true
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=dbswoql0712@gmail.com
EMAIL_PASSWORD=여기에_16자리_앱비밀번호_입력
EMAIL_RECEIVER=dbswoql0712@gmail.com
```

**💡 설명**:
- `EMAIL_SENDER`: 본인 Gmail (dbswoql0712@gmail.com)
- `EMAIL_RECEIVER`: 본인 Gmail (같은 주소!) - 본인이 본인에게 알림 받음
- `EMAIL_PASSWORD`: Gmail 앱 비밀번호 (아래에서 생성)

**체크리스트**:
- [ ] .env 파일 맨 아래에 위 9줄 복사/붙여넣기
- [ ] Gmail 앱 비밀번호 생성 (아래 가이드)
- [ ] `EMAIL_PASSWORD`에 16자리 비밀번호 입력

---

### 2. Gmail 앱 비밀번호 생성 ⭐ 중요!

**왜 필요한가?**
- CRITICAL 로그 발생 시 즉시 이메일 수신
- 주문 실패 5회 연속 시 알림
- 포트폴리오 -10% 이상 손실 시 알림
- 시스템 크래시 재시작 알림

**생성 방법**:

1. **Google 계정 접속**
   - https://myaccount.google.com/security

2. **2단계 인증 활성화** (필수)
   - "2단계 인증" 클릭
   - 설정 완료

3. **앱 비밀번호 생성**
   - "앱 비밀번호" 검색
   - 앱 선택: "메일"
   - 기기 선택: "Windows 컴퓨터"
   - "생성" 클릭

4. **16자리 비밀번호 복사**
   - 예: `abcd efgh ijkl mnop` (공백 포함)
   - `.env` 파일의 `EMAIL_PASSWORD`에 **공백 제거 후** 입력
   - 예: `EMAIL_PASSWORD=abcdefghijklmnop`

**테스트**:
```bash
python -c "from hantubot.utils.email_alert import test_email; test_email()"
```

**체크리스트**:
- [ ] 2단계 인증 활성화
- [ ] 앱 비밀번호 생성
- [ ] `.env`에 입력
- [ ] 테스트 이메일 수신 확인

---

### 3. config.yaml 설정 확인

**파일**: `configs/config.yaml`

```yaml
# 거래 모드 (중요!)
mode: mock  # 일단 모의로!

# 활성 전략
active_strategies:
  - closing_price_advanced_screener

# 전략 설정
strategy_settings:
  closing_price_advanced_screener:
    enabled: true
    auto_buy_enabled: true  # 자동 매수 ON
```

**체크리스트**:
- [ ] `mode: mock` 확인 (실전은 나중에!)
- [ ] 전략 활성화 확인
- [ ] `auto_buy_enabled: true` 확인

---

## 🎯 우선순위 2: 시스템 테스트 (1시간)

### 4. 첫 실행 테스트

```bash
# 1. 가상환경 활성화
venv\Scripts\activate

# 2. 프로그램 실행
python run.py
```

**확인 사항**:
- [ ] GUI 정상 실행
- [ ] "Start Engine" 클릭 시 정상 동작
- [ ] Discord 알림 수신 ("시스템 시작")
- [ ] 로그 파일 생성 (`logs/hantubot.log`)
- [ ] "Stop Engine" 정상 작동

---

### 5. 이메일 알림 테스트

**테스트 코드**:
```python
# test_email.py 생성
from hantubot.utils.email_alert import send_critical_alert

send_critical_alert(
    title="테스트 알림",
    error_message="이메일 설정이 정상 작동합니다!"
)
```

```bash
python test_email.py
```

**체크리스트**:
- [ ] 이메일 수신 확인
- [ ] 제목: "테스트 알림"
- [ ] 내용 정상 표시

---

### 6. 자동 시작 설정 (선택)

**Windows 작업 스케줄러**:

1. `Win + R` → `taskschd.msc` 실행
2. "작업 만들기" 클릭
3. 이름: `Hantubot 자동 시작`
4. 트리거: 월~금 08:50
5. 동작: `C:\Coding\hantubot_prod\start_hantubot.bat`

**상세 가이드**: [docs/QUICKSTART.md](docs/QUICKSTART.md#자동-시작-설정)

**체크리스트**:
- [ ] 작업 스케줄러 등록
- [ ] 수동 실행 테스트
- [ ] 다음 날 08:50 자동 실행 확인

---

## 🎯 우선순위 3: 모의투자 테스트 (1주일)

### 7. 월요일 ~ 금요일 모의투자

**목표**: 시스템 안정성 확인

**매일 확인 사항**:
- [ ] 월요일: 08:50 자동 시작 확인
- [ ] 09:00: 시초가 청산 로직 확인 (해당 시)
- [ ] 15:03: Discord 종가 후보 웹훅 수신
- [ ] 15:15-19: 1위 종목 자동 매수 확인
- [ ] 15:40: 자동 종료 확인
- [ ] 이메일 알림: CRITICAL 발생 시 수신 확인

**로그 확인**:
```bash
# 실시간 로그
tail -f logs/hantubot.log

# 오류만
tail -f logs/hantubot_error.log

# Windows (PowerShell)
Get-Content logs\hantubot.log -Wait -Tail 50
```

---

## 🎯 우선순위 4: 실전 전환 (신중하게!)

### 8. 실전투자 설정

**⚠️ 경고**: 1주일 모의투자 성공 후에만 진행!

**변경 사항**:

1. **configs/.env**
   ```env
   # 실전 API 키로 변경
   APP_KEY=실전용_APP_KEY
   APP_SECRET=실전용_APP_SECRET
   CANO=실전_계좌번호
   ```

2. **configs/config.yaml**
   ```yaml
   mode: live  # mock → live
   ```

3. **백업**
   ```bash
   # 설정 파일 백업
   copy configs\.env configs\.env.backup
   copy configs\config.yaml configs\config.yaml.backup
   ```

**체크리스트**:
- [ ] 모의투자 1주일 성공
- [ ] 모든 기능 정상 작동 확인
- [ ] 실전 API 키 발급
- [ ] 설정 파일 백업
- [ ] `mode: live` 변경
- [ ] 소액(10만원)으로 테스트

---

## 📊 전수조사 체크리스트

**별도 파일**: [INSPECTION_CHECKLIST.md](INSPECTION_CHECKLIST.md)

상세한 전수조사 항목은 별도 체크리스트 참고.

---

## 🆘 문제 발생 시

### 연락처
- **GitHub Issues**: https://github.com/PARK-Yunjae/hantubot/issues
- **Email**: dbswoql0712@gmail.com

### 로그 위치
```
logs/
├── hantubot.log           # 전체 로그
├── hantubot_warning.log   # 경고
└── hantubot_error.log     # 오류
```

### 긴급 중지
- GUI: "Stop Engine" 버튼
- 콘솔: `Ctrl + C`
- 강제 종료: 작업 관리자

---

## ✅ 최종 체크리스트

**월요일 장 시작 전**:

- [ ] `.env` 파일 설정 완료
- [ ] Gmail 앱 비밀번호 설정 완료
- [ ] 이메일 테스트 성공
- [ ] Discord 웹훅 테스트 성공
- [ ] GUI 정상 실행
- [ ] 자동 시작 설정 (선택)
- [ ] 모의투자 1주일 성공
- [ ] 로그 모니터링 방법 숙지
- [ ] 긴급 중지 방법 숙지

**모두 체크되면 준비 완료! 🚀**

---

**⏰ 남은 시간**: 월요일까지 주말 동안 여유롭게 준비하세요!
