@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo [PoshDeck] Node.js를 찾을 수 없습니다.
  echo            https://nodejs.org 에서 설치하거나  winget install OpenJS.NodeJS.LTS  를 실행하세요.
  pause
  exit /b 1
)

if not exist "node_modules\express" (
  echo [PoshDeck] 처음 실행이라 의존성을 설치합니다. 몇 분 걸릴 수 있습니다...
  call npm install
  if errorlevel 1 (
    echo [PoshDeck] 설치에 실패했습니다. 위 오류를 확인하세요.
    pause
    exit /b 1
  )
)

node server\index.js
echo.
echo [PoshDeck] 서버가 종료되었습니다.
pause
