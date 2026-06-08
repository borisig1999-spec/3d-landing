@echo off
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
cd /d M:\Sait\3d-landing
start /min python scripts\tg_bot.py
echo Telegram бот перезапущен!
timeout /t 3 /nobreak >nul
