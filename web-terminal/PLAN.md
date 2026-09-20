# 웹 기반 터미널 (PoshDeck) — 설계 계획서

Chrome에서 열리는 웹 UI로, 좌측 파일 탐색기 + 우측 다중 PowerShell 터미널을 제공하는 PC용 로컬 도구.

---

## 1. 요구사항 정리

| # | 요구사항 | 구현 방향 |
|---|---|---|
| 1 | PC(Windows) 환경에서 동작 | 로컬 Node.js 에이전트 + 브라우저 UI |
| 2 | Chrome에서 HTML로 동작 | SPA (정적 HTML/JS) + `http://127.0.0.1:7788` |
| 3 | 좌측 탐색기, 폴더 우클릭 = 윈도우 탐색기 동작 + "여기서 터미널 열기" | REST 파일 API + 컨텍스트 메뉴, 셸 연동 |
| 4 | 터미널 탭 이름 수정 | 탭 더블클릭/F2 인라인 편집, 워크스페이스에 저장 |
| 5 | 스크롤로 과거 출력 전부 확인 | xterm.js scrollback 10,000줄 + 검색 + 세션 직렬화 |
| 6 | 여러 테마 선택 | Windows Terminal 색상 스킴 포맷 호환 테마 JSON |

## 2. 아키텍처

```
┌──────────────── Chrome (http://127.0.0.1:7788) ────────────────┐
│  web/  (정적 SPA)                                              │
│   ├ explorer   : 트리 + 컨텍스트 메뉴                           │
│   ├ tabs       : 탭 바 / 이름 편집 / 분할                        │
│   ├ termhost   : xterm.js 인스턴스 관리                         │
│   └ theme      : 색상 스킴 로드 & 적용                          │
└───────────┬───────────────────────────────┬────────────────────┘
       REST │ /api/fs/*                  WS │ /pty?id=...
┌───────────┴───────────────────────────────┴────────────────────┐
│  server/  (Node.js, 127.0.0.1 바인딩)                          │
│   ├ fs-api      : 목록/생성/이름변경/삭제(휴지통)/복사/붙여넣기   │
│   ├ shell-api   : 탐색기에서 열기, 속성 대화상자, 기본앱 실행     │
│   ├ pty-manager : node-pty 로 pwsh.exe / powershell.exe 스폰     │
│   └ security    : 토큰 인증 + Origin 검사 + 경로 화이트리스트     │
└────────────────────────────────────────────────────────────────┘
```

**왜 로컬 서버가 필요한가** — 브라우저 단독으로는 임의 경로의 파일시스템 열람이나 프로세스 생성이 불가능하다(File System Access API는 사용자가 고른 폴더만, 프로세스는 아예 불가). 따라서 "HTML로 동작"은 UI 레이어에 한정하고, 실제 동작은 PC에서 돌아가는 작은 Node 에이전트가 담당한다.

**대안 비교**
- **로컬 서버 + Chrome (채택)** — 설치 가볍고, Chrome 그대로 사용, 원격 접속으로 확장 가능.
- Electron 앱 — 배포는 단일 exe로 편하지만 "Chrome에서 HTML" 요구와 어긋나고 용량 크다. 나중에 같은 web/ 코드를 그대로 감싸면 전환 가능하도록 설계한다.
- ttyd / wetty — 터미널만 제공. 탐색기·탭 이름·테마 요구를 만족 못 함.

## 3. 기술 스택

