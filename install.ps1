# Timebutler Auto - Installer

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- Localization ---
$strings = @{
    EN = @{
        AdminRequired = "--- ADMIN PRIVILEGES REQUIRED ---"
        AdminInstruction = "This script must be run as Administrator to register the Windows Task."
        HowToAdmin = "How to run as Administrator:`n1. Right-click 'install.ps1'`n2. Select 'Run with PowerShell'`n3. If it closes immediately, open PowerShell as Admin and navigate here."
        PressAnyKey = "Press any key to exit..."
        
        Header = "--- Timebutler Auto Installer ---"
        
        Step1 = "Step 1: Credentials Setup"
        AskEmail = "Please enter your Timebutler Email"
        AskPass = "Please enter your Timebutler Password"
        EnvCreated = "✓ .env file created successfully."
        EnvExists = "✓ .env file already exists. Skipping."
        
        Step2 = "Step 2: Network Configuration"
        CurrentSSIDDetected = "Detected current Wi-Fi: '{0}'"
        AskUseCurrent = "Do you want to use this network for auto-punching? (y/n)"
        AskAddMore = "Do you want to add more networks from your saved profiles? (y/n)"
        ScanningProfiles = "Scanning saved Wi-Fi profiles..."
        SelectProfiles = "Please select the networks to allow:"
        EnterNumbers = "Enter the numbers of the networks to add (comma-separated, e.g., 1,3)"
        InvalidInput = "Invalid input. Please try again."
        NoProfiles = "No saved Wi-Fi profiles found."
        SettingsSaved = "✓ Settings saved to config/settings.json with {0} network(s)."
        
        Step3 = "Step 3: Environment Setup"
        CheckingPython = "Checking for Python..."
        PythonNotFound = "Python not found."
        AskInstallPython = "Python is missing. Do you want to install it via Winget? (y/n)"
        InstallingPython = "Installing Python via Winget (this may take a while)..."
        WingetMissing = "Winget not found. Please install Python 3.8+ manually (https://python.org)."
        PythonInstallSuccess = "✓ Python installed successfully. Refreshing environment..."
        PythonInstallFail = "Python installation failed. Please install manually."
        VenvExists = "Virtual environment (.venv) found."
        AskCreateVenv = "Virtual environment not found. Create one now? (Recommended) (y/n)"
        CreatingVenv = "Creating virtual environment..."
        VenvCreated = "✓ Virtual environment created."
        AskInstallDeps = "Do you want to install/update dependencies? (y/n)"
        InstallingDeps = "Installing dependencies (this may take a minute)..."
        DepsSuccess = "✓ Dependencies installed."
        InstallingBrowsers = "Installing Playwright browsers..."
        BrowsersSuccess = "✓ Playwright browsers installed."
        
        Step4 = "Step 4: Windows Task Registration"
        TaskSuccess = "✓ Windows Task successfully registered!"
        TaskError = "Error registering task: {0}"
        ScriptMissing = "setup_task.ps1 not found!"
        
        Footer = "--- Installation Complete ---"
        FinalMsg = "You can manage your networks in 'config/settings.json'."
    }
    DE = @{
        AdminRequired = "--- FEHLENDE ADMIN-RECHTE ---"
        AdminInstruction = "Dieses Skript muss mit Administratorrechten ausgeführt werden."
        HowToAdmin = "So startest du als Administrator:`n1. Rechtsklick auf 'install.ps1'`n2. 'Mit PowerShell ausführen'`n3. Falls es schließt: PowerShell als Admin öffnen und hierher navigieren."
        PressAnyKey = "Drücke eine beliebige Taste zum Beenden..."
        
        Header = "--- Timebutler Auto Installer ---"
        
        Step1 = "Schritt 1: Zugangsdaten"
        AskEmail = "Bitte gib deine Timebutler E-Mail ein"
        AskPass = "Bitte gib dein Timebutler Passwort ein"
        EnvCreated = "✓ .env Datei erfolgreich erstellt."
        EnvExists = "✓ .env Datei existiert bereits. Überspringe."
        
        Step2 = "Schritt 2: Netzwerk-Konfiguration"
        CurrentSSIDDetected = "Aktuelles WLAN erkannt: '{0}'"
        AskUseCurrent = "Möchtest du dieses Netzwerk zum Einstempeln nutzen? (j/n)"
        AskAddMore = "Möchtest du weitere Netzwerke aus den gespeicherten Profilen hinzufügen? (j/n)"
        ScanningProfiles = "Scanne gespeicherte WLAN-Profile..."
        SelectProfiles = "Bitte wähle die Netzwerke aus:"
        EnterNumbers = "Gib die Nummern der Netzwerke ein (kommagetrennt, z.B. 1,3)"
        InvalidInput = "Ungültige Eingabe. Bitte versuche es erneut."
        NoProfiles = "Keine gespeicherten WLAN-Profile gefunden."
        SettingsSaved = "✓ Einstellungen in config/settings.json gespeichert ({0} Netzwerke)."
        
        Step3 = "Schritt 3: Umgebung einrichten"
        CheckingPython = "Prüfe Python-Installation..."
        PythonNotFound = "Python nicht gefunden."
        AskInstallPython = "Python fehlt. Soll es via Winget installiert werden? (j/n)"
        InstallingPython = "Installiere Python via Winget (das kann dauern)..."
        WingetMissing = "Winget nicht gefunden. Bitte installiere Python 3.8+ manuell (https://python.org)."
        PythonInstallSuccess = "✓ Python erfolgreich installiert. Aktualisiere Umgebung..."
        PythonInstallFail = "Python Installation fehlgeschlagen. Bitte manuell installieren."
        VenvExists = "Virtual Environment (.venv) gefunden."
        AskCreateVenv = "Kein Virtual Environment gefunden. Jetzt erstellen? (Empfohlen) (j/n)"
        CreatingVenv = "Erstelle Virtual Environment..."
        VenvCreated = "✓ Virtual Environment erstellt."
        AskInstallDeps = "Möchtest du Abhängigkeiten installieren/aktualisieren? (j/n)"
        InstallingDeps = "Installiere Abhängigkeiten (das kann kurz dauern)..."
        DepsSuccess = "✓ Abhängigkeiten installiert."
        InstallingBrowsers = "Installiere Playwright Browser..."
        BrowsersSuccess = "✓ Playwright Browser installiert."
        
        Step4 = "Schritt 4: Windows Task Registrierung"
        TaskSuccess = "✓ Windows Task erfolgreich registriert!"
        TaskError = "Fehler beim Registrieren des Tasks: {0}"
        ScriptMissing = "setup_task.ps1 nicht gefunden!"
        
        Footer = "--- Installation abgeschlossen ---"
        FinalMsg = "Du kannst die Netzwerke später in 'config/settings.json' bearbeiten."
    }
}

