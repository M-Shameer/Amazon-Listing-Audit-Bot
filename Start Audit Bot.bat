@echo off
REM ==============================================================
REM  Starts the Amazon Audit Bot and opens it in your web browser.
REM  The desktop icon "Amazon Audit Bot" runs this file.
REM  To STOP the bot: close the minimised window
REM  "Amazon Audit Bot - close this window to stop".
REM ==============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The bot is not installed on this laptop yet.
    echo Double-click "Install Audit Bot.bat" first.
    echo.
    pause
    exit /b 1
)

REM Already running? Then only open the browser.
netstat -ano | findstr /R /C:":8501 .*LISTENING" >nul
if not errorlevel 1 (
    start "" "http://localhost:8501"
    exit /b 0
)

REM Start the bot in a small minimised window.
start "Amazon Audit Bot - close this window to stop" /min ".venv\Scripts\python.exe" -m streamlit run app.py

REM Wait (up to 60 seconds) until the bot is ready, then open the browser.
set /a tries=0
:wait
timeout /t 1 /nobreak >nul
netstat -ano | findstr /R /C:":8501 .*LISTENING" >nul
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% lss 60 goto wait

echo The bot did not start within 60 seconds.
echo Open the minimised "Amazon Audit Bot" window to see the message.
pause
exit /b 1

:ready
start "" "http://localhost:8501"
exit /b 0
