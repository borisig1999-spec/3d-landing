@echo off
echo Перезапуск обоих ботов...

taskkill /F /IM pythonw.exe /T >nul 2>&1
ping 127.0.0.1 -n 3 >nul

echo Запуск VK бота...
start "" /min "C:\Program Files\Python311\pythonw.exe" M:\Sait\3d-landing\scripts\vk_bot.py

echo Запуск Telegram бота...
start "" /min "C:\Program Files\Python311\pythonw.exe" M:\Sait\3d-landing\scripts\tg_bot.py

echo Готово!
ping 127.0.0.1 -n 5 >nul
