@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _t6.py > _t6.log 2>&1
echo EXITCODE=%errorlevel%
