@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _dbg9.py > _dbg9.log 2>&1
echo EXITCODE=%errorlevel%
