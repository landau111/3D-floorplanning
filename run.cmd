@echo off
setlocal
set "DSE_PYTHON_ARGS="

rem PYTHON may be set to a Python executable to override automatic discovery.
if defined PYTHON (
    set "DSE_PYTHON=%PYTHON%"
) else if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set "DSE_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
) else (
    where py >nul 2>&1
    if errorlevel 1 (
        set "DSE_PYTHON=python"
    ) else (
        set "DSE_PYTHON=py"
        set "DSE_PYTHON_ARGS=-3"
    )
)

"%DSE_PYTHON%" %DSE_PYTHON_ARGS% -c "import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Python 3.6 or newer is required. Set PYTHON to its executable path.
    set "DSE_EXIT=2"
    goto finish
)

"%DSE_PYTHON%" %DSE_PYTHON_ARGS% -u "%~dp0folding_dse\run.py" %*
set "DSE_EXIT=%ERRORLEVEL%"

:finish
rem Keep results and errors visible when launched by double-click without arguments.
if "%~1"=="" pause
exit /b %DSE_EXIT%
