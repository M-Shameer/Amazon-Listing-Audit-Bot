@echo off
REM ==============================================================
REM  Double-click to make a small .zip copy of the bot for another
REM  laptop. Your Amazon login profile is NEVER included.
REM ==============================================================
title Make a portable copy of the Amazon Audit Bot
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_portable_copy.ps1"

echo.
pause
