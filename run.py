# hantubot_prod/run.py
import sys
import os
import tempfile
# import psutil  # 프로세스 확인용 (psutil 대신 os.kill 사용으로 변경됨)
from PySide6.QtWidgets import QApplication

# Ensure the project root is in the python path to allow for absolute imports
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now that the path is set, we can import from our application
from hantubot.gui.main_window import MainWindow

# Lock File 경로 설정 (temp 디렉토리 사용)
LOCK_FILE_PATH = os.path.join(tempfile.gettempdir(), 'hantubot.lock')

def is_instance_running():
    """
    Lock 파일을 확인하여 이미 실행 중인 인스턴스가 있는지 확인합니다.
    - 파일이 없으면: 실행 중 아님
    - 파일이 있으면: PID를 읽어서 실제 프로세스가 살아있는지 확인
    """
    if os.path.exists(LOCK_FILE_PATH):
        try:
            with open(LOCK_FILE_PATH, 'r') as f:
                pid = int(f.read().strip())
            
            # 윈도우/리눅스 호환 프로세스 체크
            # psutil을 쓰지 않고 os.kill(pid, 0)을 사용 (0은 시그널을 보내지 않고 에러만 체크)
            # 윈도우에서는 해당 PID가 없으면 OSError 발생
            try:
                os.kill(pid, 0)
            except OSError:
                # 프로세스가 없으면 좀비 파일이므로 삭제하고 False 반환
                os.remove(LOCK_FILE_PATH)
                return False
            else:
                # 프로세스가 살아있음
                return True
        except (ValueError, FileNotFoundError):
            # 파일 내용이 깨졌거나 읽기 실패 시 삭제
            if os.path.exists(LOCK_FILE_PATH):
                os.remove(LOCK_FILE_PATH)
            return False
    return False

def create_lock_file():
    """현재 프로세스의 PID로 Lock 파일을 생성합니다."""
    with open(LOCK_FILE_PATH, 'w') as f:
        f.write(str(os.getpid()))

def remove_lock_file():
    """Lock 파일을 삭제합니다."""
    if os.path.exists(LOCK_FILE_PATH):
        try:
            os.remove(LOCK_FILE_PATH)
        except OSError:
            pass

def main():
    """
    Main entry point for the Hantubot application with auto-restart on crash.
    Initializes and runs the GUI.
    """
    # [Hotfix] 중복 실행 방지
    # 로거 초기화 전에 간단히 체크 (로거 초기화 자체가 무거울 수 있음)
    if is_instance_running():
        print(f"이미 Hantubot이 실행 중입니다. (Lock file found at {LOCK_FILE_PATH})")
        print("중복 실행을 방지하기 위해 종료합니다.")
        sys.exit(1)
        
    create_lock_file()

    # Auto-restart 설정
    max_restarts = int(os.getenv('MAX_AUTO_RESTARTS', '3'))
    restart_count = 0
    
    # 로거 초기화 (첫 실행 시)
    from hantubot.reporting.logger import get_logger
    logger = get_logger("hantubot.main")
    
    try:
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
                    break  # 루프 탈출
                else:
                    logger.warning(f"Hantubot 비정상 종료 (exit_code: {exit_code})")
                    raise SystemExit(f"Exit code: {exit_code}")
            
            except (KeyboardInterrupt, SystemExit) as e:
                # 사용자 의도적 종료 또는 정상 종료
                logger.info(f"Hantubot 종료: {e}")
                break  # 루프 탈출
            
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
    
    finally:
        # 프로그램 종료 시 Lock 파일 삭제
        remove_lock_file()
        
    # 최대 재시작 횟수 초과 등으로 루프를 빠져나온 경우
    if restart_count >= max_restarts:
        logger.critical("최대 재시작 횟수 초과 - 프로그램 종료")
        sys.exit(1)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
