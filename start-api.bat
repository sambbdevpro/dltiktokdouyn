@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=src
python -m dlmass.cli --config dlmass.config.json web --host 0.0.0.0 --port 5001
endlocal
