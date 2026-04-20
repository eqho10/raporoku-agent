# RaporOku Agent — Servisi Kaldır
#
# Kullanım (Yönetici):
#   powershell -ExecutionPolicy Bypass -File uninstall_service.ps1
#
# Servisi durdurur, NSSM registry kaydını kaldırır.
# Config (~/.raporoku/) ve log dosyaları DOKUNULMAZ.

$ErrorActionPreference = "Stop"
$ServiceName = "RaporOkuAgent"
$InstallDir  = "$env:ProgramData\RaporOku"
$NssmExe     = "$InstallDir\nssm.exe"

$currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "HATA: Yönetici olarak çalıştırın." -ForegroundColor Red
    Read-Host "Çıkış için Enter"
    exit 1
}

Write-Host ""
Write-Host "RaporOku Agent servisini kaldırıyor..." -ForegroundColor Yellow

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host "  ✓ Servis zaten yok." -ForegroundColor Green
    Read-Host "Çıkış için Enter"
    exit 0
}

if (Test-Path $NssmExe) {
    & $NssmExe stop $ServiceName 2>&1 | Out-Null
    Start-Sleep -Seconds 2
    & $NssmExe remove $ServiceName confirm 2>&1 | Out-Null
} else {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
}

Start-Sleep -Seconds 2
$check = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($check) {
    Write-Host "  ✗ Servis kaldırılamadı (bir reboot gerekebilir)" -ForegroundColor Red
} else {
    Write-Host "  ✓ Servis kaldırıldı" -ForegroundColor Green
}

Write-Host ""
Write-Host "Not: $InstallDir klasörü ve ~/.raporoku config dosyaları silinmedi." -ForegroundColor DarkGray
Write-Host "İsterseniz manuel silebilirsiniz." -ForegroundColor DarkGray
Write-Host ""
Read-Host "Çıkış için Enter"
