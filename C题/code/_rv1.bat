@echo off
chcp 65001 >nul
cd /d "%~dp0"
python _view1.py > _view1.log 2>&1
echo EXITCODE=%errorlevel%
