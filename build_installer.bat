@echo off
REM ============================================================
REM  Map Poster Studio - build a Windows installer (Setup.exe)
REM  Rebuilds the exe first, finds Inno Setup 7 (or 6),
REM  then makes dist\MapPosterStudio-Setup-<version>.exe
REM ============================================================
setlocal
cd /d "%~dp0"

REM Always rebuild the exe so the installer never packs an out-of-date copy.
call build.bat /quiet || goto :fail

set "ISCC="
call :findiscc "%ProgramFiles%\Inno Setup 7\ISCC.exe"
call :findiscc "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
call :findiscc "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
call :findiscc "%ProgramFiles%\Inno Setup 6\ISCC.exe"
call :findiscc "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
call :findiscc "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  echo Inno Setup not found in the usual folders - trying winget...
  winget install --id JRSoftware.InnoSetup.7 -e --silent --accept-package-agreements --accept-source-agreements
  call :findiscc "%ProgramFiles%\Inno Setup 7\ISCC.exe"
  call :findiscc "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
  call :findiscc "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
)
if not defined ISCC (
  echo Could not find Inno Setup. Install Inno Setup 7 from https://jrsoftware.org/isdl.php and run this again.
  goto :fail
)
echo Using Inno Setup compiler: %ISCC%

for /f "delims=" %%V in ('.venv\Scripts\python.exe -c "import mapposter; print(mapposter.__version__)"') do set "VER=%%V"
echo Building installer for version %VER% ...
"%ISCC%" /DMyAppVersion=%VER% installer\MapPosterStudio.iss || goto :fail

echo.
echo ============================================================
echo  Installer: %cd%\dist\MapPosterStudio-Setup-%VER%.exe
echo ============================================================
if /i not "%~1"=="/quiet" pause
exit /b 0

:findiscc
if defined ISCC exit /b 0
if exist %1 set "ISCC=%~1"
exit /b 0

:fail
echo.
echo INSTALLER BUILD FAILED - scroll up for the error.
if /i not "%~1"=="/quiet" pause
exit /b 1
