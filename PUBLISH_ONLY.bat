@echo off
cd /d "%~dp0"
python publish_v5.py
python validate_data.py
pause
