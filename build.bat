@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ====================================
echo   마란 런처 빌드 스크립트
echo ====================================
echo.

REM --- Python 확인 ---
where python > nul 2>&1
if errorlevel 1 (
    echo [X] Python이 설치되지 않았습니다.
    echo     https://www.python.org/downloads/ 에서 설치하세요.
    echo     설치 시 "Add Python to PATH" 반드시 체크.
    pause
    exit /b 1
)
echo [O] Python 확인됨

REM --- PyInstaller 확인/설치 ---
python -m pip show pyinstaller > nul 2>&1
if errorlevel 1 (
    echo [...] pyinstaller 설치 중...
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet pyinstaller
    if errorlevel 1 (
        echo [X] pyinstaller 설치 실패
        pause
        exit /b 1
    )
)
echo [O] pyinstaller 확인됨

REM --- 이전 빌드 정리 ---
if exist "build" rmdir /s /q "build"
if exist "dist\마란런처.exe" del /q "dist\마란런처.exe"

REM --- 빌드 실행 ---
echo [...] .exe 빌드 중... ^(1~2분 걸림^)
python -m PyInstaller --noconfirm --onefile --noconsole --clean --icon "icon.ico" --name "마란런처" maran_launcher.py
if errorlevel 1 (
    echo [X] 빌드 실패
    pause
    exit /b 1
)

if not exist "dist\마란런처.exe" (
    echo [X] 빌드 산출물을 찾지 못했습니다: dist\마란런처.exe
    pause
    exit /b 1
)

echo [O] 빌드 완료: dist\마란런처.exe
echo.

REM --- 바탕화면 복사 옵션 ---
set /p COPY_TO_DESKTOP="바탕화면에 복사할까요? (y/n): "
if /i "!COPY_TO_DESKTOP!"=="y" (
    copy /Y "dist\마란런처.exe" "%USERPROFILE%\Desktop\마란런처.exe" > nul
    if errorlevel 1 (
        echo [X] 바탕화면 복사 실패
    ) else (
        echo [O] 바탕화면에 복사됨: %USERPROFILE%\Desktop\마란런처.exe
    )
)

echo.
echo 빌드 완료. 아무 키나 누르면 종료합니다.
pause > nul
endlocal
