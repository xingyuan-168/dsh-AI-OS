@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

where codex-os.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 goto from_path

if exist "%~dp0..\..\..\.venv\Scripts\codex-os.exe" goto from_source

if exist "%USERPROFILE%\.local\bin\codex-os.exe" goto from_user

1>&2 echo AI Engineering OS runtime not found. Run: uv tool install ^<repository-root^>
exit /b 50

:from_path
codex-os.exe mcp
exit /b %ERRORLEVEL%

:from_source
"%~dp0..\..\..\.venv\Scripts\codex-os.exe" mcp
exit /b %ERRORLEVEL%

:from_user
"%USERPROFILE%\.local\bin\codex-os.exe" mcp
exit /b %ERRORLEVEL%
