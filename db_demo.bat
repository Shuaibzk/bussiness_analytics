@echo off
rem ===== Panorama database demo: runs db_demo.sql against XAMPP MariaDB (starts it if needed) =====
setlocal
if "%XAMPP_DIR%"=="" set "XAMPP_DIR=D:\IDE\xampp"
set "DB_PORT=3307"
call :ensure_db
if /i "%1"=="shell" (
  echo Connecting to the panorama database. Type  exit  to leave.
  "%XAMPP_DIR%\mysql\bin\mysql.exe" -u root -h 127.0.0.1 -P %DB_PORT% panorama
  goto :eof
)
rem --force: keep going after the statements in section 8 that the database refuses (that is the point of the demo)
"%XAMPP_DIR%\mysql\bin\mysql.exe" -u root -h 127.0.0.1 -P %DB_PORT% --force -t --default-character-set=utf8mb4 panorama < "%~dp0db_demo.sql"
echo.
pause
goto :eof

:ensure_db
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort %DB_PORT% -State Listen -ErrorAction SilentlyContinue)) { Write-Host 'Starting MariaDB...'; Start-Process '%XAMPP_DIR%\mysql\bin\mysqld.exe' -ArgumentList '--defaults-file=%XAMPP_DIR%\mysql\bin\my.ini','--standalone','--bind-address=127.0.0.1' -WindowStyle Hidden -WorkingDirectory '%XAMPP_DIR%\mysql\bin'; 1..40 | ForEach-Object { if (Get-NetTCPConnection -LocalPort %DB_PORT% -State Listen -ErrorAction SilentlyContinue) { return }; Start-Sleep -Milliseconds 500 } }"
goto :eof
