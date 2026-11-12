@echo off
setlocal

rem Use Python 3.12 via the Windows launcher if available, else "python" from PATH.
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3.12"
) else (
    set "PYTHON=python"
)

if "%~1"=="" (
    echo Usage: %~nx0 --from "path\to\tickets" --out "path\to\output" [--dry-run]
    exit /b 1
)

%PYTHON% "%~dp0src\run.py" %*
exit /b %ERRORLEVEL%
