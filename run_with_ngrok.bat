@echo off
title Digital Health Record - Run with ngrok (access from anywhere)
cd /d "%~dp0"
echo.
echo  STEP 1: This window runs the app. Keep it open.
echo.
echo  STEP 2: Open a NEW Command Prompt or PowerShell and run:
echo.
echo      ngrok http 5000
echo.
echo  STEP 3: Copy the https URL from ngrok (e.g. https://xxxx.ngrok-free.app)
echo          Open that URL in your browser. QR codes will then work from any network.
echo.
echo  --- Install ngrok on Windows (if needed) ---
echo      winget install ngrok.ngrok
echo  Or download from: https://ngrok.com/download
echo  Sign up free and add token: ngrok config add-authtoken YOUR_TOKEN
echo.
python app.py
pause
