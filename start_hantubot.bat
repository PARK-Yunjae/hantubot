@echo off
chcp 65001 > nul
REM UTF-8 인코딩 설정으로 한글 깨짐 방지

REM Hantubot 자동 실행 배치 파일
echo ========================================
echo   🤖 Hantubot 자동매매 시스템 시작
echo ========================================
echo.

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM venv 환경 활성화
if exist "venv\Scripts\activate.bat" (
    echo [INFO] venv 가상환경 활성화 중...
    call venv\Scripts\activate.bat
) else (
    echo [WARNING] venv 가상환경을 찾을 수 없습니다.
    echo [INFO] 먼저 'python -m venv venv' 명령으로 가상환경을 생성하세요.
    echo.
)

:run
echo.
echo [INFO] Hantubot GUI 실행 중...
echo [INFO] 창을 닫으려면 GUI에서 'Stop Engine'을 먼저 클릭하세요.
echo.
python run.py

REM 에러 발생 시 창 유지
if errorlevel 1 (
    echo.
    echo ========================================
    echo   ❌ 실행 중 오류가 발생했습니다!
    echo ========================================
    echo.
    echo [해결방법]
    echo 1. venv 가상환경이 설치되어 있는지 확인
    echo 2. python -m venv venv 명령으로 가상환경 생성
    echo 3. pip install -r requirements.txt 로 패키지 설치
    echo.
    pause
)
