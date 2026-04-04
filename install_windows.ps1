# RaporOku Agent — Windows Otomatik Kurulum
# PowerShell ile çalıştır:
#   powershell -ExecutionPolicy Bypass -File install_windows.ps1

$ErrorActionPreference = "Stop"
$AppName = "RaporOku Agent"
$InstallDir = "$env:LOCALAPPDATA\RaporOku"
$AgentUrl = "https://raporoku.com/static/downloads/raporoku-agent.py"
$RequirementsUrl = "https://raporoku.com/static/downloads/requirements.txt"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  $AppName — Otomatik Kurulum" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Python kontrolü
Write-Host "[1/4] Python kontrol ediliyor..." -ForegroundColor Yellow
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") {
            $python = $cmd
            Write-Host "  ✓ $ver bulundu" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Host "  Python 3 bulunamadi!" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Python'u indirin: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Kurulumda 'Add Python to PATH' kutusunu isaretleyin!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Python kurduktan sonra bu scripti tekrar calistirin." -ForegroundColor Yellow
    Read-Host "Devam etmek icin Enter'a basin"
    Start-Process "https://www.python.org/downloads/"
    exit 1
}

# 2. Klasör oluştur
Write-Host "[2/4] Kurulum klasoru olusturuluyor..." -ForegroundColor Yellow
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Write-Host "  ✓ $InstallDir" -ForegroundColor Green

# 3. Dosyaları indir
Write-Host "[3/4] Dosyalar indiriliyor..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $AgentUrl -OutFile "$InstallDir\agent.py" -UseBasicParsing
    Invoke-WebRequest -Uri $RequirementsUrl -OutFile "$InstallDir\requirements.txt" -UseBasicParsing
    Write-Host "  ✓ Agent indirildi" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Indirme hatasi: $_" -ForegroundColor Red
    exit 1
}

# 4. Bağımlılıkları kur
Write-Host "[4/4] Bagimliliklar kuruluyor..." -ForegroundColor Yellow
& $python -m pip install --quiet pyserial requests 2>&1 | Out-Null
Write-Host "  ✓ pyserial + requests kuruldu" -ForegroundColor Green

# Başlatıcı .bat dosyası oluştur
$batContent = @"
@echo off
title RaporOku Agent
cd /d "$InstallDir"
$python agent.py %*
pause
"@
Set-Content -Path "$InstallDir\raporoku-agent.bat" -Value $batContent

# Masaüstü kısayolu
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\RaporOku Agent.lnk")
$Shortcut.TargetPath = "$InstallDir\raporoku-agent.bat"
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "RaporOku Agent - Yazarkasa Z Raporu"
$Shortcut.Save()

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ✓ Kurulum tamamlandi!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Konum: $InstallDir" -ForegroundColor White
Write-Host "  Masaustunde 'RaporOku Agent' kisayolu olusturuldu" -ForegroundColor White
Write-Host ""
Write-Host "  Ilk kurulum icin:" -ForegroundColor Yellow
Write-Host "    raporoku-agent.bat --setup" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Calistirmak icin:" -ForegroundColor Yellow
Write-Host "    raporoku-agent.bat" -ForegroundColor Cyan
Write-Host ""

# Setup sihirbazını başlat
$answer = Read-Host "Simdi kurulum sihirbazini baslatmak ister misiniz? (E/H)"
if ($answer -eq "E" -or $answer -eq "e") {
    & $python "$InstallDir\agent.py" --setup
}

Read-Host "Cikis icin Enter'a basin"
