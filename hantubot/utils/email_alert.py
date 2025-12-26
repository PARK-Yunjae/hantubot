# hantubot_prod/hantubot/utils/email_alert.py
"""
이메일 알림 시스템 - CRITICAL 로그 및 중요 이벤트 이메일 발송
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Rate limiting을 위한 전역 상태
_email_history: Dict[str, datetime] = {}
_email_count_hourly = 0
_email_count_daily = 0
_last_hour_reset = datetime.now()
_last_day_reset = datetime.now().date()

# 설정값
MAX_EMAILS_PER_HOUR = 10
MAX_EMAILS_PER_DAY = 50
DUPLICATE_THRESHOLD_MINUTES = 10


def _check_rate_limit() -> bool:
    """
    Rate limiting 체크
    
    Returns:
        True: 발송 가능, False: 한도 초과
    """
    global _email_count_hourly, _email_count_daily
    global _last_hour_reset, _last_day_reset
    
    now = datetime.now()
    current_date = now.date()
    
    # 시간당 카운터 리셋
    if (now - _last_hour_reset).total_seconds() >= 3600:
        _email_count_hourly = 0
        _last_hour_reset = now
    
    # 일일 카운터 리셋
    if current_date > _last_day_reset:
        _email_count_daily = 0
        _last_day_reset = current_date
    
    # 한도 체크
    if _email_count_hourly >= MAX_EMAILS_PER_HOUR:
        logger.warning(f"시간당 이메일 한도 초과 ({_email_count_hourly}/{MAX_EMAILS_PER_HOUR})")
        return False
    
    if _email_count_daily >= MAX_EMAILS_PER_DAY:
        logger.warning(f"일일 이메일 한도 초과 ({_email_count_daily}/{MAX_EMAILS_PER_DAY})")
        return False
    
    return True


def _check_duplicate(subject: str) -> bool:
    """
    중복 이메일 체크 (CRITICAL 제외)
    
    Args:
        subject: 이메일 제목
    
    Returns:
        True: 중복, False: 중복 아님
    """
    if "CRITICAL" in subject:
        return False  # CRITICAL은 항상 발송
    
    now = datetime.now()
    
    # 기록 정리 (10분 이상 지난 것)
    keys_to_remove = [
        key for key, timestamp in _email_history.items()
        if (now - timestamp).total_seconds() > DUPLICATE_THRESHOLD_MINUTES * 60
    ]
    for key in keys_to_remove:
        del _email_history[key]
    
    # 중복 체크
    if subject in _email_history:
        last_sent = _email_history[subject]
        if (now - last_sent).total_seconds() < DUPLICATE_THRESHOLD_MINUTES * 60:
            logger.debug(f"중복 이메일 차단: {subject}")
            return True
    
    return False


def send_email(subject: str, message: str, html: bool = False) -> bool:
    """
    Gmail SMTP를 통해 이메일 발송
    
    Args:
        subject: 이메일 제목
        message: 이메일 본문
        html: HTML 형식 여부
    
    Returns:
        True: 성공, False: 실패
    """
    global _email_count_hourly, _email_count_daily
    
    # 환경 변수 확인
    email_enabled = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
    if not email_enabled:
        logger.debug("이메일 알림이 비활성화되어 있습니다 (EMAIL_ENABLED=false)")
        return False
    
    # Rate limiting 체크
    if not _check_rate_limit():
        return False
    
    # 중복 체크
    if _check_duplicate(subject):
        return False
    
    # 설정 가져오기
    smtp_server = os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('EMAIL_SMTP_PORT', '587'))
    sender_email = os.getenv('EMAIL_SENDER')
    sender_password = os.getenv('EMAIL_PASSWORD')
    receiver_email = os.getenv('EMAIL_RECEIVER')
    
    if not all([sender_email, sender_password, receiver_email]):
        logger.error("이메일 설정이 완전하지 않습니다 (EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER 확인)")
        return False
    
    try:
        # 이메일 메시지 구성
        msg = MIMEMultipart('alternative')
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        
        if html:
            part = MIMEText(message, 'html')
        else:
            part = MIMEText(message, 'plain')
        
        msg.attach(part)
        
        # SMTP 연결 및 발송
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        # 발송 기록
        _email_history[subject] = datetime.now()
        _email_count_hourly += 1
        _email_count_daily += 1
        
        logger.info(f"✅ 이메일 발송 성공: {subject} (시간당: {_email_count_hourly}, 일일: {_email_count_daily})")
        return True
    
    except smtplib.SMTPAuthenticationError:
        logger.error("❌ 이메일 인증 실패 - Gmail 앱 비밀번호를 확인하세요")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"❌ SMTP 오류: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 이메일 발송 실패: {e}", exc_info=True)
        return False


def send_critical_alert(title: str, error_message: str, stack_trace: Optional[str] = None) -> bool:
    """
    CRITICAL 오류 이메일 발송
    
    Args:
        title: 오류 제목
        error_message: 오류 메시지
        stack_trace: 스택 트레이스 (선택)
    
    Returns:
        True: 성공, False: 실패
    """
    subject = f"🚨 [Hantubot] CRITICAL: {title}"
    
    body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 CRITICAL ERROR 발생
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

발생 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
오류 유형: {title}

오류 메시지:
{error_message}
"""
    
    if stack_trace:
        body += f"\n\n스택 트레이스:\n{stack_trace}"
    
    body += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hantubot 자동매매 시스템
