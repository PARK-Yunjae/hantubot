@echo off
REM Hantubot 자동 실행 배치 파일
echo ========================================
echo   Hantubot 자동매매 시스템 시작 중...
echo ========================================
echo.

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM 아나콘다 환경 활성화 시도
if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
    echo [INFO] 아나콘다 환경 활성화 중...
    call "%USERPROFILE%\anaconda3\Scripts\activate.bat" hantubot_env
    goto :run
)

if exist "%USERPROFILE%\Anaconda3\Scripts\activate.bat" (
    echo [INFO] 아나콘다 환경 활성화 중...
    call "%USERPROFILE%\Anaconda3\Scripts\activate.bat" hantubot_env
    goto :run
)

REM venv 환경 활성화 시도
if exist "venv\Scripts\activate.bat" (
    echo [INFO] venv 환경 활성화 중...
    call venv\Scripts\activate.bat
    goto :run
)

REM 환경 없이 실행
echo [WARNING] 가상환경을 찾을 수 없습니다. 기본 Python으로 실행합니다.

:run
echo.
echo [INFO] Hantubot GUI 실행 중...
echo.
python run.py

REM 에러 발생 시 창 유지
if errorlevel 1 (
    echo.
    echo [ERROR] 실행 중 오류가 발생했습니다!
    echo.
    pause
)
