@echo off
rem Dubbelklicka för att starta DeHazeIQ på Windows.
chcp 65001 >nul
cd /d "%~dp0"

where ffmpeg >nul 2>nul
if errorlevel 1 (
  if not exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
    echo FFmpeg saknas. Installera det i en terminal med:
    echo   winget install ffmpeg
    echo Starta sedan om datorn eller logga ut och in igen.
    echo.
    pause
    exit /b 1
  )
)

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3 saknas. Installera det med:  winget install Python.Python.3.12
  echo eller fran https://www.python.org ^(kryssa i "Add python.exe to PATH"^).
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Forbereder forsta start ^(skapar .venv och installerar paket^) ...
  %PY% -m venv .venv || goto :fel
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fel
)

".venv\Scripts\python.exe" -m dehazeiq %*
if errorlevel 1 pause
exit /b 0

:fel
echo.
echo Installationen misslyckades. Se felmeddelandet ovan.
pause
exit /b 1
