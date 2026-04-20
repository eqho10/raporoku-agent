# RaporOku Agent — Windows Service Installer (NSSM)
#
# Kullanım (Yönetici olarak çalıştır):
#   powershell -ExecutionPolicy Bypass -File install_service.ps1
#
# Ne yapar:
#   1. GitHub releases'ten en son raporoku-agent.exe'yi indirir
#   2. NSSM'i indirir
#   3. Windows Service olarak kaydeder (auto-start, LocalSystem)
#   4. İlk kurulum henüz yapılmadıysa setup wizard'ı çalıştırır
#   5. Servisi başlatır
#
# Avantaj: PC yeniden başladığında agent otomatik çalışır, console kapanınca durmaz.

$ErrorActionPreference = "Stop"

# ─── Config ──────────────────────────────────────────
$ServiceName   = "RaporOkuAgent"
$ServiceDisplay = "RaporOku Agent"
$ServiceDesc   = "Yazarkasa Z raporu otomatik yakalayıcı (RaporOku)"
$InstallDir    = "$env:ProgramData\RaporOku"
$AgentExe      = "$InstallDir\raporoku-agent.exe"
$NssmExe       = "$InstallDir\nssm.exe"
$GithubRepo    = "eqho10/raporoku-agent"
$NssmUrl       = "https://nssm.cc/release/nssm-2.24.zip"

# ─── Yönetici kontrol ───────────────────────────────
$currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "HATA: Bu script Yönetici olarak çalıştırılmalı." -ForegroundColor Red
    Write-Host "PowerShell'i 'Yönetici olarak çalıştır' ile açıp tekrar deneyin." -ForegroundColor Yellow
    Read-Host "Çıkış için Enter"
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RaporOku Agent — Servis Kurulumu" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ─── Klasör ─────────────────────────────────────────
Write-Host "[1/6] Kurulum klasörü hazırlanıyor..." -ForegroundColor Yellow
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Write-Host "  ✓ $InstallDir" -ForegroundColor Green

# ─── Agent .exe indir ───────────────────────────────
Write-Host "[2/6] Agent .exe indiriliyor (GitHub releases)..." -ForegroundColor Yellow
try {
    $api = "https://api.github.com/repos/$GithubRepo/releases/latest"
    $release = Invoke-RestMethod -Uri $api -UseBasicParsing -Headers @{ "User-Agent" = "RaporOkuInstaller" }
    $asset = $release.assets | Where-Object { $_.name -eq "raporoku-agent.exe" } | Select-Object -First 1
    if (-not $asset) {
        Write-Host "  ✗ Release'te raporoku-agent.exe bulunamadı" -ForegroundColor Red
        exit 1
    }
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $AgentExe -UseBasicParsing
    Write-Host "  ✓ $($release.tag_name) indirildi ($([math]::Round($asset.size/1MB,1)) MB)" -ForegroundColor Green
} catch {
    Write-Host "  ✗ İndirme hatası: $_" -ForegroundColor Red
    exit 1
}

# ─── NSSM indir ──────────────────────────────────────
Write-Host "[3/6] NSSM indiriliyor..." -ForegroundColor Yellow
if (-not (Test-Path $NssmExe)) {
    $zipPath = "$env:TEMP\nssm.zip"
    $extractPath = "$env:TEMP\nssm-extract"
    try {
        Invoke-WebRequest -Uri $NssmUrl -OutFile $zipPath -UseBasicParsing
        if (Test-Path $extractPath) { Remove-Item -Recurse -Force $extractPath }
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
        $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
        $nssmSource = Get-ChildItem -Path $extractPath -Recurse -Filter "nssm.exe" |
            Where-Object { $_.FullName -match "\\$arch\\" } | Select-Object -First 1
        if (-not $nssmSource) {
            Write-Host "  ✗ nssm.exe arşivde bulunamadı" -ForegroundColor Red
            exit 1
        }
        Copy-Item -Path $nssmSource.FullName -Destination $NssmExe -Force
        Remove-Item -Force $zipPath
        Remove-Item -Recurse -Force $extractPath
        Write-Host "  ✓ NSSM kuruldu ($arch)" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ NSSM indirilemedi: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  ✓ NSSM zaten mevcut" -ForegroundColor Green
}

# ─── Eski servis varsa kaldır ───────────────────────
Write-Host "[4/6] Önceki servis kontrolü..." -ForegroundColor Yellow
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Eski servis durduruluyor..." -ForegroundColor DarkYellow
    & $NssmExe stop $ServiceName 2>&1 | Out-Null
    Start-Sleep -Seconds 2
    & $NssmExe remove $ServiceName confirm 2>&1 | Out-Null
    Write-Host "  ✓ Eski servis kaldırıldı" -ForegroundColor Green
} else {
    Write-Host "  ✓ Önceki servis yok" -ForegroundColor Green
}

