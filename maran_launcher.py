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
from pathlib import Path

# === 설정 ===
MAC_HOST = "100.122.161.94"
MAC_USER = "moran"
MAC_PROJECT_PATH = "/Users/moran/MARAN"
MAC_PROJECT_PATH_REMOTE = "~/MARAN"
SSH_PORT = 22
CONNECT_TIMEOUT = 5

# === 자동 업데이트 ===
__version__ = "2.0.0"  # release 태그와 일치시킬 것 (v2.0.0)
GITHUB_REPO = "one2step/maran-launcher"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
INSTALL_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/i.ps1"

# === 파일 드롭존 ===
INBOX_REMOTE_DIR = "~/MARAN/inbox"
OUTBOX_REMOTE_DIR = "~/MARAN/outbox"  # Mac→Windows 방향 (Claude가 올리는 곳)
SHARED_REMOTE_DIR = "~/MARAN/shared"  # NAS 작업 폴더 (사용자가 직접 들락날락)

# === NAS (SMB 공유) ===
SMB_SHARE_NAME = "MARAN"
SMB_PATH_WIN = f"\\\\{MAC_HOST}\\{SMB_SHARE_NAME}"      # \\100.122.161.94\MARAN
SMB_PATH_URL = f"smb://{MAC_HOST}/{SMB_SHARE_NAME}"     # smb://100.122.161.94/MARAN
SMB_PATH_SHARED = f"{SMB_PATH_WIN}\\shared"             # \\100.122.161.94\MARAN\shared

# === 사무실 모드 (Pixel Agents) ===
PIXEL_AGENTS_EXT_ID = "pablodelucca.pixel-agents"

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
COLOR_ACCENT_OFFICE = "#ffb800"   # 앰버
COLOR_ACCENT_TERM = "#00ff9c"     # 네온 그린

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


def check_pixel_agents_extension():
    """Mac mini의 ~/.vscode-server/extensions/ 에 pablodelucca.pixel-agents 있는지 SSH로 확인.
    Remote-SSH 모드라 VS Code 익스텐션은 Mac 쪽에 깔림."""
    if not check_ssh_no_password():
        return False
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             f"{MAC_USER}@{MAC_HOST}",
             "ls -d ~/.vscode-server/extensions/pablodelucca.pixel-agents-* 2>/dev/null | head -1"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return bool(r.stdout.strip())
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
    cmd = [
        "ssh", "-o", "BatchMode=yes",
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
            ["powershell", "-NoProfile", "-Command", ps1],
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
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
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
        ["powershell", "-NoProfile", "-Command", ps],
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


def install_pixel_agents_extension(log_fn):
    """VS Code 확장 페이지(pixel-agents)를 띄움. 사용자가 [Install in SSH: ...] 클릭."""
    if not check_vscode_installed():
        return False, "VS Code 먼저 설치 필요"

    url = f"vscode:extension/{PIXEL_AGENTS_EXT_ID}"
    try:
        os.startfile(url)
        log_fn("VS Code 확장 페이지 띄움 (Pixel Agents).")
        log_fn("→ Remote-SSH 워크스페이스가 열려있다면 [Install in SSH: 100.122.161.94]")
        log_fn("→ 아니면 일단 로컬 [Install] 후, 사무실 모드 처음 진입 시 Mac에 자동 설치됨")
        log_fn("→ 마란 런처로 돌아와 '🔄 새로고침' 클릭")
        return True, "VS Code에서 [Install] 후 새로고침"
    except Exception:
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                creationflags=CREATE_NO_WINDOW,
            )
            return True, "VS Code에서 [Install] 후 새로고침"
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


def get_smb_address_text():
    """클립보드 복사용 SMB 주소 (Windows 형식 + URL 형식 둘 다)."""
    return f"{SMB_PATH_WIN}\n{SMB_PATH_URL}"


