# hantubot_prod/hantubot/reporting/logger.py
import logging
import os
import yaml
from datetime import datetime
import json
from logging.handlers import RotatingFileHandler

class CustomLogger:
    def __init__(self, name="hantubot", config_path="configs/config.yaml"):
        self.logger = logging.getLogger(name)
        # 중요: 중복 핸들러 추가 방지를 위해 기존 핸들러를 초기화합니다.
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
            
        self._load_config(config_path)

    def _load_config(self, config_path):
        """Loads logging configuration from config.yaml."""
        # run.py가 프로젝트 루트에서 실행된다고 가정하고 경로를 구성합니다.
        # 즉, configs/config.yaml 경로는 hantubot_prod/configs/config.yaml 입니다.
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_config_path = os.path.join(base_dir, config_path)

        try:
            with open(full_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Set logging level
            log_level_str = config.get('logging', {}).get('level', 'INFO').upper()
            self.logger.setLevel(getattr(logging, log_level_str, logging.INFO))

            # Create log directory if it doesn't exist
            log_directory = config.get('logging', {}).get('directory', 'logs')
            self.log_path = os.path.join(base_dir, log_directory)
            os.makedirs(self.log_path, exist_ok=True)

            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(console_handler)

            # Rotating File handler (10MB, 5 backups)
            current_date_str = datetime.now().strftime('%Y-%m-%d')
            file_name = f"{self.logger.name}_{current_date_str}.log"
            rotating_handler = RotatingFileHandler(
                os.path.join(self.log_path, file_name),
                maxBytes=10485760,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            rotating_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
            self.logger.addHandler(rotating_handler)
            
            # Level-specific file handlers (WARNING, ERROR, CRITICAL)
            # WARNING 이상 로그만 별도 파일에 저장
            warning_handler = RotatingFileHandler(
                os.path.join(self.log_path, f"{self.logger.name}_WARNING_{current_date_str}.log"),
                maxBytes=5242880,  # 5MB
                backupCount=3,
                encoding='utf-8'
            )
            warning_handler.setLevel(logging.WARNING)
            warning_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
            self.logger.addHandler(warning_handler)
            
            # ERROR 이상 로그만 별도 파일에 저장
            error_handler = RotatingFileHandler(
                os.path.join(self.log_path, f"{self.logger.name}_ERROR_{current_date_str}.log"),
                maxBytes=5242880,  # 5MB
                backupCount=3,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s - %(exc_info)s'))
            self.logger.addHandler(error_handler)

        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {full_config_path}")
            # Fallback to basic console logging if config not found
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing configuration file: {e}")
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def get_logger(self) -> logging.Logger:
        return self.logger

# Global logger instance (singleton pattern)
_hantubot_logger_instance = None
_email_handler_added = False

def get_logger(name="hantubot") -> logging.Logger:
    """
    애플리케이션 전반에서 사용할 로거 인스턴스를 반환합니다.
    최초 호출 시 로거를 초기화하고, 이후에는 기존 인스턴스를 반환합니다.
    name 인자는 로거의 하위 모듈 이름을 지정하는 데 사용됩니다.
    """
    global _hantubot_logger_instance, _email_handler_added
    if _hantubot_logger_instance is None:
        # Initial call sets up the root logger configuration
        _hantubot_logger_instance = CustomLogger("hantubot_root").get_logger()
        
        # EmailHandler 추가 (CRITICAL 로그를 이메일로 발송)
        if not _email_handler_added:
            try:
                from ..utils.email_alert import EmailHandler
                email_handler = EmailHandler()
                email_handler.setLevel(logging.CRITICAL)
                _hantubot_logger_instance.addHandler(email_handler)
                _email_handler_added = True
                _hantubot_logger_instance.info("✅ 이메일 알림 핸들러 추가 완료 (CRITICAL 로그)")
            except ImportError:
                _hantubot_logger_instance.warning("⚠️ EmailHandler를 불러올 수 없습니다 (email_alert.py 확인)")
            except Exception as e:
                _hantubot_logger_instance.warning(f"⚠️ EmailHandler 추가 실패: {e}")
    
    # Return a named logger that inherits settings from the root logger
    return logging.getLogger(name)

class JsonFormatter(logging.Formatter):
    """
    로그 레코드를 JSON 문자열로 포맷합니다.
    """
    def format(self, record):
        # 실제 메시지는 dict 형태일 것으로 예상합니다.
        log_obj = record.msg if isinstance(record.msg, dict) else {'message': record.getMessage()}
        
        # 표준 로그 정보 추가
        log_obj['timestamp'] = self.formatTime(record, self.datefmt)
        log_obj['level'] = record.levelname
        log_obj['name'] = record.name

        return json.dumps(log_obj, ensure_ascii=False)

def get_data_logger(name: str, log_dir: str = 'logs') -> logging.Logger:
    """
    정형화된 데이터(JSONL 형식)를 위한 로거를 생성합니다.
    """
    data_logger = logging.getLogger(name)
    data_logger.propagate = False # 루트 로거로 전파하지 않음
    data_logger.setLevel(logging.INFO)

    # 중복 방지를 위해 기존 핸들러 제거
    if data_logger.hasHandlers():
        data_logger.handlers.clear()

    # 로그 디렉토리 생성
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    full_log_path = os.path.join(base_dir, log_dir)
    os.makedirs(full_log_path, exist_ok=True)
    
    # JSONL 파일 핸들러
    current_date_str = datetime.now().strftime('%Y-%m-%d')
    file_name = f"{name}_{current_date_str}.jsonl"
    file_handler = logging.FileHandler(os.path.join(full_log_path, file_name), encoding='utf-8')
    file_handler.setFormatter(JsonFormatter())
    
    data_logger.addHandler(file_handler)
    return data_logger

if __name__ == '__main__':
    # 일반 로거 테스트
    logger = get_logger("test_module")
    logger.info("This is a standard log message.")

    # 데이터 로거 테스트
    trades_logger = get_data_logger("trades")
    trade_record = {
        'order_id': 'order_123',
        'symbol': '005930',
        'side': 'buy',
        'filled_quantity': 10,
        'fill_price': 75000
    }
    trades_logger.info(trade_record)
    
    signals_logger = get_data_logger("signals")
    signal_record = {
        'strategy_id': 'momentum_01',
        'symbol': '000660',
        'side': 'buy',
        'reason': 'Price spike 2.5%'
    }
    signals_logger.info(signal_record)
    
    print("Log tests finished. Check 'logs' directory for trades_YYYY-MM-DD.jsonl and signals_YYYY-MM-DD.jsonl")
