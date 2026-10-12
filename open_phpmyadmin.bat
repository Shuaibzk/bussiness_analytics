@echo off
rem ===== Opens phpMyAdmin on the panorama database (starts XAMPP MariaDB and Apache if they are not running) =====
setlocal
if "%XAMPP_DIR%"=="" set "XAMPP_DIR=D:\IDE\xampp"
set "DB_PORT=3307"
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort %DB_PORT% -State Listen -ErrorAction SilentlyContinue)) { Write-Host 'Starting MariaDB...'; Start-Process '%XAMPP_DIR%\mysql\bin\mysqld.exe' -ArgumentList '--defaults-file=%XAMPP_DIR%\mysql\bin\my.ini','--standalone','--bind-address=127.0.0.1' -WindowStyle Hidden -WorkingDirectory '%XAMPP_DIR%\mysql\bin'; 1..40 | ForEach-Object { if (Get-NetTCPConnection -LocalPort %DB_PORT% -State Listen -ErrorAction SilentlyContinue) { return }; Start-Sleep -Milliseconds 500 } }"
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue)) { Write-Host 'Starting Apache...'; Start-Process '%XAMPP_DIR%\apache\bin\httpd.exe' -WindowStyle Hidden -WorkingDirectory '%XAMPP_DIR%\apache\bin'; 1..20 | ForEach-Object { if (Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue) { return }; Start-Sleep -Milliseconds 500 } }"
start "" "http://localhost/phpmyadmin/index.php?route=/database/structure&db=panorama"
echo.
echo Tip: for the diagram open the "Designer" tab (More ... ^> Designer). Use the toolbar button "Hide tables with no relation"
echo      to keep only the star schema and the user tables, then drag fact_orders to the middle.
