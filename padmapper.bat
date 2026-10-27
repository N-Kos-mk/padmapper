@echo off
rem padmapper を起動する。引数はそのまま渡す (例: padmapper.bat --check)
cd /d "%~dp0"
python -m padmapper %*
pause
