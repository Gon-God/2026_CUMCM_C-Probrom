@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _smoke.py > _smoke.log 2>&1
echo DONE %errorlevel%
