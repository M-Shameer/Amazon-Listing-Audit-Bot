@echo off
REM ==============================================================
REM  Double-click this file ONCE on each laptop to install the bot.
REM  It runs install.ps1 (no PowerShell settings need changing).
REM ==============================================================
title Install Amazon Audit Bot
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"

echo.
echo You can close this window.
pause
