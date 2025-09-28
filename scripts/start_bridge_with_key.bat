@echo off
set API_KEY=SECRET
"%~dp0..\echo-bridge\.venv\Scripts\uvicorn.exe" echo_bridge.main:app --host 127.0.0.1 --port 3333 > "%~dp0..\uvicorn.out.log" 2> "%~dp0..\uvicorn.err.log"
