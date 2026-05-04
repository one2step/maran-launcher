# 🚀 마란 런처

`Ctrl + Alt + M` 한 번으로 VS Code Remote-SSH가 맥미니의 `~/MARAN` 폴더를 자동으로 열어주는 윈도우 런처.

---

## ⚡ 다른 노트북에 원클릭 설치 (PowerShell 한 줄)

GitHub Release만 있으면 외부 단축 서비스 없이 한 줄:

**PowerShell**:
```powershell
irm github.com/<USER>/<REPO>/releases/latest/download/i.ps1 | iex
```

**cmd**:
```cmd
powershell -c "irm github.com/<USER>/<REPO>/releases/latest/download/i.ps1|iex"
```

(`release.ps1`이 `i.ps1`을 짧은 이름으로 같이 업로드합니다.
`https://` 없어도 `irm`이 자동으로 붙입니다.)

### 동작

이 한 줄이 자동으로:
1. 최신 `마란런처.exe` 다운로드 → `%LOCALAPPDATA%\Programs\MaranLauncher\`
2. 바탕화면 + 시작메뉴에 바로가기 + `Ctrl+Alt+M` 단축키 등록
3. 첫 실행 시 환경 설정 화면이 떠서 Tailscale/SSH/VS Code 자동 설치

**최초 1회 GitHub 설정**이 필요합니다 — 아래 [개발자: GitHub Release 발행](#-개발자-github-release-발행) 참조.

---

## 구성 파일

| 파일 | 역할 |
|------|------|
| `maran_launcher.py` | tkinter 기반 런처 본체 (다크 테마 GUI) |
| `build.bat` | PyInstaller로 단일 exe 생성 + 바탕화면 복사 |
| `MARAN_LAUNCHER_README.md` | 이 문서 |

빌드 후 `dist\마란런처.exe` 가 생성됨.

---

## 동작 흐름

`마란런처.exe` 실행 → 두 모드 중 선택:

### 🖥 VS Code 모드
1. **Tailscale 연결** — `100.122.161.94:22` TCP 도달 확인
2. **맥미니 응답** — `ssh moran@100.122.161.94 "echo ok"` 무비번 검증
3. **VS Code 실행** — `code --remote ssh-remote+moran@100.122.161.94 /Users/moran/MARAN`

### 💻 Terminal 모드
1~2. 위와 동일
3. **Terminal 실행** — Windows Terminal(없으면 PowerShell, cmd 순) 새 창에서:
   - 옵션 ON (기본): `ssh -t moran@100.122.161.94 "cd ~/MARAN && claude"`
   - 옵션 OFF: `ssh moran@100.122.161.94`

자동 닫기 체크박스가 켜져있으면 런처 창은 1.5초 뒤 자동 종료.

### CLI 플래그
| 플래그 | 동작 |
|--------|------|
| (없음) | 자동 검사 → 누락 시 설정 화면, 정상이면 메인 화면 |
| `--vscode` | 정상이면 VS Code 모드 자동 실행. 누락 시 설정 화면 |
| `--terminal` | 정상이면 Terminal 모드 자동 실행. 누락 시 설정 화면 |
| `--auto` | (레거시) `--vscode`와 동일 |
| `--setup` | 강제로 환경 설정 화면 열기 (점검/재설치용) |

---

## 빌드 방법

```cmd
build.bat
```

내부에서 자동 실행되는 단계:
- Python / pyinstaller 설치 확인
- `pyinstaller --onefile --noconsole --name "마란런처" maran_launcher.py`
- 산출물: `dist\마란런처.exe`
- 옵션: 바탕화면에 복사 (`y/n` 묻는 프롬프트)

---

## 단축키 등록 (`Ctrl + Alt + M`)

1. 바탕화면 `마란런처.exe` 우클릭 → **바로 가기 만들기**
2. 생성된 바로가기 우클릭 → **속성**
3. **대상**: 자동 모드 원하면 끝에 플래그 추가
   ```
   "C:\Users\<USER>\Desktop\마란런처.exe"              # GUI에서 선택
   "C:\Users\<USER>\Desktop\마란런처.exe" --vscode     # VS Code 자동
   "C:\Users\<USER>\Desktop\마란런처.exe" --terminal   # 터미널 자동
   ```
4. **바로 가기 키** 칸 클릭 → `Ctrl + Alt + M` 입력
5. 확인

추천: 바로가기 두 개 만들어서
- `Ctrl + Alt + M` → 플래그 없이 (GUI에서 매번 선택)
- `Ctrl + Alt + V` → `--vscode`
- `Ctrl + Alt + T` → `--terminal`

식으로 단축키 분리해도 OK.

---

## 사전 조건 (자동 검사 + 자동 설치)

마란 런처는 첫 실행 시 다음 항목을 자동으로 검사하고, 누락된 것이 있으면 **🔧 환경 설정** 화면으로 안내합니다:

| 항목 | 자동 설치 | 비고 |
|------|-----------|------|
| Tailscale | ✅ winget | 설치 후 앱에서 사용자 로그인 1회 필요 |
| Tailscale 로그인 (맥 도달) | ❌ | Tailscale 앱에서 직접 로그인 |
| SSH 키 | ✅ ssh-keygen | `~/.ssh/id_ed25519` 자동 생성 |
| 맥미니 무비번 SSH | ❌ | PowerShell 창에서 비번 1회 입력 |
| VS Code (옵션) | ✅ winget | VS Code 모드 쓸 때만 |
| Remote-SSH 확장 (옵션) | ✅ `code --install-extension` | VS Code 모드 쓸 때만 |
| Windows Terminal (옵션) | ✅ winget | Terminal 모드 UX 향상 |

**🚀 모두 자동 설치** 버튼 한 번이면 위 ✅ 항목이 일괄 설치됩니다 (UAC 창에서 '예' 클릭 필요).

수동 단계 두 가지(Tailscale 로그인, SSH 키 등록)는 가이드된 화면이 알려주는 대로 따라가면 됩니다.

---

## 설정 변경

`maran_launcher.py` 상단의 상수만 바꾸고 다시 빌드:

```python
MAC_HOST = "100.122.161.94"
MAC_USER = "moran"
MAC_PROJECT_PATH = "/Users/moran/MARAN"
```

다른 폴더용 런처(예: MOAI 전용)는 파일 복사 후 위 상수만 바꿔서 별도 이름으로 빌드.

---

## 트러블슈팅

| 증상 | 원인 / 해결 |
|------|-------------|
| ✗ Tailscale 연결 | Tailscale 트레이 아이콘이 로그인 상태인지 확인. 맥미니가 켜져있는지 확인 |
| ✗ 맥미니 응답 | SSH 키 무비번 등록 안됨. 위 "사전 조건" 항목 참조 |
| ✗ VS Code 실행 | `code` 명령이 PATH에 없음. VS Code에서 PATH 등록 후 PowerShell 재시작 |
| 빌드 시 한글 깨짐 | `build.bat` 첫 줄 `chcp 65001` 확인. CMD 글꼴이 한글 지원하는지 확인 |
| 바로가기 단축키 인식 안됨 | 바탕화면 / 시작메뉴 안의 바로가기에서만 동작. exe 자체에는 단축키 못 검 |

---

## 라이선스 / 비고

개인 프로젝트용 내부 도구. tkinter는 Python 표준 라이브러리이므로 추가 설치 불필요.
