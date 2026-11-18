@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _dbg8.py > _dbg8.log 2>&1
echo EXITCODE=%errorlevel%
