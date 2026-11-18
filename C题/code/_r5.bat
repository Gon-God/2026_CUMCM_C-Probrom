@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _dbg7.py > _dbg7.log 2>&1
echo EXITCODE=%errorlevel%
