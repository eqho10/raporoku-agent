@echo off
title RaporOku Agent - Kurulum
color 0B
echo.
echo  ============================================
echo   RaporOku Agent - Windows Kurulum
echo  ============================================
echo.

:: Kurulum dizini
set INSTALL_DIR=%LOCALAPPDATA%\RaporOku
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Python kontrolü
echo [1/4] Python kontrol ediliyor...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Python bulundu
    set PYTHON=python
    goto :install
)
python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Python3 bulundu
    set PYTHON=python3
    goto :install
)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Py bulundu
    set PYTHON=py
    goto :install
)

echo   [!] Python bulunamadi!
echo.
echo   Python indiriliyor...
echo   Lutfen kurulumda "Add Python to PATH" kutusunu isaretleyin!
echo.
start https://www.python.org/downloads/
echo   Python kurduktan sonra bu dosyayi tekrar calistirin.
pause
exit /b 1

:install
echo [2/4] Dosyalar indiriliyor...
powershell -Command "Invoke-WebRequest -Uri 'https://raporoku.com/static/downloads/raporoku-agent.py' -OutFile '%INSTALL_DIR%\agent.py'" >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!] Indirme hatasi. Internet baglantinizi kontrol edin.
    pause
    exit /b 1
)
echo   [OK] Agent indirildi

echo [3/4] Bagimliliklar kuruluyor...
%PYTHON% -m pip install --quiet pyserial requests >nul 2>&1
echo   [OK] pyserial + requests kuruldu

echo [4/4] Kisayollar olusturuluyor...

:: Başlatıcı .bat
(
echo @echo off
echo title RaporOku Agent
echo cd /d "%INSTALL_DIR%"
echo %PYTHON% agent.py %%*
echo pause
) > "%INSTALL_DIR%\raporoku-agent.bat"

:: Setup .bat
(
echo @echo off
echo title RaporOku Agent - Kurulum Sihirbazi
echo cd /d "%INSTALL_DIR%"
echo %PYTHON% agent.py --setup
echo pause
) > "%INSTALL_DIR%\raporoku-setup.bat"

:: Masaüstü kısayolları
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\RaporOku Agent.lnk'); $s.TargetPath = '%INSTALL_DIR%\raporoku-agent.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'RaporOku Agent'; $s.Save()"
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\RaporOku Kurulum.lnk'); $s.TargetPath = '%INSTALL_DIR%\raporoku-setup.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'RaporOku Kurulum'; $s.Save()"

echo.
echo  ============================================
echo   [OK] Kurulum tamamlandi!
echo  ============================================
echo.
echo   Konum: %INSTALL_DIR%
echo.
echo   Masaustunde 2 kisayol olusturuldu:
echo     1. "RaporOku Kurulum" - Ilk kurulum (cihaz anahtari girin)
echo     2. "RaporOku Agent"   - Normal calistirma
echo.
echo   Ilk once "RaporOku Kurulum" kisayolunu calistirin!
echo.

set /p answer=Simdi kurulum sihirbazini baslatmak ister misiniz? (E/H):
if /i "%answer%"=="E" (
    cd /d "%INSTALL_DIR%"
    %PYTHON% agent.py --setup
)

pause
