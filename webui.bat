@echo off
REM ============================================================
REM  viralens - one-click launcher (Windows)
REM  Double-click this file. It opens the viralens control panel
REM  in your browser. On first run it installs the dependencies
REM  needed for fetching/analysis. Everything runs locally on
REM  your PC (the UI binds to 127.0.0.1 only); nothing is uploaded.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- find Python 3 ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [!] Python 3.10+ was not found.
    echo     Install it from https://www.python.org/downloads/
    echo     and tick "Add Python to PATH", then run this again.
    pause
    exit /b 1
)

REM --- one-time: install fetch/analysis dependencies ---
if not exist ".viralens_deps_ok" (
    echo [*] First run: installing dependencies ^(one-time, needs internet^)...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [!] Dependency install failed. The UI will still open, but
        echo     fetching/analysis may not work until dependencies install.
    ) else (
        echo done> ".viralens_deps_ok"
    )
)

echo [*] Starting viralens - your browser will open automatically...
%PY% scripts\app.py
pause
