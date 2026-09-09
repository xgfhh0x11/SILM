@echo off
REM Installation script for Interrupt Latency Monitor Driver
REM Requires administrator privileges and test-signing enabled.

setlocal

set DRIVER_PATH=%~dp0x64\Release\InterruptLatencyMonitor.sys

echo Installing Interrupt Latency Monitor Driver...
echo Driver: %DRIVER_PATH%
echo.

REM Check for administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: This script requires administrator privileges.
    echo Please run as administrator.
    exit /b 1
)

REM Check that the driver binary exists at the canonical build output.
if not exist "%DRIVER_PATH%" (
    echo Error: %DRIVER_PATH% not found.
    echo.
    echo Build the driver first:
    echo   build_vs.bat        ^(from a VS 2022 Developer prompt^)
    echo.
    echo Output is written to x64\Release\InterruptLatencyMonitor.sys.
    exit /b 1
)

REM Stop and remove existing service if present
sc query InterruptLatencyMonitor >nul 2>&1
if %errorLevel% equ 0 (
    echo Stopping existing service...
    sc stop InterruptLatencyMonitor
    timeout /t 2 /nobreak >nul
    sc delete InterruptLatencyMonitor
)

REM Install driver
echo Creating service...
sc create InterruptLatencyMonitor type= kernel binPath= "%DRIVER_PATH%" start= demand
if errorlevel 1 (
    echo Failed to create service!
    exit /b 1
)

REM Start service
echo Starting service...
sc start InterruptLatencyMonitor
if errorlevel 1 (
    echo Failed to start service!
    echo.
    echo If `sc start` returned 0xC0000428 ^(STATUS_INVALID_IMAGE_HASH^),
    echo the driver is unsigned. Enable test signing and sign the
    echo driver with a self-signed cert ^(`bcdedit /set testsigning on`,
    echo `New-SelfSignedCertificate -Type CodeSigningCert ...`,
    echo `signtool sign /fd SHA256 ...`^).
    exit /b 1
)

echo.
echo Driver installed and started successfully!
echo.
echo Verify:   sc query InterruptLatencyMonitor
echo Uninstall:
echo           sc stop InterruptLatencyMonitor
echo           sc delete InterruptLatencyMonitor

endlocal
