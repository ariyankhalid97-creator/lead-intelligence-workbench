@echo off
cd /d "%~dp0"
title Free Lead Finder
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
".venv\Scripts\python.exe" dashboard.py --port 8788
if errorlevel 1 (
  echo.
  echo The dashboard could not start. Make sure Python is installed.
  pause
)

