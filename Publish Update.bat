@echo off
REM Double-click on your MAIN laptop to send this version of the bot to GitHub.
title Publish Amazon Audit Bot update
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish_update.ps1"
echo.
pause
