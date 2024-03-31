@echo off

rem Запись в лог
echo %DATE% %TIME% - Скрипт начал выполнение >> "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt"

rem Запуск Redis в фоновом режиме
start /B redis-server

rem Задержка для дополнительной уверенности, что Redis успел запуститься
timeout /t 5

rem Активация виртуального окружения Python и запуск скрипта в фоновом режиме
& . "C:\Users\lokasan\PycharmProjects\car_number\venv\Scripts\activate.ps1"
Start-Process pythonw.exe -ArgumentList "C:\Users\lokasan\PycharmProjects\car_number\bot.py" -NoNewWindow

rem Деактивация виртуального окружения Python (если это необходимо)
& . "C:\Users\lokasan\PycharmProjects\car_number\venv\Scripts\deactivate.ps1"

rem Запись в лог
echo %DATE% %TIME% - Скрипт завершил выполнение >> "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt"

rem Завершение выполнения скрипта
exit