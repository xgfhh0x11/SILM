@echo off
REM Build script using x64 Native Tools
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"

set DDK_INC_PATH=C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\km
set KMDF_INC_PATH=C:\Program Files (x86)\Windows Kits\10\Include\wdf\kmdf\1.15
set DDK_LIB_PATH=C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\km\x64

echo Building InterruptLatencyMonitor driver...
msbuild "InterruptLatencyMonitor.sln" /p:Configuration=Release /p:Platform=x64 /t:Build /v:minimal /nologo

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ BUILD SUCCESSFUL!
    echo.
    if exist "x64\Release\InterruptLatencyMonitor.sys" (
        echo Driver file: x64\Release\InterruptLatencyMonitor.sys
        dir "x64\Release\InterruptLatencyMonitor.sys"
    )
) else (
    echo.
    echo ❌ BUILD FAILED!
    exit /b 1
)

