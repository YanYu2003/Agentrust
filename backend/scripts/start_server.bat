@echo off
REM Start the Agentrust backend server

cd /d "%~dp0\.."

echo Starting Agentrust Backend Server...
echo ==================================

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Please run setup.bat first.
    exit /b 1
)

REM Activate virtual environment and start server
call venv\Scripts\activate.bat

REM Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
