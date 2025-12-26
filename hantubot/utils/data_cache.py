# hantubot_prod/hantubot/utils/data_cache.py
"""
데이터 캐싱 시스템
- 일봉 데이터, API 응답 등을 메모리에 캐싱
- TTL(Time To Live) 기반 자동 만료
- 메모리 사용량 제한
"""
import time
from typing import Any, Optional, Dict, Callable
from functools import wraps
from collections import OrderedDict
import threading


class TTLCache:
    """
    TTL (Time To Live) 기반 캐시
    
    특징:
    - 시간 기반 자동 만료
    - LRU (Least Recently Used) 방식
    - 스레드 안전
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: float = 3600):
        """
        Args:
            max_size: 최대 캐시 항목 수
            ttl_seconds: 캐시 유효 시간 (초)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()
        
        # 통계
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """캐시에서 값 조회"""
        with self._lock:
            # 키 존재 확인
            if key not in self._cache:
                self.misses += 1
                return None
            
            # 만료 확인
            if self._is_expired(key):
                self._remove(key)
                self.misses += 1
                return None
            
            # LRU: 최근 사용으로 이동
            self._cache.move_to_end(key)
            self.hits += 1
            return self._cache[key]
    
    def set(self, key: str, value: Any):
        """캐시에 값 저장"""
        with self._lock:
            # 이미 존재하면 업데이트
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
                self._timestamps[key] = time.time()
                return
            
            # 크기 제한 확인
            if len(self._cache) >= self.max_size:
                # 가장 오래된 항목 제거
                oldest_key = next(iter(self._cache))
                self._remove(oldest_key)
            
            # 새 항목 추가
            self._cache[key] = value
            self._timestamps[key] = time.time()
    
    def _is_expired(self, key: str) -> bool:
        """만료 여부 확인"""
        if key not in self._timestamps:
            return True
        
        age = time.time() - self._timestamps[key]
        return age > self.ttl_seconds
    
    def _remove(self, key: str):
        """캐시에서 항목 제거"""
        if key in self._cache:
            del self._cache[key]
        if key in self._timestamps:
            del self._timestamps[key]
    
    def clear(self):
        """캐시 전체 삭제"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self.hits = 0
            self.misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회"""
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': round(hit_rate, 2),
                'ttl_seconds': self.ttl_seconds
            }
    
    def cleanup_expired(self):
        """만료된 항목 정리"""
        with self._lock:
            expired_keys = [
                key for key in self._cache 
                if self._is_expired(key)
            ]
            
            for key in expired_keys:
                self._remove(key)
            
            return len(expired_keys)


# 전역 캐시 인스턴스
_price_cache = TTLCache(max_size=500, ttl_seconds=60)  # 가격: 1분
_daily_data_cache = TTLCache(max_size=200, ttl_seconds=3600)  # 일봉: 1시간
_api_cache = TTLCache(max_size=1000, ttl_seconds=300)  # API: 5분


def cached(cache_instance: TTLCache = None, key_func: Callable = None):
    """
    함수 결과를 캐싱하는 데코레이터
    
    Args:
        cache_instance: 사용할 캐시 인스턴스
        key_func: 캐시 키 생성 함수
    
    Example:
        @cached(cache_instance=_price_cache)
        def get_current_price(symbol):
            return api_call(symbol)
    """
    if cache_instance is None:
        cache_instance = _api_cache
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 캐시 키 생성
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 기본: 함수명 + 인자
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 캐시 조회
            cached_value = cache_instance.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 함수 실행
            result = func(*args, **kwargs)
            
            # 결과 캐싱
            if result is not None:
                cache_instance.set(cache_key, result)
            
            return result
        
        return wrapper
    return decorator


def get_cache_stats() -> Dict[str, Dict]:
    """모든 캐시 통계 조회"""
    return {
        'price_cache': _price_cache.get_stats(),
        'daily_data_cache': _daily_data_cache.get_stats(),
        'api_cache': _api_cache.get_stats()
    }


def clear_all_caches():
    """모든 캐시 초기화"""
    _price_cache.clear()
    _daily_data_cache.clear()
    _api_cache.clear()


def cleanup_all_caches():
    """모든 캐시의 만료 항목 정리"""
    expired_counts = {
        'price_cache': _price_cache.cleanup_expired(),
        'daily_data_cache': _daily_data_cache.cleanup_expired(),
        'api_cache': _api_cache.cleanup_expired()
    }
    return expired_counts


if __name__ == '__main__':
    # 테스트
    print("=== 데이터 캐싱 시스템 테스트 ===\n")
    
    # 테스트 1: 기본 캐시 사용
    cache = TTLCache(max_size=3, ttl_seconds=2)
    
    print("테스트 1: 기본 캐시")
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    print(f"key1: {cache.get('key1')}")
    print(f"key2: {cache.get('key2')}")
    print(f"key3 (없음): {cache.get('key3')}")
    print(f"통계: {cache.get_stats()}\n")
    
    # 테스트 2: TTL 만료
    print("테스트 2: TTL 만료 (2초 대기)")
    time.sleep(2.1)
    print(f"key1 (만료됨): {cache.get('key1')}")
    print(f"통계: {cache.get_stats()}\n")
    
    # 테스트 3: LRU (크기 제한)
    print("테스트 3: LRU (최대 3개)")
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    print(f"a, b, c 저장: {cache.get_stats()['size']}개")
    cache.set("d", 4)  # a가 제거됨
    print(f"d 추가 후: {cache.get_stats()['size']}개")
    print(f"a (제거됨): {cache.get('a')}")
    print(f"d: {cache.get('d')}\n")
    
    # 테스트 4: 데코레이터
    print("테스트 4: 캐싱 데코레이터")
    
    call_count = 0
    
    @cached(cache_instance=TTLCache(max_size=10, ttl_seconds=5))
    def expensive_function(x):
        global call_count
        call_count += 1
        print(f"  실제 함수 호출 (call_count={call_count})")
        return x * 2
    
    print(f"첫 호출: {expensive_function(5)}")
    print(f"두번째 호출 (캐시): {expensive_function(5)}")
    print(f"다른 인자: {expensive_function(10)}")
    print(f"총 실제 호출 횟수: {call_count}\n")
    
    # 테스트 5: 전역 캐시 통계
    print("테스트 5: 전역 캐시 통계")
    stats = get_cache_stats()
    for name, stat in stats.items():
        print(f"{name}: {stat}")
    
    print("\n=== 테스트 완료 ===")
