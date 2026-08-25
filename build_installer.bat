:: Build the OpenRender Windows installer with Inno Setup.
:: Looks for ISCC.exe (Inno Setup 6 or 7) in the usual per-user/machine paths.
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ISCC="
for %%P in (
    "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
    "%ProgramFiles%\Inno Setup 7\ISCC.exe"
) do (
    if exist %%~P if not defined ISCC set "ISCC=%%~P"
)

if not defined ISCC (
    echo   ERROR: Inno Setup not found.
    echo   Install it from https://jrsoftware.org/isdl.php ^(free^), then run
    echo   this script again. The installer script is:
    echo     installer\OpenRender-installer.iss
    exit /b 1
)

echo   Using: %ISCC%
echo   Compiling installer...
"%ISCC%" "installer\OpenRender-installer.iss"
if errorlevel 1 (
    echo   ERROR: compilation failed - see messages above.
    exit /b 1
)
echo.
echo   Installer ready: installer-output\OpenRender-Setup-0.0.1-beta.exe
exit /b 0
