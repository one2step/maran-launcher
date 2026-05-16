#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
마란 런처
- 첫 실행 시 필수 의존성을 자동 검사하고 누락된 항목을 설치 가이드
- VS Code Remote-SSH 모드 / Terminal SSH 모드 선택해서 맥미니 접속
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path

# === 설정 ===
MAC_HOST = "100.122.161.94"
MAC_USER = "moran"
MAC_PROJECT_PATH = "/Users/moran/MARAN"
MAC_PROJECT_PATH_REMOTE = "~/MARAN"
SSH_PORT = 22
CONNECT_TIMEOUT = 5

# === 자동 업데이트 ===
__version__ = "2.5.12"  # release 태그와 일치시킬 것 (v2.5.12)
GITHUB_REPO = "one2step/maran-launcher"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
INSTALL_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/i.ps1"

# === 파일 드롭존 ===
INBOX_REMOTE_DIR = "~/MARAN/inbox"
OUTBOX_REMOTE_DIR = "~/MARAN/outbox"  # Mac→Windows 방향 (Claude가 올리는 곳)
SHARED_REMOTE_DIR = "~/MARAN/shared"  # NAS 작업 폴더 (사용자가 직접 들락날락)

# === 인박스 업로드 로컬 로그 (사용자 데이터) ===
INBOX_LOG_FILENAME = "inbox_log.json"
INBOX_LOG_MAX = 50            # 디스크에 누적 보관 최대 건수
INBOX_LOG_SHOW = 5            # UI 좌측 패널에 표시할 최근 건수

# === NAS (SMB 공유) ===
SMB_SHARE_NAME = "MARAN"
SMB_PATH_WIN = f"\\\\{MAC_HOST}\\{SMB_SHARE_NAME}"      # \\100.122.161.94\MARAN
SMB_PATH_URL = f"smb://{MAC_HOST}/{SMB_SHARE_NAME}"     # smb://100.122.161.94/MARAN
SMB_PATH_SHARED = f"{SMB_PATH_WIN}\\shared"             # \\100.122.161.94\MARAN\shared
SMB_PATH_OUTBOX = f"{SMB_PATH_WIN}\\outbox"             # \\100.122.161.94\MARAN\outbox

# === DELIVERY (Mac→Windows 결과물 전달) ===
OUTBOX_INDEX_REMOTE = "~/MARAN/outbox/_index.json"
DELIVERY_POLL_MS = 30_000     # 30초마다 ssh로 _index 갱신
DELIVERY_SHOW_COUNT = 5       # UI에 보여줄 최근 항목 수

# === 옵셔널: drag&drop (Windows에서 windnd 있으면 활성) ===
try:
    import windnd  # type: ignore
    HAS_WINDND = True
except Exception:
    HAS_WINDND = False

# === 옵셔널: 클립보드 이미지 (PIL) ===
try:
    from PIL import ImageGrab  # type: ignore
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# === 옵셔널: 트레이 아이콘 (pystray) ===
try:
    import pystray  # type: ignore
    from PIL import Image as PILImage, ImageDraw as PILImageDraw  # type: ignore
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False

# === 단일 인스턴스 socket ===
SINGLE_INSTANCE_PORT = 17239  # 임의 포트, 첫 인스턴스가 점유
SINGLE_INSTANCE_HOST = "127.0.0.1"
TRAY_TITLE = "MARAN.LAUNCH"

# === 색상 (v2.0 Hacker — Mr.Robot/lazygit 톤) ===
COLOR_BG = "#0a0a0a"          # 거의 검정
COLOR_PANEL = "#131313"        # 패널 (한 톤 밝게)
COLOR_PANEL2 = "#1a1a1a"       # 더 밝은 패널
COLOR_BORDER = "#2a2a2a"       # 박스 테두리
COLOR_FG = "#c9d1d9"           # 메인 텍스트
COLOR_DIM = "#4a5263"          # 부차 텍스트
COLOR_DIM2 = "#6a737d"         # 더 옅은 부차
COLOR_OK = "#00ff9c"           # 동작/성공 (네온 그린)
COLOR_WARN = "#ffb800"         # 경고/주의 (앰버)
COLOR_ERROR = "#ff5555"        # 오류 (빨강)
COLOR_INFO = "#5fafff"         # 정보 (사이안)
COLOR_PROGRESS = "#ffb800"

# 모드별 액센트 색 (버튼 텍스트만 색깔, 배경은 패널 톤)
COLOR_ACCENT_VSCODE = "#5fafff"   # 사이안
COLOR_ACCENT_TERM = "#00ff9c"     # 네온 그린
COLOR_ACCENT_LLAMA = "#ffb86c"    # 오렌지 (로컬 LLM — Qwen via Ollama)
COLOR_ACCENT_DANGER = "#ff5555"   # 빨강 (--dangerously-skip-permissions)
COLOR_ACCENT_GEMINI = "#f1fa8c"   # 노랑 (Gemini CLI — 제미나이)
COLOR_ACCENT_PLANET = "#bd93f9"   # 보라 (메인 홈페이지 행성)

# 메인 홈페이지 (PLANET 버튼)
PLANET_URL = "https://maran-chat-2026.web.app"

# 호환성 (기존 코드 이름 유지 — 차후 정리)
COLOR_BTN_VSCODE = COLOR_PANEL2
COLOR_BTN_VSCODE_HOVER = COLOR_BORDER
COLOR_BTN_TERM = COLOR_PANEL2
COLOR_BTN_TERM_HOVER = COLOR_BORDER
COLOR_BTN_INSTALL = COLOR_PANEL2
COLOR_BTN_INSTALL_HOVER = COLOR_BORDER
COLOR_BTN_NEUTRAL = COLOR_PANEL2
COLOR_BTN_NEUTRAL_HOVER = COLOR_BORDER

# === 폰트 (모노스페이스, Cascadia Mono → Consolas → 시스템 폴백) ===
# Tk는 첫 번째 폰트 없으면 자동 폴백
FONT_MONO = ("Cascadia Mono", 10)
FONT_MONO_BOLD = ("Cascadia Mono", 10, "bold")
FONT_MONO_BIG = ("Cascadia Mono", 12, "bold")
FONT_MONO_TINY = ("Cascadia Mono", 8)
FONT_TITLE = ("Cascadia Mono", 13, "bold")
FONT_HEADER = ("Cascadia Mono", 9, "bold")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_CONSOLE = 0x00000010 if os.name == "nt" else 0

_PS_FALLBACK   = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
_SSH_DIR       = r"C:\Windows\System32\OpenSSH"
_SSH_FALLBACK  = rf"{_SSH_DIR}\ssh.exe"


def _find_powershell() -> str:
    return shutil.which("powershell") or _PS_FALLBACK


def _find_ssh() -> str | None:
    found = shutil.which("ssh")
    if found:
        return found
    p = Path(_SSH_FALLBACK)
    return str(p) if p.exists() else None


def _find_openssh_tool(name: str) -> str | None:
    """Find any OpenSSH tool (ssh, scp, ssh-keygen) — same dir as ssh.exe."""
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(_SSH_DIR) / f"{name}.exe"
    return str(candidate) if candidate.exists() else None


def _find_sshkeygen() -> str | None:
    return _find_openssh_tool("ssh-keygen")


def _find_scp() -> str | None:
    return _find_openssh_tool("scp")


def check_ssh_client_installed() -> bool:
    return _find_ssh() is not None


def install_ssh_client(log_fn):
    """OpenSSH Client 3-method install: UAC elevation → winget → settings page."""

    if check_ssh_client_installed():
        return True, "이미 설치됨"

    # ── Method 1: Add-WindowsCapability via UAC-elevated PowerShell ──
    log_fn("방법 1/3: Windows 선택적 기능으로 설치 (UAC 창이 뜨면 '예' 클릭)")
    result_file = Path(tempfile.gettempdir()) / "maran_openssh_result.txt"
    result_file.unlink(missing_ok=True)

    rf_escaped = str(result_file).replace("\\", "\\\\")
    inner = (
        "$cap = Get-WindowsCapability -Online -Name 'OpenSSH.Client*' -EA SilentlyContinue; "
        "if ($cap -and $cap.State -eq 'Installed') { 'OK' | Out-File '" + rf_escaped + "' -Encoding UTF8; exit 0 } "
        "Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 | Out-Null; "
        "if ($?) { 'OK' } else { 'FAIL' } | Out-File '" + rf_escaped + "' -Encoding UTF8"
    )
    inner_tmp = Path(tempfile.gettempdir()) / "maran_openssh_inner.ps1"
    inner_tmp.write_bytes(b"\xef\xbb\xbf" + inner.encode("utf-8"))

    try:
        outer = (
            f"Start-Process powershell -Verb RunAs -Wait "
            f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{inner_tmp}\"'"
        )
        subprocess.run(
            [_find_powershell(), "-NoProfile", "-Command", outer],
            timeout=180, creationflags=CREATE_NO_WINDOW,
        )
        if result_file.exists() and "OK" in result_file.read_text(encoding="utf-8", errors="ignore"):
            _refresh_path_from_registry()
            if check_ssh_client_installed():
                return True, "OpenSSH Client 설치 완료 (선택적 기능)"
    except Exception as e:
        log_fn(f"  방법1 오류: {e}")

    # ── Method 2: winget ──
    log_fn("방법 2/3: winget으로 설치 시도...")
    try:
        ok, msg = winget_install("Microsoft.OpenSSH.Beta", log_fn)
        _refresh_path_from_registry()
        if check_ssh_client_installed():
            return True, "OpenSSH Client 설치 완료 (winget)"
    except Exception as e:
        log_fn(f"  방법2 오류: {e}")

    # ── Method 3: open Settings page ──
    log_fn("방법 3/3: 설정 창 자동 열기 → 수동 설치")
    try:
        subprocess.Popen(
            [_find_powershell(), "-NoProfile", "-Command",
             "Start-Process 'ms-settings:optionalfeatures'"],
            creationflags=CREATE_NO_WINDOW,
        )
        log_fn("  설정 > 앱 > 선택적 기능 > '기능 추가' > 'OpenSSH 클라이언트' 검색 > 설치")
        log_fn("  설치 완료 후 '🔄 새로고침' 클릭")
    except Exception:
        log_fn("  수동: 설정 > 앱 > 선택적 기능 > OpenSSH 클라이언트")
    return False, "수동 설치 후 새로고침 필요"


# ============================================================
# Prereq Check Functions
# ============================================================

