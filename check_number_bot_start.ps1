# Запись в лог
Add-Content -Path "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt" -Value "$(Get-Date) - Скрипт начал выполнение"

# Запуск Redis в фоновом режиме
Start-Process "redis-server" -NoNewWindow -PassThru

# Задержка для дополнительной уверенности, что Redis успел запуститься
Start-Sleep -Seconds 5

# Активация виртуального окружения Python и запуск скрипта
. "C:\Users\lokasan\PycharmProjects\car_number\venv\Scripts\Activate.ps1"
cd C:\Users\lokasan\PycharmProjects\car_number
Start-Process "python.exe" bot.py


# Запись в лог
Add-Content -Path "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt" -Value "$(Get-Date) - Скрипт завершил выполнение"
