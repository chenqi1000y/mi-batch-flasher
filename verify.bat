@echo off
setlocal
echo ===========================================
echo    Fastboot Device Check
echo ===========================================
echo.
set "ADB=C:\Program Files (x86)\Minimal ADB and Fastboot"
set "MI=E:\rom\tools\MiFlash2018\MiFlash2018-5-28-0\Source\ThirdParty\Google\Android"

echo [1] Minimal ADB fastboot:
"%ADB%\fastboot.exe" devices
echo.
echo [2] MiFlash bundled fastboot:
"%MI%\fastboot.exe" devices
echo.
echo -------------------------------------------
echo  Serial number shown  = driver OK, ready to flash
echo  Both lists empty     = driver NOT installed
echo.
echo  Device Manager check: Win+X, then Device Manager
echo  "Android" with yellow mark = driver missing
echo  "Android Bootloader Interface" = driver OK
echo -------------------------------------------
echo.
pause
