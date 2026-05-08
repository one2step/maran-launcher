# CLAUDE.md

Claude Code가 이 프로젝트에서 작업할 때 필요한 맥락 정보.

## 프로젝트 개요

**마란 런처 (Maran Launcher)** — Windows에서 `Ctrl+Alt+M` 한 번으로 맥미니 `~/MARAN` 폴더에 SSH로 자동 연결해주는 작은 GUI 런처.

- 형은 윈도우 PC들과 맥미니를 Tailscale로 연결해서, 어느 PC에서든 빠르게 맥미니의 Claude Code 환경에 진입하기 위해 만듦.
- **세 가지 모드** (v1.1+): VS Code Remote-SSH / **사무실 (VS Code + Pixel Agents)** / Terminal SSH.
- **자동 업데이트** (v1.1+): 시작 시 GitHub release 체크 → 새 버전 있으면 상단 노란 배너 → 클릭 시 install.ps1 자동 재실행.
- **파일 드롭존 + Ctrl+V** (v1.1+): 런처 창에 파일 드래그 / 클립보드 이미지·파일 Ctrl+V → scp로 Mac mini `~/MARAN/inbox/` 자동 업로드.
- **NAS 빠른 액션** (v1.2+): [📁 폴더 열기] 한 번에 Windows 탐색기에서 `\\100.122.161.94\MARAN` 마운트. [📋 주소 복사]로 SMB 주소 클립보드. 큰 드롭존 + [파일 업로드]/[클립보드] 두 버튼 분리 + outbox 폴더 (Mac→Windows 양방향).
- **공유폴더 (NAS 작업 영역)** (v1.3+): [🗂 공유폴더] 버튼 → `\\100.122.161.94\MARAN\shared` 직접 진입. `~/MARAN/shared/`는 NAS처럼 자유롭게 쓰는 작업 폴더 (코드/메모리와 분리). inbox/outbox는 자동화용, shared는 사용자가 직접 들락날락.
- **v2.0 해커 톤 전면 리디자인** (v2.0+): Mr.Robot/lazygit 영감. 검정 배경 + 옅은 흰 + 네온그린(동작)/앰버(주의)/사이안(정보) 액센트. Cascadia Mono 폰트. 섹션 헤더 STATUS/EXEC/NAS/TRANSFER로 정보 밀도 높임. 클립보드 버튼 제거 (Ctrl+V 통합). 업데이트는 하단 footer에 항상 표시 (새 버전 있으면 빨간 강조). HackerStatusRow 클래스로 `▸ name ......... ● ACTIVE` 한 줄.

## Repo / 배포

- **GitHub**: https://github.com/one2step/maran-launcher (Public)
- **원클릭 설치 명령**: `irm bit.ly/maran44 | iex`
  - bit.ly/maran44 → GitHub release의 `i.ps1`로 redirect
- **Tech 스택**: Python 3.12 + tkinter + PyInstaller (Windows .exe)
- **사용자 PC 설치 위치**: `%LOCALAPPDATA%\Programs\MaranLauncher\MaranLauncher.exe`

## 파일 구조

| 파일 | 역할 |
|------|------|
| `maran_launcher.py` | 본체. GUI(Setup/Main 두 화면) + prereq 검사/설치 로직 |
| `make_icon.py` | Catppuccin 톤 M 아이콘 생성 (PIL) |
| `build.bat` | 로컬 PyInstaller 빌드 (Windows 전용) |
| `release.ps1` | gh CLI 사용. 빌드 → 태그 → GitHub Release 자동 (Windows 전용) |
| `install.ps1` / `dist/i.ps1` | 사용자가 `irm \| iex`로 받는 설치 스크립트 (ASCII only, PS5.1 호환) |
| `selfcheck.py` | 모든 prereq 함수 + 경로 탐색 검증용 (개발자용) |
| `icon.ico` / `icon.png` | 앱 아이콘 |
| `.github/workflows/release.yml` | 태그 push 시 GitHub Actions가 자동 빌드 + 릴리즈 |

## 핵심 설정 (maran_launcher.py 상단)

