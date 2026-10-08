@echo off
setlocal
pushd "%~dp0"
py -3.13 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,13) else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
if exist ".venv\Scripts\python.exe" goto dependencies
echo Preparing the beta's Python environment...
py -3.13 -m venv ".venv"
if errorlevel 1 goto failed
:dependencies
if exist ".venv\beta-ready" goto launch
echo Installing the beta's dependencies. This is only needed once.
".venv\Scripts\python.exe" -m pip install -r "requirements-beta.txt"
if errorlevel 1 goto failed
echo 0.1.0-beta> ".venv\beta-ready"
:launch
".venv\Scripts\python.exe" "wrestler_beta.py"
if errorlevel 1 goto failed
popd
exit /b 0
:missing_python
echo Install Python 3.13 for Windows from https://www.python.org/downloads/windows/
echo Include the Python launcher, then run this file again.
pause
popd
exit /b 1
:failed
echo The beta could not start. Review the message above.
pause
popd
exit /b 1
