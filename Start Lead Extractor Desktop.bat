@echo off
cd /d "%~dp0"
title Lead Extractor Desktop
if not exist "node_modules\electron\dist\electron.exe" (
  echo Installing the local desktop shell once...
  call npm install
  if errorlevel 1 (
    echo.
    echo Electron could not be installed. The original Start Dashboard.bat still works.
    pause
    exit /b 1
  )
)
start "" "node_modules\electron\dist\electron.exe" "."