```python
MAC_HOST = "100.122.161.94"      # 맥미니 Tailscale IP
MAC_USER = "moran"
MAC_PROJECT_PATH = "/Users/moran/MARAN"

__version__ = "1.1.0"            # release 태그(v1.1.0)와 일치시킬 것
GITHUB_REPO = "one2step/maran-launcher"
INBOX_REMOTE_DIR = "~/MARAN/inbox"
PIXEL_AGENTS_EXT_ID = "pablodelucca.pixel-agents"
```

**버전 올릴 때**: `__version__` 상수 수정 → 같은 값으로 git tag (`v1.x.y`) push.
GitHub Actions가 빌드 → 다음 사용자 런처 시작 시 자동 업데이트 배너 뜸.

## 아키텍처 메모

### GUI
- **tkinter** (PySide6 안 씀 — exe 크기/의존성 절약)
- **두 화면 전환**: `SetupView` (prereq 설치) ↔ `MainView` (모드 선택)
- 첫 실행에서 기본 prereq(`check_mac_reachable + check_ssh_no_password`) 실패하면 자동으로 Setup으로
- 우측 상단 ⚙ 버튼으로 언제든 Setup 회귀

### Prereq 자동 설치 (3단계 폴백)
모든 winget 호출은 `winget_install()`로 통합. 흐름:
1. winget 호출
2. winget 자체가 없으면 `install_winget()` (AppX 재등록 → GitHub releases msixbundle 다운로드)
3. winget 끝까지 안 되면 항목별 직접 다운로드 폴백:
   - Tailscale: `https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe`
   - VS Code: 공식 User installer + `/VERYSILENT`
   - Windows Terminal: Microsoft Store 페이지 자동 열기

### VS Code 실행 (다중 폴백)
Remote-SSH가 가장 자주 깨지는 부분. `_launch_vscode()`는 4단 폴백:
1. `os.startfile("vscode://vscode-remote/ssh-remote+user@host/path")` — URL 핸들러 (PATH/code.cmd 의존성 0)
2. `cmd /c start "" vscode://...` — URL 핸들러 다른 경로
3. `code --folder-uri vscode-remote://...` — canonical CLI
4. `code --remote ssh-remote+host /path` — legacy CLI

`find_code_exe()`는 PATH → 레지스트리에서 PATH 다시 읽기 → 일반 설치 위치 → `HKEY_CLASSES_ROOT\vscode\shell\open\command` 까지 4단 탐색.

### 확장 설치 검증
`code --list-extensions` CLI 안 씀 (PATH 의존성 때문에 가끔 실패). 대신 `~/.vscode/extensions/` 폴더에 `ms-vscode-remote.remote-ssh-*` 디렉토리 존재 여부 직접 검사.

## 인코딩 함정 (꼭 알아둘 것)

- **PowerShell 5.1은 BOM 없는 UTF-8 파일을 ANSI/CP949로 잘못 디코드**.
- 한국어 윈도우에서 launcher가 임시 .ps1 파일 생성 시 → 한글 깨지면서 파일명/경로 파라미터 손상 → 실패.
- 해결: 임시 .ps1 파일은 **반드시 UTF-8 BOM 붙여서 저장** (`b"\xef\xbb\xbf" + content.encode("utf-8")`).
- 또는 ASCII-only로 작성. `install.ps1`은 사용자 PC에서 `irm | iex`로 실행되므로 영문만 사용.
- launcher 본체 GUI는 한글 OK (.exe에 박혀있어 인코딩 이슈 없음).

## 빌드 / 릴리즈

### 로컬 (Windows에서)
```cmd
build.bat
```

### GitHub Release (Windows에서)
```powershell
.\release.ps1                  # 자동 버전
.\release.ps1 -Version v1.2.0  # 명시적
```
- `gh release create` 사용
- 자산 3개: `maran-launcher.exe`, `install.ps1`, `i.ps1`
- "latest" 태그가 자동으로 새 릴리즈를 가리킴 (bit.ly 링크 그대로 유지됨)