# --- Language Selection ---
Write-Host "Select Language / Sprache wählen:" -ForegroundColor Cyan
Write-Host "[1] English"
Write-Host "[2] Deutsch"
$langInput = Read-Host "> "
if ($langInput -eq "2") { $L = $strings.DE } else { $L = $strings.EN }

Write-Host ""
Write-Host $L.Header -ForegroundColor Cyan
Write-Host ""

# --- Admin Check ---
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host $L.AdminRequired -ForegroundColor Red
    Write-Host $L.AdminInstruction
    Write-Host ""
    Write-Host $L.HowToAdmin
    Write-Host ""
    Write-Host $L.PressAnyKey
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit
}

# --- Step 1: Credentials ---
Write-Host $L.Step1 -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    $email = Read-Host $L.AskEmail
    $pass = Read-Host $L.AskPass
    
    $envContent = "TIMEBUTLER_USERNAME=$email`r`nTIMEBUTLER_PASSWORD=$pass"
    Set-Content -Path ".env" -Value $envContent -Encoding utf8
    Write-Host $L.EnvCreated -ForegroundColor Green
} else {
    Write-Host $L.EnvExists -ForegroundColor Gray
}
Write-Host ""

# --- Step 2: Networks ---
Write-Host $L.Step2 -ForegroundColor Yellow

$selectedSSIDs = @()
$addMore = $false

# 1. Detect Current
$currentSSID = $null
try {
    $netshOut = netsh wlan show interfaces
    if ($netshOut -match '^\s*SSID\s*:\s*(.+)$') {
        $currentSSID = $matches[1].Trim()
    }
} catch {}

if ($currentSSID) {
    Write-Host ($L.CurrentSSIDDetected -f $currentSSID) -ForegroundColor Cyan
    $response = Read-Host $L.AskUseCurrent
    if ($response -match "^[yj]") {
        $selectedSSIDs += $currentSSID
        $responseMore = Read-Host $L.AskAddMore
        if ($responseMore -match "^[yj]") {
            $addMore = $true
        }
    } else {
        $addMore = $true
    }
} else {
    $addMore = $true
}

# 2. Select from List (if needed)
if ($addMore) {
    Write-Host $L.ScanningProfiles
    $profiles = @()
    $netshProfiles = netsh wlan show profiles
    foreach ($line in $netshProfiles) {
        if ($line -match ':\s*(.+)$' -and $line -notmatch '----') {
             $pName = $matches[1].Trim()
             if ($pName) { $profiles += $pName }
        }
    }
    
    $profiles = $profiles | Select-Object -Unique

    if ($profiles.Count -gt 0) {
        Write-Host $L.SelectProfiles
        for ($i=0; $i -lt $profiles.Count; $i++) {
            Write-Host "[$($i+1)] $($profiles[$i])"
        }
        
        $selection = Read-Host $L.EnterNumbers
        if ($selection) {
            try {
                $indices = $selection -split ',' | ForEach-Object { $_.Trim() }
                foreach ($idx in $indices) {
                    if ($idx -match '^\d+$') {
                        $i = [int]$idx - 1
                        if ($i -ge 0 -and $i -lt $profiles.Count) {
                            $selectedSSIDs += $profiles[$i]
                        }
                    }
                }
            } catch {
                Write-Warning $L.InvalidInput
            }
        }
    } else {
        Write-Warning $L.NoProfiles
    }
}

