@echo off
echo ========================================
echo  RaporOku Agent - Windows Build
echo ========================================
echo.

pip install -r requirements.txt

pyinstaller --onefile --name raporoku-agent --icon=icon.ico --console agent.py

echo.
echo Build tamamlandi: dist\raporoku-agent.exe
echo.
pause
