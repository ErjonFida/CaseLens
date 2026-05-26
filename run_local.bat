@echo off
title Legal Assistant RAG App - Local Host
echo =======================================================
echo     Starting Legal Assistant RAG App (Local Mode)
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
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies.
    pause
    exit /b 1
)
echo.

:: Launch FastAPI App
echo Launching server at http://localhost:8000 ...
python main.py
pause
