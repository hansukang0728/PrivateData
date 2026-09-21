@echo off
cd /d "%~dp0"
title PoshDeck 셸 메뉴 진단
echo 마우스를 메뉴가 뜨길 원하는 위치에 두고 잠시 기다리세요.
echo.
set "T=%~1"
if "%T%"=="" set "T=%CD%"
where py >nul 2>nul
if not errorlevel 1 ( py -3 pyserver\shellmenu.py "%T%" ) else ( python pyserver\shellmenu.py "%T%" )
