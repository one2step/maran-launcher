# =============================================================
# Maran Launcher - Installer (ASCII-only for PS 5.1 compatibility)
#
# Usage:
#   PowerShell:  irm bit.ly/<alias> | iex
#   cmd:         powershell -c "irm bit.ly/<alias>|iex"
#
# What it does:
#   1) Downloads latest exe to %LOCALAPPDATA%\Programs\MaranLauncher\
#   2) Creates Desktop + Start Menu shortcut with Ctrl+Alt+M hotkey
#   3) Optionally launches it
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

# 1) Install directory
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
# Clean up any leftover files with garbled names from previous broken installs
Get-ChildItem -Path $INSTALL_DIR -Filter "*.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne $EXE_LOCAL } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "  [1/3] Install folder ready    " -NoNewline
Write-Host "OK" -ForegroundColor Green
Write-Host "        $INSTALL_DIR" -ForegroundColor DarkGray

# 2) Download exe
$exePath = Join-Path $INSTALL_DIR $EXE_LOCAL
Write-Host "  [2/3] Downloading exe         " -NoNewline
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

# 3) Create shortcuts with Ctrl+Alt+M
$WshShell = New-Object -ComObject WScript.Shell
$desktopLnk = Join-Path $env:USERPROFILE "Desktop\$LNK_NAME.lnk"
$startLnk   = Join-Path $env:APPDATA   "Microsoft\Windows\Start Menu\Programs\$LNK_NAME.lnk"

# Remove leftover broken Korean-named shortcuts from previous installs
Get-ChildItem -Path "$env:USERPROFILE\Desktop" -Filter "*.lnk" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "$LNK_NAME.lnk" -and $_.Name -match "(?i)maran|launcher" } |
    Remove-Item -Force -ErrorAction SilentlyContinue

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
Write-Host "  [3/3] Shortcut + hotkey       " -NoNewline
Write-Host "OK (Ctrl+Alt+M)" -ForegroundColor Green

Write-Host ""
Write-Host "  Done." -ForegroundColor Green
Write-Host "  Installed: $exePath" -ForegroundColor DarkGray
Write-Host "  Shortcut : Desktop + Start Menu" -ForegroundColor DarkGray
Write-Host "  Hotkey   : Ctrl + Alt + M" -ForegroundColor DarkGray
Write-Host ""

$run = Read-Host "  Run now? (Y/n)"
if ($run -ne "n" -and $run -ne "N") {
    Start-Process -FilePath $exePath
    Write-Host "  Launched. First run will show the setup screen." -ForegroundColor Cyan
}
Write-Host ""
