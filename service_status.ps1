# RaporOku Agent — Servis Durumu / Yönetim Yardımcısı
#
# Kullanım:
#   powershell -ExecutionPolicy Bypass -File service_status.ps1
#   powershell -ExecutionPolicy Bypass -File service_status.ps1 -Action start
#   powershell -ExecutionPolicy Bypass -File service_status.ps1 -Action stop
#   powershell -ExecutionPolicy Bypass -File service_status.ps1 -Action restart
#   powershell -ExecutionPolicy Bypass -File service_status.ps1 -Action logs

param(
    [ValidateSet("status","start","stop","restart","logs")]
    [string]$Action = "status"
)

$ServiceName = "RaporOkuAgent"
$InstallDir  = "$env:ProgramData\RaporOku"
$NssmExe     = "$InstallDir\nssm.exe"
$StdoutLog   = "$InstallDir\service-stdout.log"

function Need-Admin {
    $u = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $u.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "HATA: Bu komut Yönetici gerektirir." -ForegroundColor Red
        exit 1
    }
}

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

switch ($Action) {
    "status" {
        if (-not $svc) {
            Write-Host "Servis kurulu değil." -ForegroundColor Red
            Write-Host "Kurmak için: install_service.ps1 (Yönetici)" -ForegroundColor Yellow
            exit 1
        }
        Write-Host "Servis     : $($svc.Name)" -ForegroundColor White
        Write-Host "Görünen adı: $($svc.DisplayName)" -ForegroundColor White
        $color = if ($svc.Status -eq "Running") { "Green" } else { "Red" }
        Write-Host "Durum      : $($svc.Status)" -ForegroundColor $color
        Write-Host "Başlangıç  : $($svc.StartType)" -ForegroundColor White
        if (Test-Path $StdoutLog) {
            Write-Host ""
            Write-Host "Son 10 log satırı:" -ForegroundColor Yellow
            Get-Content -Path $StdoutLog -Tail 10
        }
    }
    "start" {
        Need-Admin
        Start-Service -Name $ServiceName
        Write-Host "✓ Başlatıldı" -ForegroundColor Green
    }
    "stop" {
        Need-Admin
        Stop-Service -Name $ServiceName -Force
        Write-Host "✓ Durduruldu" -ForegroundColor Green
    }
    "restart" {
        Need-Admin
        Restart-Service -Name $ServiceName -Force
        Write-Host "✓ Yeniden başlatıldı" -ForegroundColor Green
    }
    "logs" {
        if (-not (Test-Path $StdoutLog)) {
            Write-Host "Log dosyası bulunamadı: $StdoutLog" -ForegroundColor Red
            exit 1
        }
        Write-Host "Son 50 log satırı (Ctrl+C ile çık):" -ForegroundColor Yellow
        Get-Content -Path $StdoutLog -Tail 50 -Wait
    }
}
