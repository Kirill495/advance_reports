@echo off
setlocal

rem Use Python 3.12 via the Windows launcher if available, else "python" from PATH.
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3.12"
) else (
    set "PYTHON=python"
)

%PYTHON% "%~dp0src\ui.py" %*
exit /b %ERRORLEVEL%
