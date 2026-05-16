# =============================================================
# Maran Launcher - Installer (ASCII-only for PS 5.1 compatibility)
#
# Usage:
#   PowerShell:  irm bit.ly/maran44 | iex
#   cmd:         powershell -c "irm bit.ly/maran44|iex"
#
# Steps:
#   1) Creates install folder
#   2) Downloads latest MaranLauncher.exe
#   3) Creates Desktop + Start Menu shortcut with Ctrl+Alt+M hotkey
#   4) Checks / installs OpenSSH Client (Windows optional feature)
#   5) Generates SSH key (id_ed25519) if missing
#   6) Launches the exe
# =============================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# === Config ===
$REPO_OWNER = "one2step"
$REPO_NAME  = "maran-launcher"
$EXE_ASSET  = "maran-launcher.exe"
$EXE_LOCAL  = "MaranLauncher.exe"
$LNK_NAME   = "Maran Launcher"

$INSTALL_DIR = Join-Path $env:LOCALAPPDATA "Programs\MaranLauncher"
$EXE_URL     = "https://github.com/$REPO_OWNER/$REPO_NAME/releases/latest/download/$EXE_ASSET"

Write-Host ""
Write-Host "  M  Maran Launcher Installer" -ForegroundColor Cyan
Write-Host "  ---------------------------" -ForegroundColor DarkGray
Write-Host ""

# ===========================================================
# [1/6] Install directory
# ===========================================================
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
# Clean up leftover files with garbled names from previous broken installs
Get-ChildItem -Path $INSTALL_DIR -Filter "*.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne $EXE_LOCAL } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "  [1/6] Install folder ready    " -NoNewline
Write-Host "OK" -ForegroundColor Green
Write-Host "        $INSTALL_DIR" -ForegroundColor DarkGray

# ===========================================================
# [2/6] Download exe
# ===========================================================
$exePath = Join-Path $INSTALL_DIR $EXE_LOCAL

# Stop any running launcher so the .exe is not locked during overwrite
$running = Get-Process -Name "MaranLauncher" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "  [*] Stopping running launcher " -NoNewline
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    Write-Host "OK" -ForegroundColor Green
}

Write-Host "  [2/6] Downloading exe         " -NoNewline
try {
    Invoke-WebRequest -Uri $EXE_URL -OutFile $exePath -UseBasicParsing
    $size = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host "OK ($size MB)" -ForegroundColor Green
} catch {
    Write-Host "FAIL" -ForegroundColor Red
    Write-Host "        URL: $EXE_URL"
    Write-Host "        Error: $_" -ForegroundColor Red
    exit 1
}

# ===========================================================
# [3/6] Create shortcuts with Ctrl+Alt+M
# ===========================================================
$WshShell = New-Object -ComObject WScript.Shell

