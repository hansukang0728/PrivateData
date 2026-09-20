# PrivateData

새로 만드는 작업물을 담는 저장소.

## 구성

| 경로 | 내용 |
|---|---|
| `web-terminal/` | 웹 기반 PowerShell 터미널(PoshDeck) — 설계 계획서 + 목업 |

### web-terminal

Chrome에서 열리는 PowerShell 작업대. 좌측 파일 탐색기(윈도우 탐색기식 우클릭 메뉴 + "여기서 터미널 열기"),
우측 다중 터미널 탭(이름 편집 가능), 스크롤백, 테마 8종.

- `web-terminal/PLAN.md` — 아키텍처, API 설계, 로드맵 M0~M5
- `web-terminal/mockups/index.html` — 동작 목업. 더블클릭하면 Chrome에서 바로 열립니다

다음 단계는 M1(로컬 Node 에이전트 + node-pty로 PowerShell 세션 연결).
