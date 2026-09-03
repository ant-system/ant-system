@echo off
cd /d "%~dp0"
if not exist "%~dp0ANT_실행.vbs" (
  echo ANT_실행.vbs 파일이 없습니다.
  pause
  exit /b 1
)
start "" wscript.exe "%~dp0ANT_실행.vbs"
exit /b 0
