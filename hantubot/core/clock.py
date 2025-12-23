# hantubot_prod/hantubot/core/clock.py
import datetime
import holidays
import yaml
import os
import logging

# Basic logger setup for this module, will be replaced by centralized logger later
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

class MarketClock:
    """
    한국 증시의 개장 시간, 휴장일 등을 관리하고 현재 시각을 기준으로
    거래 가능 여부를 판단하는 클래스.
    """
    def __init__(self, config_path="configs/config.yaml"):
        self._config = self._load_config(config_path)
        self._market_open_time = datetime.time.fromisoformat(self._config['trading_hours']['market_open'])
        self._market_close_time = datetime.time.fromisoformat(self._config['trading_hours']['market_close'])
        self._closing_call_start_time = datetime.time.fromisoformat(self._config['trading_hours']['closing_call_start'])
        self._korean_holidays = holidays.KR()
        logger.info(f"MarketClock initialized. Open: {self._market_open_time}, Close: {self._market_close_time}, Closing Call Start: {self._closing_call_start_time}")

    def _load_config(self, config_path):
        """설정 파일을 로드합니다."""
        # Ensure path is relative to the project root if run from run.py
        # When run from run.py, os.getcwd() will be hantubot_prod/
        # So config_path 'configs/config.yaml' is correct relative path.
        # If run directly as a script within core/, adjust for testing
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_config_path = os.path.join(base_dir, config_path)
        
        try:
            with open(full_config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {full_config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file: {e}")
            raise

    def is_trading_day(self, date: datetime.date = None) -> bool:
        """
        주어진 날짜 또는 오늘이 한국 증시 거래일인지 확인합니다.
        (주말 및 공휴일 제외)
        """
        if date is None:
            date = datetime.date.today()

        if date.weekday() >= 5:  # 0-Monday, 5-Saturday, 6-Sunday
            return False
        if date in self._korean_holidays:
            return False
        return True

    def is_market_open(self, now: datetime.datetime = None) -> bool:
        """
        현재 시각(KST)이 한국 증시 개장 시간 내에 있는지 확인합니다.
        (거래일 여부도 함께 확인)
        """
        if now is None:
            now = datetime.datetime.now() # KST assumed, for production will need explicit timezone

        if not self.is_trading_day(now.date()):
            return False

        current_time = now.time()
        return self._market_open_time <= current_time < self._market_close_time

    def is_market_closing_approach(self, now: datetime.datetime = None) -> bool:
        """
        현재 시각(KST)이 장 마감 동시호가 시작 시간 이후인지 확인합니다.
        (거래일 여부도 함께 확인)
        """
        if now is None:
            now = datetime.datetime.now() # KST assumed

        if not self.is_trading_day(now.date()):
            return False
            
        current_time = now.time()
        return self._closing_call_start_time <= current_time < self._market_close_time

    def get_market_times(self):
        """설정된 시장 시간을 반환합니다."""
        return {
            'open': self._market_open_time,
            'close': self._market_close_time,
            'closing_call_start': self._closing_call_start_time
        }

if __name__ == '__main__':
    # 테스트 코드
    # 이 스크립트를 직접 실행할 경우, config.yaml 경로를 상대적으로 조정합니다.
    # 예: hantubot_prod/hantubot/core 에서 실행 시 -> config_path="../../../configs/config.yaml"
    # hantubot_prod/ 에서 실행 시 -> config_path="configs/config.yaml"
    
    # 현재 작업 디렉토리 기준 'hantubot_prod'의 루트 경로를 찾고, 그 아래 configs/config.yaml 접근
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_script_dir, '..', '..', '..'))
    test_config_path = os.path.join(project_root, 'configs', 'config.yaml')

    clock = MarketClock(config_path=os.path.join('configs', 'config.yaml')) # When run from project root, this path is correct.

    today = datetime.date.today()
    now = datetime.datetime.now() # Assuming system time is KST

    print(f"Today ({today}) is a trading day: {clock.is_trading_day(today)}")
    print(f"Market is open now ({now.time()}): {clock.is_market_open(now)}")
    print(f"Market closing approach now ({now.time()}): {clock.is_market_closing_approach(now)}")

    # 예시 시간으로 테스트 (장 시작 시간)
    test_open_time = datetime.datetime(today.year, today.month, today.day, 9, 0, 1)
    print(f"Market is open at {test_open_time.time()}: {clock.is_market_open(test_open_time)}")

    # 예시 시간으로 테스트 (장 마감 직전)
    test_pre_close_time = datetime.datetime(today.year, today.month, today.day, 15, 29, 59)
    print(f"Market is open at {test_pre_close_time.time()}: {clock.is_market_open(test_pre_close_time)}")
    print(f"Market closing approach at {test_pre_close_time.time()}: {clock.is_market_closing_approach(test_pre_close_time)}")

    # 예시 시간으로 테스트 (장 외 시간)
    test_after_close_time = datetime.datetime(today.year, today.month, today.day, 16, 0, 0)
    print(f"Market is open at {test_after_close_time.time()}: {clock.is_market_open(test_after_close_time)}")
