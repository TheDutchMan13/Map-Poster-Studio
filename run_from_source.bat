@echo off
REM Run without building the exe (uses the .venv that build.bat creates).
REM No arguments opens the window; arguments are passed to the command line,
REM e.g.  run_from_source.bat -c Phoenix -C USA -t noir -d 6mi
cd /d "%~dp0"
if not exist .venv (
  echo Run build.bat once first to set up the environment.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python MapPosterStudio.py %*
