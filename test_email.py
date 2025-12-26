#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
이메일 알림 테스트 스크립트
"""
import os
from dotenv import load_dotenv
from hantubot.utils.email_alert import send_critical_alert

# .env 파일 로드 (중요!)
load_dotenv('configs/.env')

print("=" * 60)
print("📧 이메일 테스트 시작...")
print("=" * 60)
print(f"EMAIL_ENABLED: {os.getenv('EMAIL_ENABLED')}")
print(f"EMAIL_SENDER: {os.getenv('EMAIL_SENDER')}")
print(f"EMAIL_RECEIVER: {os.getenv('EMAIL_RECEIVER')}")
print("=" * 60)

try:
    send_critical_alert(
        title="🧪 Hantubot 이메일 테스트",
        error_message="""
이메일 설정이 정상 작동합니다!

✅ SMTP 연결 성공
✅ 인증 성공
✅ 이메일 전송 성공

시스템 준비 완료. 월요일 실전 운영 가능합니다!

---
테스트 일시: 2025-12-26
        """
    )
    
    print("\n✅ 이메일 전송 완료!")
    print("📬 수신함(dbswoql0712@gmail.com)을 확인하세요.")
    print("   (스팸함도 확인해주세요!)")
    
except Exception as e:
    print(f"\n❌ 이메일 전송 실패: {e}")
    print("\n문제 해결:")
    print("1. configs/.env 파일의 EMAIL_PASSWORD 확인")
    print("2. Gmail 앱 비밀번호가 정확한지 확인")
    print("3. 2단계 인증이 활성화되어 있는지 확인")

print("=" * 60)
