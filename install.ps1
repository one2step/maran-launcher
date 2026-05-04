# =============================================================
# 마란 런처 원클릭 설치 스크립트
#
# 사용법:
#   짧게 (bit.ly 단축 후):
#     PowerShell:  irm bit.ly/maran | iex
#     cmd:         powershell -c "irm bit.ly/maran|iex"
#
#   원본 URL:
#     irm https://github.com/<USER>/<REPO>/releases/latest/download/install.ps1 | iex
#
# 동작:
#   1) 최신 .exe 다운로드 → %LOCALAPPDATA%\Programs\MaranLauncher\
#   2) 바탕화면 + 시작메뉴에 바로가기 생성 (Ctrl+Alt+M 단축키 포함)
#   3) 선택: 즉시 실행
# =============================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# === 설정 ===
$REPO_OWNER = "one2step"
$REPO_NAME  = "maran-launcher"
$EXE_ASSET  = "maran-launcher.exe"   # GitHub Release에 올린 자산 이름
$EXE_LOCAL  = "마란런처.exe"          # 로컬 저장 시 이름

$INSTALL_DIR = Join-Path $env:LOCALAPPDATA "Programs\MaranLauncher"
$EXE_URL     = "https://github.com/$REPO_OWNER/$REPO_NAME/releases/latest/download/$EXE_ASSET"

# === 시작 ===
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host ""
Write-Host "  M  마란 런처 설치" -ForegroundColor Cyan
Write-Host "  ---------------" -ForegroundColor DarkGray
Write-Host ""

# 1) 설치 폴더 생성
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
Write-Host "  [1/3] 설치 폴더 준비   " -NoNewline
Write-Host "✓" -ForegroundColor Green
Write-Host "        $INSTALL_DIR" -ForegroundColor DarkGray

# 2) EXE 다운로드
$exePath = Join-Path $INSTALL_DIR $EXE_LOCAL
Write-Host "  [2/3] EXE 다운로드     " -NoNewline
try {
    Invoke-WebRequest -Uri $EXE_URL -OutFile $exePath -UseBasicParsing
    $size = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host "✓ ($size MB)" -ForegroundColor Green
} catch {
    Write-Host "✗" -ForegroundColor Red
    Write-Host "        URL: $EXE_URL"
    Write-Host "        오류: $_" -ForegroundColor Red
    Write-Host "        ※ install.ps1 안의 REPO_OWNER / REPO_NAME 을 본인 깃허브로 수정했는지 확인하세요." -ForegroundColor Yellow
    exit 1
}

# 3) 바로가기 생성 (Ctrl+Alt+M 단축키)
$WshShell = New-Object -ComObject WScript.Shell
$desktopLnk = Join-Path $env:USERPROFILE "Desktop\마란런처.lnk"
$startLnk   = Join-Path $env:APPDATA   "Microsoft\Windows\Start Menu\Programs\마란런처.lnk"

foreach ($lnk in @($desktopLnk, $startLnk)) {
    $sc = $WshShell.CreateShortcut($lnk)
    $sc.TargetPath       = $exePath
    $sc.WorkingDirectory = $INSTALL_DIR
    $sc.IconLocation     = "$exePath,0"
    $sc.Hotkey           = "CTRL+ALT+M"
    $sc.WindowStyle      = 1
    $sc.Description      = "맥미니 MARAN 폴더 자동 연결"
    $sc.Save()
}
Write-Host "  [3/3] 단축키 등록      " -NoNewline
Write-Host "✓ Ctrl+Alt+M" -ForegroundColor Green

Write-Host ""
Write-Host "  ✅ 설치 완료." -ForegroundColor Green
Write-Host ""
Write-Host "  실행 위치 : $exePath" -ForegroundColor DarkGray
Write-Host "  단축키    : Ctrl + Alt + M" -ForegroundColor DarkGray
Write-Host "  바로가기  : 바탕화면 / 시작메뉴" -ForegroundColor DarkGray
Write-Host ""

# 4) 즉시 실행 여부
$run = Read-Host "  지금 실행할까요? (Y/n)"
if ($run -ne "n" -and $run -ne "N") {
    Start-Process -FilePath $exePath
    Write-Host "  실행됨. 첫 실행이면 환경 설정 화면이 뜹니다." -ForegroundColor Cyan
}
Write-Host ""
