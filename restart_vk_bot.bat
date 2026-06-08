@echo off
taskkill /F /IM python.exe /T >nul 2>&1
ping 127.0.0.1 -n 3 >nul
start "" /min python M:\Sait\3d-landing\scripts\vk_bot.py
echo VK бот запущен!
ping 127.0.0.1 -n 5 >nul
