@echo off
cd /d "%~dp0"
python launch.py --stop
if errorlevel 1 pause
