@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _find.py > _find.log 2>&1
echo EXITCODE=%errorlevel%