def trigger_self_update(log_fn=None):
    """install.ps1 (i.ps1)을 PowerShell 새 창에서 실행 → 자동 다운로드 + 교체."""
    if os.name != "nt":
        return False, "Windows 전용"
    cmd = f"irm {INSTALL_URL} | iex"
    try:
        subprocess.Popen(
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass",
             "-Command", cmd],
            creationflags=CREATE_NEW_CONSOLE,
        )
        if log_fn:
            log_fn("PowerShell 창에서 업데이트 진행. 끝나면 런처를 다시 켜세요.")
        return True, "업데이터 띄움"
    except Exception as e:
        return False, str(e)


def ensure_inbox_dir():
    """Mac mini에 ~/MARAN/inbox/ + ~/MARAN/outbox/ + ~/MARAN/shared/ 폴더 보장."""
    try:
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             f"{MAC_USER}@{MAC_HOST}",
             f"mkdir -p {INBOX_REMOTE_DIR} {OUTBOX_REMOTE_DIR} {SHARED_REMOTE_DIR}"],
            capture_output=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return True
    except Exception:
        return False


def upload_file_to_mac(local_path, log_fn=None):
    """scp로 로컬 파일을 Mac mini의 ~/MARAN/inbox/ 에 업로드."""
    p = Path(local_path)
    if not p.exists() or not p.is_file():
        return False, f"파일 없음: {local_path}"

    if not check_mac_reachable():
        return False, "Mac mini 도달 불가 (Tailscale 점검)"

    target = f"{MAC_USER}@{MAC_HOST}:{INBOX_REMOTE_DIR}/"
    try:
        ensure_inbox_dir()
        r = subprocess.run(
            ["scp", "-B", "-o", "ConnectTimeout=10",
             str(p), target],
            capture_output=True, text=True, timeout=180,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            return True, f"업로드 완료: {p.name}"
        return False, (r.stderr or r.stdout or "scp 실패")[:200].strip()
    except FileNotFoundError:
        return False, "scp 없음. OpenSSH 클라이언트 설치 필요"
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
            ok, msg = upload_file_to_mac(fp, log_fn)
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
        return upload_file_to_mac(str(tmp), log_fn)

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
    return upload_file_to_mac(str(tmp), log_fn)


def open_tailscale_app(log_fn):
    candidates = [
        r"C:\Program Files\Tailscale\Tailscale.exe",
        r"C:\Program Files (x86)\Tailscale\Tailscale.exe",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                subprocess.Popen([p])
                log_fn("Tailscale 앱 실행. 로그인 후 '🔄 새로고침' 클릭하세요.")
                return True, "Tailscale 앱 띄움"
            except Exception:
                pass
    return False, "Tailscale 실행 파일을 찾지 못함. 먼저 설치하세요."


def generate_ssh_key(log_fn):
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
            ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            return True, "생성 완료"
        return False, (r.stderr or r.stdout or "")[:200]
    except FileNotFoundError:
        return False, ("ssh-keygen 없음. 설정 > 앱 > 선택적 기능에서 "
                       "'OpenSSH 클라이언트' 추가 필요.")
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
    pub_path_safe = str(pub).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
Write-Host ''
Write-Host 'Enter Mac password ONCE when prompted.' -ForegroundColor Yellow
Write-Host '(After this, SSH will work without password.)' -ForegroundColor DarkGray
Write-Host ''

$pub = (Get-Content -LiteralPath '{pub_path_safe}' -Raw).Trim()
$cmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pub' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

ssh -o StrictHostKeyChecking=accept-new {MAC_USER}@{MAC_HOST} $cmd
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
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass",
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
            bg=COLOR_BTN_INSTALL, fg="#1e1e2e",
            activebackground=COLOR_BTN_INSTALL_HOVER,
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
                bg=COLOR_BTN_INSTALL, fg="#1e1e2e",
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
        self._build()

    def pack(self, **kw): self.frame.pack(**kw)
    def pack_forget(self): self.frame.pack_forget()

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
            ("ssh_key", "SSH 키 생성",
             check_ssh_key, generate_ssh_key, "생성", True),
            ("ssh_no_pw", "맥미니 무비번 SSH",
             check_ssh_no_password, push_ssh_key_to_mac, "등록", True),
            ("vscode", "VS Code 설치 (옵션)",
             check_vscode_installed, install_vscode, "설치", False),
            ("remote_ssh", "VS Code Remote-SSH 확장 (옵션)",
             check_remote_ssh_extension, install_remote_ssh_extension,
             "VS Code 열기", False),
            ("pixel_agents", "Pixel Agents 익스텐션 (사무실 모드)",
             check_pixel_agents_extension, install_pixel_agents_extension,
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
            bg=COLOR_BTN_INSTALL, fg="#1e1e2e",
            activebackground=COLOR_BTN_INSTALL_HOVER,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.install_all,
            padx=14, pady=6,
        ).pack(side=tk.LEFT, padx=4)

        self.continue_btn = tk.Button(
            btns, text="메인으로  ➜",
            font=("맑은 고딕", 10, "bold"),
            bg=COLOR_BTN_VSCODE, fg="#1e1e2e",
            activebackground=COLOR_BTN_VSCODE_HOVER,
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
            self.continue_btn.config(text="✅ 메인으로  ➜", bg=COLOR_OK)
        else:
            self.continue_btn.config(text="메인으로  ➜", bg=COLOR_BTN_VSCODE)
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

    def _install_all_thread(self):
        self.log("\n=== 전체 자동 설치 시작 ===")
        # 사용자 입력 없이 가능한 항목들만 자동 실행
        sequence = [
            ("tailscale_install", install_tailscale),
            ("vscode", install_vscode),
            ("wt", install_windows_terminal),
            ("remote_ssh", install_remote_ssh_extension),
            ("ssh_key", generate_ssh_key),
        ]
        for key, fn in sequence:
            row = self.rows[key]
            if row.check_fn():
                self.log(f"⏭  {row.name}: 이미 OK")
                continue
            row.set_busy()
            self.log(f"\n▶ {row.name}")
            try:
                result = fn(self.log)
                if isinstance(result, tuple):
                    ok, msg = result
                else:
                    ok, msg = bool(result), ""
                self.log(("✅ " if ok else "❌ ") + (msg or ("완료" if ok else "실패")))
            except Exception as e:
                self.log(f"❌ 오류: {e}")
            time.sleep(0.4)

        self.log("\n=== 자동 설치 종료 ===")
        self.log("👉 다음 단계는 수동입니다:")
        self.log("   1) 'Tailscale 열기' → 앱에서 로그인 → '새로고침'")
        self.log("   2) '등록' → 새 PowerShell 창에서 비번 1회 입력 → '새로고침'")
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
        # HEADER — MARAN.LAUNCH v1.x.y / TARGET / setup btn
        # ════════════════════════════════════════════════════════
        header = tk.Frame(self.frame, bg=COLOR_BG)
        header.pack(fill=tk.X, padx=14, pady=(10, 0))

        title_left = tk.Frame(header, bg=COLOR_BG)
        title_left.pack(side=tk.LEFT)
        tk.Label(
            title_left, text="MARAN.LAUNCH",
            font=FONT_TITLE, fg=COLOR_OK, bg=COLOR_BG,
        ).pack(side=tk.LEFT)
        tk.Label(
            title_left, text=f"  v{__version__}",
            font=FONT_MONO, fg=COLOR_DIM2, bg=COLOR_BG,
        ).pack(side=tk.LEFT, padx=(2, 0))

        tk.Button(
            header, text="[⚙ setup]",
            font=FONT_MONO, fg=COLOR_DIM, bg=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_OK,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.on_setup if self.on_setup else lambda: None,
        ).pack(side=tk.RIGHT)

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
        # STATUS — Tailscale / SSH / Pixel Agents 라이브 상태
        # ════════════════════════════════════════════════════════
        self._section_header(self.frame, "STATUS")
        status_box = tk.Frame(self.frame, bg=COLOR_BG)
        status_box.pack(fill=tk.X, padx=20, pady=(2, 4))
        self.s_tail = HackerStatusRow(status_box, "tailscale")
        self.s_tail.pack(fill=tk.X, pady=1)
        self.s_mac = HackerStatusRow(status_box, "ssh-agent")
        self.s_mac.pack(fill=tk.X, pady=1)
        self.s_run = HackerStatusRow(status_box, "pixel-agents")
        self.s_run.pack(fill=tk.X, pady=1)

        self._sep(self.frame)

        # ════════════════════════════════════════════════════════
        # EXEC — 모드 선택 버튼 3개
        # ════════════════════════════════════════════════════════
        self._section_header(self.frame, "EXEC")
        exec_box = tk.Frame(self.frame, bg=COLOR_BG)
        exec_box.pack(fill=tk.X, padx=20, pady=(2, 6))

        self.btn_vscode = self._hack_btn(
            exec_box, "▸ vscode", COLOR_ACCENT_VSCODE,
            lambda: self.start("vscode"),
        )
        self.btn_vscode.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_office = self._hack_btn(
            exec_box, "▸ office", COLOR_ACCENT_OFFICE,
            lambda: self.start("office"),
        )
        self.btn_office.pack(side=tk.LEFT, padx=6)

        self.btn_term = self._hack_btn(
            exec_box, "▸ shell", COLOR_ACCENT_TERM,
            lambda: self.start("terminal"),
        )
        self.btn_term.pack(side=tk.LEFT, padx=6)

        # 옵션 (작게)
        opts = tk.Frame(self.frame, bg=COLOR_BG)
        opts.pack(fill=tk.X, padx=20, pady=(2, 4))
        self.auto_close = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="auto-close",
            variable=self.auto_close,
            font=FONT_MONO_TINY,
            fg=COLOR_DIM, bg=COLOR_BG,
            selectcolor=COLOR_PANEL2,
            activebackground=COLOR_BG, activeforeground=COLOR_FG, bd=0,
        ).pack(side=tk.LEFT)
        self.auto_claude = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="shell→claude",
            variable=self.auto_claude,
            font=FONT_MONO_TINY,
            fg=COLOR_DIM, bg=COLOR_BG,
            selectcolor=COLOR_PANEL2,
            activebackground=COLOR_BG, activeforeground=COLOR_FG, bd=0,
        ).pack(side=tk.LEFT, padx=(8, 0))

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
        # TRANSFER — 드롭존 (Ctrl+V 안내, 클립보드 버튼 제거)
        # ════════════════════════════════════════════════════════
        self._section_header(self.frame, "TRANSFER", suffix="  → ~/MARAN/inbox/")

        drop_outer = tk.Frame(
            self.frame, bg=COLOR_PANEL,
            highlightbackground=COLOR_BORDER, highlightthickness=1,
        )
        drop_outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=(2, 6))

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

    def _refresh_conn_state(self):
        """target_bar 우측 연결 상태 라벨 갱신."""
        try:
            ok = check_mac_reachable()
            txt = "● DIRECT" if ok else "● UNREACHABLE"
            color = COLOR_OK if ok else COLOR_ERROR
            self.frame.after(0, lambda: self.conn_state.config(text=txt, fg=color))
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
            self._upload_files(paths)
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
                return
        self.log(f"❌ {msg}")
        self._flash_drop_zone(COLOR_ERROR)

    def _upload_files(self, paths):
        threading.Thread(
            target=self._upload_files_thread, args=(paths,), daemon=True
        ).start()

    def _upload_files_thread(self, paths):
        ok_count = 0
        for p in paths:
            self.log(f"⬆ 업로드: {Path(p).name}")
            ok, msg = upload_file_to_mac(p, self.log)
            if ok:
                ok_count += 1
                self.log(f"✅ {msg}")
            else:
                self.log(f"❌ {Path(p).name}: {msg}")
        if ok_count > 0:
            self._flash_drop_zone(COLOR_OK)
            self.log(f"📦 {ok_count}/{len(paths)} 업로드 완료 → ~/MARAN/inbox/")
        else:
            self._flash_drop_zone(COLOR_ERROR)

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
        self.btn_office.config(state=tk.DISABLED)
        self.btn_term.config(state=tk.DISABLED)
        for s in (self.s_tail, self.s_mac, self.s_run):
            s.pending()
        run_label = {
            "vscode": "VS Code 실행",
            "office": "VS Code + 사무실 실행",
            "terminal": "Terminal 실행",
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
            elif mode == "office":
                self.log("VS Code + Pixel Agents 사무실 실행 중...")
                ok = self._launch_vscode()
                if ok:
                    if not check_pixel_agents_extension():
                        self.log("⚠ Pixel Agents 익스텐션 미설치 — VS Code에서 자동 설치 페이지가 뜹니다.")
                        try:
                            time.sleep(2)
                            os.startfile(f"vscode:extension/{PIXEL_AGENTS_EXT_ID}")
                        except Exception:
                            pass
                fail_msg = "VS Code 실행 실패. ⚙ 설정에서 점검하세요."
                done_msg = "✅ VS Code 열리면 하단 [Pixel Agents] 패널 → '+ Agent' 클릭."
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

            if self.auto_close.get():
                self.frame.after(1500, self.frame.master.destroy)
            else:
                self.btn_vscode.config(state=tk.NORMAL)
                self.btn_office.config(state=tk.NORMAL)
                self.btn_term.config(state=tk.NORMAL)
        except Exception as e:
            self.log(f"예기치 않은 오류: {e}")
            self._fail()

    def _fail(self):
        self.btn_vscode.config(state=tk.NORMAL)
        self.btn_office.config(state=tk.NORMAL)
        self.btn_term.config(state=tk.NORMAL)

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
            ssh_args = ["ssh", "-t", target, remote_cmd]
        else:
            ssh_args = ["ssh", target]

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
                ["powershell", "-NoExit", "-Command", ps_cmd],
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
        # v2.0: 모노스페이스 + 정보 밀도 → 좀 좁고 길게
        self.root.geometry(self._center(560, 700))
        # 사용자가 창 크기 조절 가능
        self.root.resizable(True, True)
        # 윈도우 배경 + 타이틀바 톤 통일 (Tk 한계로 타이틀바는 OS 기본)
        self.root.configure(bg=COLOR_BG)
        self.main_view.pack(fill=tk.BOTH, expand=True)

    def _center(self, w, h):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}"

    def run(self):
        self.root.mainloop()


def main():
    p = argparse.ArgumentParser(description="마란 런처")
    p.add_argument("--auto", action="store_true",
                   help="(레거시) 자동으로 VS Code 모드 실행")
    p.add_argument("--vscode", action="store_true",
                   help="자동으로 VS Code Remote-SSH 모드 실행")
    p.add_argument("--office", action="store_true",
                   help="자동으로 사무실 모드 (VS Code + Pixel Agents) 실행")
    p.add_argument("--terminal", action="store_true",
                   help="자동으로 Terminal SSH 모드 실행")
    p.add_argument("--setup", action="store_true",
                   help="환경 설정 화면으로 시작 (강제)")
    p.add_argument("--version", action="version",
                   version=f"마란 런처 v{__version__}")
    args = p.parse_args()

    auto_mode = None
    if args.terminal:
        auto_mode = "terminal"
    elif args.office:
        auto_mode = "office"
    elif args.vscode or args.auto:
        auto_mode = "vscode"

    MaranLauncher(auto_mode=auto_mode, force_setup=args.setup).run()


if __name__ == "__main__":
    main()
