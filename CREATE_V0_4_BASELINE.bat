@echo off
setlocal
chcp 65001 >nul
title AI Company OS - Create V0.4 Baseline
cd /d "%~dp0"

if not exist ".git" (
  echo [ERROR] This folder is not a Git repository.
  pause
  exit /b 1
)

set "REPO_PATH=%CD:\=/%"
git config --global --get-all safe.directory | findstr /x /c:"%REPO_PATH%" >nul 2>&1
if errorlevel 1 (
  git config --global --add safe.directory "%REPO_PATH%"
  if errorlevel 1 (
    echo [ERROR] Could not register this folder as a Git safe directory.
    pause
    exit /b 1
  )
)

git status --porcelain >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git still cannot access this repository.
  pause
  exit /b 1
)

git rev-parse -q --verify refs/tags/v0.4-baseline >nul 2>&1
if not errorlevel 1 (
  echo [INFO] The v0.4-baseline tag already exists. No new commit was created.
  git log -1 --oneline --decorate v0.4-baseline
  pause
  exit /b 0
)

git check-ignore -q .env
if errorlevel 1 (
  echo [ERROR] .env is not ignored. Baseline creation stopped.
  pause
  exit /b 1
)

git ls-files --error-unmatch .env >nul 2>&1
if not errorlevel 1 (
  echo [ERROR] .env is already tracked. Baseline creation stopped.
  pause
  exit /b 1
)

git config user.name >nul 2>&1
if errorlevel 1 git config --local user.name "Codex"

git config user.email >nul 2>&1
if errorlevel 1 git config --local user.email "codex@local.invalid"

git add -A
if errorlevel 1 (
  echo [ERROR] Could not stage files.
  pause
  exit /b 1
)

for /f "delims=" %%F in ('git diff --cached --name-only') do (
  if /i "%%F"==".env" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".db" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".sqlite" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".sqlite3" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".dump" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".backup" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".pem" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".key" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".p12" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
  if /i "%%~xF"==".pfx" (
    set "UNSAFE_FILE=%%F"
    goto unsafe
  )
)

git diff --cached --check
if errorlevel 1 (
  echo [ERROR] Git found whitespace errors. Baseline creation stopped.
  pause
  exit /b 1
)

git commit -m "chore: preserve AI Company OS v0.4 baseline"
if errorlevel 1 (
  echo [ERROR] Baseline commit failed.
  pause
  exit /b 1
)

git tag -a v0.4-baseline -m "AI Company OS V0.4 baseline"
if errorlevel 1 (
  echo [ERROR] Baseline tag failed. The commit exists, but the tag was not created.
  pause
  exit /b 1
)

echo.
echo [SUCCESS] V0.4 baseline commit and tag were created.
git log -1 --oneline --decorate
echo.
echo Return to Codex and say: baseline complete, continue Phase 1
pause
exit /b 0

:unsafe
echo [ERROR] A sensitive or database file was staged: %UNSAFE_FILE%
echo Baseline creation stopped before commit.
pause
exit /b 1
