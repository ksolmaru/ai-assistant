@echo off
cd /d "%~dp0"
setlocal

if not exist "venv\Scripts\activate.bat" (
  echo [ERROR] venv^가 없습니다. 먼저 venv 생성/설치를 진행해주세요.
  echo 예: python -m venv venv ^&^& venv\Scripts\activate ^&^& pip install -r requirements.txt
  pause
  exit /b 1
)

call venv\Scripts\activate.bat

rem 서버 준비 완료를 감지하면 브라우저 자동 오픈(백그라운드)
start "" /B powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:5000/' -TimeoutSec 2 ^| Out-Null; Start-Process 'http://localhost:5000/'; exit 0}catch{Start-Sleep -Seconds 1}} exit 1"

python app.py

pause
