taskkill /F /IM python.exe /T
Start-Sleep -Seconds 2
Start-Process -WindowStyle Minimized -FilePath "python" -ArgumentList "M:\Sait\3d-landing\scripts\vk_bot.py" -WorkingDirectory "M:\Sait\3d-landing"
Write-Host "VK бот запущен!"
Start-Sleep -Seconds 3
