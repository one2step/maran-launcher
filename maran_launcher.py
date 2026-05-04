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

# === 색상 (Catppuccin Mocha) ===
COLOR_BG = "#1e1e2e"
COLOR_PANEL = "#181825"
COLOR_FG = "#cdd6f4"
COLOR_DIM = "#6c7086"
COLOR_OK = "#a6e3a1"
COLOR_WARN = "#f9e2af"
COLOR_ERROR = "#f38ba8"
COLOR_PROGRESS = "#f9e2af"
COLOR_BTN_VSCODE = "#89b4fa"
COLOR_BTN_VSCODE_HOVER = "#b4befe"
COLOR_BTN_TERM = "#a6e3a1"
COLOR_BTN_TERM_HOVER = "#c6f0bd"
COLOR_BTN_INSTALL = "#fab387"
COLOR_BTN_INSTALL_HOVER = "#ffc4a0"
COLOR_BTN_NEUTRAL = "#45475a"
COLOR_BTN_NEUTRAL_HOVER = "#585b70"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_CONSOLE = 0x00000010 if os.name == "nt" else 0


# ============================================================
# Prereq Check Functions
# ============================================================

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


def find_code_exe():
    """code / code.cmd 의 실제 경로를 반환. PATH에 없어도 일반 설치 위치 탐색."""
    for name in ("code.cmd", "code"):
        p = shutil.which(name)
        if p:
            return p
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd",
        Path(r"C:\Program Files\Microsoft VS Code\bin\code.cmd"),
        Path(r"C:\Program Files (x86)\Microsoft VS Code\bin\code.cmd"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def check_vscode_installed():
    return find_code_exe() is not None


def check_remote_ssh_extension():
    code = find_code_exe()
    if not code:
        return False
    try:
        r = subprocess.run(
            [code, "--list-extensions"],
            shell=True, capture_output=True, text=True,
            timeout=15, creationflags=CREATE_NO_WINDOW,
        )
        return "ms-vscode-remote.remote-ssh" in (r.stdout or "")
    except Exception:
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

def winget_install(package_id, log_fn):
    if not check_winget_available():
        return False, "winget 미설치 (Windows 10 1809 이전 버전). 직접 설치 필요."
    log_fn(f"winget으로 {package_id} 설치 중... (UAC 창 뜨면 '예' 클릭)")
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


def install_tailscale(log_fn):
    ok, msg = winget_install("Tailscale.Tailscale", log_fn)
    if ok:
        log_fn("✅ Tailscale 설치 완료. Tailscale 앱에서 로그인이 필요합니다.")
        time.sleep(1)
        open_tailscale_app(log_fn)
    return ok, msg


def install_vscode(log_fn):
    return winget_install("Microsoft.VisualStudioCode", log_fn)


def install_windows_terminal(log_fn):
    return winget_install("Microsoft.WindowsTerminal", log_fn)


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
    """Main view용: 진행 상태 ○/◐/●/✗"""

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
        # 우측 상단 설정 버튼
        top = tk.Frame(self.frame, bg=COLOR_BG)
        top.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Button(
            top, text="⚙", font=("Segoe UI Symbol", 12),
            bg=COLOR_BG, fg=COLOR_DIM,
            activebackground=COLOR_BG, activeforeground=COLOR_FG,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self.on_setup if self.on_setup else lambda: None,
            padx=6,
        ).pack(side=tk.RIGHT)

        tk.Label(
            self.frame, text="🚀 마란 런처",
            font=("맑은 고딕", 18, "bold"),
            fg=COLOR_FG, bg=COLOR_BG,
        ).pack(pady=(2, 4))

        tk.Label(
            self.frame, text="맥미니에 어떻게 접속할까요?",
            font=("맑은 고딕", 9),
            fg=COLOR_DIM, bg=COLOR_BG,
        ).pack(pady=(0, 14))

        btns = tk.Frame(self.frame, bg=COLOR_BG)
        btns.pack(pady=(0, 14))

        self.btn_vscode = tk.Button(
            btns, text="🖥  VS Code", width=14,
            font=("맑은 고딕", 11, "bold"),
            bg=COLOR_BTN_VSCODE, fg="#1e1e2e",
            activebackground=COLOR_BTN_VSCODE_HOVER,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=lambda: self.start("vscode"),
            padx=10, pady=8,
        )
        self.btn_vscode.pack(side=tk.LEFT, padx=6)

        self.btn_term = tk.Button(
            btns, text="💻  Terminal", width=14,
            font=("맑은 고딕", 11, "bold"),
            bg=COLOR_BTN_TERM, fg="#1e1e2e",
            activebackground=COLOR_BTN_TERM_HOVER,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=lambda: self.start("terminal"),
            padx=10, pady=8,
        )
        self.btn_term.pack(side=tk.LEFT, padx=6)

        rows = tk.Frame(self.frame, bg=COLOR_BG)
        rows.pack(fill=tk.X, padx=60)
        self.s_tail = StatusRow(rows, "Tailscale 연결")
        self.s_tail.pack(fill=tk.X, pady=3)
        self.s_mac = StatusRow(rows, "맥미니 응답")
        self.s_mac.pack(fill=tk.X, pady=3)
        self.s_run = StatusRow(rows, "실행")
        self.s_run.pack(fill=tk.X, pady=3)

        self.log_var = tk.StringVar(value="원하는 모드를 선택하세요.")
        tk.Label(
            self.frame, textvariable=self.log_var,
            font=("맑은 고딕", 9), fg=COLOR_DIM, bg=COLOR_BG,
            wraplength=400, justify=tk.CENTER,
        ).pack(pady=(12, 6), padx=20)

        opts = tk.Frame(self.frame, bg=COLOR_BG)
        opts.pack(pady=(0, 12))

        self.auto_close = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="완료 후 자동 닫기",
            variable=self.auto_close,
            font=("맑은 고딕", 9),
            fg=COLOR_DIM, bg=COLOR_BG,
            selectcolor=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_FG, bd=0,
        ).pack(side=tk.LEFT, padx=8)

        self.auto_claude = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts, text="Terminal: 자동 claude 실행",
            variable=self.auto_claude,
            font=("맑은 고딕", 9),
            fg=COLOR_DIM, bg=COLOR_BG,
            selectcolor=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_FG, bd=0,
        ).pack(side=tk.LEFT, padx=8)

    def log(self, msg):
        self.log_var.set(msg)
        self.frame.update_idletasks()

    def start(self, mode):
        self.btn_vscode.config(state=tk.DISABLED)
        self.btn_term.config(state=tk.DISABLED)
        for s in (self.s_tail, self.s_mac, self.s_run):
            s.pending()
        self.s_run.label.config(
            text="VS Code 실행" if mode == "vscode" else "Terminal 실행"
        )
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
                self.btn_term.config(state=tk.NORMAL)
        except Exception as e:
            self.log(f"예기치 않은 오류: {e}")
            self._fail()

    def _fail(self):
        self.btn_vscode.config(state=tk.NORMAL)
        self.btn_term.config(state=tk.NORMAL)

    @staticmethod
    def _launch_vscode():
        host_spec = f"ssh-remote+{MAC_USER}@{MAC_HOST}"
        code = find_code_exe()
        if not code:
            return False
        try:
            subprocess.Popen(
                [code, "--remote", host_spec, MAC_PROJECT_PATH],
                shell=True if os.name == "nt" else False,
                creationflags=CREATE_NO_WINDOW,
            )
            return True
        except Exception:
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
        self.root.geometry(self._center(460, 430))
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
    p.add_argument("--terminal", action="store_true",
                   help="자동으로 Terminal SSH 모드 실행")
    p.add_argument("--setup", action="store_true",
                   help="환경 설정 화면으로 시작 (강제)")
    args = p.parse_args()

    auto_mode = None
    if args.terminal:
        auto_mode = "terminal"
    elif args.vscode or args.auto:
        auto_mode = "vscode"

    MaranLauncher(auto_mode=auto_mode, force_setup=args.setup).run()


if __name__ == "__main__":
    main()
