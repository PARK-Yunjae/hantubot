# hantubot_prod/hantubot/execution/rate_limiter.py
"""
KIS API Rate Limiter - 토큰 버킷 방식
"""
import asyncio
import time
from typing import Optional
from ..reporting.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    토큰 버킷 방식 Rate Limiter
    
    KIS API 초당 요청 제한을 관리합니다.
    - 실전: 초당 20회
    - 모의: 초당 5회 (보수적)
    """
    
    def __init__(self, max_calls: int = 20, period: float = 1.0, name: str = "RateLimiter"):
        """
        Args:
            max_calls: 주기당 최대 호출 횟수
            period: 주기 (초)
            name: Limiter 이름 (로깅용)
        """
        self.max_calls = max_calls
        self.period = period
        self.name = name
        self.calls = []
        self.lock = asyncio.Lock()
        
        logger.info(f"[{self.name}] 초기화: 최대 {max_calls}회/{period}초")
    
    async def acquire(self):
        """토큰 획득 (API 호출 전 반드시 호출)"""
        async with self.lock:
            now = time.time()
            
            # period 이전 호출 제거
            self.calls = [c for c in self.calls if now - c < self.period]
            
            # 한도 초과 시 대기
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    logger.warning(
                        f"[{self.name}] API 호출 한도 도달 ({len(self.calls)}/{self.max_calls}). "
                        f"{sleep_time:.2f}초 대기 중..."
                    )
                    await asyncio.sleep(sleep_time)
                    # 대기 후 가장 오래된 호출 제거
                    self.calls = self.calls[1:]
            
            # 현재 호출 기록
            self.calls.append(time.time())
    
    def get_remaining_calls(self) -> int:
        """남은 호출 가능 횟수 반환"""
        now = time.time()
        self.calls = [c for c in self.calls if now - c < self.period]
        return self.max_calls - len(self.calls)
    
    def reset(self):
        """호출 이력 초기화"""
        self.calls = []
        logger.info(f"[{self.name}] 호출 이력 초기화")


# 전역 Rate Limiter 인스턴스 (Broker에서 사용)
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(is_mock: bool = False) -> RateLimiter:
    """
    전역 Rate Limiter 인스턴스 반환
    
    Args:
        is_mock: 모의투자 여부 (모의는 더 보수적)
    
    Returns:
        RateLimiter 인스턴스
    """
    global _global_rate_limiter
    
    if _global_rate_limiter is None:
        max_calls = 5 if is_mock else 20
        name = "KIS-Mock" if is_mock else "KIS-Live"
        _global_rate_limiter = RateLimiter(max_calls=max_calls, period=1.0, name=name)
    
    return _global_rate_limiter


if __name__ == '__main__':
    # 테스트
    import asyncio
    
    async def test_rate_limiter():
        limiter = RateLimiter(max_calls=3, period=1.0, name="Test")
        
        print("=== Rate Limiter 테스트 ===")
        print(f"설정: 최대 3회/1초\n")
        
        for i in range(5):
            print(f"호출 {i+1} 시작...")
            await limiter.acquire()
            print(f"호출 {i+1} 완료 (남은 횟수: {limiter.get_remaining_calls()})\n")
        
        print("=== 테스트 완료 ===")
    
    asyncio.run(test_rate_limiter())
