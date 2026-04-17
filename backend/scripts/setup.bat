@echo off
REM Setup script for Agentrust backend

cd /d "%~dp0\.."

echo Setting up Agentrust Backend...
echo ==============================
echo.

REM Create virtual environment if not exists
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
echo.

REM Create data directory
if not exist "data" mkdir data
echo Data directory ready: data\
echo.

REM Initialize database
echo Initializing database...
python scripts/init_db.py
echo.

echo ==============================
echo Setup complete!
echo.
echo To start the server:
echo   .\scripts\start_server.bat
echo.
echo To run the demo:
echo   python scripts\demo.py