- **서버**: Node.js 20+, Express, `ws`, [`node-pty`](https://github.com/microsoft/node-pty) (ConPTY 사용), `trash`(휴지통 삭제), `chokidar`(탐색기 자동 갱신)
- **프론트**: 프레임워크 없이 ES 모듈 + [`xterm.js`](https://xtermjs.org) (`fit`, `search`, `webgl`, `serialize`, `unicode11` 애드온)
- **셸**: 기본 `pwsh.exe`(PowerShell 7), 없으면 `powershell.exe`(5.1), 선택지로 `cmd.exe` / WSL

## 4. API 설계

### REST (파일 작업)
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/fs/list?path=` | 하위 폴더/파일 목록 (이름, 크기, 수정일, 속성) |
| GET | `/api/fs/drives` | 드라이브 목록 (C:, D:, 네트워크) |
| POST | `/api/fs/mkdir` | 새 폴더 |
| POST | `/api/fs/rename` | 이름 바꾸기 |
| POST | `/api/fs/delete` | 삭제 (기본 휴지통, `permanent:true`면 영구) |
| POST | `/api/fs/clipboard` | 복사/잘라내기 → 붙여넣기 |
| POST | `/api/shell/open` | 기본 앱으로 열기 (`start ""`) |
| POST | `/api/shell/reveal` | Windows 탐색기에서 표시 (`explorer /select,`) |
| POST | `/api/shell/properties` | 속성 대화상자 (`Shell.Application` COM) |

### WebSocket (터미널)
```
클라 → 서버 : {type:"spawn", cwd, shell, cols, rows}
              {type:"input", data}
              {type:"resize", cols, rows}
서버 → 클라 : {type:"data", data}
              {type:"exit", code}
```
- 세션은 서버에 유지 → 브라우저 새로고침/탭 닫힘 후에도 재연결하면 출력이 이어진다.

## 5. 탐색기 컨텍스트 메뉴 매핑

| 메뉴 | 단축키 | 구현 |
|---|---|---|
| 열기 | Enter | `shell/open` |
| **여기서 터미널 열기** ▸ | | 새 탭 spawn (`PowerShell 7` / `Windows PowerShell` / `cmd` / `WSL`) |
| 새 창에서 열기 | | 탐색기 루트 변경 |
| 새로 만들기 ▸ 폴더 / 텍스트 문서 | | `fs/mkdir`, `fs/write` |
| 잘라내기 / 복사 / 붙여넣기 | Ctrl+X/C/V | `fs/clipboard` |
| 이름 바꾸기 | F2 | 인라인 편집 → `fs/rename` |
| 삭제 | Del / Shift+Del | `fs/delete` (휴지통 / 영구) |
| 경로 복사 | Ctrl+Shift+C | 클립보드 |
| Windows 탐색기에서 표시 | | `shell/reveal` |
| 속성 | Alt+Enter | `shell/properties` |

## 6. 터미널 탭

- 탭 추가(+) / 닫기(x) / 드래그 재정렬 / Ctrl+Tab 순환
- **이름 편집**: 더블클릭 또는 F2 → 인라인 입력 → Enter 확정, Esc 취소. 기본 이름은 `폴더명 — pwsh`
- 탭별 셸 종류 아이콘, 실행 중 표시(●), 종료된 탭은 흐리게
- 분할(Split): 우측 영역을 2~4 페인으로 나눠 동시에 보기
- 상태는 `localStorage`에 워크스페이스 단위로 저장 (탭 이름/경로/순서/테마)

## 7. 스크롤백

- `scrollback: 10000` (설정에서 조절), 마우스 휠 / Shift+PgUp / Ctrl+Home
- Ctrl+F 검색 하이라이트 + 다음/이전
- 탭 전환 시 스크롤 위치 보존, `SerializeAddon`으로 세션 복원
- "전체 로그 저장" → `.txt` / `.html` 내보내기

## 8. 테마

Windows Terminal color scheme JSON과 같은 키(`background`, `foreground`, `black`~`brightWhite`, `cursorColor`, `selectionBackground`)를 사용해 기존 스킴을 그대로 붙여넣을 수 있게 한다. 같은 토큰으로 UI 크롬(탭 바, 탐색기)도 물들여 한 덩어리로 보이게 한다.

기본 제공: Campbell(PowerShell 기본), One Half Dark, Dracula, Nord, Tokyo Night, Gruvbox Dark, Rosé Pine, Solarized Light.
추가 설정: 폰트(Cascadia Code / JetBrains Mono / D2Coding), 글자 크기, 줄 간격, 커서 모양, 배경 투명도.

## 9. 로드맵

| 단계 | 내용 | 산출물 |
|---|---|---|
| M0 | 목업 확정 (현재 단계) | `mockups/index.html` — 레이아웃 3안 · 테마 8종 |
| M1 | 서버 뼈대 + PTY 1개 연결 | 브라우저에서 PowerShell 입출력 성공 |
| M2 | 탭 다중화 · 이름 편집 · 분할 | 요구 3·4 완료 |
| M3 | 탐색기 트리 + 컨텍스트 메뉴 | 요구 3 완료 |
| M4 | 테마 엔진 · 스크롤백 · 검색 · 세션 복원 | 요구 5·6 완료 |
| M5 | 설정 저장, 단축키, 패키징(`npx poshdeck`) | 배포본 |

## 10. 보안 주의

로컬 터미널을 여는 서버이므로 사실상 원격 코드 실행 창구다. 반드시:
- `127.0.0.1`에만 바인딩 (`0.0.0.0` 금지)
- 실행 시 1회용 토큰 발급 → URL 쿼리로 전달, 이후 쿠키 저장
- WebSocket `Origin` 검사, CSRF 방지
- 파일 API는 지정한 루트 밖 경로 접근 차단(`path.resolve` 후 prefix 검사)
- 외부 공개가 필요하면 Cloudflare Tunnel 등 인증 있는 경로로만

## 11. 다음 액션

목업 3안 중 하나를 고르면 M1(서버 뼈대 + PTY 연결)부터 실제 코드로 착수한다.
