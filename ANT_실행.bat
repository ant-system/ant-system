@echo off
cd /d "%~dp0"
set "ANTPY="
where py >nul 2>nul && set "ANTPY=py"
if not defined ANTPY (
  where python >nul 2>nul && set "ANTPY=python"
)
if not defined ANTPY (
  echo Python 3 is required.
  pause
  exit /b 1
)
%ANTPY% launcher.py
