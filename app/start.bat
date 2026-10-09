@echo off
rem Alternative way to start Aura (if Aura.exe does not open).
rem Arranque alternativo de Aura (si Aura.exe no abre).
start "" "%~dp0..\runtime\pythonw.exe" -I "%~dp0main.py" %*
