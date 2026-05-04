# =============================================================
# 마란 런처 GitHub Release 발행 스크립트 (개발자용)
#
# 사전 조건:
#   - GitHub CLI 설치됨 (winget install GitHub.cli)
#   - gh auth login 완료됨
#   - 현재 폴더가 git 저장소 루트 (origin = github.com/<USER>/<REPO>)
#
# 사용법:
#   .\release.ps1                  # 버전 자동 (yyyy.MM.dd)
#   .\release.ps1 -Version v1.2.0  # 명시적 버전
# =============================================================

param(
    [string]$Version = "v$(Get-Date -Format 'yyyy.MM.dd-HHmm')",
    [string]$Notes   = ""
)

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot

Write-Host ""
Write-Host "  M  마란 런처 릴리즈: $Version" -ForegroundColor Cyan
Write-Host ""

# 0) gh CLI 확인
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "  ✗ GitHub CLI(gh) 미설치." -ForegroundColor Red
    Write-Host "    설치: winget install GitHub.cli" -ForegroundColor Yellow
    exit 1
}

# 1) 빌드
Write-Host "  [1/4] PyInstaller 빌드..." -ForegroundColor White
Push-Location $ROOT
try {
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }

    python -m PyInstaller --noconfirm --onefile --noconsole --clean `
        --icon "icon.ico" --name "마란런처" maran_launcher.py | Out-Null

    if (-not (Test-Path "dist\마란런처.exe")) {
        throw "빌드 산출물 없음: dist\마란런처.exe"
    }
    Write-Host "        ✓ dist\마란런처.exe" -ForegroundColor Green
} finally {
    Pop-Location
}

# 2) 릴리즈용 영문 이름으로 복사
$releaseExe = Join-Path $ROOT "dist\maran-launcher.exe"
Copy-Item -Force "$ROOT\dist\마란런처.exe" $releaseExe
Write-Host "  [2/4] 릴리즈 자산 준비   ✓" -ForegroundColor Green

# 3) git 태그 (선택)
$hasTag = git tag --list $Version
if (-not $hasTag) {
    git tag $Version
    git push origin $Version 2>&1 | Out-Null
}
Write-Host "  [3/4] git 태그            ✓ $Version" -ForegroundColor Green

# 4) GitHub Release 생성 + 자산 업로드
# install.ps1 을 i.ps1 로도 복사 (짧은 URL용)
$shortPs1 = Join-Path $ROOT "dist\i.ps1"
Copy-Item -Force "$ROOT\install.ps1" $shortPs1

$assets = @(
    $releaseExe,
    (Join-Path $ROOT "install.ps1"),
    $shortPs1
)
$existsRelease = gh release view $Version 2>$null
if ($existsRelease) {
    Write-Host "  [4/4] 기존 릴리즈에 자산 갱신 중..." -ForegroundColor Yellow
    gh release upload $Version $assets --clobber
} else {
    if (-not $Notes) { $Notes = "Maran Launcher $Version" }
    gh release create $Version $assets --title "Maran Launcher $Version" --notes $Notes
}
Write-Host "  [4/4] GitHub Release 발행 ✓" -ForegroundColor Green

# 결과
$repo = (gh repo view --json nameWithOwner -q .nameWithOwner)
$shortUrl = "github.com/$repo/releases/latest/download/i.ps1"

Write-Host ""
Write-Host "  ✅ 릴리즈 완료." -ForegroundColor Green
Write-Host ""
Write-Host "  외울 명령 (PowerShell):" -ForegroundColor Cyan
Write-Host "    irm $shortUrl | iex" -ForegroundColor White
Write-Host ""
Write-Host "  외울 명령 (cmd):" -ForegroundColor Cyan
Write-Host "    powershell -c `"irm $shortUrl|iex`"" -ForegroundColor White
Write-Host ""
