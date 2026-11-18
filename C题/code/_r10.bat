@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _dbg10.py > _dbg10.log 2>&1
echo EXITCODE=%errorlevel%
