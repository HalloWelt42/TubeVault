# ╔══════════════════════════════════════════════════════════════╗
# ║  TubeVault - Setup Script v1.1.0 (Windows PowerShell)        ║
# ║  Erstellt Verzeichnisse und .env für Erstinstallation.       ║
# ║  Benötigt: Docker Desktop für Windows mit WSL 2              ║
# ║  © HalloWelt42 - Private Nutzung                             ║
# ╚══════════════════════════════════════════════════════════════╝

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "+===========================================+"
Write-Host "|  TubeVault - Setup (Windows)              |"
Write-Host "+===========================================+"
Write-Host ""

# ── Docker prüfen ──────────────────────────────────────────────
try {
    $null = Get-Command docker -ErrorAction Stop
} catch {
    Write-Host "X Docker ist nicht installiert." -ForegroundColor Red
    Write-Host "  Installiere Docker Desktop fuer Windows:"
    Write-Host "  https://www.docker.com/products/docker-desktop/"
    Write-Host ""
    Write-Host "  WICHTIG: In den Docker Desktop Einstellungen muss"
    Write-Host "  'Use the WSL 2 based engine' aktiviert sein."
    exit 1
}

# Docker Daemon prüfen
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker nicht bereit" }
} catch {
    Write-Host "X Docker Desktop laeuft nicht." -ForegroundColor Red
    Write-Host "  Starte Docker Desktop und warte bis das Icon gruen wird."
    Write-Host ""
    Write-Host "  Falls WSL 2 nicht eingerichtet ist:"
    Write-Host "  1. PowerShell als Admin oeffnen"
    Write-Host "  2. wsl --install"
    Write-Host "  3. PC neu starten"
    Write-Host "  4. Docker Desktop starten"
    exit 1
}

# Docker Compose prüfen
try {
    $composeVersion = docker compose version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Compose nicht verfuegbar" }
} catch {
    Write-Host "X Docker Compose ist nicht verfuegbar." -ForegroundColor Red
    Write-Host "  Docker Compose ist in Docker Desktop enthalten."
    Write-Host "  Bitte Docker Desktop aktualisieren."
    exit 1
}

# Versionen anzeigen
$dockerVer = (docker --version) -replace '.*(\d+\.\d+\.\d+).*', '$1'
$composeVer = (docker compose version --short)
Write-Host "  Docker $dockerVer" -ForegroundColor Green
Write-Host "  Docker Compose $composeVer" -ForegroundColor Green
Write-Host ""

# ── Verzeichnisse anlegen ──────────────────────────────────────
Write-Host "Erstelle Datenverzeichnisse..."
$dirs = @(
    "data\db",
    "data\videos",
    "data\audio",
    "data\thumbnails",
    "data\avatars",
    "data\metadata",
    "data\banners",
    "data\subtitles",
    "data\exports",
    "data\temp",
    "data\rss_thumbs",
    "data\texts",
    "data\scan",
    "data\backups",
    "config"
)

foreach ($dir in $dirs) {
    $fullPath = Join-Path $PSScriptRoot $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
    Write-Host "   + $dir"
}
Write-Host ""

# ── .env erstellen ─────────────────────────────────────────────
$envFile = Join-Path $PSScriptRoot ".env"
$envExample = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host ".env erstellt (aus .env.example)"
        Write-Host "   -> Passe die Werte in .env nach Bedarf an."
    } else {
        Write-Host "! .env.example nicht gefunden - erstelle Standard-.env" -ForegroundColor Yellow
        @"
TUBEVAULT_BACKEND_PORT=8031
TUBEVAULT_FRONTEND_PORT=8032
MAX_CONCURRENT_DOWNLOADS=1
DEFAULT_QUALITY=720p
"@ | Set-Content -Path $envFile -Encoding UTF8
        Write-Host ".env mit Standardwerten erstellt."
    }
} else {
    Write-Host ".env existiert bereits - wird nicht ueberschrieben."
}
Write-Host ""

# ── System-Info ────────────────────────────────────────────────
$os = (Get-CimInstance Win32_OperatingSystem)
$ramGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$disk = Get-PSDrive -Name (Get-Location).Drive.Name
$diskFreeGB = [math]::Round($disk.Free / 1GB, 1)

Write-Host "System-Info:"
Write-Host "   Plattform:  Windows ($([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture))"
Write-Host "   OS:         $($os.Caption)"
Write-Host "   RAM:        $ramGB GB"
Write-Host "   Disk frei:  $diskFreeGB GB"
Write-Host ""

# ── Speicherplatz-Warnung ──────────────────────────────────────
if ($diskFreeGB -lt 10) {
    Write-Host "!  Weniger als 10 GB frei!" -ForegroundColor Yellow
    Write-Host "   TubeVault speichert Videos lokal - fuer groessere Sammlungen"
    Write-Host "   wird mehr Speicherplatz empfohlen."
    Write-Host ""
}

# ── Line-Ending-Fix (für bestehende Clones) ───────────────────
Write-Host "Normalisiere Zeilenenden (LF fuer Docker)..."
try {
    git rm --cached -r . 2>&1 | Out-Null
    git reset HEAD 2>&1 | Out-Null
    Write-Host "   + Zeilenenden normalisiert (.gitattributes aktiv)" -ForegroundColor Green
} catch {
    Write-Host "   Git-Normalisierung uebersprungen (kein Problem beim Erstclone)" -ForegroundColor Yellow
}
Write-Host ""

# ── Fertig ─────────────────────────────────────────────────────
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
if (-not $localIP) { $localIP = "localhost" }

Write-Host "Setup abgeschlossen! Starte TubeVault mit:" -ForegroundColor Green
Write-Host ""
Write-Host "   docker compose up -d --build"
Write-Host ""
Write-Host "   Frontend: http://${localIP}:8032"
Write-Host "   Backend:  http://${localIP}:8031/docs"
Write-Host ""
