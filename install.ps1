# Timebutler Auto - Simplified Installer

$ErrorActionPreference = "Stop"

# Check for Administrator privileges
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "--- FEHLENDE ADMIN-RECHTE ---" -ForegroundColor Red
    Write-Host "Dieses Skript muss mit Administratorrechten ausgeführt werden, um den Windows Task zu registrieren."
    Write-Host ""
    Write-Host "So starten Sie als Administrator:"
    Write-Host "1. Klicken Sie mit der rechten Maustaste auf die Datei 'install.ps1'."
    Write-Host "2. Wählen Sie 'Mit PowerShell ausführen'."
    Write-Host "3. Falls das Fenster sofort schließt, öffnen Sie 'PowerShell' über das Startmenü"
    Write-Host "   per Rechtsklick -> 'Als Administrator ausführen' und navigieren Sie hierher."
    Write-Host ""
    Write-Host "Drücken Sie eine beliebige Taste zum Beenden..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit
}

Write-Host "--- Timebutler Auto Installer ---" -ForegroundColor Cyan
Write-Host "Dieses Skript richtet Timebutler Auto für Sie ein."
Write-Host ""

# 1. Credentials Setup (.env)
if (-not (Test-Path ".env")) {
    Write-Host "Schritt 1: Zugangsdaten einrichten" -ForegroundColor Yellow
    $email = Read-Host "Bitte geben Sie Ihre Timebutler E-Mail ein"
    $pass = Read-Host "Bitte geben Sie Ihr Timebutler Passwort ein"
    
    $envContent = "TIMEBUTLER_USERNAME=$email`r`nTIMEBUTLER_PASSWORD=$pass"
    Set-Content -Path ".env" -Value $envContent -Encoding utf8
    Write-Host "✓ .env Datei erfolgreich erstellt." -ForegroundColor Green
} else {
    Write-Host "✓ .env Datei existiert bereits. Überspringe Einrichtung." -ForegroundColor Gray
}

Write-Host ""

# 2. Configuration Setup (settings.json)
if (-not (Test-Path "config/settings.json")) {
    Write-Host "Schritt 2: Konfiguration erstellen" -ForegroundColor Yellow
    if (Test-Path "config/settings.sample.json") {
        Copy-Item -Path "config/settings.sample.json" -Destination "config/settings.json"
        Write-Host "✓ config/settings.json wurde aus der Vorlage erstellt." -ForegroundColor Green
        Write-Host "ACHTUNG: Bitte öffnen Sie 'config/settings.json' nach der Installation und tragen Sie Ihre WLAN-Namen (SSIDs) ein!" -ForegroundColor Red
    } else {
        Write-Warning "config/settings.sample.json nicht gefunden. Bitte erstellen Sie config/settings.json manuell."
    }
} else {
    Write-Host "✓ config/settings.json existiert bereits." -ForegroundColor Gray
}

Write-Host ""

# 3. Python Environment Detection
Write-Host "Schritt 3: Python Umgebung prüfen" -ForegroundColor Yellow
$pythonPath = "pythonw.exe"
if (Test-Path ".venv\Scripts\pythonw.exe") {
    $pythonPath = Resolve-Path ".venv\Scripts\pythonw.exe"
    Write-Host "✓ Virtual Environment gefunden: $pythonPath" -ForegroundColor Green
} else {
    Write-Host "⚠ Kein Virtual Environment (.venv) gefunden. Nutze System-Python ($pythonPath)." -ForegroundColor Yellow
    Write-Host "  Stellen Sie sicher, dass alle Abhängigkeiten installiert sind (pip install -r requirements.txt)."
}

Write-Host ""

# 4. Task Registration
Write-Host "Schritt 4: Windows Task registrieren" -ForegroundColor Yellow
if (Test-Path "setup_task.ps1") {
    try {
        # Call the existing setup script with the detected python path
        .\setup_task.ps1 -PythonPath $pythonPath -ErrorAction Stop
        Write-Host "✓ Windows Task erfolgreich registriert!" -ForegroundColor Green
    } catch {
        Write-Error "Fehler beim Registrieren des Tasks: $_"
        exit 1
    }
} else {
    Write-Error "setup_task.ps1 nicht gefunden! Bitte stellen Sie sicher, dass Sie sich im Projektverzeichnis befinden."
    exit 1
}

Write-Host ""
Write-Host "--- Installation abgeschlossen ---" -ForegroundColor Cyan
Write-Host "Bitte denken Sie daran, Ihre WLAN-SSIDs in 'config/settings.json' einzutragen."
Write-Host "Drücken Sie eine beliebige Taste zum Beenden..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
