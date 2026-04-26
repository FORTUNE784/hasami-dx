@echo off
cd /d %~dp0

call venv\Scripts\activate.bat

python auto_start.py

pause