로그 확인: logs/hantubot_root_{datetime.now().strftime('%Y-%m-%d')}.log
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return send_email(subject, body)


def send_order_failure_alert(symbol: str, symbol_name: str, side: str, 
                             quantity: int, price: int, reason: str, 
                             retry_count: int) -> bool:
    """
    주문 실패 알림 (5회 연속 실패 시)
    
    Args:
        symbol: 종목 코드
        symbol_name: 종목명
        side: 'buy' 또는 'sell'
        quantity: 수량
        price: 가격
        reason: 실패 사유
        retry_count: 재시도 횟수
    
    Returns:
        True: 성공, False: 실패
    """
    if retry_count < 5:
        return False  # 5회 미만은 발송하지 않음
    
    side_kr = "매수" if side == "buy" else "매도"
    subject = f"⚠️ [Hantubot] 주문 실패 ({retry_count}회 연속)"
    
    body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 주문 실패 ({retry_count}회 연속)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

종목: {symbol_name} ({symbol})
주문 유형: {side_kr}
수량: {quantity}주
가격: {price:,}원

실패 사유:
{reason}

재시도 횟수: {retry_count}/{retry_count}
마지막 시도: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
수동 확인 필요
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return send_email(subject, body)


def send_portfolio_alert(current_balance: int, initial_balance: int, 
                        pnl_pct: float, positions: list) -> bool:
    """
    포트폴리오 이상 알림 (-10% 초과)
    
    Args:
        current_balance: 현재 잔고
        initial_balance: 초기 잔고
        pnl_pct: 손익률 (%)
        positions: 보유 종목 리스트
    
    Returns:
        True: 성공, False: 실패
    """
    if pnl_pct > -10.0:
        return False  # -10% 이상은 발송하지 않음
    
    subject = f"⚠️ [Hantubot] 포트폴리오 이상 ({pnl_pct:.1f}%)"
    
    positions_text = "\n".join([
        f"- {pos['symbol']} {pos['name']}: {pos['pnl_pct']:.2f}% ({pos['quantity']}주)"
        for pos in positions
    ])
    
    body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 포트폴리오 손실률 경고
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

현재 잔고: {current_balance:,}원
초기 잔고: {initial_balance:,}원
손익률: {pnl_pct:.2f}%

보유 종목:
{positions_text if positions_text else '(보유 종목 없음)'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
포트폴리오 점검 권장
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return send_email(subject, body)


def send_system_restart_alert(reason: str, restart_count: int, max_restarts: int) -> bool:
    """
    시스템 재시작 알림
    
    Args:
        reason: 재시작 사유
        restart_count: 현재 재시작 횟수
        max_restarts: 최대 재시작 횟수
    
    Returns:
        True: 성공, False: 실패
    """
    subject = f"🔄 [Hantubot] 시스템 재시작 ({restart_count}/{max_restarts})"
    
    body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 시스템 자동 재시작
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

재시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
재시작 횟수: {restart_count}/{max_restarts}

재시작 사유:
{reason}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{"⚠️ 최대 재시작 횟수 근접 - 수동 확인 필요" if restart_count >= max_restarts - 1 else "자동 재시작 진행 중..."}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return send_email(subject, body)


def send_test_email() -> bool:
    """
    이메일 설정 테스트
    
    Returns:
        True: 성공, False: 실패
    """
    subject = "✅ [Hantubot] 이메일 알림 테스트"
    body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 이메일 알림 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

테스트 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

이 이메일이 정상적으로 수신되었다면
Hantubot 이메일 알림 시스템이 정상 작동 중입니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hantubot 자동매매 시스템
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return send_email(subject, body)


# Critical 로그 핸들러 (로깅 시스템과 통합)
class EmailHandler(logging.Handler):
    """
    CRITICAL 레벨 로그를 이메일로 발송하는 핸들러
    """
    def emit(self, record):
        """로그 레코드 처리"""
        try:
            if record.levelno >= logging.CRITICAL:
                # 스택 트레이스 포함
                if record.exc_info:
                    import traceback
                    stack_trace = ''.join(traceback.format_exception(*record.exc_info))
                else:
                    stack_trace = None
                
                send_critical_alert(
                    title=record.name,
                    error_message=record.getMessage(),
                    stack_trace=stack_trace
                )
        except Exception:
            self.handleError(record)


if __name__ == '__main__':
    # 테스트 실행
    print("이메일 알림 시스템 테스트")
    print("=" * 50)
    
    # .env 파일 로드
    from dotenv import load_dotenv
    load_dotenv('configs/.env')
    
    # 테스트 이메일 발송
    result = send_test_email()
    
    if result:
        print("✅ 테스트 이메일 발송 성공!")
        print(f"수신 이메일: {os.getenv('EMAIL_RECEIVER')}")
        print("받은편지함 또는 스팸함을 확인하세요.")
    else:
        print("❌ 테스트 이메일 발송 실패")
        print("configs/.env 파일의 이메일 설정을 확인하세요.")
