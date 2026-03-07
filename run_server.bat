@echo off
title Digital Health Record - Server
cd /d "%~dp0"
echo.
echo  Starting Digital Health Record server...
echo  Open in browser: http://127.0.0.1:5000
echo  Login: admin / admin123
echo.
echo  Keep this window open. Close it to stop the server.
echo.
python app.py
pause
