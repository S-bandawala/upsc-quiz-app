@echo off
echo ============================================================
echo  UPSC PRE Quiz - Setup and Launch
echo ============================================================

cd /d "%~dp0"

:: Load .env if it exists
if exist .env (
    echo Loading .env...
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
)

:: Check API key
if "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo ERROR: ANTHROPIC_API_KEY is not set!
    echo   1. Copy .env.example to .env
    echo   2. Set your API key in .env
    echo   3. Re-run this script
    pause
    exit /b 1
)

echo API key detected: %ANTHROPIC_API_KEY:~0,12%...

:: Check if DB already exists
if exist data\upsc_beta.db (
    echo.
    echo Database already exists. Skipping extraction.
    echo [To re-extract, delete data\upsc_beta.db and data\raw_questions.json]
    goto :start_server
)

echo.
echo [1/2] Extracting questions from PDFs (this takes ~15-20 min)...
python scripts\extract_questions.py
if errorlevel 1 ( echo FAILED at extraction. & pause & exit /b 1 )

echo.
echo [2/2] Classifying and building database...
python scripts\classify_and_build_db.py
if errorlevel 1 ( echo FAILED at classification. & pause & exit /b 1 )

:start_server
echo.
echo ============================================================
echo  Starting server at http://localhost:8000
echo  Open frontend\index.html in your browser
echo  Press Ctrl+C to stop
echo ============================================================
echo.
cd backend
python -m uvicorn main:app --reload --port 8000
