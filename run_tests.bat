@echo off
REM ============================================================
REM  Map Poster Studio - theme regression test
REM  Renders a small saved map of downtown Phoenix in every theme and
REM  compares it with tests\baseline. No internet or .pbf needed.
REM    run_tests.bat            check
REM    run_tests.bat --update   accept the current look as the new baseline
REM  Differences: tests\output\*_diff.png  (baseline | now | difference)
REM ============================================================
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo No .venv yet - run build.bat once first.
  if /i not "%~1"=="/quiet" pause
  exit /b 1
)
.venv\Scripts\python.exe tests\regress.py %*
set "RC=%ERRORLEVEL%"
if /i not "%~1"=="/quiet" if /i not "%~1"=="--update" pause
exit /b %RC%
