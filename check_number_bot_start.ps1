# ������ � ���
Add-Content -Path "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt" -Value "$(Get-Date) - ������ ����� ����������"

# ������ Redis � ������� ������
Start-Process "redis-server" -NoNewWindow -PassThru

# �������� ��� �������������� �����������, ��� Redis ����� �����������
Start-Sleep -Seconds 5

# ��������� ������������ ��������� Python � ������ �������
. "C:\Users\lokasan\PycharmProjects\car_number\venv\Scripts\Activate.ps1"
cd C:\Users\lokasan\PycharmProjects\car_number
Start-Process "python.exe" bot.py


# ������ � ���
Add-Content -Path "C:\Users\lokasan\PycharmProjects\car_number\script_log.txt" -Value "$(Get-Date) - ������ �������� ����������"
