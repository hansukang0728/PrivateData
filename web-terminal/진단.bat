@echo off
cd /d "%~dp0"
title PoshDeck 진단
where py >nul 2>nul
if not errorlevel 1 (
  py -3 pyserver\check.py
) else (
  python pyserver\check.py
)
