@echo off
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
cd /d M:\Sait\3d-landing
start /min python scripts\tg_bot.py
timeout /t 2 /nobreak >nul
start /min python scripts\vk_bot.py
echo Оба бота перезапущены!
timeout /t 3 /nobreak >nul
