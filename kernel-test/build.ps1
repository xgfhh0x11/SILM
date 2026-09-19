<#
.SYNOPSIS
    Builds the InterruptLatencyMonitor kernel driver (Release|x64) via MSBuild.

.DESCRIPTION
    Runs entirely on the HOST (the machine with Visual Studio 2022 + WDK
    10.0.26100 + KMDF 1.15 installed, per BUILD_AND_VERIFY.md). Does not
    touch any VM. Locates vcvars64.bat and msbuild, builds
    InterruptLatencyMonitor.sln Release|x64, and on success prints the
    absolute path to the resulting .sys. On failure it prints the MSBuild
    error output verbatim and exits non-zero -- it never reports success
    it did not actually observe.

.PARAMETER RepoRoot
    Path to the SILM repo root. Defaults to the parent of this script's
    directory (kernel-test/../).

.PARAMETER VsDevCmdPath
    Optional explicit path to vcvars64.bat, if auto-detection fails.

.PARAMETER TestCertificateThumbprint
    Optional. If the host's certificate store has more than one code-signing
    test certificate, MSBuild's auto TestSign step fails with "SignTool
    error: Multiple certificates were found" instead of picking one. Pass
    the SHA1 thumbprint of the specific certificate to use (see
    Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert) to disambiguate.
    This is forwarded as /p:TestCertificate=<thumbprint> to MSBuild.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -VsDevCmdPath 'C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat'
    .\build.ps1 -TestCertificateThumbprint AA30F23DAABE6F52330C3B662A4504AF082F0FF3
#>

[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$VsDevCmdPath,
    [string]$TestCertificateThumbprint
)

$ErrorActionPreference = 'Stop'

function Write-Section($msg) {
    Write-Host ''
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

Write-Section 'SILM driver build (host, Release|x64)'
Write-Host "Repo root: $RepoRoot"

$slnPath = Join-Path $RepoRoot 'InterruptLatencyMonitor.sln'
if (-not (Test-Path $slnPath)) {
    Write-Host "FAILED: solution not found at $slnPath" -ForegroundColor Red
    exit 1
}

# --- Locate vcvars64.bat -----------------------------------------------
$candidateVcVars = @()
if ($VsDevCmdPath) { $candidateVcVars += $VsDevCmdPath }
$candidateVcVars += @(
    'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'
    'C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat'
    'C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat'
    'C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
)

# vswhere-based discovery, if present (more robust than the hardcoded list).
$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
if (Test-Path $vswhere) {
    try {
        $vsInstallPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
        if ($vsInstallPath) {
            $candidateVcVars = @((Join-Path $vsInstallPath 'VC\Auxiliary\Build\vcvars64.bat')) + $candidateVcVars
        }
    } catch {
        # Non-fatal; fall through to the hardcoded candidate list.
    }
}

$vcvars = $candidateVcVars | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $vcvars) {
    Write-Host 'FAILED: could not locate vcvars64.bat. Pass -VsDevCmdPath explicitly.' -ForegroundColor Red
    Write-Host 'Tried:'
    $candidateVcVars | ForEach-Object { Write-Host "  $_" }
    exit 1
}
Write-Host "Using VC vars: $vcvars"

# --- Locate msbuild.exe (needs to run inside the vcvars64 environment) --
# We shell out to cmd.exe to source vcvars64.bat, then invoke msbuild, so
# msbuild resolves the WDK-aware PlatformToolset (WindowsKernelModeDriver10.0).
$logPath = Join-Path $env:TEMP "silm-build-$(Get-Date -Format yyyyMMdd-HHmmss).log"

$msbuildProps = '/p:Configuration=Release /p:Platform=x64'
if ($TestCertificateThumbprint) {
    $msbuildProps += " /p:TestCertificate=$TestCertificateThumbprint"
    Write-Host "Using test-signing certificate thumbprint: $TestCertificateThumbprint"
}

$cmdArgs = @(
    '/c'
    "call `"$vcvars`" >nul && msbuild `"$slnPath`" $msbuildProps /t:Build /v:normal /nologo"
)

Write-Section 'Running MSBuild (Release|x64)'
Write-Host "Log: $logPath"

$proc = Start-Process -FilePath 'cmd.exe' -ArgumentList $cmdArgs -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $logPath -RedirectStandardError "$logPath.err"

$stdout = if (Test-Path $logPath) { Get-Content $logPath -Raw } else { '' }
$stderr = if (Test-Path "$logPath.err") { Get-Content "$logPath.err" -Raw } else { '' }

Write-Host $stdout
if ($stderr) { Write-Host $stderr -ForegroundColor Yellow }

$sysPath = Join-Path $RepoRoot 'x64\Release\InterruptLatencyMonitor.sys'

if ($proc.ExitCode -ne 0) {
    Write-Section 'BUILD FAILED'
    Write-Host "MSBuild exited with code $($proc.ExitCode)." -ForegroundColor Red
    Write-Host 'Errors (grep for "error"):' -ForegroundColor Red
    $errorLines = ($stdout + "`n" + $stderr) -split "`r?`n" | Where-Object { $_ -match '\berror\b' }
    if ($errorLines) {
        $errorLines | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    } else {
        Write-Host '  (no line matched /error/ -- see full log above/at' $logPath ')' -ForegroundColor Red
    }
    Write-Host ''
    Write-Host "Full log: $logPath"
    exit $proc.ExitCode
}

# Even if MSBuild reports exit 0, verify the artifact actually exists before
# declaring success -- do not trust the exit code alone.
if (-not (Test-Path $sysPath)) {
    Write-Section 'BUILD REPORTED SUCCESS BUT ARTIFACT MISSING'
    Write-Host "MSBuild exited 0 but $sysPath does not exist." -ForegroundColor Red
    Write-Host "Full log: $logPath"
    exit 1
}

Write-Section 'BUILD SUCCEEDED'
$item = Get-Item $sysPath
Write-Host "Driver:   $($item.FullName)"
Write-Host "Size:     $($item.Length) bytes"
Write-Host "Modified: $($item.LastWriteTime)"
Write-Host ''
Write-Host 'Next: copy the .sys (and any .inf/.cat if you sign it) into the guest, then see kernel-test/README.md.'
exit 0
