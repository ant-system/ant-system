@echo off
cd /d "%~dp0"
set "ANTPYW="
where pyw >nul 2>nul && set "ANTPYW=pyw"
if not defined ANTPYW (
  where pythonw >nul 2>nul && set "ANTPYW=pythonw"
)
if defined ANTPYW (
  start "" /b %ANTPYW% launcher.py
  exit /b 0
)
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
start "" /b %ANTPY% launcher.py
exit /b 0
