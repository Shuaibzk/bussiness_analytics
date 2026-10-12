@echo off
rem ===== Panorama Analytics - one-click start (everything stays on D:) =====
setlocal
cd /d "%~dp0"
set "TEMP=%~dp0.tmp"
set "TMP=%~dp0.tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
set "OLLAMA_MODELS=D:\Ollama\models"
if "%XAMPP_DIR%"=="" set "XAMPP_DIR=D:\IDE\xampp"
set "DB_PORT=3307"

rem 1) database: XAMPP MariaDB (bound to localhost only; skipped if it is already running, e.g. from the XAMPP control panel)
if exist "%XAMPP_DIR%\mysql\bin\mysqld.exe" (
  powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort %DB_PORT% -State Listen -ErrorAction SilentlyContinue)) { Write-Host 'Starting MariaDB...'; Start-Process '%XAMPP_DIR%\mysql\bin\mysqld.exe' -ArgumentList '--defaults-file=%XAMPP_DIR%\mysql\bin\my.ini','--standalone','--bind-address=127.0.0.1' -WindowStyle Hidden -WorkingDirectory '%XAMPP_DIR%\mysql\bin'; $ok=$false; 1..40 | ForEach-Object { if (Get-NetTCPConnection -LocalPort %DB_PORT% -State Listen -ErrorAction SilentlyContinue) { $ok=$true; return }; Start-Sleep -Milliseconds 500 }; if (-not $ok) { Write-Host 'MariaDB did not start - open the XAMPP control panel and start MySQL.' } }"
) else (
  echo [warn] XAMPP not found at %XAMPP_DIR% - set XAMPP_DIR or start MariaDB yourself.
)

rem 2) local LLM server (optional - the app degrades gracefully without it)
where ollama >nul 2>nul
if %errorlevel%==0 (
  powershell -NoProfile -Command "if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) { Start-Process ollama -ArgumentList 'serve' -WindowStyle Minimized }"
) else if exist "D:\Ollama\ollama.exe" (
  powershell -NoProfile -Command "if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) { Start-Process 'D:\Ollama\ollama.exe' -ArgumentList 'serve' -WindowStyle Minimized }"
) else (
  echo [info] Ollama not found - AI chat will run in data-readout mode. Run setup_ollama.ps1 to enable it.
)

rem 3) build the UI once (skipped if already built)
if not exist "frontend\dist\index.html" (
  echo Building frontend...
  pushd frontend
  call npm install
  call npm run build
  popd
)

rem 4) API + UI on one port (applies pending database migrations on start-up)
start "" "http://localhost:8000"
cd backend
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