$finalSSIDs = $selectedSSIDs | Select-Object -Unique

# Write settings.json
$settingsDir = "config"
if (-not (Test-Path $settingsDir)) { New-Item -ItemType Directory -Path $settingsDir | Out-Null }
$settingsPath = "$settingsDir/settings.json"

$jsonPayload = @{ allowed_ssids = @($finalSSIDs) } | ConvertTo-Json
Set-Content -Path $settingsPath -Value $jsonPayload -Encoding utf8
Write-Host ($L.SettingsSaved -f $finalSSIDs.Count) -ForegroundColor Green
Write-Host ""

# --- Step 3: Python Environment ---
Write-Host $L.Step3 -ForegroundColor Yellow
Write-Host $L.CheckingPython

# Helper to check python
function Test-Python {
    try {
        $null = python --version
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-Python)) {
    Write-Warning $L.PythonNotFound
    # Check for winget
    $wingetAvailable = $false
    try { $null = winget --version; $wingetAvailable = $true } catch { $wingetAvailable = $false }

    if ($wingetAvailable) {
        $resp = Read-Host $L.AskInstallPython
        if ($resp -match "^[yj]") {
            Write-Host $L.InstallingPython -ForegroundColor Cyan
            # Install Python 3 via winget
            try {
                winget install -e --id Python.Python.3 --scope machine --accept-package-agreements --accept-source-agreements
                
                # REFRESH ENVIRONMENT
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
                
                if (Test-Python) {
                    Write-Host $L.PythonInstallSuccess -ForegroundColor Green
                } else {
                    Write-Error $L.PythonInstallFail
                    exit 1
                }
            } catch {
                Write-Error $L.PythonInstallFail
                exit 1
            }
        } else {
             Write-Error $L.PythonNotFound
             exit 1
        }
    } else {
        Write-Error $L.WingetMissing
        exit 1
    }
}

$venvPath = ".venv"
$venvPythonExe = Join-Path $venvPath "Scripts\python.exe"
$venvPythonWExe = Join-Path $venvPath "Scripts\pythonw.exe"
$doInstall = $false

if (Test-Path $venvPythonExe) {
    Write-Host $L.VenvExists -ForegroundColor Green
    $resp = Read-Host $L.AskInstallDeps
    if ($resp -match "^[yj]") { $doInstall = $true }
} else {
    $resp = Read-Host $L.AskCreateVenv
    if ($resp -match "^[yj]") {
        Write-Host $L.CreatingVenv
        python -m venv $venvPath
        if ($LASTEXITCODE -eq 0) {
            Write-Host $L.VenvCreated -ForegroundColor Green
            $doInstall = $true
        } else {
            Write-Error "Failed to create virtual environment."
            exit 1
        }
    }
}

if ($doInstall) {
    if (Test-Path $venvPythonExe) {
        Write-Host $L.InstallingDeps
        & $venvPythonExe -m pip install --upgrade pip
        & $venvPythonExe -m pip install -r requirements.txt
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host $L.DepsSuccess -ForegroundColor Green
            Write-Host $L.InstallingBrowsers
            & $venvPythonExe -m playwright install chromium
            if ($LASTEXITCODE -eq 0) {
                Write-Host $L.BrowsersSuccess -ForegroundColor Green
            }
        } else {
            Write-Error "Dependency installation failed."
            exit 1
        }
    }
}

# Determine correct Python path for the task
$pythonPath = "pythonw.exe"
if (Test-Path $venvPythonWExe) {
    $pythonPath = Resolve-Path $venvPythonWExe
}

Write-Host ""

# --- Step 4: Task ---
Write-Host $L.Step4 -ForegroundColor Yellow
if (Test-Path "setup_task.ps1") {
    try {
        .\setup_task.ps1 -PythonPath $pythonPath -ErrorAction Stop
        Write-Host $L.TaskSuccess -ForegroundColor Green
    } catch {
        Write-Error ($L.TaskError -f $_)
        exit 1
    }
} else {
    Write-Error $L.ScriptMissing
    exit 1
}

Write-Host ""
Write-Host $L.Footer -ForegroundColor Cyan
Write-Host $L.FinalMsg
Write-Host $L.PressAnyKey
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

