@echo off

rem ������ � ���
echo %DATE% %TIME% - ������ ����� ���������� >> "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt"

rem ������ Redis � ������� ������
start /B redis-server

rem �������� ��� �������������� �����������, ��� Redis ����� �����������
timeout /t 5

rem ��������� ������������ ��������� Python � ������ ������� � ������� ������
& . "C:\Users\lokasan\PycharmProjects\car_number\venv\Scripts\activate.ps1"
Start-Process pythonw.exe -ArgumentList "C:\Users\lokasan\PycharmProjects\car_number\bot.py" -NoNewWindow

rem ����������� ������������ ��������� Python (���� ��� ����������)
& . "C:\Users\lokasan\PycharmProjects\car_number\venv\Scripts\deactivate.ps1"

rem ������ � ���
echo %DATE% %TIME% - ������ �������� ���������� >> "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt"

rem ���������� ���������� �������
exit