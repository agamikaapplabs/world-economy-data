@echo off
cd /d "%~dp0"
echo Rebuilding full market history...
python fetch_markets.py --full-history
pause
