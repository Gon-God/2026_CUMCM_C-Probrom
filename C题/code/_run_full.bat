@echo off
chcp 65001 >nul
cd /d "%~dp0"
python run_all.py > _run_full.log 2>&1
echo EXITCODE=%errorlevel%