# ─── Setup wizard kontrol ───────────────────────────
$configFile = "$env:USERPROFILE\.raporoku\config.json"
$needSetup = -not (Test-Path $configFile)
if ($needSetup) {
    # LocalSystem servis çalışır ama setup kullanıcı profilinde config ister.
    # Önce interactive setup wizard'ı kullanıcı hesabında çalıştır.
    Write-Host "[5/6] İlk kurulum sihirbazı çalıştırılıyor..." -ForegroundColor Yellow
    Write-Host "  (Cihaz anahtarınızı isteyecek)" -ForegroundColor DarkGray
    & $AgentExe --setup
    if (-not (Test-Path $configFile)) {
        Write-Host "  ✗ Setup tamamlanmadı — servis yine de kurulacak ancak çalışmayacak." -ForegroundColor Red
        Write-Host "    Daha sonra: $AgentExe --setup" -ForegroundColor Yellow
    }
}

# ─── Servis kaydı ───────────────────────────────────
Write-Host "[6/6] Servis kaydediliyor..." -ForegroundColor Yellow
& $NssmExe install $ServiceName $AgentExe 2>&1 | Out-Null
& $NssmExe set $ServiceName AppDirectory $InstallDir 2>&1 | Out-Null
& $NssmExe set $ServiceName DisplayName $ServiceDisplay 2>&1 | Out-Null
& $NssmExe set $ServiceName Description $ServiceDesc 2>&1 | Out-Null
& $NssmExe set $ServiceName Start SERVICE_AUTO_START 2>&1 | Out-Null
# Servis çökerse 5sn'de yeniden başlat
& $NssmExe set $ServiceName AppExit Default Restart 2>&1 | Out-Null
& $NssmExe set $ServiceName AppRestartDelay 5000 2>&1 | Out-Null
# stdout/stderr logları
& $NssmExe set $ServiceName AppStdout "$InstallDir\service-stdout.log" 2>&1 | Out-Null
& $NssmExe set $ServiceName AppStderr "$InstallDir\service-stderr.log" 2>&1 | Out-Null
& $NssmExe set $ServiceName AppRotateFiles 1 2>&1 | Out-Null
& $NssmExe set $ServiceName AppRotateBytes 5242880 2>&1 | Out-Null  # 5MB
Write-Host "  ✓ Servis kaydedildi" -ForegroundColor Green

# ─── Başlat ─────────────────────────────────────────
& $NssmExe start $ServiceName 2>&1 | Out-Null
Start-Sleep -Seconds 3
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$status = if ($svc) { $svc.Status } else { "Yok" }

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ✓ Kurulum tamamlandı" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Servis adı     : $ServiceName" -ForegroundColor White
Write-Host "  Durumu         : $status" -ForegroundColor White
Write-Host "  Dizin          : $InstallDir" -ForegroundColor White
Write-Host "  Log            : $InstallDir\service-stdout.log" -ForegroundColor White
Write-Host ""
Write-Host "  Kontrol:" -ForegroundColor Yellow
Write-Host "    Get-Service $ServiceName" -ForegroundColor Cyan
Write-Host "    & `"$NssmExe`" status $ServiceName" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Kaldırmak için: uninstall_service.ps1 (Yönetici olarak)" -ForegroundColor DarkGray
Write-Host ""
Read-Host "Çıkış için Enter"
