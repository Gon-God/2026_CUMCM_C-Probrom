@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _dbg6b.py > _dbg6b.log 2>&1
echo EXITCODE=%errorlevel%
