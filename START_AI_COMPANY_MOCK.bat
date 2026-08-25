@echo off
chcp 65001 >nul
title AI Company OS - Mock Mode
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [오류] Python 실행 환경이 없습니다.
  echo PowerShell에서 py -3.11 -m venv .venv 를 실행한 뒤 의존성을 설치해 주세요.
  pause
  exit /b 1
)

set "DATABASE_URL=sqlite+aiosqlite:///./ai_company_local.db"
set "TASK_EXECUTION_MODE=inline"
set "AUTO_CREATE_SCHEMA=true"
set "AI_PROVIDER=mock"
set "AUTH_ENABLED=false"
set "PUBLIC_BASE_URL=http://127.0.0.1:8000"

echo AI Company OS를 비용 없는 체험 모드로 시작합니다.
echo 브라우저가 자동으로 열리지 않으면 http://127.0.0.1:8000 을 여세요.
echo 프로그램을 종료하려면 이 창에서 Ctrl+C를 누르세요.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo 프로그램이 종료되었습니다.
pause
