# Mac mini ↔ Windows/iPhone 파일 공유 셋업 (SMB + Tailscale)

마란 런처의 드롭존/클립보드 붙여넣기는 즉석 전송용이고, 폴더 통째로 파일 탐색하면서 옮기고 싶을 땐 **SMB 공유**가 더 편함.

이미 Tailscale + SSH 키 셋업은 마란 런처가 다 해놨다고 가정.

---

## 1단계 — Mac mini에서 SMB 공유 켜기 (3분, 1회만)

**GUI 방식 (권장)**:
1. Mac mini에서 시스템 설정 → 일반 → 공유
2. **파일 공유** 토글 ON
3. ⓘ 옆 → **공유 폴더**에 `MARAN` 폴더 (`/Users/moran/MARAN`) 추가
4. 사용자 권한: `moran` → **읽기 및 쓰기**
5. 옵션 → **SMB로 파일 및 폴더 공유** 체크
6. **WindowsTo** 옆 → moran 계정 체크 → 비번 입력 (이게 Windows에서 마운트 시 입력할 비번)

**CLI 방식 (참고만, GUI보다 까다로움)**:
```bash
# Mac mini SSH 접속 후
sudo sharing -a /Users/moran/MARAN -n MARAN -s 001
sudo launchctl load -w /System/Library/LaunchDaemons/com.apple.smbd.plist
```

확인:
```bash
sharing -l   # 공유 목록 출력
```

---

## 2단계 — Windows에서 접근 (셋업 1분)

### 방법 A: 탐색기 주소창 직접 입력 (즉석 사용)

Windows + E 키 → 탐색기 주소창에:
```
\\100.122.161.94\MARAN
```

처음 한 번 자격증명 묻는 창:
- 사용자: `moran`
- 비밀번호: Mac 사용자 비번
- ☑ 자격증명 기억 — 체크

이후 즉시 접근 가능. 드래그 앤 드롭 그대로 동작.

### 방법 B: 네트워크 드라이브로 매핑 (반영구)

탐색기 → 내 PC 우클릭 → **네트워크 드라이브 연결**:
- 드라이브: `M:` (또는 원하는 글자)
- 폴더: `\\100.122.161.94\MARAN`
- ☑ 로그인할 때 다시 연결
- ☑ 다른 자격 증명을 사용하여 연결

→ 이후 `M:\` 드라이브가 항상 마운트 상태.

### 방법 C: cmd 일회성 (스크립트용)

```cmd
net use M: \\100.122.161.94\MARAN /user:moran <비번> /persistent:yes
```

해제: `net use M: /delete`

---

## 3단계 — iPhone Files 앱에서 접근

1. Files 앱 → 우상단 ⋯ → **서버에 연결**
2. 서버: `smb://100.122.161.94`
3. 등록된 사용자 → moran / Mac 비번
4. 이후 Files 사이드바에 즉시 나타남, 사진 드래그하면 업로드

---

## 보안 노트

- Tailscale tailnet 안에서만 접근 가능 (외부 인터넷 노출 X)
- SMB는 일반적인 LAN 프로토콜이라 Tailscale 안에서 안전
- 비번은 Mac 로그인 비번 그대로 — 약하면 SMB 전용 강한 비번으로 별도 사용자 만들기 권장 (1인 운영이라 큰 이슈는 아님)

---

## 트러블슈팅

| 증상 | 원인 / 해결 |
|------|-------------|
| 탐색기에서 못 찾음 | Tailscale 켜져있는지, Mac mini 슬립 아닌지 확인 |
| 자격증명 거부 | Windows에서 한 번 → 자격증명 관리자 → `100.122.161.94` 항목 삭제 후 재시도 |
| 한글 파일명 깨짐 | Mac SMB는 NFD, Windows는 NFC — Python으로 옮기는 거면 `unicodedata.normalize('NFC', name)` |
| iPhone에서 연결 안됨 | smb:// 프로토콜 명시 필수. 그냥 IP만 입력하면 SFTP로 가버림 |
| 속도 느림 | Tailscale 직접 연결(direct) 모드 확인. `tailscale status` → "direct" 아닌 "relay"면 NAT 문제 |

---

## 마란 런처 드롭존과의 차이

| 기능 | 적합한 상황 |
|------|------------|
| **마란 런처 드롭존 + Ctrl+V** | 즉석 한 장. 스크린샷 캡처 후 바로 Ctrl+V → ~/MARAN/inbox/ |
| **SMB 공유** | 폴더 탐색하면서 여러 파일 옮기기, Mac 파일 직접 편집 |
| **텔레그램** | 폰에서 한 장 빠르게 (지금처럼 계속 쓰기) |

세 가지 다 공존 가능. 상황 따라 골라 쓰면 됨.
