@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting server at http://127.0.0.1:5000
python app.py
pause
