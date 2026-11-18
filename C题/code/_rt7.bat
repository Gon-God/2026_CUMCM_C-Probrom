@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _t7.py > _t7.log 2>&1
echo EXITCODE=%errorlevel%