def fetch_latest_version():
    """GitHub API에서 latest release tag. 'v1.2.3' → '1.2.3'. 실패시 None.
    네트워크 5초 타임아웃. 백그라운드 스레드에서만 호출할 것."""
    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            RELEASES_API,
            headers={"User-Agent": f"maran-launcher/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
        return (data.get("tag_name") or "").lstrip("v") or None
    except Exception:
        return None


def is_newer_version(latest, current):
    """버전 'a.b.c' 형식 비교. latest > current면 True. 파싱 실패시 False."""
    try:
        ln = [int(x) for x in latest.split(".")[:3]]
        cn = [int(x) for x in current.split(".")[:3]]
        ln += [0] * (3 - len(ln))
        cn += [0] * (3 - len(cn))
        return tuple(ln) > tuple(cn)
    except Exception:
        return False


def check_winget_available():
    return shutil.which("winget") is not None


def check_tailscale_installed():
    if shutil.which("tailscale"):
        return True
    return any(Path(p).exists() for p in [
        r"C:\Program Files\Tailscale\tailscale.exe",
        r"C:\Program Files (x86)\Tailscale\tailscale.exe",
    ])


def check_mac_reachable():
    """Tailscale로 맥미니 TCP 도달 가능?"""
    try:
        with socket.create_connection((MAC_HOST, SSH_PORT), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def _refresh_path_from_registry():
    """winget 설치 후 PATH 변경을 현재 프로세스에 반영."""
    if os.name != "nt":
        return
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as k:
            sys_path = winreg.QueryValueEx(k, "Path")[0]
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            user_path = winreg.QueryValueEx(k, "Path")[0]
        os.environ["PATH"] = sys_path + os.pathsep + user_path
    except Exception:
        pass


def find_code_exe():
    """code.cmd / code / Code.exe 의 실제 경로 반환. PATH·레지스트리·일반 설치 위치 모두 탐색."""
    # 1) 현재 PATH
    for name in ("code.cmd", "code"):
        p = shutil.which(name)
        if p:
            return p

    # 2) PATH를 시스템 레지스트리에서 다시 읽고 재시도 (winget 직후 대비)
    _refresh_path_from_registry()
    for name in ("code.cmd", "code"):
        p = shutil.which(name)
        if p:
            return p

    # 3) 일반 설치 위치 직접 탐색
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd",
        Path(r"C:\Program Files\Microsoft VS Code\bin\code.cmd"),
        Path(r"C:\Program Files (x86)\Microsoft VS Code\bin\code.cmd"),
        # Insiders 빌드도 대응
        Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs" / "Microsoft VS Code Insiders" / "bin" / "code-insiders.cmd",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # 4) 레지스트리에서 vscode 핸들러 경로 추출
    if os.name == "nt":
        try:
            import winreg
            import re as _re
            with winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, r"vscode\shell\open\command"
            ) as k:
                cmd_str = winreg.QueryValueEx(k, "")[0]
            m = _re.match(r'"([^"]+)"', cmd_str)
            if m:
                exe_path = m.group(1)
                # Code.exe → bin/code.cmd 추정
                bin_cmd = Path(exe_path).parent / "bin" / "code.cmd"
                if bin_cmd.exists():
                    return str(bin_cmd)
                if Path(exe_path).exists():
                    return exe_path
        except Exception:
            pass
    return None


def check_vscode_installed():
    return find_code_exe() is not None


def check_remote_ssh_extension():
    """파일 시스템 직접 검사: ~/.vscode/extensions/ 안에 ms-vscode-remote.remote-ssh-* 있는지."""
    ext_root = Path.home() / ".vscode" / "extensions"
    if not ext_root.exists():
        return False
    try:
        for d in ext_root.iterdir():
            if d.is_dir() and d.name.lower().startswith("ms-vscode-remote.remote-ssh"):
                return True
    except OSError:
        pass
    return False


def check_windows_terminal():
    return shutil.which("wt") is not None


def check_ssh_key():
    home = Path.home()
    ssh_dir = home / ".ssh"
    if not ssh_dir.exists():
        return False
    return any((ssh_dir / k).exists() for k in [
        "id_ed25519", "id_rsa", "id_ecdsa"
    ])


def check_ssh_no_password():
    if not check_mac_reachable():
        return False
    ssh = _find_ssh()
    if not ssh:
        return False
    cmd = [
        ssh, "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{MAC_USER}@{MAC_HOST}", "echo", "ok",
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=CONNECT_TIMEOUT + 5,
            creationflags=CREATE_NO_WINDOW,
        )
        return r.returncode == 0 and "ok" in (r.stdout or "")
    except Exception:
        return False


# ============================================================
# Install Action Functions
# 모든 함수는 (success: bool, message: str) 튜플 반환
# ============================================================

def install_winget(log_fn):
    """winget(App Installer) 자체를 자동 설치 시도. PS + AppX."""
    log_fn("winget 자동 설치 시도 중...")

    # 1) 이미 설치된 Microsoft.DesktopAppInstaller 재등록
    try:
        ps1 = (
            "Get-AppxPackage Microsoft.DesktopAppInstaller | "
            "ForEach-Object { Add-AppxPackage -DisableDevelopmentMode "
            "-Register \"$($_.InstallLocation)\\AppXManifest.xml\" }"
        )
        subprocess.run(
            [_find_powershell(), "-NoProfile", "-Command", ps1],
            capture_output=True, text=True, timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        time.sleep(2)
        _refresh_path_from_registry()
        if check_winget_available():
            return True, "winget 활성화됨 (재등록)"
    except Exception:
        pass

    # 2) GitHub releases 에서 latest msixbundle 다운로드 + 설치
    log_fn("Microsoft.DesktopAppInstaller msixbundle 다운로드 중...")
    try:
        ps2 = (
            "$ErrorActionPreference = 'Stop';"
            "$asset = (Invoke-RestMethod 'https://api.github.com/repos/microsoft/winget-cli/releases/latest').assets | "
            "Where-Object { $_.name -like '*.msixbundle' } | Select-Object -First 1;"
            "$tmp = \"$env:TEMP\\winget-installer.msixbundle\";"
            "Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmp -UseBasicParsing;"
            "Add-AppxPackage -Path $tmp;"
            "'OK'"
        )
        r = subprocess.run(
            [_find_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps2],
            capture_output=True, text=True, timeout=300,
            creationflags=CREATE_NO_WINDOW,
        )
        time.sleep(2)
        _refresh_path_from_registry()
        if check_winget_available():
            return True, "winget 설치 완료"
        return False, ((r.stderr or r.stdout) or "")[:300].strip()
    except Exception as e:
        return False, str(e)


def winget_install(package_id, log_fn):
    """winget 으로 패키지 설치. winget 자체가 없으면 자동 설치 후 재시도."""
    if not check_winget_available():
        log_fn("winget 미설치 → 자동 설치 시도")
        ok, msg = install_winget(log_fn)
        if not ok:
            return False, f"winget 설치 실패: {msg}"

    log_fn(f"winget 으로 {package_id} 설치 중... (UAC 창 뜨면 '예' 클릭)")
    try:
        r = subprocess.run(
            ["winget", "install", "--exact", "--id", package_id,
             "--silent", "--accept-source-agreements",
             "--accept-package-agreements"],
            capture_output=True, text=True, timeout=600,
            creationflags=CREATE_NO_WINDOW,
        )
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return True, "설치 완료"
        if "already installed" in out.lower() or "이미 설치" in out:
            return True, "이미 설치됨"
        return False, out[:300].strip()
    except subprocess.TimeoutExpired:
        return False, "타임아웃 (10분 초과)"
    except Exception as e:
        return False, str(e)


def _ps_download(url, out_path, log_fn, timeout=300):
    """PowerShell 로 파일 다운로드. (tls 1.2 + redirect follow)"""
    ps = (
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;"
        f"Invoke-WebRequest -Uri '{url}' -OutFile '{out_path}' -UseBasicParsing"
    )
    r = subprocess.run(
        [_find_powershell(), "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[:200])


def install_tailscale_direct(log_fn):
    """winget 없이 Tailscale 공식 setup.exe 직접 실행."""
    url = "https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe"
    tmp = Path(tempfile.gettempdir()) / "tailscale-setup.exe"
    log_fn(f"Tailscale 직접 다운로드 중...")
    try:
        _ps_download(url, tmp, log_fn, timeout=240)
    except Exception as e:
        return False, f"다운로드 실패: {e}"
    log_fn("설치 마법사 실행. UAC '예' → 화면 따라 [Install].")
    try:
        subprocess.Popen([str(tmp)])
        return True, "설치 마법사 띄움 (수동 진행)"
    except Exception as e:
        return False, str(e)


def install_vscode_direct(log_fn):
    """winget 없이 VS Code User installer 직접 실행 (자동 설치)."""
    url = "https://code.visualstudio.com/sha/download?build=stable&os=win32-x64-user"
    tmp = Path(tempfile.gettempdir()) / "vscode-user-setup.exe"
    log_fn("VS Code User installer 다운로드 중...")
    try:
        _ps_download(url, tmp, log_fn, timeout=300)
    except Exception as e:
        return False, f"다운로드 실패: {e}"

    log_fn("VS Code 자동 설치 중... (1~2분)")
    try:
        r = subprocess.run(
            [str(tmp), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             "/MERGETASKS=!runcode,addcontextmenufiles,addcontextmenufolders,"
             "associatewithfiles,addtopath"],
            timeout=420, creationflags=CREATE_NO_WINDOW,
        )
        _refresh_path_from_registry()
        if r.returncode == 0:
            return True, "설치 완료"
        return False, f"설치 종료 코드 {r.returncode}"
    except Exception as e:
        return False, str(e)


def install_tailscale(log_fn):
    ok, msg = winget_install("Tailscale.Tailscale", log_fn)
    if not ok:
        log_fn(f"winget 경로 실패: {msg}")
        log_fn("→ 공식 설치 파일 직접 다운로드로 폴백")
        ok, msg = install_tailscale_direct(log_fn)
    if ok:
        log_fn("✅ Tailscale 준비됨. 앱에서 로그인이 필요합니다.")
        time.sleep(1)
        open_tailscale_app(log_fn)
    return ok, msg


def install_vscode(log_fn):
    ok, msg = winget_install("Microsoft.VisualStudioCode", log_fn)
    if not ok:
        log_fn(f"winget 경로 실패: {msg}")
        log_fn("→ VS Code 공식 installer 직접 다운로드로 폴백")
        ok, msg = install_vscode_direct(log_fn)
    return ok, msg


def install_windows_terminal(log_fn):
    ok, msg = winget_install("Microsoft.WindowsTerminal", log_fn)
    if ok:
        return ok, msg
    log_fn(f"winget 경로 실패: {msg}")
    log_fn("→ Microsoft Store 페이지 열기 (수동 [받기] 클릭)")
    try:
        # ms-windows-store URL: 9N0DX20HK701 = Windows Terminal
        os.startfile("ms-windows-store://pdp/?productid=9N0DX20HK701")
        return True, "Microsoft Store 열림. [받기] 클릭하세요."
    except Exception:
        try:
            os.startfile("https://aka.ms/terminal")
            return True, "다운로드 페이지 열림. 수동 설치 후 새로고침."
        except Exception as e:
            return False, str(e)


def install_remote_ssh_extension(log_fn):
    """VS Code의 Remote-SSH 확장 페이지를 직접 띄움. 사용자가 [Install] 클릭."""
    if not check_vscode_installed():
        return False, "VS Code 먼저 설치 필요"

    url = "vscode:extension/ms-vscode-remote.remote-ssh"

    # 방법 1: os.startfile (Windows ShellExecute, vscode:// 핸들러 호출)
    try:
        os.startfile(url)
        log_fn("VS Code 확장 페이지를 열었습니다.")
        log_fn("→ VS Code 화면에서 [Install] 버튼 클릭")
        log_fn("→ 마란 런처로 돌아와서 '🔄 새로고침' 클릭")
        return True, "VS Code에서 [Install] 클릭 → 새로고침"
    except Exception:
        pass

    # 방법 2: cmd /c start 폴백
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", url],
            creationflags=CREATE_NO_WINDOW,
        )
        log_fn("VS Code 확장 페이지를 열었습니다.")
        log_fn("→ VS Code 화면에서 [Install] 버튼 클릭")
        log_fn("→ 마란 런처로 돌아와서 '🔄 새로고침' 클릭")
        return True, "VS Code에서 [Install] 클릭 → 새로고침"
    except Exception as e:
        return False, f"VS Code 실행 실패: {e}"


def _open_smb_path(path, log_fn=None):
    """공통: Windows 탐색기로 SMB 경로 열기."""
    if os.name != "nt":
        return False, "Windows 전용 (Mac에선 Finder → Cmd+K → smb://100.122.161.94)"
    try:
        os.startfile(path)
        if log_fn:
            log_fn(f"탐색기에서 {path} 열림")
        return True, f"탐색기 열림: {path}"
    except Exception as e:
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", path],
                creationflags=CREATE_NO_WINDOW,
            )
            return True, "탐색기 열림 (cmd 폴백)"
        except Exception as e2:
            return False, f"실패: {e} / {e2}"


def open_smb_folder(log_fn=None):
    """\\\\100.122.161.94\\MARAN 전체 열기."""
    return _open_smb_path(SMB_PATH_WIN, log_fn)


def open_smb_shared(log_fn=None):
    """\\\\100.122.161.94\\MARAN\\shared 만 열기 (NAS 작업 폴더)."""
    return _open_smb_path(SMB_PATH_SHARED, log_fn)


def open_smb_outbox(log_fn=None):
    """\\\\100.122.161.94\\MARAN\\outbox 만 열기 (Mac→Windows 결과물)."""
    return _open_smb_path(SMB_PATH_OUTBOX, log_fn)


def smb_path_for_outbox_rel(rel_path):
    """rel_path('테스트프로젝트/2026-..._foo.pdf') → SMB Windows 경로."""
    win_rel = rel_path.replace("/", "\\")
    return f"{SMB_PATH_OUTBOX}\\{win_rel}"


def open_explorer_select(file_path):
    """탐색기에서 그 파일이 선택된 상태로 폴더 열기. Windows /select 옵션."""
    if os.name != "nt":
        return False
    try:
        # /select, 다음 인자에 공백 없이 파일경로
        subprocess.Popen(
            ["explorer.exe", f"/select,{file_path}"],
            creationflags=CREATE_NO_WINDOW,
        )
        return True
    except Exception:
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", "explorer.exe", f"/select,{file_path}"],
                creationflags=CREATE_NO_WINDOW,
            )
            return True
        except Exception:
            return False


def open_file_default_app(file_path):
    """파일을 Windows 기본 앱으로 직접 열기."""
    if os.name != "nt":
        return False
    try:
        os.startfile(file_path)
        return True
    except Exception:
        return False


def fetch_outbox_index():
    """Mac mini의 ~/MARAN/outbox/_index.json을 SSH로 읽어옴.
    실패하면 빈 리스트. 30초마다 호출."""
    if not check_ssh_no_password():
        return []
    try:
        r = subprocess.run(
            [_find_ssh(), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             f"{MAC_USER}@{MAC_HOST}",
             f"cat {OUTBOX_INDEX_REMOTE} 2>/dev/null || echo '[]'"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        import json
        data = json.loads(r.stdout)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def get_smb_address_text():
    """클립보드 복사용 SMB 주소 (Windows 형식 + URL 형식 둘 다)."""
    return f"{SMB_PATH_WIN}\n{SMB_PATH_URL}"


def trigger_self_update(log_fn=None):
    """자동 업데이트: 임시 PowerShell 스크립트 → 현재 런처 종료 → 새 .exe 다운로드 → 새 런처 실행.
    install.ps1이 MARAN_QUIET=1 환경변수 보면 자동 모드로 동작 (Read-Host 스킵)."""
    if os.name != "nt":
        return False, "Windows 전용"

    script = f"""
$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.WindowTitle = 'MARAN.LAUNCH auto-update'

Write-Host ''
Write-Host '  M  Maran Launcher - Auto Update' -ForegroundColor Cyan
Write-Host '  --------------------------------' -ForegroundColor DarkGray
Write-Host ''

Write-Host '  [1/3] Closing current launcher... ' -NoNewline
Get-Process -Name 'MaranLauncher' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1000
Write-Host 'OK' -ForegroundColor Green
Write-Host ''

Write-Host '  [2/3] Downloading + installing latest...' -ForegroundColor White
$env:MARAN_QUIET = '1'
try {{
    irm {INSTALL_URL} | iex
}} catch {{
    Write-Host ''
    Write-Host '  [!] Update failed: ' -NoNewline -ForegroundColor Red
    Write-Host $_
    Write-Host '  Press any key to close this window...' -ForegroundColor DarkGray
    [void][System.Console]::ReadKey($true)
    exit 1
}}

Write-Host ''
Write-Host '  [3/3] Done. New launcher started.' -ForegroundColor Green
Write-Host '  This window closes in 3 seconds.' -ForegroundColor DarkGray
Start-Sleep -Seconds 3
"""

    tmp = Path(tempfile.gettempdir()) / "maran_self_update.ps1"
    # PS 5.1 한글 인코딩 회피 위해 UTF-8 BOM
    tmp.write_bytes(b"\xef\xbb\xbf" + script.encode("utf-8"))

    try:
        subprocess.Popen(
            [_find_powershell(), "-ExecutionPolicy", "Bypass", "-File", str(tmp)],
            creationflags=CREATE_NEW_CONSOLE,
        )
        if log_fn:
            log_fn("자동 업데이트 시작 — 새 PowerShell 창에서 진행, 끝나면 새 런처 자동 실행")
        return True, "업데이터 시작됨"
    except Exception as e:
        return False, str(e)


def ensure_inbox_dir():
    """Mac mini에 ~/MARAN/inbox/ + ~/MARAN/outbox/ + ~/MARAN/shared/ 폴더 보장."""
    try:
        subprocess.run(
            [_find_ssh(), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             f"{MAC_USER}@{MAC_HOST}",
             f"mkdir -p {INBOX_REMOTE_DIR} {OUTBOX_REMOTE_DIR} {SHARED_REMOTE_DIR}"],
            capture_output=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return True
    except Exception:
        return False


def _user_data_dir():
    """런처가 사용자 데이터(인박스 로그 등)를 저장하는 폴더.
    Windows: %LOCALAPPDATA%\\MaranLauncher
    macOS/Linux: ~/.maran_launcher (개발 환경 호환)
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "MaranLauncher"
    return Path(os.path.expanduser("~")) / ".maran_launcher"


def _inbox_log_path():
    return _user_data_dir() / INBOX_LOG_FILENAME


def log_inbox_upload(name, source="file"):
    """업로드 성공 후 호출. inbox_log.json 에 한 줄 추가 (최대 INBOX_LOG_MAX)."""
    import json
    try:
        path = _inbox_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        if path.exists():
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(entries, list):
                    entries = []
            except Exception:
                entries = []
        entries.append({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "name": Path(name).name,
            "source": source,  # file / clipboard / drop
        })
        entries = entries[-INBOX_LOG_MAX:]
        path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def read_inbox_log(n=INBOX_LOG_SHOW):
    """최근 n 건을 최신이 위로 오게 반환."""
    import json
    try:
        path = _inbox_log_path()
        if not path.exists():
            return []
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            return []
        return list(reversed(entries[-n:]))
    except Exception:
        return []


def upload_file_to_mac(local_path, log_fn=None, source="file"):
    """scp로 로컬 파일을 Mac mini의 ~/MARAN/inbox/ 에 업로드."""
    p = Path(local_path)
    if not p.exists() or not p.is_file():
        return False, f"파일 없음: {local_path}"

    if not check_mac_reachable():
        return False, "Mac mini 도달 불가 (Tailscale 점검)"

    scp = _find_scp()
    if not scp:
        return False, "scp 없음. OpenSSH 클라이언트 설치 필요"
    target = f"{MAC_USER}@{MAC_HOST}:{INBOX_REMOTE_DIR}/"
    try:
        ensure_inbox_dir()
        r = subprocess.run(
            [scp, "-B", "-o", "ConnectTimeout=10", str(p), target],
            capture_output=True, text=True, timeout=180,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            log_inbox_upload(p.name, source=source)
            return True, f"업로드 완료: {p.name}"
        return False, (r.stderr or r.stdout or "scp 실패")[:200].strip()
    except Exception as e:
        return False, str(e)


def upload_clipboard_to_mac(log_fn=None):
    """Windows 클립보드 → Mac inbox.
    이미지면 PNG로 저장 후 업로드. 파일 경로 리스트면 각각 업로드.
    텍스트는 .txt로 저장 후 업로드."""
    if not HAS_PIL:
        return False, "Pillow 미설치 (이미지 클립보드 지원 안 됨)"

    try:
        clip = ImageGrab.grabclipboard()
    except Exception as e:
        return False, f"클립보드 읽기 실패: {e}"

    # 1) 파일 경로 리스트 (Windows에서 파일 복사 → 클립보드)
    if isinstance(clip, list):
        if not clip:
            return False, "클립보드에 파일 없음"
        ok_count = 0
        msgs = []
        for fp in clip:
            ok, msg = upload_file_to_mac(fp, log_fn, source="clipboard")
            if ok:
                ok_count += 1
            msgs.append(f"{Path(fp).name}: {msg}")
        return ok_count > 0, f"{ok_count}/{len(clip)} 업로드. " + " | ".join(msgs[:3])

    # 2) PIL 이미지 (스크린샷 또는 그림판 복사)
    if clip is not None and hasattr(clip, "save"):
        ts = time.strftime("%Y%m%d_%H%M%S")
        tmp = Path(tempfile.gettempdir()) / f"maran_clip_{ts}.png"
        try:
            clip.save(str(tmp), "PNG")
        except Exception as e:
            return False, f"이미지 저장 실패: {e}"
        return upload_file_to_mac(str(tmp), log_fn, source="clipboard")

    # 3) 텍스트 폴백 (PIL.ImageGrab은 텍스트 안 줌 → tkinter clipboard 사용)
    return False, "클립보드에 이미지/파일 없음 (텍스트는 미지원)"


def upload_clipboard_text_to_mac(text, log_fn=None):
    """tkinter clipboard로 받은 텍스트 → .txt 파일로 업로드."""
    if not text or not text.strip():
        return False, "빈 텍스트"
    ts = time.strftime("%Y%m%d_%H%M%S")
    tmp = Path(tempfile.gettempdir()) / f"maran_clip_{ts}.txt"
    try:
        tmp.write_text(text, encoding="utf-8")
    except Exception as e:
        return False, f"텍스트 저장 실패: {e}"
    return upload_file_to_mac(str(tmp), log_fn, source="clipboard")


def open_tailscale_app(log_fn):
    candidates = [
        r"C:\Program Files\Tailscale\Tailscale.exe",
        r"C:\Program Files (x86)\Tailscale\Tailscale.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tailscale" / "Tailscale.exe"),
        shutil.which("Tailscale") or "",
        shutil.which("tailscale") or "",
    ]
    for p in candidates:
        if p and Path(p).exists():
            try:
                subprocess.Popen([p])
                log_fn("Tailscale 앱 실행됨. 로그인 후 '🔄 새로고침' 클릭하세요.")
                return True, "Tailscale 앱 띄움"
            except Exception:
                pass
    # Fallback: open via shell protocol
    try:
        os.startfile("tailscale:")
        log_fn("Tailscale 앱 실행됨 (쉘 프로토콜). 로그인 후 새로고침.")
        return True, "Tailscale 앱 띄움"
    except Exception:
        pass
    log_fn("Tailscale 실행 실패. 설치를 먼저 완료하세요.")
    return False, "Tailscale 실행 불가 — 설치 후 재시도"


def generate_ssh_key(log_fn):
    keygen = _find_sshkeygen()
    if not keygen:
        log_fn("ssh-keygen 없음 → OpenSSH 클라이언트 먼저 설치하세요")
        return False, "OpenSSH 클라이언트 미설치 (위 단계 먼저)"
    home = Path.home()
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(exist_ok=True)
    key_path = ssh_dir / "id_ed25519"
    if key_path.exists():
        log_fn(f"SSH 키 이미 존재: {key_path}")
        return True, "이미 존재"
    log_fn(f"SSH 키 생성 중: {key_path}")
    try:
        r = subprocess.run(
            [keygen, "-t", "ed25519", "-f", str(key_path), "-N", ""],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            return True, "생성 완료"
        return False, (r.stderr or r.stdout or "")[:200]
    except Exception as e:
        return False, str(e)


def push_ssh_key_to_mac(log_fn):
    pub = Path.home() / ".ssh" / "id_ed25519.pub"
    if not pub.exists():
        return False, "공개키 없음. 먼저 'SSH 키 생성'을 눌러주세요."
    if not check_mac_reachable():
        return False, "맥미니 도달 불가. Tailscale 로그인을 먼저 완료하세요."

    # PowerShell 스크립트 생성 (ASCII only, PS 5.1 호환).
    # echo '<key>' >> 방식: pipe 인코딩 이슈 회피.
    ssh_exe = _find_ssh() or _SSH_FALLBACK
    pub_path_safe = str(pub).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
Write-Host ''

# Find ssh.exe (OpenSSH Client)
$sshExe = $null
foreach ($candidate in @('{ssh_exe}', "$env:SystemRoot\\System32\\OpenSSH\\ssh.exe")) {{
    if (Test-Path $candidate) {{ $sshExe = $candidate; break }}
}}
if (-not $sshExe) {{
    $found = Get-Command ssh -ErrorAction SilentlyContinue
    if ($found) {{ $sshExe = $found.Source }}
}}
if (-not $sshExe) {{
    Write-Host '[ERR] ssh.exe not found.' -ForegroundColor Red
    Write-Host '      Install: Settings > Apps > Optional features > OpenSSH Client' -ForegroundColor DarkGray
    Write-Host '      Or run:  Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0' -ForegroundColor DarkGray
    Read-Host 'Press Enter to close'; exit 1
}}
Write-Host "  ssh: $sshExe" -ForegroundColor DarkGray
Write-Host ''
Write-Host 'Enter Mac password ONCE when prompted.' -ForegroundColor Yellow
Write-Host '(After this, SSH will work without password.)' -ForegroundColor DarkGray
Write-Host ''

$pub = (Get-Content -LiteralPath '{pub_path_safe}' -Raw).Trim()
$cmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pub' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

& $sshExe -o StrictHostKeyChecking=accept-new {MAC_USER}@{MAC_HOST} $cmd
$ok = $LASTEXITCODE -eq 0

Write-Host ''
if ($ok) {{
    Write-Host '[OK] Registered. Click Refresh in Maran Launcher.' -ForegroundColor Green
}} else {{
    Write-Host '[FAIL] Registration failed.' -ForegroundColor Red
    Write-Host '       Check: password correct? Mac reachable via Tailscale?' -ForegroundColor DarkGray
}}
Write-Host ''
Read-Host 'Press Enter to close'
""".strip()

    tmp = Path(tempfile.gettempdir()) / "maran_push_key.ps1"
    # UTF-8 with BOM 으로 저장 → PS 5.1이 인코딩 정확히 인식
    tmp.write_bytes(b"\xef\xbb\xbf" + script.encode("utf-8"))

    try:
        subprocess.Popen(
            [_find_powershell(), "-NoExit", "-ExecutionPolicy", "Bypass",
             "-File", str(tmp)],
            creationflags=CREATE_NEW_CONSOLE,
        )
        log_fn("새 PowerShell 창에서 비밀번호 1회 입력 → 닫고 '새로고침' 클릭.")
        return True, "PowerShell 창 띄움"
    except Exception as e:
        return False, str(e)


# ============================================================
# UI Components
# ============================================================

class StatusRow:
    """레거시: 진행 상태 ○/◐/●/✗ (SetupView에서만 사용)"""

    def __init__(self, parent, label_text):
        self.frame = tk.Frame(parent, bg=COLOR_BG)
        self.icon = tk.Label(
            self.frame, text="○", font=("Segoe UI Symbol", 14),
            fg=COLOR_DIM, bg=COLOR_BG, width=2,
        )
        self.icon.pack(side=tk.LEFT, padx=(0, 10))
        self.label = tk.Label(
            self.frame, text=label_text, font=("맑은 고딕", 11),
            fg=COLOR_FG, bg=COLOR_BG, anchor="w",
        )
        self.label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def pack(self, **kw): self.frame.pack(**kw)
    def pending(self): self.icon.config(text="○", fg=COLOR_DIM)
    def progress(self): self.icon.config(text="◐", fg=COLOR_PROGRESS)
    def ok(self): self.icon.config(text="●", fg=COLOR_OK)
    def error(self): self.icon.config(text="✗", fg=COLOR_ERROR)


class HackerStatusRow:
    """v2.0 모노스페이스 한 줄: '▸ tailscale ........... ● ACTIVE'"""

    LABEL_W = 18  # name 영역 폭 (도트 패딩 포함)

    def __init__(self, parent, name):
        self.name = name
        self.frame = tk.Frame(parent, bg=COLOR_BG)

        # 좌측: ▸ name ........
        dots = "." * max(0, self.LABEL_W - len(name))
        self.left = tk.Label(
            self.frame,
            text=f"  ▸ {name} {dots}",
            font=FONT_MONO, fg=COLOR_DIM2, bg=COLOR_BG,
            anchor="w",
        )
        self.left.pack(side=tk.LEFT)

        # 우측: ● STATUS
        self.icon = tk.Label(
            self.frame, text="●",
            font=FONT_MONO_BOLD, fg=COLOR_DIM, bg=COLOR_BG,
        )
        self.icon.pack(side=tk.LEFT, padx=(2, 4))

        self.status_text = tk.Label(
            self.frame, text="STANDBY",
            font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_BG,
        )
        self.status_text.pack(side=tk.LEFT)

        # 호환용 alias (기존 코드가 self.s_run.label 식 참조)
        self.label = self.left

    def pack(self, **kw): self.frame.pack(**kw)
    def pending(self):
        self.icon.config(fg=COLOR_DIM)
        self.status_text.config(text="STANDBY", fg=COLOR_DIM)
    def progress(self):
        self.icon.config(fg=COLOR_WARN)
        self.status_text.config(text="WORKING", fg=COLOR_WARN)
    def ok(self):
        self.icon.config(fg=COLOR_OK)
        self.status_text.config(text="ACTIVE", fg=COLOR_OK)
    def error(self):
        self.icon.config(fg=COLOR_ERROR)
        self.status_text.config(text="ERROR", fg=COLOR_ERROR)


class PrereqRow:
    """Setup view용: prereq 상태 + 액션 버튼"""

    def __init__(self, parent, name, check_fn, install_fn=None,
                 action_label="설치", required=True):
        self.name = name
        self.check_fn = check_fn
        self.install_fn = install_fn
        self.action_label = action_label
        self.required = required

        self.frame = tk.Frame(parent, bg=COLOR_BG)
        self.icon = tk.Label(
            self.frame, text="○", font=("Segoe UI Symbol", 13),
            fg=COLOR_DIM, bg=COLOR_BG, width=2,
        )
        self.icon.pack(side=tk.LEFT, padx=(0, 8))

        self.label = tk.Label(
            self.frame, text=name, font=("맑은 고딕", 10),
            fg=COLOR_FG, bg=COLOR_BG, anchor="w",
        )
        self.label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.button = tk.Button(
            self.frame, text=action_label, font=("맑은 고딕", 9),
            bg=COLOR_BTN_INSTALL, fg=COLOR_FG,
            activebackground=COLOR_BTN_INSTALL_HOVER, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            padx=12, pady=2, width=10,
        )
        if install_fn:
            self.button.pack(side=tk.RIGHT, padx=4)

    def pack(self, **kw): self.frame.pack(**kw)

    def set_command(self, cmd):
        self.button.config(command=cmd)

    def refresh(self):
        ok = self.check_fn()
        if ok:
            self.icon.config(text="✓", fg=COLOR_OK)
            self.button.config(
                state=tk.DISABLED, text="OK",
                bg=COLOR_OK, fg="#1e1e2e",
                disabledforeground="#1e1e2e",
            )
        else:
            self.icon.config(
                text="✗" if self.required else "⚠",
                fg=COLOR_ERROR if self.required else COLOR_WARN,
            )
            self.button.config(
                state=tk.NORMAL, text=self.action_label,
                bg=COLOR_BTN_INSTALL, fg=COLOR_FG,
            )
        return ok

    def set_busy(self):
        self.icon.config(text="◐", fg=COLOR_PROGRESS)
        self.button.config(state=tk.DISABLED, text="...")


# ============================================================
# Setup View
# ============================================================

class SetupView:
    def __init__(self, parent, on_continue):
        self.on_continue = on_continue
        self.frame = tk.Frame(parent, bg=COLOR_BG)
        self.rows = {}
        self._drag_x = self._drag_y = 0
        self._build()
        self.frame.after(0, lambda: self._bind_drag_recursive(self.frame))

    def pack(self, **kw): self.frame.pack(**kw)
    def pack_forget(self): self.frame.pack_forget()

    def _drag_start(self, event):
        root = self.frame.master
        self._drag_x = event.x_root - root.winfo_x()
        self._drag_y = event.y_root - root.winfo_y()

    def _drag_move(self, event):
        try:
            root = self.frame.master
            root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")
        except Exception:
            pass

    def _bind_drag_recursive(self, widget):
        if not isinstance(widget, tk.Button):
            widget.bind("<ButtonPress-1>", self._drag_start, add="+")
            widget.bind("<B1-Motion>",     self._drag_move,  add="+")
        for child in widget.winfo_children():
            self._bind_drag_recursive(child)

    def _build(self):
        tk.Label(
            self.frame, text="🔧  환경 설정",
            font=("맑은 고딕", 16, "bold"),
            fg=COLOR_FG, bg=COLOR_BG,
        ).pack(pady=(20, 4))
        tk.Label(
            self.frame,
            text="필수 항목(✗)을 모두 ✓로 만들면 메인 화면으로 진행할 수 있습니다.",
            font=("맑은 고딕", 9),
            fg=COLOR_DIM, bg=COLOR_BG,
        ).pack(pady=(0, 14))

        rows_frame = tk.Frame(self.frame, bg=COLOR_BG)
        rows_frame.pack(fill=tk.X, padx=30, pady=2)

        # (key, name, check_fn, install_fn, label, required)
        prereq_defs = [
            ("tailscale_install", "Tailscale 설치",
             check_tailscale_installed, install_tailscale, "설치", True),
            ("tailscale_login", "Tailscale 로그인 (맥미니 도달)",
             check_mac_reachable, open_tailscale_app, "Tailscale 열기", True),
            ("openssh", "OpenSSH 클라이언트 (ssh.exe)",
             check_ssh_client_installed, install_ssh_client, "설치", True),
            ("ssh_key", "SSH 키 생성",
             check_ssh_key, generate_ssh_key, "생성", True),
            ("ssh_no_pw", "맥미니 무비번 SSH",
             check_ssh_no_password, push_ssh_key_to_mac, "등록", True),
            ("vscode", "VS Code 설치 (옵션)",
             check_vscode_installed, install_vscode, "설치", False),
            ("remote_ssh", "VS Code Remote-SSH 확장 (옵션)",
             check_remote_ssh_extension, install_remote_ssh_extension,
             "VS Code 열기", False),
            ("wt", "Windows Terminal (옵션)",
             check_windows_terminal, install_windows_terminal, "설치", False),
        ]

        for key, name, cf, inf, lbl, req in prereq_defs:
            row = PrereqRow(rows_frame, name, cf, inf, lbl, req)
            row.set_command(lambda r=row, fn=inf: self._action(r, fn))
            row.pack(fill=tk.X, pady=3)
            self.rows[key] = row

        # 컨트롤 버튼
        btns = tk.Frame(self.frame, bg=COLOR_BG)
        btns.pack(pady=(14, 8))

        tk.Button(
            btns, text="🔄 새로고침",
            font=("맑은 고딕", 10),
            bg=COLOR_BTN_NEUTRAL, fg=COLOR_FG,
            activebackground=COLOR_BTN_NEUTRAL_HOVER,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.refresh_all,
            padx=14, pady=6,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btns, text="🚀 모두 자동 설치",
            font=("맑은 고딕", 10, "bold"),
            bg=COLOR_BTN_INSTALL, fg=COLOR_OK,
            activebackground=COLOR_BTN_INSTALL_HOVER, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.install_all,
            padx=14, pady=6,
        ).pack(side=tk.LEFT, padx=4)

        self.continue_btn = tk.Button(
            btns, text="메인으로  ➜",
            font=("맑은 고딕", 10, "bold"),
            bg=COLOR_BTN_VSCODE, fg=COLOR_FG,
            activebackground=COLOR_BTN_VSCODE_HOVER, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.on_continue,
            padx=14, pady=6,
        )
        self.continue_btn.pack(side=tk.LEFT, padx=4)

        # 로그 박스
        log_frame = tk.Frame(self.frame, bg=COLOR_PANEL)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=(6, 14))

        self.log_text = tk.Text(
            log_frame, font=("Consolas", 9),
            bg=COLOR_PANEL, fg=COLOR_DIM,
            relief=tk.FLAT, bd=0, height=8, wrap=tk.WORD,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.log_text.insert(
            tk.END,
            "준비됨. 항목별 버튼 또는 '🚀 모두 자동 설치'로 시작하세요.\n"
            "Tailscale 로그인과 SSH 키 등록은 사용자 입력이 필요합니다.\n",
        )
        self.log_text.config(state=tk.DISABLED)

    def log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.frame.update_idletasks()

    def refresh_all(self):
        all_required_ok = True
        for key, row in self.rows.items():
            ok = row.refresh()
            if row.required and not ok:
                all_required_ok = False

        if all_required_ok:
            self.continue_btn.config(text="✅ 메인으로  ➜", bg=COLOR_OK,
                                     fg="#0a0a0a", activeforeground="#0a0a0a")
        else:
            self.continue_btn.config(text="메인으로  ➜", bg=COLOR_BTN_VSCODE,
                                     fg=COLOR_FG)
        return all_required_ok

    def _action(self, row, install_fn):
        threading.Thread(
            target=self._action_thread, args=(row, install_fn), daemon=True,
        ).start()

    def _action_thread(self, row, install_fn):
        row.set_busy()
        self.log(f"\n--- {row.name} ---")
        try:
            result = install_fn(self.log)
            if isinstance(result, tuple):
                ok, msg = result
            else:
                ok, msg = bool(result), ""
            self.log(("✅ " if ok else "❌ ") + f"{row.name}: {msg or ('완료' if ok else '실패')}")
        except Exception as e:
            self.log(f"❌ {row.name}: {e}")
        time.sleep(1)
        self.refresh_all()

    def install_all(self):
        threading.Thread(target=self._install_all_thread, daemon=True).start()

    def _run_step(self, key, fn):
        """단일 prereq 실행. (ok, msg) 반환."""
        row = self.rows.get(key)
        if row and row.check_fn():
            self.log(f"  ⏭  {row.name}: 이미 OK")
            return True, "OK"
        if row:
            row.set_busy()
        self.log(f"\n▶ {row.name if row else key}")
        try:
            result = fn(self.log)
            ok, msg = result if isinstance(result, tuple) else (bool(result), "")
            self.log(("  ✅ " if ok else "  ❌ ") + (msg or ("완료" if ok else "실패")))
            return ok, msg
        except Exception as e:
            self.log(f"  ❌ 오류: {e}")
            return False, str(e)

    def _install_all_thread(self):
        self.log("\n══════════════════════════════════")
        self.log("  🚀 원클릭 전체 설치 시작")
        self.log("══════════════════════════════════")

        # ── Phase 1: 완전 자동 (UAC만 클릭) ──
        self.log("\n[ Phase 1 / 3 ]  자동 설치 (UAC 창 뜨면 '예' 클릭)")

        self._run_step("tailscale_install", install_tailscale)
        self._run_step("openssh",           install_ssh_client)

        # OpenSSH 설치 후 PATH 갱신
        _refresh_path_from_registry()

        self._run_step("ssh_key",           generate_ssh_key)
        self._run_step("vscode",            install_vscode)
        self._run_step("wt",                install_windows_terminal)
        self._run_step("remote_ssh",        install_remote_ssh_extension)

        self.refresh_all()

        # ── Phase 2: Tailscale 로그인 대기 ──
        self.log("\n[ Phase 2 / 3 ]  Tailscale 로그인")
        if not check_mac_reachable():
            open_tailscale_app(self.log)
            self.log("  ⏳ 맥미니 연결 대기 중... (로그인 완료 후 자동 진행)")
            for _ in range(60):          # 최대 2분 대기
                time.sleep(2)
                if check_mac_reachable():
                    self.log("  ✅ 맥미니 연결됨!")
                    break
            else:
                self.log("  ⚠  2분 안에 연결 안 됨. '새로고침' 후 '등록' 직접 클릭하세요.")
                self.refresh_all()
                return
        else:
            self.log("  ⏭  맥미니 이미 연결됨")

        # ── Phase 3: SSH 키 등록 (비번 1회) ──
        self.log("\n[ Phase 3 / 3 ]  맥미니 무비번 SSH 등록")
        if check_ssh_no_password():
            self.log("  ⏭  이미 무비번 SSH OK")
        else:
            self.log("  → PowerShell 창이 열립니다. 맥 비밀번호 1회 입력 후 Enter.")
            self._run_step("ssh_no_pw", push_ssh_key_to_mac)
            # 최대 3분 대기 (PS 창에서 비번 입력 대기)
            self.log("  ⏳ 비밀번호 입력 완료 대기 중... (창 닫히면 자동 진행)")
            for _ in range(90):
                time.sleep(2)
                if check_ssh_no_password():
                    self.log("  ✅ 무비번 SSH 등록 완료!")
                    break
            else:
                self.log("  ⚠  3분 초과. '새로고침' 후 상태 확인하세요.")

        self.log("\n══════════════════════════════════")
        self.log("  설치 완료. '메인으로 ➜' 클릭!")
        self.log("══════════════════════════════════\n")
        self.refresh_all()


# ============================================================
# Main View
# ============================================================

class MainView:
    def __init__(self, parent, on_setup=None):
        self.on_setup = on_setup
        self._auto_pending = None
        self.frame = tk.Frame(parent, bg=COLOR_BG)
        self._build()
        # 백그라운드 업데이트 체크 (UI 블록 X)
        threading.Thread(target=self._check_update_async, daemon=True).start()

    def pack(self, **kw):
        self.frame.pack(**kw)
        if self._auto_pending:
            mode = self._auto_pending
            self._auto_pending = None
            self.frame.after(300, lambda: self.start(mode))

    def pack_forget(self): self.frame.pack_forget()

    def schedule_auto(self, mode):
        self._auto_pending = mode

    def _build(self):
        # ════════════════════════════════════════════════════════
        # HEADER — MARAN.LAUNCH v1.x.y / TARGET / setup btn / [_][×]
        # 헤더 영역 자체가 창 드래그 핸들 (frameless 모드용)
        # ════════════════════════════════════════════════════════
        header = tk.Frame(self.frame, bg=COLOR_BG)
        header.pack(fill=tk.X, padx=14, pady=(10, 0))

        title_left = tk.Frame(header, bg=COLOR_BG)
        title_left.pack(side=tk.LEFT)
        title_label = tk.Label(
            title_left, text="MARAN.LAUNCH",
            font=FONT_TITLE, fg=COLOR_OK, bg=COLOR_BG,
        )
        title_label.pack(side=tk.LEFT)
        version_label = tk.Label(
            title_left, text=f"  v{__version__}",
            font=FONT_MONO, fg=COLOR_DIM2, bg=COLOR_BG,
        )
        version_label.pack(side=tk.LEFT, padx=(2, 0))

        # 우상단 윈도우 컨트롤 (오른쪽부터 배치)
        # [×] 트레이로
        tk.Button(
            header, text="[×]",
            font=FONT_MONO_BOLD, fg=COLOR_ERROR, bg=COLOR_BG,
            activebackground=COLOR_BG, activeforeground="#ff8888",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._on_close_to_tray,
        ).pack(side=tk.RIGHT, padx=(2, 0))

        # [_] 작업표시줄로 최소화
        tk.Button(
            header, text="[_]",
            font=FONT_MONO_BOLD, fg=COLOR_DIM, bg=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_FG,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._on_minimize,
        ).pack(side=tk.RIGHT, padx=(2, 0))

        # [⚙ setup]
        tk.Button(
            header, text="[⚙ setup]",
            font=FONT_MONO, fg=COLOR_DIM, bg=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.on_setup if self.on_setup else lambda: None,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        # 헤더 드래그 핸들러 (frameless 창 이동)
        for w in (header, title_left, title_label, version_label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # TARGET line
        target_bar = tk.Frame(self.frame, bg=COLOR_BG)
        target_bar.pack(fill=tk.X, padx=14, pady=(2, 8))
        tk.Label(
            target_bar, text=f"TARGET: {MAC_USER}@{MAC_HOST}",
            font=FONT_MONO, fg=COLOR_DIM2, bg=COLOR_BG,
        ).pack(side=tk.LEFT)
        self.conn_state = tk.Label(
            target_bar, text="● CHECKING",
            font=FONT_MONO_BOLD, fg=COLOR_DIM, bg=COLOR_BG,
        )
        self.conn_state.pack(side=tk.RIGHT)

        # 구분선
        self._sep(self.frame)

        # ════════════════════════════════════════════════════════
        # STATUS — Tailscale / SSH / 실행 라이브 상태
        # ════════════════════════════════════════════════════════
        self._section_header(self.frame, "STATUS")
        status_box = tk.Frame(self.frame, bg=COLOR_BG)
        status_box.pack(fill=tk.X, padx=20, pady=(2, 4))
        self.s_tail = HackerStatusRow(status_box, "tailscale")
        self.s_tail.pack(fill=tk.X, pady=1)
        self.s_mac = HackerStatusRow(status_box, "ssh-agent")
        self.s_mac.pack(fill=tk.X, pady=1)
        self.s_run = HackerStatusRow(status_box, "exec")
        self.s_run.pack(fill=tk.X, pady=1)

        self._sep(self.frame)

        # ════════════════════════════════════════════════════════
        # PLANET — 메인 홈페이지 허브 (독립 행)
        # ════════════════════════════════════════════════════════
        planet_box = tk.Frame(self.frame, bg=COLOR_BG)
        planet_box.pack(fill=tk.X, padx=20, pady=(2, 4))
        self.btn_planet = tk.Button(
            planet_box, text="◉  PLANET  —  maran-chat-2026.web.app",
            font=FONT_MONO_BOLD, fg=COLOR_ACCENT_PLANET, bg=COLOR_PANEL,
            activebackground=COLOR_PANEL2, activeforeground=COLOR_ACCENT_PLANET,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._open_planet,
            padx=10, pady=4, anchor="w",
        )
        self.btn_planet.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_game = tk.Button(
            planet_box, text="🎮  GAME",
            font=FONT_MONO_BOLD, fg=COLOR_OK, bg=COLOR_PANEL,
            activebackground=COLOR_PANEL2, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._open_game_direct,
            padx=15, pady=4,
        )
        self.btn_game.pack(side=tk.RIGHT)

        self._sep(self.frame)

        # ════════════════════════════════════════════════════════
        # EXEC — 모드 선택 버튼
        # ════════════════════════════════════════════════════════
        self._section_header(self.frame, "EXEC")
        exec_box = tk.Frame(self.frame, bg=COLOR_BG)
        exec_box.pack(fill=tk.X, padx=20, pady=(2, 6))

        self.btn_vscode = self._hack_btn(
            exec_box, "▸ vscode", COLOR_ACCENT_VSCODE,
            lambda: self.start("vscode"),
        )
        self.btn_vscode.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_term = self._hack_btn(
            exec_box, "▸ shell", COLOR_ACCENT_TERM,
            lambda: self.start("terminal"),
        )
        self.btn_term.pack(side=tk.LEFT, padx=6)

        self.btn_llama = self._hack_btn(
            exec_box, "λ llama", COLOR_ACCENT_LLAMA,
            lambda: self.start("llama"),
        )
        self.btn_llama.pack(side=tk.LEFT, padx=6)

        self.btn_danger = self._hack_btn(
            exec_box, "! danger", COLOR_ACCENT_DANGER,
            lambda: self.start("danger"),
        )
        self.btn_danger.pack(side=tk.LEFT, padx=6)

        self.btn_gemini = self._hack_btn(
            exec_box, "✦ gemini", COLOR_ACCENT_GEMINI,
            lambda: self.start("gemini"),
        )
        self.btn_gemini.pack(side=tk.LEFT, padx=6)

        # 옵션 (작게) — auto-close 제거 (v2.2.1+, 항상 창 유지, 트레이로만 닫음)
        opts = tk.Frame(self.frame, bg=COLOR_BG)
        opts.pack(fill=tk.X, padx=20, pady=(2, 4))
        # 호환성 위해 변수만 유지 (코드 다른 곳에서 참조하지 않게 됐지만 안전망)
        self.auto_close = tk.BooleanVar(value=False)
        self.auto_claude = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="shell→claude",
            variable=self.auto_claude,
            font=FONT_MONO_TINY,
            fg=COLOR_DIM, bg=COLOR_BG,
            selectcolor=COLOR_PANEL2,
            activebackground=COLOR_BG, activeforeground=COLOR_FG, bd=0,
        ).pack(side=tk.LEFT)
        tk.Label(
            opts, text="  · close → tray ([×])  · re-open → Ctrl+Alt+M",
            font=FONT_MONO_TINY, fg=COLOR_DIM2, bg=COLOR_BG,
        ).pack(side=tk.LEFT)

        self._sep(self.frame)

        # ════════════════════════════════════════════════════════
        # NAS — 공유폴더 / MARAN / 주소복사
        # ════════════════════════════════════════════════════════
        self._section_header(self.frame, "NAS", suffix=f"  {SMB_PATH_URL}")
        nas_box = tk.Frame(self.frame, bg=COLOR_BG)
        nas_box.pack(fill=tk.X, padx=20, pady=(2, 6))

        self._hack_btn(
            nas_box, "▸ shared", COLOR_OK, self._open_smb_shared,
        ).pack(side=tk.LEFT, padx=(0, 6))
        self._hack_btn(
            nas_box, "▸ root", COLOR_INFO, self._open_smb_folder,
        ).pack(side=tk.LEFT, padx=6)
        self._hack_btn(
            nas_box, "⌘ copy addr", COLOR_DIM2, self._copy_smb_address,
        ).pack(side=tk.LEFT, padx=6)

        self._sep(self.frame)

        # ════════════════════════════════════════════════════════
        # DELIVERY — Mac→Windows 결과물 (outbox 폴링)
        # ════════════════════════════════════════════════════════
        delivery_head = tk.Frame(self.frame, bg=COLOR_BG)
        delivery_head.pack(fill=tk.X, padx=14, pady=(6, 0))
        tk.Label(
            delivery_head, text="DELIVERY",
            font=FONT_HEADER, fg=COLOR_OK, bg=COLOR_BG,
        ).pack(side=tk.LEFT)
        self.delivery_count = tk.Label(
            delivery_head, text="  (0)",
            font=FONT_MONO_TINY, fg=COLOR_DIM2, bg=COLOR_BG,
        )
        self.delivery_count.pack(side=tk.LEFT)
        tk.Button(
            delivery_head, text="[↻ refresh]",
            font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._refresh_delivery_now,
        ).pack(side=tk.RIGHT)
        tk.Button(
            delivery_head, text="[📁 outbox]",
            font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=lambda: open_smb_outbox(self.log),
        ).pack(side=tk.RIGHT, padx=(0, 6))

        # 항목 리스트 컨테이너 (재렌더 시 비우고 다시 채움)
        self.delivery_list = tk.Frame(self.frame, bg=COLOR_BG)
        self.delivery_list.pack(fill=tk.X, padx=20, pady=(2, 4))
        # 초기 안내
        self._delivery_entries = []
        self._delivery_last_seen_ts = ""
        self._render_delivery_list()

        # 시작 즉시 1회 fetch + 30초마다 자동 폴링
        threading.Thread(target=self._poll_delivery_once, daemon=True).start()
        self._schedule_delivery_poll()

        self._sep(self.frame)

        # ════════════════════════════════════════════════════════
        # TRANSFER — 좌측 최근 업로드 로그 / 우측 드롭존 (좌우 분할)
        # ════════════════════════════════════════════════════════
        self._section_header(self.frame, "TRANSFER", suffix="  → ~/MARAN/inbox/")

        transfer_split = tk.Frame(self.frame, bg=COLOR_BG)
        transfer_split.pack(fill=tk.BOTH, expand=True, padx=20, pady=(2, 6))

        # 좌측 패널 — 최근 업로드 로그 (5개)
        log_panel = tk.Frame(
            transfer_split, bg=COLOR_PANEL,
            highlightbackground=COLOR_BORDER, highlightthickness=1,
        )
        log_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        log_head = tk.Frame(log_panel, bg=COLOR_PANEL)
        log_head.pack(fill=tk.X, padx=8, pady=(6, 4))
        tk.Label(
            log_head, text="recent uploads",
            font=FONT_MONO_BOLD, fg=COLOR_OK, bg=COLOR_PANEL,
        ).pack(side=tk.LEFT)
        tk.Label(
            log_head, text=f"  · last {INBOX_LOG_SHOW}",
            font=FONT_MONO_TINY, fg=COLOR_DIM2, bg=COLOR_PANEL,
        ).pack(side=tk.LEFT)

        self.inbox_log_labels = []
        for _ in range(INBOX_LOG_SHOW):
            row = tk.Label(
                log_panel, text="  --:--:--  -",
                font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_PANEL,
                anchor="w", justify=tk.LEFT,
            )
            row.pack(fill=tk.X, padx=8, pady=1)
            self.inbox_log_labels.append(row)

        # 우측 패널 — 드롭존 (Ctrl+V / [+ select file])
        drop_outer = tk.Frame(
            transfer_split, bg=COLOR_PANEL,
            highlightbackground=COLOR_BORDER, highlightthickness=1,
        )
        drop_outer.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

        # 가운데 정렬 위해 spacer
        tk.Frame(drop_outer, bg=COLOR_PANEL).pack(expand=True)

        self.drop_title = tk.Label(
            drop_outer,
            text=":: drag files / press Ctrl+V to paste ::",
            font=FONT_MONO, fg=COLOR_DIM2, bg=COLOR_PANEL,
        )
        self.drop_title.pack(pady=(0, 8))

        # 큰 파일 선택 버튼 (가운데)
        tk.Button(
            drop_outer, text="[ + select file ]",
            font=FONT_MONO_BOLD, fg=COLOR_OK, bg=COLOR_PANEL,
            activebackground=COLOR_PANEL2, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._pick_file_to_upload,
            padx=10, pady=4,
        ).pack()

        tk.Frame(drop_outer, bg=COLOR_PANEL).pack(expand=True)

        self.drop_zone = drop_outer  # 호환성

        # Ctrl+V 클립보드 paste — frame 전체
        self.frame.bind_all("<Control-v>", self._handle_paste)
        self.frame.bind_all("<Control-V>", self._handle_paste)

        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(drop_outer, func=self._handle_drop)
                windnd.hook_dropfiles(self.drop_title, func=self._handle_drop)
            except Exception:
                pass

        # 시작 시 로그 1회 로드
        self._refresh_inbox_log()

        # ════════════════════════════════════════════════════════
        # FOOTER — version / IP / update check (항상 표시)
        # ════════════════════════════════════════════════════════
        footer = tk.Frame(
            self.frame, bg=COLOR_PANEL2,
            highlightbackground=COLOR_BORDER, highlightthickness=1,
        )
        footer.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)

        self.foot_version = tk.Label(
            footer, text=f" v{__version__} ",
            font=FONT_MONO_TINY, fg=COLOR_DIM2, bg=COLOR_PANEL2,
        )
        self.foot_version.pack(side=tk.LEFT)
        tk.Label(
            footer, text="│",
            font=FONT_MONO_TINY, fg=COLOR_BORDER, bg=COLOR_PANEL2,
        ).pack(side=tk.LEFT)
        tk.Label(
            footer, text=f" {MAC_HOST} ",
            font=FONT_MONO_TINY, fg=COLOR_DIM2, bg=COLOR_PANEL2,
        ).pack(side=tk.LEFT)
        tk.Label(
            footer, text="│",
            font=FONT_MONO_TINY, fg=COLOR_BORDER, bg=COLOR_PANEL2,
        ).pack(side=tk.LEFT)

        # 우측: 업데이트 표시 (항상 보이게)
        self.foot_update = tk.Button(
            footer, text=" ↻ check update ",
            font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_PANEL2,
            activebackground=COLOR_BORDER, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._do_update,
            padx=4,
        )
        self.foot_update.pack(side=tk.RIGHT)

        # 라이브 로그 줄 (footer 위쪽 작은 줄)
        self.log_var = tk.StringVar(value=":: ready ::")
        log_line = tk.Frame(self.frame, bg=COLOR_BG)
        log_line.pack(fill=tk.X, side=tk.BOTTOM, padx=14, pady=(2, 2))
        tk.Label(
            log_line, textvariable=self.log_var,
            font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_BG,
            anchor="w", justify=tk.LEFT,
        ).pack(fill=tk.X)

        # 헬퍼: 호환성을 위한 update_bar / update_label / update_btn (배너는 제거됨)
        # 새 버전 표시는 _show_update_banner에서 foot_update 텍스트만 갱신
        self.update_bar = None  # legacy
        self.update_label = None
        self.update_btn = self.foot_update

        # 시작 시 연결 상태 빠른 체크 (target_bar의 conn_state)
        threading.Thread(target=self._refresh_conn_state, daemon=True).start()

        # 전체 프레임에 드래그 바인딩 (Button 제외 — 클릭 보존)
        # after() 로 미뤄서 모든 자식 위젯이 생성된 뒤 실행
        self.frame.after(0, lambda: self._bind_drag_recursive(self.frame))

    # ────────────────────────────────────────────────────────────
    # UI 헬퍼들
    # ────────────────────────────────────────────────────────────

    def _sep(self, parent):
        """가로 구분선 (얇은 회색)."""
        line = tk.Frame(parent, bg=COLOR_BORDER, height=1)
        line.pack(fill=tk.X, padx=14, pady=(2, 2))

    def _section_header(self, parent, label, suffix=""):
        """섹션 헤더: STATUS / EXEC / NAS / TRANSFER 같은 라벨."""
        bar = tk.Frame(parent, bg=COLOR_BG)
        bar.pack(fill=tk.X, padx=14, pady=(6, 0))
        tk.Label(
            bar, text=label,
            font=FONT_HEADER, fg=COLOR_OK, bg=COLOR_BG,
        ).pack(side=tk.LEFT)
        if suffix:
            tk.Label(
                bar, text=suffix,
                font=FONT_MONO_TINY, fg=COLOR_DIM2, bg=COLOR_BG,
            ).pack(side=tk.LEFT)

    def _hack_btn(self, parent, text, accent_color, command):
        """해커 톤 버튼: 어두운 배경 + 액센트 색 텍스트 + 테두리."""
        btn = tk.Button(
            parent, text=text,
            font=FONT_MONO_BOLD, fg=accent_color, bg=COLOR_PANEL2,
            activebackground=COLOR_BORDER, activeforeground=accent_color,
            relief=tk.FLAT, bd=0, cursor="hand2",
            highlightbackground=COLOR_BORDER, highlightthickness=1,
            command=command,
            padx=10, pady=5,
        )
        return btn

    def _open_planet(self):
        """메인 홈페이지(허브) 기본 브라우저로 열기."""
        try:
            webbrowser.open(PLANET_URL)
            self.log(f"PLANET 열림: {PLANET_URL}")
        except Exception as e:
            self.log(f"PLANET 열기 실패: {e}")

    def _open_game_direct(self):
        """메인 UI 게임 버튼 클릭: HTTP 서버를 통해 게임 실행."""
        import webbrowser
        url = "https://maran-chat-2026.web.app/game/"
        try:
            webbrowser.open(url)
            self.log("🎮 우주 생존기 실행 중...")
        except Exception as e:
            self.log(f"게임 실행 실패: {e}")

    def _refresh_conn_state(self):
        """target_bar 우측 연결 상태 라벨 갱신."""
        try:
            ok = check_mac_reachable()
            txt = "● DIRECT" if ok else "● UNREACHABLE"
            color = COLOR_OK if ok else COLOR_ERROR
            self.frame.after(0, lambda: self.conn_state.config(text=txt, fg=color))
        except Exception:
            pass

    # ────────────────────────────────────────────────────────────
    # Frameless 창 드래그 / 최소화 / 트레이로
    # ────────────────────────────────────────────────────────────

    def _drag_start(self, event):
        self._drag_x = event.x_root - self.frame.master.winfo_x()
        self._drag_y = event.y_root - self.frame.master.winfo_y()

    def _drag_move(self, event):
        try:
            x = event.x_root - self._drag_x
            y = event.y_root - self._drag_y
            self.frame.master.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _bind_drag_recursive(self, widget):
        """Label·Frame 위젯에 드래그 바인딩 (Button 제외 — 클릭 동작 보존)."""
        if not isinstance(widget, tk.Button):
            widget.bind("<ButtonPress-1>", self._drag_start, add="+")
            widget.bind("<B1-Motion>",     self._drag_move,  add="+")
        for child in widget.winfo_children():
            self._bind_drag_recursive(child)

    def _on_minimize(self):
        """[_] 클릭 → 작업표시줄로 최소화 (frameless에선 OS 윈도우 hide+iconify 트릭)."""
        try:
            root = self.frame.master
            # frameless 창은 그냥 iconify가 안 먹음 → 임시로 overrideredirect 해제
            root.overrideredirect(False)
            root.iconify()
            # 다시 보일 때 재진입은 _on_deiconify에서 overrideredirect 복원
        except Exception:
            pass

    def _on_close_to_tray(self):
        """[×] 클릭 → 창 숨기고 트레이만 남김. 프로세스 종료 X."""
        try:
            root = self.frame.master
            root.withdraw()
        except Exception:
            pass

    # ────────────────────────────────────────────────────────────
    # DELIVERY (Mac→Windows outbox 폴링)
    # ────────────────────────────────────────────────────────────

    def _schedule_delivery_poll(self):
        """30초마다 자동 폴링 (after는 메인 스레드에서 동작)."""
        self.frame.after(DELIVERY_POLL_MS, self._tick_delivery)

    def _tick_delivery(self):
        threading.Thread(target=self._poll_delivery_once, daemon=True).start()
        self._schedule_delivery_poll()

    def _poll_delivery_once(self):
        """백그라운드 스레드: SSH로 _index.json fetch → UI 업데이트."""
        try:
            entries = fetch_outbox_index()
        except Exception:
            entries = []
        # UI 업데이트는 메인 스레드에서
        self.frame.after(0, lambda: self._apply_delivery_entries(entries))

    def _apply_delivery_entries(self, entries):
        """fetch 결과 반영 + 새 항목 감지 → footer NEW 강조."""
        prev_top = self._delivery_entries[0]["ts"] if self._delivery_entries else ""
        self._delivery_entries = sorted(
            entries, key=lambda e: e.get("ts", ""), reverse=True,
        )
        # 새 항목 도착 검출
        new_top = self._delivery_entries[0]["ts"] if self._delivery_entries else ""
        if new_top and new_top != prev_top:
            # 새 도착이고 이전에 본 적 없으면 NEW 깜박
            if new_top != self._delivery_last_seen_ts:
                self._signal_new_delivery(self._delivery_entries[0])
        self._render_delivery_list()

    def _refresh_delivery_now(self):
        """수동 [↻ refresh] 클릭."""
        self.log("▸ refreshing delivery index...")
        threading.Thread(target=self._poll_delivery_once, daemon=True).start()

    def _render_delivery_list(self):
        """delivery_list 컨테이너 비우고 최근 N개 다시 그림."""
        try:
            for child in self.delivery_list.winfo_children():
                child.destroy()
        except Exception:
            return

        entries = self._delivery_entries[:DELIVERY_SHOW_COUNT]
        self.delivery_count.config(text=f"  ({len(self._delivery_entries)})")

        if not entries:
            tk.Label(
                self.delivery_list,
                text=":: empty :: run `python scripts/maran_deliver.py <file> [project]`",
                font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_BG,
                anchor="w",
            ).pack(fill=tk.X)
            return

        for entry in entries:
            is_new = entry["ts"] > self._delivery_last_seen_ts
            self._build_delivery_row(self.delivery_list, entry, is_new)

    def _build_delivery_row(self, parent, entry, is_new):
        row = tk.Frame(parent, bg=COLOR_BG)
        row.pack(fill=tk.X, pady=1)

        # NEW 마커
        marker = "●" if is_new else " "
        marker_color = COLOR_ERROR if is_new else COLOR_DIM2
        tk.Label(
            row, text=marker,
            font=FONT_MONO_BOLD, fg=marker_color, bg=COLOR_BG, width=2,
        ).pack(side=tk.LEFT)

        # 시간 HH:MM
        ts = entry.get("ts", "")
        time_str = ts[11:16] if len(ts) >= 16 else ts[-5:]
        tk.Label(
            row, text=time_str,
            font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_BG, width=6, anchor="w",
        ).pack(side=tk.LEFT)

        # 파일명 (truncate)
        fname = entry.get("filename", "")
        # 앞 timestamp prefix(2026-...) 제거하고 짧게
        if "_" in fname:
            parts = fname.split("_", 2)
            if len(parts) >= 3:
                short_fname = parts[2]
            else:
                short_fname = fname
        else:
            short_fname = fname
        if len(short_fname) > 28:
            short_fname = short_fname[:27] + "…"

        tk.Label(
            row, text=short_fname,
            font=FONT_MONO, fg=COLOR_FG, bg=COLOR_BG, anchor="w",
        ).pack(side=tk.LEFT, padx=(2, 6))

        # 우측: 프로젝트명 + 열기 버튼 (이미지면 [🖼] 추가)
        smb = smb_path_for_outbox_rel(entry.get("rel_path", ""))
        fname_lower = entry.get("filename", "").lower()
        is_image = any(fname_lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))

        tk.Button(
            row, text="[📁]",
            font=FONT_MONO_TINY, fg=COLOR_OK, bg=COLOR_BG,
            activebackground=COLOR_PANEL2, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=lambda p=smb: self._on_delivery_click(p, entry),
            padx=4,
        ).pack(side=tk.RIGHT)

        if is_image:
            tk.Button(
                row, text="[🖼]",
                font=FONT_MONO_TINY, fg=COLOR_ACCENT_GEMINI, bg=COLOR_BG,
                activebackground=COLOR_PANEL2, activeforeground=COLOR_ACCENT_GEMINI,
                relief=tk.FLAT, bd=0, cursor="hand2",
                command=lambda p=smb: self._on_delivery_preview(p, entry),
                padx=4,
            ).pack(side=tk.RIGHT)

        proj = entry.get("project", "")[:14]
        tk.Label(
            row, text=proj,
            font=FONT_MONO_TINY, fg=COLOR_INFO, bg=COLOR_BG, anchor="e",
        ).pack(side=tk.RIGHT, padx=(0, 6))

    def _on_delivery_click(self, smb_path, entry):
        """[📁] 클릭: 탐색기에서 파일 위치 열기 + NEW 마커 해제."""
        if open_explorer_select(smb_path):
            self.log(f"▸ opened: {Path(smb_path).name}")
        else:
            open_smb_outbox(self.log)
        self._mark_delivery_seen()

    def _on_delivery_preview(self, smb_path, entry):
        """[🖼] 클릭: 이미지 팝업 뷰어."""
        self._mark_delivery_seen()
        threading.Thread(
            target=self._show_image_popup, args=(smb_path, entry), daemon=True
        ).start()

    def _mark_delivery_seen(self):
        self._delivery_last_seen_ts = self._delivery_entries[0]["ts"] if self._delivery_entries else ""
        self._render_delivery_list()
        try:
            self.foot_update.config(text=" ↻ check update ", fg=COLOR_DIM)
        except Exception:
            pass

    def _show_image_popup(self, smb_path, entry):
        """이미지 표시: PIL 있으면 인앱 팝업, 없으면 Windows 기본 뷰어로 열기."""
        try:
            from PIL import Image as PILImage, ImageTk

            img = PILImage.open(smb_path)
            img.thumbnail((800, 600), PILImage.LANCZOS)

            def _popup():
                win = tk.Toplevel(self.root)
                win.title(Path(smb_path).name)
                win.configure(bg=COLOR_BG)
                win.resizable(False, False)

                photo = ImageTk.PhotoImage(img)
                win._photo = photo  # GC 방지

                tk.Label(win, image=photo, bg=COLOR_BG).pack(padx=8, pady=8)

                fname = entry.get("filename", Path(smb_path).name)
                proj = entry.get("project", "")
                tk.Label(
                    win, text=f"{fname}  ·  {proj}",
                    font=FONT_MONO_TINY, fg=COLOR_DIM, bg=COLOR_BG,
                ).pack(pady=(0, 6))

                tk.Button(
                    win, text="[ close ]",
                    font=FONT_MONO_TINY, fg=COLOR_DIM2, bg=COLOR_BG,
                    activebackground=COLOR_PANEL2, activeforeground=COLOR_FG,
                    relief=tk.FLAT, bd=0, cursor="hand2",
                    command=win.destroy,
                ).pack(pady=(0, 8))

                win.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
                win.geometry(f"+{x}+{y}")
                win.focus_force()

            self.root.after(0, _popup)

        except Exception:
            # PIL 없거나 ImageTk 실패 → Windows 기본 뷰어로 열기
            try:
                os.startfile(smb_path)
                self.log(f"▸ 이미지 열기: {Path(smb_path).name}")
            except Exception as e:
                self.log(f"이미지 열기 실패: {e}")

    def _signal_new_delivery(self, entry):
        """새 결과물 도착 알림: footer 깜박 + log."""
        try:
            short = entry.get("filename", "")[:30]
            proj = entry.get("project", "")
            self.log(f"[NEW] {short} @ {proj}")
            # footer 우측 임시로 NEW 강조 (업데이트 알림과 우선순위 충돌 시 update가 이김)
            self.foot_update.config(
                text=f" [NEW] delivery ",
                fg=COLOR_ERROR,
            )
            def _flash(times=4, on=True):
                if times <= 0:
                    return
                self.foot_update.config(fg=COLOR_ERROR if on else COLOR_WARN)
                self.frame.after(280, lambda: _flash(times - 1, not on))
            _flash()
        except Exception:
            pass

    # ============================================================
    # Auto-update
    # ============================================================

    def _check_update_async(self):
        """백그라운드: GitHub API에서 최신 버전 체크 → 새 버전 있으면 배너 표시."""
        latest = fetch_latest_version()
        if not latest:
            return
        if is_newer_version(latest, __version__):
            self.frame.after(0, lambda: self._show_update_banner(latest))

    def _show_update_banner(self, latest_ver):
        """v2.0+: 노란 배너 대신 footer 우측 라벨을 빨간 강조로 변경."""
        try:
            self.foot_update.config(
                text=f" [!] v{latest_ver} → update ",
                fg=COLOR_ERROR,
            )
            # 짧은 깜박임으로 시선 유도
            def _flash(times=4, on=True):
                if times <= 0:
                    self.foot_update.config(fg=COLOR_ERROR)
                    return
                self.foot_update.config(fg=COLOR_ERROR if on else COLOR_WARN)
                self.frame.after(280, lambda: _flash(times - 1, not on))
            _flash()
        except Exception:
            pass

    def _do_update(self):
        ok, msg = trigger_self_update(self.log)
        if ok:
            self.log("업데이트 PowerShell 창 띄움. 끝나면 런처 다시 켜세요.")
        else:
            self.log(f"업데이트 실패: {msg}")

    # ============================================================
    # File drop / clipboard
    # ============================================================

    def _pick_file_to_upload(self):
        """드롭존 클릭 시 파일 선택 다이얼로그."""
        try:
            from tkinter import filedialog
            paths = filedialog.askopenfilenames(
                title="Mac mini로 전송할 파일 선택",
            )
            if paths:
                self._upload_files(list(paths))
        except Exception as e:
            self.log(f"파일 선택 실패: {e}")

    def _handle_drop(self, files):
        """windnd hook 콜백. files: list[bytes] 경로"""
        try:
            paths = [
                f.decode("utf-8", errors="replace") if isinstance(f, bytes) else f
                for f in files
            ]
            self._upload_files(paths, source="drop")
        except Exception as e:
            self.log(f"드롭 처리 실패: {e}")

    def _handle_paste(self, event=None):
        """Ctrl+V → 클립보드에서 이미지/파일/텍스트 추출 → Mac 전송."""
        # 이미지/파일 우선 (PIL.ImageGrab)
        threading.Thread(target=self._paste_thread, daemon=True).start()

    def _paste_thread(self):
        self.log("📋 클립보드 확인 중...")
        ok, msg = upload_clipboard_to_mac(self.log)
        if ok:
            self.log(f"✅ {msg}")
            self._flash_drop_zone(COLOR_OK)
            try:
                self.frame.after(0, self._refresh_inbox_log)
            except Exception:
                pass
            return
        # 텍스트 폴백
        try:
            text = self.frame.clipboard_get()
        except tk.TclError:
            text = ""
        if text:
            ok, msg = upload_clipboard_text_to_mac(text, self.log)
            if ok:
                self.log(f"✅ {msg}")
                self._flash_drop_zone(COLOR_OK)
                try:
                    self.frame.after(0, self._refresh_inbox_log)
                except Exception:
                    pass
                return
        self.log(f"❌ {msg}")
        self._flash_drop_zone(COLOR_ERROR)

    def _upload_files(self, paths, source="file"):
        threading.Thread(
            target=self._upload_files_thread, args=(paths, source), daemon=True
        ).start()

    def _upload_files_thread(self, paths, source="file"):
        ok_count = 0
        for p in paths:
            self.log(f"⬆ 업로드: {Path(p).name}")
            ok, msg = upload_file_to_mac(p, self.log, source=source)
            if ok:
                ok_count += 1
                self.log(f"✅ {msg}")
            else:
                self.log(f"❌ {Path(p).name}: {msg}")
        if ok_count > 0:
            self._flash_drop_zone(COLOR_OK)
            self.log(f"📦 {ok_count}/{len(paths)} 업로드 완료 → ~/MARAN/inbox/")
            try:
                self.frame.after(0, self._refresh_inbox_log)
            except Exception:
                pass
        else:
            self._flash_drop_zone(COLOR_ERROR)

    def _refresh_inbox_log(self):
        """좌측 'recent uploads' 5줄을 inbox_log.json 최신 상태로 갱신."""
        try:
            entries = read_inbox_log(INBOX_LOG_SHOW)
        except Exception:
            entries = []
        for i, lbl in enumerate(self.inbox_log_labels):
            if i < len(entries):
                e = entries[i]
                ts_full = e.get("ts", "")  # "YYYY-MM-DD HH:MM:SS"
                ts_short = ts_full[-8:] if len(ts_full) >= 8 else ts_full
                name = e.get("name", "?")
                src = e.get("source", "")
                src_mark = {"clipboard": "📋", "drop": "⬇", "file": "📁"}.get(src, "·")
                if len(name) > 32:
                    name = name[:29] + "..."
                lbl.config(
                    text=f"  {ts_short}  {src_mark} {name}",
                    fg=COLOR_DIM if i > 0 else COLOR_OK,
                )
            else:
                lbl.config(text="  --:--:--  -", fg=COLOR_DIM2)

    def _flash_drop_zone(self, color):
        """드롭존 타이틀 색깔 잠깐 깜박여서 결과 시각 피드백."""
        try:
            orig = self.drop_title.cget("fg")
            self.drop_title.config(fg=color)
            self.frame.after(900, lambda: self.drop_title.config(fg=orig))
        except Exception:
            pass

    # ============================================================
    # NAS (SMB)
    # ============================================================

    def _open_smb_folder(self):
        ok, msg = open_smb_folder(self.log)
        if not ok:
            self.log(f"❌ NAS 폴더 열기 실패: {msg}")
        else:
            self.log(f"📂 {msg}")
            self.log("   (첫 접근시 자격증명 창: moran / Mac 비번)")

    def _open_smb_shared(self):
        ok, msg = open_smb_shared(self.log)
        if not ok:
            self.log(f"❌ 공유폴더 열기 실패: {msg}")
        else:
            self.log(f"🗂 공유폴더 열림 (~/MARAN/shared/)")

    def _copy_smb_address(self):
        addr = get_smb_address_text()
        try:
            self.frame.clipboard_clear()
            self.frame.clipboard_append(addr)
            self.frame.update()  # 클립보드 영구화 (창 닫혀도 유지)
            self.log(f"📋 SMB 주소 복사됨: {SMB_PATH_WIN}")
        except Exception as e:
            self.log(f"❌ 클립보드 실패: {e}")

    def log(self, msg):
        self.log_var.set(msg)
        self.frame.update_idletasks()

    def start(self, mode):
        self.btn_vscode.config(state=tk.DISABLED)
        self.btn_term.config(state=tk.DISABLED)
        self.btn_llama.config(state=tk.DISABLED)
        self.btn_danger.config(state=tk.DISABLED)
        self.btn_gemini.config(state=tk.DISABLED)
        for s in (self.s_tail, self.s_mac, self.s_run):
            s.pending()
        run_label = {
            "vscode": "VS Code 실행",
            "terminal": "Terminal 실행",
            "llama": "llama 대화창",
            "danger": "danger mode (sonnet)",
            "gemini": "Gemini CLI (제미나이)",
        }.get(mode, "실행")
        self.s_run.label.config(text=run_label)
        threading.Thread(target=self._pipeline, args=(mode,), daemon=True).start()

    def _pipeline(self, mode):
        try:
            self.s_tail.progress()
            self.log(f"Tailscale 네트워크 확인 중 ({MAC_HOST})...")
            if not check_mac_reachable():
                self.s_tail.error()
                self.log("Tailscale 연결 실패. ⚙ 설정에서 점검하세요.")
                self._fail()
                return
            self.s_tail.ok()

            self.s_mac.progress()
            self.log("맥미니 SSH 응답 확인 중...")
            if not check_ssh_no_password():
                self.s_mac.error()
                self.log("맥미니 SSH 응답 없음. ⚙ 설정에서 키 등록을 진행하세요.")
                self._fail()
                return
            self.s_mac.ok()

            self.s_run.progress()
            if mode == "vscode":
                self.log("VS Code Remote-SSH 실행 중...")
                ok = self._launch_vscode()
                fail_msg = "VS Code 실행 실패. ⚙ 설정에서 VS Code를 설치하세요."
                done_msg = "✅ VS Code에서 MARAN 폴더를 확인하세요."
            elif mode == "llama":
                self.log("맥미니 로컬 LLM 대화창(Qwen via Ollama) 실행 중...")
                ok = self._launch_llama()
                fail_msg = "llama 대화창 실행 실패. 맥미니에 ollama가 설치돼있는지 확인하세요."
                done_msg = "✅ 새 터미널 창에 라우터 REPL이 열렸습니다."
            elif mode == "danger":
                self.log("danger mode (claude --dangerously-skip-permissions --model sonnet) 실행 중...")
                ok = self._launch_danger()
                fail_msg = "danger mode 실행 실패."
                done_msg = "✅ 새 터미널 창에 danger mode claude가 열렸습니다."
            elif mode == "gemini":
                self.log("Gemini CLI 실행 중 (제미나이)...")
                ok = self._launch_gemini()
                fail_msg = "Gemini CLI 실행 실패. 맥미니에 gemini CLI가 설치돼있는지 확인하세요."
                done_msg = "✅ 새 터미널 창에 Gemini CLI가 열렸습니다."
            else:
                self.log("Terminal SSH 세션 실행 중...")
                ok = self._launch_terminal(self.auto_claude.get())
                fail_msg = "Terminal 실행 실패."
                done_msg = "✅ 새 터미널 창에서 MARAN으로 SSH 접속됩니다."

            if not ok:
                self.s_run.error()
                self.log(fail_msg)
                self._fail()
                return
            self.s_run.ok()
            self.log(done_msg)

            # v2.2.1: 작업 완료 후에도 창은 계속 띄움. 트레이([×])로 사용자가 직접 닫음.
            self.btn_vscode.config(state=tk.NORMAL)
            self.btn_term.config(state=tk.NORMAL)
            self.btn_llama.config(state=tk.NORMAL)
            self.btn_danger.config(state=tk.NORMAL)
            self.btn_gemini.config(state=tk.NORMAL)
        except Exception as e:
            self.log(f"예기치 않은 오류: {e}")
            self._fail()

    def _fail(self):
        self.btn_vscode.config(state=tk.NORMAL)
        self.btn_term.config(state=tk.NORMAL)
        self.btn_llama.config(state=tk.NORMAL)
        self.btn_danger.config(state=tk.NORMAL)
        self.btn_gemini.config(state=tk.NORMAL)

    @staticmethod
    def _launch_vscode():
        """다중 폴백:
        1) vscode:// URL 핸들러 (PATH 의존 X, 가장 확실)
        2) code --folder-uri (canonical CLI 방식)
        3) code --remote (legacy CLI 방식)
        """
        host_spec = f"ssh-remote+{MAC_USER}@{MAC_HOST}"
        # vscode:// URL 핸들러는 vscode-remote/ssh-remote+host/path 를 wrap 해서 받음
        wrapper_url = (
            f"vscode://vscode-remote/ssh-remote+{MAC_USER}@{MAC_HOST}{MAC_PROJECT_PATH}"
        )
        folder_uri = (
            f"vscode-remote://ssh-remote+{MAC_USER}@{MAC_HOST}{MAC_PROJECT_PATH}"
        )

        # 1) Windows: URL 핸들러 (PATH/code.cmd 의존성 0)
        if os.name == "nt":
            try:
                os.startfile(wrapper_url)
                return True
            except Exception:
                pass
            # cmd start 폴백 (URL 핸들러 다른 경로)
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", wrapper_url],
                    creationflags=CREATE_NO_WINDOW,
                )
                return True
            except Exception:
                pass

        # 2) code --folder-uri (canonical)
        code = find_code_exe()
        if code:
            try:
                if os.name == "nt":
                    cmd_str = f'"{code}" --folder-uri "{folder_uri}"'
                    subprocess.Popen(
                        cmd_str, shell=True, creationflags=CREATE_NO_WINDOW,
                    )
                else:
                    subprocess.Popen([code, "--folder-uri", folder_uri])
                return True
            except Exception:
                pass

            # 3) code --remote (legacy)
            try:
                if os.name == "nt":
                    cmd_str = f'"{code}" --remote {host_spec} "{MAC_PROJECT_PATH}"'
                    subprocess.Popen(
                        cmd_str, shell=True, creationflags=CREATE_NO_WINDOW,
                    )
                else:
                    subprocess.Popen(
                        [code, "--remote", host_spec, MAC_PROJECT_PATH]
                    )
                return True
            except Exception:
                pass

        return False

    @staticmethod
    def _launch_terminal(run_claude):
        target = f"{MAC_USER}@{MAC_HOST}"
        if run_claude:
            remote_cmd = f"cd {MAC_PROJECT_PATH_REMOTE} && claude"
            ssh_args = [_find_ssh(), "-t", target, remote_cmd]
        else:
            ssh_args = [_find_ssh(), target]

        if shutil.which("wt"):
            try:
                subprocess.Popen(
                    ["wt", "--title", "MARAN"] + ssh_args,
                    creationflags=CREATE_NO_WINDOW,
                )
                return True
            except Exception:
                pass

        try:
            ps_cmd = " ".join(_ps_quote(a) for a in ssh_args)
            subprocess.Popen(
                [_find_powershell(), "-NoExit", "-Command", ps_cmd],
                creationflags=CREATE_NEW_CONSOLE,
            )
            return True
        except FileNotFoundError:
            pass

        try:
            cmd_str = " ".join(_cmd_quote(a) for a in ssh_args)
            subprocess.Popen(
                f'start "MARAN" cmd /k {cmd_str}', shell=True,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _launch_llama():
        """맥미니 로컬 LLM 대화창(maran_chat REPL) 새 터미널에서 실행.
        _launch_terminal 과 동일 패턴 — wt > powershell > cmd 폴백.
        """
        target = f"{MAC_USER}@{MAC_HOST}"
        # ssh -t 로 인터랙티브 TTY 강제. zsh 로그인 셸 띄워서 PATH 보장 후 python 실행.
        remote_cmd = (
            f"cd {MAC_PROJECT_PATH_REMOTE} && "
            f"python3 scripts/maran_chat.py"
        )
        ssh_args = [_find_ssh(), "-t", target, remote_cmd]

        if shutil.which("wt"):
            try:
                subprocess.Popen(
                    ["wt", "--title", "MARAN llama"] + ssh_args,
                    creationflags=CREATE_NO_WINDOW,
                )
                return True
            except Exception:
                pass

        try:
            ps_cmd = " ".join(_ps_quote(a) for a in ssh_args)
            subprocess.Popen(
                [_find_powershell(), "-NoExit", "-Command", ps_cmd],
                creationflags=CREATE_NEW_CONSOLE,
            )
            return True
        except FileNotFoundError:
            pass

        try:
            cmd_str = " ".join(_cmd_quote(a) for a in ssh_args)
            subprocess.Popen(
                f'start "MARAN llama" cmd /k {cmd_str}', shell=True,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _launch_danger():
        """danger mode: claude --dangerously-skip-permissions --model claude-sonnet-4-6.
        _launch_llama 과 동일 패턴 — wt > powershell > cmd 폴백.
        """
        target = f"{MAC_USER}@{MAC_HOST}"
        remote_cmd = (
            f"cd {MAC_PROJECT_PATH_REMOTE} && "
            f"claude --dangerously-skip-permissions --model claude-sonnet-4-6"
        )
        ssh_args = [_find_ssh(), "-t", target, remote_cmd]

        if shutil.which("wt"):
            try:
                subprocess.Popen(
                    ["wt", "--title", "MARAN danger"] + ssh_args,
                    creationflags=CREATE_NO_WINDOW,
                )
                return True
            except Exception:
                pass

        try:
            ps_cmd = " ".join(_ps_quote(a) for a in ssh_args)
            subprocess.Popen(
                [_find_powershell(), "-NoExit", "-Command", ps_cmd],
                creationflags=CREATE_NEW_CONSOLE,
            )
            return True
        except FileNotFoundError:
            pass

        try:
            cmd_str = " ".join(_cmd_quote(a) for a in ssh_args)
            subprocess.Popen(
                f'start "MARAN danger" cmd /k {cmd_str}', shell=True,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _launch_gemini():
        """Gemini CLI 새 터미널에서 실행.
        GEMINI_CLI_TRUST_WORKSPACE=true 환경변수로 trust 오류 우회.
        """
        target = f"{MAC_USER}@{MAC_HOST}"
        remote_cmd = (
            f"cd {MAC_PROJECT_PATH_REMOTE} && "
            f"GEMINI_CLI_TRUST_WORKSPACE=true gemini"
        )
        ssh_args = [_find_ssh(), "-t", target, remote_cmd]

        if shutil.which("wt"):
            try:
                subprocess.Popen(
                    ["wt", "--title", "MARAN gemini"] + ssh_args,
                    creationflags=CREATE_NO_WINDOW,
                )
                return True
            except Exception:
                pass

        try:
            ps_cmd = " ".join(_ps_quote(a) for a in ssh_args)
            subprocess.Popen(
                [_find_powershell(), "-NoExit", "-Command", ps_cmd],
                creationflags=CREATE_NEW_CONSOLE,
            )
            return True
        except FileNotFoundError:
            pass

        try:
            cmd_str = " ".join(_cmd_quote(a) for a in ssh_args)
            subprocess.Popen(
                f'start "MARAN gemini" cmd /k {cmd_str}', shell=True,
            )
            return True
        except Exception:
            return False


def _ps_quote(s):
    if not s:
        return "''"
    if all(c.isalnum() or c in r"-_./:@~+=" for c in s):
        return s
    return "'" + s.replace("'", "''") + "'"


def _cmd_quote(s):
    if not s:
        return '""'
    if " " in s or '"' in s:
        return '"' + s.replace('"', r'\"') + '"'
    return s


# ============================================================
# Root Application
# ============================================================

class MaranLauncher:
    def __init__(self, auto_mode=None, force_setup=False):
        self.auto_mode = auto_mode
        self.root = tk.Tk()
        self.root.title("마란 런처")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        # frameless: OS 타이틀바/창 컨트롤 제거 (헤더에 자체 [_][×] 둠)
        try:
            self.root.overrideredirect(True)
        except Exception:
            pass

        # 외부에서 OS X로 닫으려 해도 트레이로 가게 (frameless면 안 옴 — 보험)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # iconify로 작업표시줄 갔다가 다시 deiconify되면 overrideredirect 복원
        self.root.bind("<Map>", self._on_map)

        # frameless 창을 작업표시줄에 항상 표시 (Windows-only 트릭)
        # update_idletasks 후 hwnd 확정되면 스타일 강제
        self.root.after(50, self._force_taskbar_icon)

        # 트레이 컨트롤러 (있으면)
        self.tray = None

        self.setup_view = SetupView(self.root, on_continue=self.show_main)
        self.main_view = MainView(self.root, on_setup=self.show_setup)

        # 초기 화면 결정
        if force_setup or self._needs_setup():
            self.show_setup()
            if auto_mode:
                self.setup_view.log(
                    f"⚠ --{auto_mode} 모드 요청됨. 환경 설정을 먼저 완료하세요."
                )
        else:
            if auto_mode:
                self.main_view.schedule_auto(auto_mode)
            self.show_main()

    def _on_map(self, event=None):
        """창이 다시 보여질 때(아이콘 → 화면) overrideredirect 복원."""
        try:
            self.root.overrideredirect(True)
        except Exception:
            pass
        # 재진입 시엔 redraw 사이클 없이 스타일만 보정 (깜빡임/자식 누락 방지)
        self.root.after(20, lambda: self._force_taskbar_icon(redraw=False))

    def _force_taskbar_icon(self, redraw=True):
        """frameless(overrideredirect=True) 창을 Windows 작업표시줄에 강제 표시.

        원리: tk overrideredirect(True) 는 Windows 에서 WS_EX_TOOLWINDOW 를 자동
        적용해 작업표시줄 아이콘을 숨김. WS_EX_APPWINDOW 를 켜고 TOOLWINDOW 를
        끈 뒤 SetWindowPos(SWP_FRAMECHANGED) 로 OS 가 스타일 변경을 인식하게 함.
        redraw=True 일 때만 withdraw→deiconify 사이클로 작업표시줄 아이콘 캐시 강제 갱신
        (시작/트레이 복귀 시점). 일반 <Map> 재진입에선 redraw=False — 깜빡임 방지.
        macOS/Linux 에서는 no-op.
        """
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                return
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            if new_style == style:
                return
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            # SetWindowPos(SWP_FRAMECHANGED) 로 frame 변경 통지 (resize/redraw 없음)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
            if redraw:
                # 작업표시줄 아이콘 캐시 강제 갱신 — 시작/트레이복귀 1회만
                self.root.withdraw()
                self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    # ────────────────────────────────────────────────────────────
    # Tray 통합
    # ────────────────────────────────────────────────────────────

    def attach_tray(self, tray):
        self.tray = tray

    def show_window(self):
        """다른 인스턴스 또는 트레이에서 호출 — 메인 스레드로 위임."""
        try:
            self.root.after(0, self._show_window_main)
        except Exception:
            pass

    def _show_window_main(self):
        try:
            self.root.deiconify()
            self.root.overrideredirect(True)
            # 트레이 → 복귀: taskbar 아이콘 보장(_force_taskbar_icon의 withdraw→deiconify 30ms)
            # 이후에 전면 표시 — 80ms 딜레이로 사이클 완료 후 확실히 올림
            self.root.after(20, self._force_taskbar_icon)
            self.root.after(80, self._raise_to_front)
        except Exception:
            pass

    def _raise_to_front(self):
        """창을 전면으로 올리고 포커스 획득. Win32 SetForegroundWindow 병행."""
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(200, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
            if os.name == "nt":
                try:
                    import ctypes
                    hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                    if hwnd:
                        SW_SHOW = 5
                        ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
        except Exception:
            pass

    def hide_to_tray(self):
        try:
            self.root.withdraw()
        except Exception:
            pass

    def quit_app(self):
        """완전 종료 — 트레이 멈추고 mainloop 종료."""
        try:
            if self.tray is not None:
                self.tray.stop()
        except Exception:
            pass
        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            pass

    @staticmethod
    def _needs_setup():
        """기본 prereq: Tailscale 연결 + 무비번 SSH"""
        return not (check_mac_reachable() and check_ssh_no_password())

    def show_setup(self):
        self.main_view.pack_forget()
        self.root.geometry(self._center(520, 660))
        self.setup_view.pack(fill=tk.BOTH, expand=True)
        self.setup_view.refresh_all()

    def show_main(self):
        self.setup_view.pack_forget()
        self.root.geometry(self._center(580, 820))
        self.root.resizable(True, True)
        self.root.configure(bg=COLOR_BG)
        self._init_bg_canvas()
        self.main_view.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        self.root.after(150, self._draw_bg_effects)

    def _init_bg_canvas(self):
        """배경 Canvas 초기화 (별자리 + 그라데이션 테두리용)."""
        if hasattr(self, "_bg_canvas"):
            return
        canvas = tk.Canvas(self.root, bg=COLOR_BG, highlightthickness=0)
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        # Canvas.lower()는 캔버스 아이템 메서드라 args 필요 — Tcl 직접 호출로 위젯 z-order 낮춤
        self.root.tk.call("lower", canvas._w)
        self._bg_canvas = canvas

    def _draw_bg_effects(self):
        """그라데이션 테두리 + 별자리를 bg_canvas에 그림. 정적(애니메이션 없음)."""
        import random
        if not hasattr(self, "_bg_canvas"):
            return
        c = self._bg_canvas
        c.delete("all")
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if w < 10 or h < 10:
            return

        # --- 그라데이션 테두리 (중심으로 갈수록 어두워짐) ---
        # 네온그린 기반 4단계 glow
        border_colors = ["#0e2b1c", "#0b2016", "#081610", "#060e0a"]
        for i, col in enumerate(border_colors):
            c.create_rectangle(i, i, w - i - 1, h - i - 1,
                               outline=col, width=1)

        # --- 별자리 ---
        random.seed(42)  # 고정 시드 → 매번 같은 패턴
        stars = []
        for _ in range(45):
            x = random.randint(8, w - 8)
            y = random.randint(8, h - 8)
            stars.append((x, y))
            # 별 크기: 대부분 1px, 간혹 2px
            r = 1 if random.random() > 0.15 else 2
            brightness = random.choice(["#1e2d24", "#162218", "#1a2a1f", "#243320"])
            c.create_oval(x - r, y - r, x + r, y + r, fill=brightness, outline="")

        # 가까운 별끼리 연결 (거리 90px 이내, 최대 연결 30개)
        connections = 0
        for i in range(len(stars)):
            for j in range(i + 1, len(stars)):
                if connections >= 30:
                    break
                dx = stars[i][0] - stars[j][0]
                dy = stars[i][1] - stars[j][1]
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < 90:
                    c.create_line(
                        stars[i][0], stars[i][1],
                        stars[j][0], stars[j][1],
                        fill="#0f1f16", width=1,
                    )
                    connections += 1

    def _center(self, w, h):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}"

    def run(self):
        self.root.mainloop()


# ============================================================
# Tray Icon (pystray)
# ============================================================

def make_tray_image():
    """16x16 또는 32x32 'M' 픽셀 아이콘. 검정 배경 + 네온 그린."""
    if not HAS_TRAY:
        return None
    img = PILImage.new("RGB", (32, 32), (10, 10, 10))
    d = PILImageDraw.Draw(img)
    # M 글자 (대각선 두 줄 + 양쪽 세로)
    g = (0, 255, 156)
    # 좌세로
    d.rectangle([6, 6, 9, 26], fill=g)
    # 우세로
    d.rectangle([22, 6, 25, 26], fill=g)
    # 가운데 V (대각선 두 줄)
    for i in range(8):
        d.point((9 + i, 7 + i), fill=g)
        d.point((10 + i, 7 + i), fill=g)
        d.point((22 - i, 7 + i), fill=g)
        d.point((21 - i, 7 + i), fill=g)
    return img


class TrayController:
    """pystray 트레이 아이콘 + 좌클릭=Show, 우클릭=Show/Quit."""

    def __init__(self, on_show, on_quit):
        if not HAS_TRAY:
            self.icon = None
            return
        self.icon = pystray.Icon(
            "maran_launcher",
            icon=make_tray_image(),
            title=TRAY_TITLE,
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Show MARAN.LAUNCH", on_show, default=True,
                ),
                pystray.MenuItem(
                    "GAME :: 우주 생존기", self._open_game,
                ),
                pystray.MenuItem("Quit", on_quit),
            ),
        )

    def run(self):
        if self.icon:
            try:
                self.icon.run()
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass

    def _open_game(self, icon, item):
        import webbrowser
        url = "https://maran-chat-2026.web.app/game/"
        webbrowser.open(url)


# ============================================================
# Single Instance (socket-based)
# ============================================================

def try_acquire_single_instance():
    """첫 인스턴스면 listening socket 반환. 이미 떠있으면 None."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT))
        s.listen(5)
        return s
    except OSError:
        return None


def send_signal_to_first_instance(signal=b"SHOW"):
    """이미 떠있는 인스턴스에 신호 전송."""
    # Windows 포그라운드 잠금 해제: 이 프로세스가 가진 전면권을 다른 프로세스에게 양도
    # (키보드 단축키로 실행된 2번째 인스턴스만 이 권한을 가짐)
    if os.name == "nt" and b"SHOW" in signal:
        try:
            import ctypes
            ASFW_ANY = 0xFFFFFFFF
            ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT))
        s.sendall(signal + b"\n")
        s.close()
        return True
    except Exception:
        return False


def listen_for_signals(server_sock, launcher):
    """첫 인스턴스의 listener 스레드. SHOW/QUIT 받음."""
    while True:
        try:
            client, _ = server_sock.accept()
            data = client.recv(64)
            client.close()
            if not data:
                continue
            if b"SHOW" in data:
                launcher.show_window()
            elif b"QUIT" in data:
                launcher.quit_app()
                break
        except Exception:
            time.sleep(0.5)


# ============================================================
# Entry Point
# ============================================================

def main():
    p = argparse.ArgumentParser(description="마란 런처")
    p.add_argument("--auto", action="store_true",
                   help="(레거시) 자동으로 VS Code 모드 실행")
    p.add_argument("--vscode", action="store_true",
                   help="자동으로 VS Code Remote-SSH 모드 실행")
    p.add_argument("--terminal", action="store_true",
                   help="자동으로 Terminal SSH 모드 실행")
    p.add_argument("--setup", action="store_true",
                   help="환경 설정 화면으로 시작 (강제)")
    p.add_argument("--quit", action="store_true",
                   help="실행 중인 마란 런처 종료 (트레이 포함)")
    p.add_argument("--version", action="version",
                   version=f"마란 런처 v{__version__}")
    args = p.parse_args()

    # --quit: 실행 중인 인스턴스에 종료 신호만 보내고 끝
    if args.quit:
        sent = send_signal_to_first_instance(b"QUIT")
        sys.exit(0 if sent else 1)

    auto_mode = None
    if args.terminal:
        auto_mode = "terminal"
    elif args.vscode or args.auto:
        auto_mode = "vscode"

    # === 단일 인스턴스 체크 ===
    server_sock = try_acquire_single_instance()
    if server_sock is None:
        # 이미 마란 런처가 떠있음 → 그쪽에 SHOW 신호 보내고 자기는 종료
        send_signal_to_first_instance(b"SHOW")
        # 모드 자동 실행 요청이면 SHOW 다음 자동 모드는 무시 (간단 처리)
        sys.exit(0)

    # === 첫 인스턴스 ===
    launcher = MaranLauncher(auto_mode=auto_mode, force_setup=args.setup)

    # 트레이 시작 (pystray 있을 때만)
    if HAS_TRAY:
        tray = TrayController(
            on_show=lambda icon=None, item=None: launcher.show_window(),
            on_quit=lambda icon=None, item=None: launcher.quit_app(),
        )
        launcher.attach_tray(tray)
        threading.Thread(target=tray.run, daemon=True).start()

    # 단일 인스턴스 listener 스레드
    threading.Thread(
        target=listen_for_signals, args=(server_sock, launcher), daemon=True,
    ).start()

    launcher.run()


if __name__ == "__main__":
    main()
