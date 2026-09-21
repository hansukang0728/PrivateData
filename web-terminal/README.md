# PoshDeck

Chrome 에서 여는 PowerShell 작업대. 왼쪽은 파일 탐색기, 오른쪽은 부모–자식으로 묶인 터미널 그룹.

```
┌─ 탐색기 ─┬─ 부모 터미널 ───────┬─ ① data      ● 실행 ─┐
│ 📁 data  │                     ├─ ② output ───────────┤
│ 📁 docs  │  PS C:\...>         ├─ ③ docs ─────────────┤
│ 📁 output│                     │ ▏④ logs      ⌃ 펼치기 │
└──────────┴─────────────────────┴──────────────────────┘
```

> 명령줄을 별로 안 쓰신다면 **[`사용법.txt`](사용법.txt)** 를 여세요. 메모장에서 바로 열리는 한글 사용 설명서입니다.

## 실행

**`poshdeck.bat` 더블클릭.** 끝입니다. 설치할 것도, 내려받을 것도 없습니다.
서버가 뜨면 Chrome 이 자동으로 열립니다. 창을 닫아도 서버는 살아 있고,
**검은 콘솔 창에서 Ctrl+C** 를 눌러야 완전히 종료됩니다.

필요한 것: **Python 3.8 이상**뿐입니다. `py -3 --version` 으로 확인하세요.
pip 로 설치할 패키지가 **하나도 없습니다** — 표준 라이브러리만 씁니다.
브라우저 쪽 라이브러리(xterm.js)도 `web/vendor/` 에 붙박이로 들어 있습니다.

```powershell
py -3 pyserver\poshdeck.py      # 직접 띄우기
py -3 pyserver\poshdeck.py --no-open   # 브라우저 자동 실행 없이
```

### Node 백엔드 (선택)

Node 가 있는 환경이라면 그쪽으로도 돕니다. 기능은 같습니다.

```powershell
npm install      # express, ws, node-pty
npm start
```

`poshdeck.bat` 은 Python → Node 순으로 찾아서 있는 쪽으로 띄웁니다.

## 쓰는 법

| 하고 싶은 것 | 방법 |
|---|---|
| 자식 터미널 만들기 | 부모 페인 헤더의 **⊕** → 하위 폴더 선택 · 또는 `Ctrl+Shift+D` |
| 다른 폴더에서 터미널 열기 | 탐색기에서 폴더 **우클릭** → "자식 터미널로 열기" / "새 그룹으로 열기" |
| 새 그룹 | 탭 바의 **＋** · `Ctrl+Shift+T` |
| 자식 사이 이동 | 페인 클릭 · `Alt+1~4` (부모는 `Alt+0`) |
| 이름 바꾸기 | 페인 헤더 이름 **더블클릭** · `F2` |
| 접힌 자식 펼치기 | 오른쪽 열 아래 **막대 클릭** |
| 글자 크기 | 탭 바의 `A−` `A+` · `Ctrl +/−` · 페인 위에서 **`Ctrl+휠`** 은 그 창만 |
| 검색 | `Ctrl+F` |
| 탐색기 접기 | `Ctrl+B` |
| 테마 | 탭 바 오른쪽 ◑ |
| 접기·승격·닫기 | 페인 헤더 **우클릭** |

자식이 화면 한도(기본 3개)를 넘으면 가장 오래 안 쓴 자식이 아래 막대로 접힙니다.
**실행 중인 터미널(● 표시)은 접기에서 보호**됩니다. 접혀도 세션은 살아 있어 출력이 계속 쌓입니다.

그룹 구성·폴더·이름·배치는 **자동 저장**되어 다음에 열면 그대로 복원됩니다(실행 중이던 명령은 복원하지 않습니다).

| 문서 | 내용 |
|---|---|
| [`사용법.txt`](사용법.txt) | 한글 사용 설명서 (메모장용, 더블클릭) |
| [`SPEC-groups.md`](SPEC-groups.md) | 부모–자식 그룹 규칙 |
| [`PLAN.md`](PLAN.md) | 전체 설계와 로드맵 |

## 구조

웹 UI 하나에 백엔드 둘. 프로토콜이 같아서 어느 쪽으로 띄워도 화면은 같습니다.

