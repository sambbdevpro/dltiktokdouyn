@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=src
python -m dlmass.cli --config dlmass.config.json web --host 127.0.0.1 --port 5001
endlocal
