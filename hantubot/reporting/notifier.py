# hantubot_prod/hantubot/reporting/notifier.py
import requests
import json
import os
import yaml
from dotenv import load_dotenv
from .logger import get_logger
import datetime

# Initialize logger for this module
logger = get_logger(__name__)

class Notifier:
    """
    다양한 채널(현재 Discord)로 알림 메시지를 전송하는 클래스.
    설정 파일에서 웹훅 URL을 로드하여 사용한다.
    """
    def __init__(self, config_path="configs/config.yaml"):
        # Load environment variables (from .env file)
        load_dotenv() 
        
        # Load configuration from config.yaml
        self._config = self._load_config(config_path)
        
        # Determine Discord settings
        # Prioritize .env for secrets, fallback to config.yaml for enabled flag or if .env is missing.
        self._discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self._discord_enabled = self._config.get('notifications', {}).get('discord', {}).get('enabled', False)
        
        if self._discord_enabled and not self._discord_webhook_url:
            logger.warning("Discord notifications are enabled but DISCORD_WEBHOOK_URL is not set in .env.")
        elif self._discord_enabled:
            logger.info("Discord notifications enabled.")
        else:
            logger.info("Discord notifications disabled in config.yaml.")

    def _load_config(self, config_path):
        """Loads configuration from config.yaml."""
        # Adjust path for loading config from the root of hantubot_prod
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_config_path = os.path.join(base_dir, config_path)
        try:
            with open(full_config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {full_config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file: {e}")
            return {}

    def send_discord_message(self, message: str = None, embed: dict = None):
        """
        Discord 웹훅을 통해 메시지 또는 임베드를 전송합니다.
        message 또는 embed 중 하나는 필수입니다.
        """
        if not self._discord_enabled or not self._discord_webhook_url:
            return

        headers = {'Content-Type': 'application/json'}
        payload = {}

        if message:
            payload['content'] = message
        if embed:
            payload['embeds'] = [embed]
        
        if not payload:
            logger.warning("Attempted to send empty message/embed to Discord. No payload provided.")
            return

        try:
            response = requests.post(self._discord_webhook_url, headers=headers, data=json.dumps(payload))
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            logger.debug(f"Discord message sent successfully. Status: {response.status_code}")
        except requests.exceptions.HTTPError as errh:
            logger.error(f"Discord HTTP Error: {errh} - Response: {errh.response.text}")
        except requests.exceptions.ConnectionError as errc:
            logger.error(f"Discord Connection Error: {errc}")
        except requests.exceptions.Timeout as errt:
            logger.error(f"Discord Timeout Error: {errt}")
        except requests.exceptions.RequestException as err:
            logger.error(f"Discord Request Error: {err}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while sending Discord message: {e}")

    # 향후 Slack 등 다른 알림 채널 확장을 위한 send_slack_message 등 추가 가능
    # 현재는 Discord만 구현합니다.

    def send_alert(self, message: str, level: str = 'info', **kwargs):
        """
        통합된 알림 전송 메서드.
        주요 이벤트를 Discord로 전송하고, 로거에도 기록합니다.
        kwargs를 통해 Discord embed 형식의 추가 정보를 전달할 수 있습니다.
        """
        # 로거에 기록
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(message)

        # Discord로 전송 (embed가 있으면 embed를, 없으면 message를 본문으로)
        # 웹훅 URL이 없거나 비활성화되어 있으면 전송 시도하지 않음
        if self._discord_enabled and self._discord_webhook_url:
            discord_embed = kwargs.get('embed')
            if discord_embed:
                self.send_discord_message(embed=discord_embed)
            else:
                self.send_discord_message(message=message)


if __name__ == '__main__':
    # Notifier 테스트 코드
    # 중요: 실제 테스트를 위해서는 'hantubot_prod/configs/.env' 파일을 생성하고
    # DISCORD_WEBHOOK_URL에 유효한 웹훅 URL을 입력해야 합니다.
    # config.yaml의 'notifications.discord.enabled'를 true로 설정해야 합니다.

    # 임시 .env 파일 경로 설정
    test_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'configs', '.env')
    
    # 임시 .env 파일 생성 및 테스트 실행
    try:
        with open(test_env_path, 'w', encoding='utf-8') as f: # 인코딩 추가
            f.write('DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_TEST_WEBHOOK_URL_HERE"\n')
            f.write('KIS_APP_KEY="test_key"\n')
            f.write('KIS_APP_SECRET="test_secret"\n')
            f.write('KIS_ACCOUNT_NO="test_account"\n')
        
        print(f"Temporary .env created at: {test_env_path}. Please replace YOUR_TEST_WEBHOOK_URL_HERE with a real Discord webhook URL for testing.")

        # Notifier 인스턴스 생성
        notifier = Notifier(config_path=os.path.join('configs', 'config.yaml'))

        # 단순 메시지 전송
        notifier.send_alert("Hantubot 테스트 알림입니다: 정상 작동 확인 (단순 메시지).", level='info')

        # 임베드 메시지 전송 예시 (요구사항에 있는 체결 알림 포맷)
        transaction_embed = {
          "title": "📈 체결 알림",
          "color": 3066993,
          "fields": [
            { "name": "종목", "value": "삼성전자 (005930)", "inline": True },
            { "name": "방향", "value": "매수 (BUY)", "inline": True },
            { "name": "체결 수량", "value": "10주", "inline": False },
            { "name": "체결 단가", "value": "75,200원", "inline": True },
            { "name": "체결 금액", "value": "752,000원", "inline": True }
          ],
          "footer": {
            "text": "전략: momentum_strategy · " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
          }
        }
        notifier.send_alert("체결 알림 발생", level='info', embed=transaction_embed)

        # 에러 알림
        error_embed = {
            "title": "🚨 중요 오류 발생",
            "description": "API 연결에 실패했습니다. 즉시 확인이 필요합니다.",
            "color": 15158332,
            "fields": [
                {"name": "오류 유형", "value": "ConnectionError", "inline": True},
                {"name": "발생 시각", "value": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True},
                {"name": "모듈", "value": "Broker", "inline": False}
            ]
        }
        notifier.send_alert("Critical Error: API 연결 실패!", level='critical', embed=error_embed)

    except Exception as e:
        print(f"An error occurred during notifier test: {e}")
        logger.error(f"Error during notifier test: {e}", exc_info=True)
    finally:
        # 테스트 후 임시 .env 파일 삭제
        if os.path.exists(test_env_path):
            os.remove(test_env_path)
            print(f"Temporary .env file removed: {test_env_path}")
