:<<"::CMD"
@echo off
rem ---------------------------------------------------------------------------
rem Polyglot launcher: a Windows batch file AND a POSIX shell script.
rem   Windows : double-click, or  start.bat
rem   Linux   : ./start.bat   (or  sh start.bat)
rem cmd.exe skips the leading ':' label line; the shell swallows this whole
rem batch section as a here-document ending at the '::CMD' line below.
rem Keep this file LF-only and free of goto/parenthesised blocks - both are
rem what break batch files that use Unix line endings.
rem ---------------------------------------------------------------------------
setlocal
pushd "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
set "FRESH="
if not exist "%VENV_PY%" set "FRESH=1"

if defined FRESH echo First install...
if defined FRESH python -m venv .venv

if not exist "%VENV_PY%" echo ERROR: could not create .venv - is Python 3 installed and on PATH?
if not exist "%VENV_PY%" pause
if not exist "%VENV_PY%" exit /b 1

if defined FRESH "%VENV_PY%" -m pip install -r requirements.txt
if defined FRESH echo ------------------------------------

"%VENV_PY%" main.py

popd
endlocal
pause
exit /b
::CMD

set -e
cd "$(dirname "$0")"

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

VENV_PY=.venv/bin/python

if [ ! -x "$VENV_PY" ]; then
    echo "First install..."

    "$PY" -m venv .venv
    "$VENV_PY" -m pip install -r requirements.txt

    echo "------------------------------------"
fi

exec "$VENV_PY" main.py
