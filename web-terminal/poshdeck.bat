@echo off
setlocal
cd /d "%~dp0"
title PoshDeck

rem ── 1순위: Python (설치할 패키지가 없습니다) ────────────────
where py >nul 2>nul
if not errorlevel 1 goto runpy
where python >nul 2>nul
if not errorlevel 1 goto runpython
goto trynode

:runpy
py -3 pyserver\poshdeck.py %*
goto done

:runpython
python pyserver\poshdeck.py %*
goto done

rem ── 2순위: Node (있으면 이쪽도 됩니다) ──────────────────────
:trynode
where node >nul 2>nul
if errorlevel 1 goto nothing
if not exist "node_modules\express" (
  echo [PoshDeck] Node 의존성을 설치합니다. 몇 분 걸릴 수 있습니다...
  call npm install
  if errorlevel 1 goto npmfail
)
node server\index.js %*
goto done

:npmfail
echo.
echo [PoshDeck] npm 설치에 실패했습니다. Python 이 있다면 그쪽이 더 간단합니다.
goto done

:nothing
echo.
echo [PoshDeck] Python 도 Node 도 찾을 수 없습니다.
echo.
echo   Python 은 대부분의 Windows 에 이미 있거나, Microsoft Store 에서
echo   설치 권한 없이 받을 수 있습니다. 명령 프롬프트에서 아래를 쳐보세요:
echo.
echo       py -3 --version
echo       python --version
echo.

:done
echo.
echo [PoshDeck] 서버가 종료되었습니다.
pause
