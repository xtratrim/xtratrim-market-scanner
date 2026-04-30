@echo off
cd /d "%~dp0"
echo Starting Market Scanner for other devices on your Wi-Fi...
echo.
echo Open this computer's local IP address from another device:
ipconfig | findstr /i "IPv4"
echo.
"C:\Users\PJ Chitolie\AppData\Local\Python\pythoncore-3.14-64\python.exe" app.py --host 0.0.0.0 --port 8787
pause
