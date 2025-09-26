@echo off
set PYTHON_EXEC=%~dp0..\.venv\Scripts\python.exe
set PYTHONPATH=%~dp0..
set API_KEY=%1
echo Starting bridge with API_KEY=%API_KEY% using %PYTHON_EXEC%
"%PYTHON_EXEC%" -m uvicorn echo_bridge.main:app --host %2 --port %3 > "%~dp0..\bridge.log" 2>&1
