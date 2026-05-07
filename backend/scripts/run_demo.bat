@echo off
setlocal
REM Cycle 4 - ASCII only. IAM starts first and must pass /health before other services.

for %%I in ("%~dp0..") do set "BACKEND_ROOT=%%~fI"
cd /d "%BACKEND_ROOT%"

echo ========================================
echo Agentrust one-click demo Cycle 4
echo ========================================
echo ROOT=%BACKEND_ROOT%
echo.

if exist "%BACKEND_ROOT%\venv\Scripts\activate.bat" (
  call "%BACKEND_ROOT%\venv\Scripts\activate.bat"
)

set "PYEXE=python"
if exist "%BACKEND_ROOT%\venv\Scripts\python.exe" (
  set "PYEXE=%BACKEND_ROOT%\venv\Scripts\python.exe"
)

echo Step 1 - IAM port 8000 - env inline per window ^(START breaks main:app args; no shared-env race^)
start "Agentrust-IAM" cmd /k set "UVICORN_APP=main:app" ^& set "UVICORN_PORT=8000" ^& call "%BACKEND_ROOT%\scripts\spawn_uvicorn.bat"

echo Waiting 8 seconds for uvicorn to bind...
timeout /t 8 /nobreak >nul

echo Waiting for IAM http://127.0.0.1:8000/health ...
"%PYEXE%" "%BACKEND_ROOT%\scripts\wait_health.py" http://127.0.0.1:8000/health 90
if errorlevel 1 (
  echo.
  echo ERROR - IAM did not respond on port 8000.
  echo   1^) Open the window titled [Agentrust-IAM] and read the last error ^(traceback^).
  echo   2^) In PowerShell run - netstat -ano ^| findstr :8000
  echo      If another program uses 8000, close it or change port in this bat file.
  echo   3^) Or from backend folder - MUST use env vars if CMD START mangled main: colon -
  echo      set UVICORN_APP=main:app
  echo      set UVICORN_PORT=8000
  echo      scripts\spawn_uvicorn.bat
  echo      Or direct: python -m uvicorn main:app --host 127.0.0.1 --port 8000
  echo   4^) Ensure deps - pip install -r requirements.txt ^(use venv if you have one^)
  pause
  exit /b 1
)

echo Step 2 - Enterprise agent port 8001
start "Agent-Enterprise" cmd /k set "UVICORN_APP=agents.enterprise_data_agent:app" ^& set "UVICORN_PORT=8001" ^& call "%BACKEND_ROOT%\scripts\spawn_uvicorn.bat"

echo Step 3 - External search agent port 8002
start "Agent-ExternalSearch" cmd /k set "UVICORN_APP=agents.external_search_agent:app" ^& set "UVICORN_PORT=8002" ^& call "%BACKEND_ROOT%\scripts\spawn_uvicorn.bat"

echo Step 4 - Doc helper agent port 8003
start "Agent-DocHelper" cmd /k set "UVICORN_APP=agents.doc_helper_agent:app" ^& set "UVICORN_PORT=8003" ^& call "%BACKEND_ROOT%\scripts\spawn_uvicorn.bat"

timeout /t 2 /nobreak >nul

echo Step 5 - Dashboard Vite port 5173
where npm >nul 2>&1
if errorlevel 1 (
  echo WARNING - npm not in PATH, skip Dashboard
) else (
  REM Use %%~fI directly so DASH_ROOT is not empty inside parentheses block
  for %%I in ("%BACKEND_ROOT%\..\dashboard") do start "Agentrust-Dashboard" cmd /k cd /d "%%~fI" ^&^& npm run dev
)

if "%SKIP_DEMOS%"=="1" (
  echo SKIP_DEMOS=1 set, skipping demo scripts
) else (
  echo Step 6 - demo_cycle4_normal.py
  "%PYEXE%" "%BACKEND_ROOT%\scripts\demo_cycle4_normal.py"
  echo Step 6 - demo_cycle4_abnormal.py
  "%PYEXE%" "%BACKEND_ROOT%\scripts\demo_cycle4_abnormal.py"
)

start http://localhost:5173

echo.
echo Done. Opened browser http://localhost:5173
echo Feishu template JSON - scripts\feishu_app_scopes.cycle4.template.json
echo Close spawned CMD windows to stop servers.
pause
