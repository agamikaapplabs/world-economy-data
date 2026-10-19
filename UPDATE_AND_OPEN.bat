@echo off
setlocal
cd /d "%~dp0"
set MACRO_ARGS=
if /I "%~1"=="--full" set MACRO_ARGS=--force-all
if /I "%~1"=="full" set MACRO_ARGS=--force-all
echo ==============================================================
echo World Economy Cockpit V5
echo Raw collection - canonical history - current views - report
echo ==============================================================
echo.
echo [1/6] Markets...
python fetch_markets.py
echo.
echo [2/6] Macro...
python fetch_macro.py %MACRO_ARGS%
echo.
echo [3/6] Resources...
python fetch_resources.py
echo.
echo [4/6] India activity...
python fetch_india_activity.py
echo.
echo [5/6] Publish V5...
python publish_v5.py
if errorlevel 1 exit /b 1
echo.
echo [6/6] Validate...
python validate_data.py
if errorlevel 1 pause & exit /b 1
start "World Economy Cockpit V5 Server" /min python serve.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765/
