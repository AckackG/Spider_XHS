@echo off
setlocal

cd /d "%~dp0.."

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"

if not exist "myscripts\backups" mkdir "myscripts\backups"

if exist "myscripts\mydata_raw\*" (
    echo Backing up mydata_raw to myscripts\backups\backup_mydata_raw_%TS%.zip...
    tar -a -cf "myscripts\backups\backup_mydata_raw_%TS%.zip" -C "myscripts\mydata_raw" .
    if errorlevel 1 (
        echo Backup mydata_raw failed.
        pause
        exit /b %errorlevel%
    )
)

if exist "myscripts\mydata\*" (
    echo Backing up mydata to myscripts\backups\backup_mydata_%TS%.zip...
    tar -a -cf "myscripts\backups\backup_mydata_%TS%.zip" -C "myscripts\mydata" .
    if errorlevel 1 (
        echo Backup mydata failed.
        pause
        exit /b %errorlevel%
    )
)

echo [1/2] Crawling Xiaohongshu data...
uv run python myscripts\src\11111.py
if errorlevel 1 (
    echo Crawl failed with exit code %errorlevel%.
    pause
    exit /b %errorlevel%
)

echo [2/2] Trimming final JSONL...
uv run python myscripts\src\trim_xhs_raw.py
if errorlevel 1 (
    echo Postprocess failed with exit code %errorlevel%.
    pause
    exit /b %errorlevel%
)

echo Done.
pause
