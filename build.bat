@echo off
REM ============================================================
REM  Map Poster Studio - build the Windows exe
REM  Double-click this file. Needs Python 3.11+ installed.
REM  Result: dist\MapPosterStudio\MapPosterStudio.exe
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY="
for %%V in (3.12 3.13 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)
echo Using: %PY%

if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat || goto :fail

echo Installing dependencies (first time takes a few minutes)...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :fail

echo Building exe...
pyinstaller --noconfirm --clean MapPosterStudio.spec || goto :fail

echo Smoke test...
dist\MapPosterStudio\MapPosterStudio.exe --list-themes >nul || goto :fail

echo Theme regression test...
python tests\regress.py >nul 2>&1 && echo   all themes match the baseline. || echo   WARNING: theme regression test found changes. Run run_tests.bat to see them.

echo.
echo ============================================================
echo  Built: %cd%\dist\MapPosterStudio\MapPosterStudio.exe
echo  Copy the whole dist\MapPosterStudio folder anywhere you like.
echo ============================================================
if /i not "%~1"=="/quiet" pause
exit /b 0

:fail
echo.
echo BUILD FAILED - scroll up for the error.
if /i not "%~1"=="/quiet" pause
exit /b 1
