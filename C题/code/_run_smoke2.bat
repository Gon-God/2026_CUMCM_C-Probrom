@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _smoke2.py > _smoke2.log 2>&1
echo DONE %errorlevel%
