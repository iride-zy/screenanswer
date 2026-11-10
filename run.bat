@echo off
cd /d "%~dp0"
for /f "tokens=1,* delims== " %%A in ('findstr /b /c:"home = " ".venv\pyvenv.cfg" 2^>nul') do set "PYHOME=%%B"
if not defined PYHOME (
    echo Cannot find .venv\pyvenv.cfg, run "uv sync" first.
    pause
    exit /b 1
)
set "PYTHONPATH=%~dp0.venv\Lib\site-packages"
start "" "%PYHOME%\pythonw.exe" "%~dp0screenanswer.py"
