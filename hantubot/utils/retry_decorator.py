# hantubot_prod/hantubot/utils/retry_decorator.py
"""
API 호출 재시도 데코레이터
- 일시적 네트워크 오류, 타임아웃 등 자동 재시도
- 지수 백오프 (exponential backoff) 지원
"""
import time
import logging
from functools import wraps
from typing import Callable, Any, Tuple, Type

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = 3, 
                    delay: float = 1.0, 
                    exponential_backoff: bool = True,
                    exceptions: Tuple[Type[Exception], ...] = (Exception,),
                    on_final_failure: Callable[[Exception], None] = None):
    """
    API 호출 실패 시 자동 재시도 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        delay: 초기 지연 시간 (초)
        exponential_backoff: 지수 백오프 사용 여부 (True: 1s, 2s, 4s...)
        exceptions: 재시도할 예외 타입들
        on_final_failure: 최종 실패 시 호출할 콜백 함수
    
    Example:
        @retry_on_failure(max_retries=3, delay=1)
        def get_current_price(symbol):
            return broker.get_price(symbol)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                
                except exceptions as e:
                    # 마지막 시도면 예외 발생
                    if attempt == max_retries - 1:
                        logger.error(
                            f"❌ {func.__name__} 최종 실패 "
                            f"(재시도 {max_retries}회): {e}"
                        )
                        
                        # 최종 실패 콜백 실행
                        if on_final_failure:
                            try:
                                on_final_failure(e)
                            except Exception as callback_error:
                                logger.error(f"콜백 실행 실패: {callback_error}")
                        
                        raise
                    
                    # 재시도 로직
                    wait_time = delay * (2 ** attempt) if exponential_backoff else delay
                    logger.warning(
                        f"⚠️ {func.__name__} 실패 "
                        f"(재시도 {attempt + 1}/{max_retries}): {e}"
                    )
                    logger.info(f"⏳ {wait_time:.1f}초 후 재시도...")
                    time.sleep(wait_time)
            
            # 여기 도달하면 안되지만 안전장치
            raise RuntimeError(f"{func.__name__} 최대 재시도 횟수 초과")
        
        return wrapper
    return decorator


def retry_with_timeout(max_retries: int = 3,
                      timeout: float = 10.0,
                      delay: float = 1.0):
    """
    타임아웃 + 재시도 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        timeout: 타임아웃 시간 (초)
        delay: 재시도 지연 (초)
    
    Note: 이 데코레이터는 타임아웃 기능이 필요한 경우에만 사용
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"{func.__name__} 타임아웃 ({timeout}초)")
            
            for attempt in range(max_retries):
                try:
                    # 타임아웃 설정 (Unix 계열만 지원)
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(int(timeout))
                    
                    try:
                        result = func(*args, **kwargs)
                    finally:
                        signal.alarm(0)  # 타임아웃 해제
                    
                    return result
                
                except (TimeoutError, Exception) as e:
                    if attempt == max_retries - 1:
                        logger.error(f"❌ {func.__name__} 최종 실패: {e}")
                        raise
                    
                    logger.warning(f"⚠️ {func.__name__} 재시도 {attempt + 1}/{max_retries}")
                    time.sleep(delay)
            
            raise RuntimeError(f"{func.__name__} 최대 재시도 횟수 초과")
        
        return wrapper
    return decorator


# 사전 정의된 재시도 데코레이터들
def retry_api_call(func: Callable) -> Callable:
    """API 호출용 재시도 (3회, 1초 간격, 지수 백오프)"""
    return retry_on_failure(
        max_retries=3,
        delay=1.0,
        exponential_backoff=True
    )(func)


def retry_network_call(func: Callable) -> Callable:
    """네트워크 호출용 재시도 (5회, 0.5초 간격)"""
    return retry_on_failure(
        max_retries=5,
        delay=0.5,
        exponential_backoff=True
    )(func)


def retry_critical_call(func: Callable) -> Callable:
    """중요 호출용 재시도 (3회, 2초 간격, 실패 시 이메일)"""
    def send_failure_email(error: Exception):
        """실패 시 이메일 발송"""
        try:
            from ..utils.email_alert import send_critical_alert
            send_critical_alert(
                title=f"API 호출 최종 실패: {func.__name__}",
                error_message=str(error)
            )
        except Exception as e:
            logger.error(f"이메일 발송 실패: {e}")
    
    return retry_on_failure(
        max_retries=3,
        delay=2.0,
        exponential_backoff=True,
        on_final_failure=send_failure_email
    )(func)


if __name__ == '__main__':
    # 테스트
    import random
    
    print("=== Retry 데코레이터 테스트 ===\n")
    
    # 테스트 1: 성공 케이스
    @retry_on_failure(max_retries=3, delay=0.1)
    def test_success():
        """항상 성공하는 함수"""
        print("✅ 성공!")
        return "OK"
    
    print("테스트 1: 성공 케이스")
    result = test_success()
    print(f"결과: {result}\n")
    
    # 테스트 2: 재시도 후 성공
    attempt_count = 0
    
    @retry_on_failure(max_retries=3, delay=0.1, exponential_backoff=False)
    def test_retry_success():
        """2번 실패 후 성공"""
        global attempt_count
        attempt_count += 1
        print(f"시도 {attempt_count}...")
        
        if attempt_count < 3:
            raise ValueError("일시적 오류")
        
        return "성공!"
    
    print("테스트 2: 재시도 후 성공")
    attempt_count = 0
    result = test_retry_success()
    print(f"결과: {result}\n")
    
    # 테스트 3: 최종 실패
    @retry_on_failure(max_retries=2, delay=0.1)
    def test_failure():
        """항상 실패하는 함수"""
        raise ConnectionError("연결 실패")
    
    print("테스트 3: 최종 실패")
    try:
        test_failure()
    except ConnectionError as e:
        print(f"예상된 실패: {e}\n")
    
    # 테스트 4: 사전 정의 데코레이터
    @retry_api_call
    def test_api():
        """API 호출 시뮬레이션"""
        if random.random() < 0.7:
            raise TimeoutError("타임아웃")
        return "API 응답"
    
    print("테스트 4: API 재시도")
    try:
        result = test_api()
        print(f"결과: {result}")
    except TimeoutError as e:
        print(f"실패: {e}")
    
    print("\n=== 테스트 완료 ===")