### Mac에서 빌드하려면 → GitHub Actions
PyInstaller로 .exe 빌드는 Windows 전용. Mac에서는 직접 빌드 불가.
대신 `.github/workflows/release.yml`이 태그 push에 트리거됨:
```bash
git tag v1.0.1
git push origin v1.0.1
# GitHub Actions가 windows-latest 러너에서 빌드 → release 발행
```

## 알려진 제약

- 1인 사용 도구. Tailscale + SSH 키 + GitHub 한 계정 가정
- 윈도우 7/8 미지원 (Tailscale 자체가 미지원)
- macOS는 코드상 지원 (`os.name != "nt"` 분기 있음) 하지만 미테스트

## v1.1+ 신규 컴포넌트

### 자동 업데이트 (`fetch_latest_version`, `is_newer_version`, `trigger_self_update`)
- MainView 생성 즉시 백그라운드 스레드 → GitHub `releases/latest` API 호출 (5초 타임아웃)
- `__version__` 보다 새 태그 있으면 상단 노란 배너 표시
- 업데이트 버튼 클릭 → PowerShell 새 창 + `irm bit.ly/maran44 | iex` 자동 실행
- install.ps1이 .exe 덮어쓰기 처리 (런처 종료 후 재시작 안내)

### 사무실 모드 (`mode == "office"`)
- 동작: VS Code Remote-SSH + (없으면) Pixel Agents 익스텐션 페이지 자동 띄움
- Pixel Agents (`pablodelucca.pixel-agents`)가 Claude Code 트랜스크립트(`~/.claude/projects/...`) 읽어서 캐릭터 애니메이션
- 익스텐션은 **Mac mini 측**에 설치됨 (`~/.vscode-server/extensions/`)
- 체크 방법: SSH로 Mac mini에서 `ls ~/.vscode-server/extensions/pablodelucca.pixel-agents-*`

### 파일 드롭존 (`upload_file_to_mac`, `upload_clipboard_to_mac`)
- MainView 하단 `tk.Label` 드롭존 + 클릭 시 파일 다이얼로그
- `windnd` (Windows-only, hidden import 필수) → 진짜 드래그&드롭
- `PIL.ImageGrab.grabclipboard()` → 클립보드 이미지/파일 경로 추출
- `tk.clipboard_get()` → 텍스트 폴백
- 모두 Mac mini의 `~/MARAN/inbox/`로 scp 업로드 (없으면 mkdir)

### 의존성 추가
- `pillow` (이미 있음, ImageGrab 용)
- `windnd` (Windows drag&drop)
- PyInstaller hidden imports: `windnd`, `PIL.ImageGrab`

## 개선 아이디어 (TODO — v1.2+)

- 여러 폴더 프로파일 지원 (현재는 `/Users/moran/MARAN` 하드코딩)
- 손상된 `~/.vscode-server` 자동 정리
- 마지막 사용 모드 기억 (settings.json)
- macOS / Linux 빌드 추가 (다른 사람이 형 환경 흉내내고 싶을 때)
- inbox 자동 정리 정책 (예: 30일 지난 파일 자동 이동)
- 사무실 모드 진입 시 VS Code의 Pixel Agents 패널 자동 표시 (URL command 가능 여부 조사)
- 클립보드 텍스트 paste 시 파일명에 첫 줄 일부 포함 (`maran_clip_<timestamp>_first_line.txt`)

## 자주 까먹는 것

- 사용자가 `irm bit.ly/maran44 | iex`로 받는 .ps1은 GitHub release asset (`i.ps1`). 수정 후엔 release에 재업로드 필수
- bit.ly 링크는 release latest로 redirect되므로 코드 수정해도 링크 그대로 둬도 됨
- maran 런처 GUI는 한국어로 두되, 사용자 PC에서 실행되는 .ps1 (install.ps1, 임시 push key 스크립트) 은 ASCII or BOM 필수
- VS Code Remote-SSH 첫 연결 시 VS Code Server 설치에 1~2분 — 사용자가 "안 떠요" 하면 그거일 수 있음