# Get actual paths from registry (handles OneDrive redirection)
function Get-SpecialFolder($name) {
    $path = (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" -ErrorAction SilentlyContinue).$name
    if ($null -eq $path) {
        $path = (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" -ErrorAction SilentlyContinue).$name
    }
    if ($null -ne $path) {
        return [System.Environment]::ExpandEnvironmentVariables($path)
    }
    return $null
}

$desktopDir   = Get-SpecialFolder "Desktop"
$startMenuDir = Get-SpecialFolder "Programs"

if ($null -eq $desktopDir -or !(Test-Path $desktopDir)) {
    $desktopDir = Join-Path $env:USERPROFILE "Desktop"
}
if ($null -eq $startMenuDir -or !(Test-Path $startMenuDir)) {
    $startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
}

$desktopLnk = Join-Path $desktopDir "$LNK_NAME.lnk"
$startLnk   = Join-Path $startMenuDir "$LNK_NAME.lnk"

# Remove leftover broken Korean-named shortcuts from previous installs
if (Test-Path $desktopDir) {
    Get-ChildItem -Path $desktopDir -Filter "*.lnk" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "$LNK_NAME.lnk" -and $_.Name -match "(?i)maran|launcher" } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

foreach ($lnk in @($desktopLnk, $startLnk)) {
    $sc = $WshShell.CreateShortcut($lnk)
    $sc.TargetPath       = $exePath
    $sc.WorkingDirectory = $INSTALL_DIR
    $sc.IconLocation     = "$exePath,0"
    $sc.Hotkey           = "CTRL+ALT+M"
    $sc.WindowStyle      = 1
    $sc.Description      = "Connect to Mac MARAN folder via VS Code or Terminal"
    $sc.Save()
}
Write-Host "  [3/6] Shortcut + hotkey       " -NoNewline
Write-Host "OK (Ctrl+Alt+M)" -ForegroundColor Green

Write-Host "  Installed: $exePath" -ForegroundColor DarkGray
Write-Host "  Shortcut : Desktop + Start Menu" -ForegroundColor DarkGray
Write-Host "  Hotkey   : Ctrl + Alt + M" -ForegroundColor DarkGray
Write-Host ""

# ===========================================================
# [4/6] OpenSSH Client (Windows optional feature)
# ===========================================================
Write-Host "  [4/6] OpenSSH Client          " -NoNewline
$sshExe = "$env:SystemRoot\System32\OpenSSH\ssh.exe"
if (Test-Path $sshExe) {
    Write-Host "OK (already installed)" -ForegroundColor Green
} else {
    Write-Host "installing..." -ForegroundColor Yellow
    try {
        $cap = Get-WindowsCapability -Online -Name "OpenSSH.Client*" -ErrorAction Stop
        if ($cap.State -ne "Installed") {
            Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 | Out-Null
        }
        if (Test-Path $sshExe) {
            Write-Host "        OK" -ForegroundColor Green
        } else {
            Write-Host "        FAIL - run launcher and click OpenSSH install" -ForegroundColor Red
        }
    } catch {
        Write-Host "        FAIL (needs admin) - launcher will retry" -ForegroundColor Red
    }
}

# ===========================================================
# [5/6] SSH key (id_ed25519)
# ===========================================================
Write-Host "  [5/6] SSH key (id_ed25519)    " -NoNewline
$keyPath    = "$env:USERPROFILE\.ssh\id_ed25519"
$sshKeygen  = "$env:SystemRoot\System32\OpenSSH\ssh-keygen.exe"
if (Test-Path $keyPath) {
    Write-Host "OK (already exists)" -ForegroundColor Green
} elseif (Test-Path $sshKeygen) {
    New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.ssh" | Out-Null
    & $sshKeygen -t ed25519 -f $keyPath -N "" 2>$null | Out-Null
    if (Test-Path $keyPath) {
        Write-Host "OK (generated)" -ForegroundColor Green
    } else {
        Write-Host "FAIL - launcher will retry" -ForegroundColor Red
    }
} else {
    # Try PATH fallback (PS 5.1 compatible - no ?. operator)
    $kgCmd = Get-Command ssh-keygen -ErrorAction SilentlyContinue
    if ($kgCmd) {
        New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.ssh" | Out-Null
        & $kgCmd.Source -t ed25519 -f $keyPath -N "" 2>$null | Out-Null
        if (Test-Path $keyPath) {
            Write-Host "OK (generated)" -ForegroundColor Green
        } else {
            Write-Host "FAIL - launcher will retry" -ForegroundColor Red
        }
    } else {
        Write-Host "SKIP - OpenSSH not ready, launcher will handle" -ForegroundColor DarkGray
    }
}

# ===========================================================
# [6/6] Launch
# ===========================================================
Write-Host ""
Write-Host "  Done." -ForegroundColor Green
Write-Host ""

# MARAN_QUIET=1 -> auto-update flow (no interactive prompt)
if ($env:MARAN_QUIET -eq "1") {
    Start-Process -FilePath $exePath
    Write-Host "  [auto] Relaunched." -ForegroundColor Green
} else {
    $run = Read-Host "  Run now? (Y/n)"
    if ($run -ne "n" -and $run -ne "N") {
        Start-Process -FilePath $exePath
        Write-Host "  Launched. Click install-all inside the launcher." -ForegroundColor Cyan
    }
}
Write-Host ""
