# hantubot_prod/run.py
import sys
import os
from PySide6.QtWidgets import QApplication

# Ensure the project root is in the python path to allow for absolute imports
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now that the path is set, we can import from our application
from hantubot.gui.main_window import MainWindow

def main():
    """
    Main entry point for the Hantubot application with auto-restart on crash.
    Initializes and runs the GUI.
    """
    # Auto-restart 설정
    max_restarts = int(os.getenv('MAX_AUTO_RESTARTS', '3'))
    restart_count = 0
    
    # 로거 초기화 (첫 실행 시)
    from hantubot.reporting.logger import get_logger
    logger = get_logger("hantubot.main")
    
    while restart_count < max_restarts:
        try:
            logger.info(f"Hantubot 시작 (시도: {restart_count + 1}/{max_restarts})")
            
            app = QApplication(sys.argv)
            window = MainWindow()
            window.show()
            exit_code = app.exec()
            
            # 정상 종료 (exit_code = 0)
            if exit_code == 0:
                logger.info("Hantubot 정상 종료")
                sys.exit(0)
            else:
                logger.warning(f"Hantubot 비정상 종료 (exit_code: {exit_code})")
                raise SystemExit(f"Exit code: {exit_code}")
        
        except (KeyboardInterrupt, SystemExit) as e:
            # 사용자 의도적 종료 또는 정상 종료
            logger.info(f"Hantubot 종료: {e}")
            sys.exit(0)
        
        except Exception as e:
            restart_count += 1
            logger.critical(f"프로그램 크래시 (재시작 {restart_count}/{max_restarts}): {e}", exc_info=True)
            
            # 이메일 알림 (선택사항)
            try:
                from hantubot.utils.email_alert import send_system_restart_alert
                send_system_restart_alert(
                    reason=str(e),
                    restart_count=restart_count,
                    max_restarts=max_restarts
                )
            except Exception as email_error:
                logger.warning(f"이메일 알림 실패: {email_error}")
            
            if restart_count < max_restarts:
                import time
                wait_seconds = 5
                logger.info(f"{wait_seconds}초 후 자동 재시작... ({restart_count}/{max_restarts})")
                time.sleep(wait_seconds)
            else:
                logger.critical(f"최대 재시작 횟수({max_restarts})에 도달했습니다. 프로그램을 종료합니다.")
                sys.exit(1)
    
    # 최대 재시작 횟수 초과
    logger.critical("최대 재시작 횟수 초과 - 프로그램 종료")
    sys.exit(1)

if __name__ == "__main__":
    main()
