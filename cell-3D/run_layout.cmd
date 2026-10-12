@echo off
setlocal
set "PYTHONUTF8=1"
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
set "PYTHONHOME="
set "PYTHONPATH="
if exist "%~dp0runtime\python.exe" (
  "%~dp0runtime\python.exe" "%~dp0run.py" %*
  goto done
)
if defined LAYOUT_PYTHON (
  "%LAYOUT_PYTHON%" "%~dp0run.py" %*
  goto done
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0run.py" %*
  goto done
)
python "%~dp0run.py" %*
:done
set "LAYOUT_EXIT=%errorlevel%"
if "%~1"=="" pause
exit /b %LAYOUT_EXIT%
