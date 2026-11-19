@echo off
rem Keep this file ASCII-only and CRLF: cmd.exe misparses UTF-8 batch files.
rem Chinese messages come from the Python side.
setlocal
pushd "%~dp0."

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :no_python

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto :old_python

rem Passed through the environment, not argv: a dragged folder path may end
rem with a backslash, which would break C-runtime argv quoting.
set "AUTORENAME_DIR=%~1"

%PY% -m autorename
set "CODE=%ERRORLEVEL%"
popd
if not "%CODE%"=="0" pause
exit /b %CODE%

:no_python
echo Python 3.10+ not found.
echo Install Python 3.10 or newer, and tick "Add python.exe to PATH" during setup.
pause
exit /b 1

:old_python
echo Python 3.10 or newer is required.
pause
exit /b 1
