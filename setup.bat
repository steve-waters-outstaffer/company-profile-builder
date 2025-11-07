@echo off
echo ========================================
echo Company Profile Builder - Setup Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9+ from python.org
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please install Node.js from nodejs.org
    pause
    exit /b 1
)

echo [1/4] Setting up Python backend...
cd backend

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)

echo.
echo [2/4] Setting up React frontend...
cd ..\frontend

echo Installing Node dependencies...
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install Node dependencies
    pause
    exit /b 1
)

cd ..

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo.
echo 1. Set your API keys (in PowerShell or CMD):
echo    $env:TAVILY_API_KEY="your_key"
echo    $env:SCRAPECREATORS_API_KEY="your_key"
echo    $env:GOOGLE_API_KEY="your_key"
echo.
echo 2. Run the application:
echo    - Open TWO terminals
echo    - Terminal 1: cd backend ^&^& .\venv\Scripts\activate ^&^& python app.py
echo    - Terminal 2: cd frontend ^&^& npm run dev
echo.
echo 3. Open http://localhost:5173 in your browser
echo.
pause
