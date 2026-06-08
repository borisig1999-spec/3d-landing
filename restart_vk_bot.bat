@echo off
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
cd /d M:\Sait\3d-landing
start "VK Bot" /min python scripts\vk_bot.py
timeout /t 5 /nobreak >nul
tasklist /FI "WINDOWTITLE eq VK Bot" 2>nul | find "python" >nul && echo VK бот запущен! || echo ОШИБКА: бот не запустился
timeout /t 3 /nobreak >nul