```
pyserver/            ← 기본. 표준 라이브러리만, 설치 불필요
  poshdeck.py   HTTP + WebSocket 서버, 토큰 발급
  sessions.py   셸 세션 — 출력 분배, "바쁜가/어디인가" 추적
  ptyconpty.py  Windows ConPTY 를 ctypes 로 직접 호출
  ptyposix.py   리눅스·맥용 PTY (개발/검증용)
  wsproto.py    RFC 6455 WebSocket 프레이밍
  fsops.py      파일 작업 + 윈도우 셸 동작

server/              ← 선택. Node 가 있는 환경용
  index.js      Express + ws / pty.js  node-pty
  fsapi.js · shellops.js · security.js · workspace.js
web/
  app.js        그룹 상태와 화면 — 여기가 규칙의 본체
  term.js       페인 하나 = xterm 하나
  explorer.js   탐색기 · conn.js  WebSocket · menu.js  메뉴/토스트 · themes.js  테마
  vendor/       xterm.js 배포본 (npm 없이 쓰려고 저장소에 포함)
```

## 보안

로컬 터미널을 여는 서버입니다. 사실상 이 PC에서 명령을 실행할 수 있는 창구입니다.

- `127.0.0.1` 에만 바인딩합니다. 외부에서는 접속할 수 없습니다
- 실행할 때마다 **1회용 토큰**을 새로 발급합니다. 콘솔에 찍힌 주소를 남에게 주지 마세요
- WebSocket 은 Origin 을, 쓰기 요청은 CSRF 를 검사합니다
- 파일 접근 범위는 **제한 없음(C: 전체)** 이 기본입니다. 좁히려면 설정 파일의 `roots` 에 폴더를 넣으세요:

```json
// %LOCALAPPDATA%\poshdeck\config.json
{ "roots": ["C:\\Users\\hansu\\HansuKangDailyData"], "defaultShell": "pwsh", "port": 7788 }
```

## 잘 안 될 때

| 증상 | 해볼 것 |
|---|---|
| `Python 도 Node 도 찾을 수 없습니다` | `py -3 --version` 을 쳐보세요. 없으면 Microsoft Store 의 Python 은 설치 권한 없이 받을 수 있습니다 |
| `ConPTY(CreatePseudoConsole)가 없습니다` | Windows 10 1809(2018년) 이상이 필요합니다. 그 아래 버전은 Node 백엔드 + node-pty 로만 가능합니다 |
| `npm install` 에서 node-pty 빌드 실패 | Node 백엔드를 쓸 때만 해당됩니다. Python 쪽으로 띄우면 이 문제가 없습니다 |
| 터미널이 비어 있고 "세션이 종료되었습니다" | PowerShell 7 이 없을 수 있습니다. `config.json` 의 `defaultShell` 을 `"powershell"`(5.1) 로 바꿔 보세요 |
| 프롬프트에 이상한 글자가 보임 | 셸 초기화 스크립트(`%LOCALAPPDATA%\poshdeck\psinit.ps1`)를 지우면 다시 생성됩니다 |
| 한글이 깨짐 | 폰트를 Cascadia Mono 또는 D2Coding 으로. 출력 인코딩은 UTF-8 로 맞춰져 있습니다 |
| 포트 충돌 | 7788 이 쓰이고 있으면 자동으로 다음 포트를 찾습니다. 콘솔에 찍힌 주소를 보세요 |
| 브라우저가 401 | 토큰이 든 주소로 들어가야 합니다. 콘솔의 주소를 그대로 복사하세요 |

## 지금 상태

- **Python 백엔드**(기본) — 리눅스에서 전 구간 확인: 세션 생성·입출력·한글 출력·자식 4개 생성과 접기·
  탐색기·우클릭 메뉴·새로고침 후 세션 유지까지
- **Node 백엔드**(선택) — 같은 범위를 리눅스에서 확인
- **Windows 의 ConPTY 경로는 미검증** — 이 저장소를 만든 환경이 리눅스라 `pwsh.exe` 를 띄워볼 수 없었습니다.
  첫 실행에서 문제가 나오면 검은 콘솔 창의 내용을 그대로 알려주세요
- 다음: 탭 드래그 재정렬, 그룹을 별도 창으로 떼기, 스크롤백 내보내기
