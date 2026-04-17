@echo off
REM Run the Agentrust Demo

cd /d "%~dp0\.."

echo Running Agentrust Demo...
echo ========================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Running setup first...
    call scripts\setup.bat
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the demo
python scripts\demo.py
