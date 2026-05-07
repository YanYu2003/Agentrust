@echo off
setlocal EnableExtensions
REM Reset DB: run from anywhere. Script lives in backend\scripts -> cd to backend root.

cd /d "%~dp0.."

echo ========================================
echo   Agentrust database reset
echo ========================================
echo.

echo [1/2] Removing old database...
if exist "..\data\agentrust.db" (
    del /q "..\data\agentrust.db"
    echo   Deleted ..\data\agentrust.db
) else (
    echo   Database file not found, skipped.
)

echo.
echo [2/2] Initializing database and CA root key...
python "%~dp0init_db.py"
if errorlevel 1 (
    echo ERROR: init_db.py failed.
    exit /b 1
)

echo.
echo ========================================
echo   Done. You can run demo.py or start the server.
echo ========================================
pause
