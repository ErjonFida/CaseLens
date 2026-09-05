@echo off
title CaseLens - Local Host
echo =======================================================
echo     Starting CaseLens (Local Mode)
echo =======================================================
echo.

:: Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in your system PATH.
    echo Please install Python 3.10+ and make sure to check "Add Python to PATH".
    pause
    exit /b 1
)

:: Check for .env file
if not exist .env (
    echo [WARNING] .env file not found. Creating one...
    if exist .env.example (
        copy .env.example .env >nul
        echo [INFO] Created .env file from template.
    ) else (
        echo GEMINI_API_KEY=> .env
        echo JWT_SECRET=supersecretkey_for_legal_assistant_rag_app>> .env
        echo [INFO] Created default .env file.
    )
    echo [IMPORTANT] Please open the .env file in the Legal_Assistant directory 
    echo             and add your GEMINI_API_KEY.
    echo.
)

:: Install dependencies
echo Installing requirements...
cd backend
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies.
    pause
    exit /b 1
)
echo.

:: Run Alembic migrations
echo Running database migrations...
alembic upgrade head
if %errorlevel% neq 0 (
    echo [WARNING] Migration failed - database may not be available yet.
)
echo.

:: Launch FastAPI App
echo Launching server at http://localhost:8000 ...
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
