@echo off
REM Double-click to get the latest version of the bot from GitHub.
REM Your settings, history, templates and Amazon login are kept.
title Update Amazon Audit Bot
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
echo.
pause
