param(
    [string]$PythonExe = "E:\anaconda\python.exe"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$releasesDir = Join-Path $projectRoot "releases"
$releaseZipPath = Join-Path $releasesDir "AttendanceRebuild-portable.zip"
$localRuntimeDir = Join-Path $projectRoot "dist\AttendanceRebuild\.attendance_auth"
$runtimeBackupDir = Join-Path $projectRoot ".build_state_backup\release-local-runtime"
$runtimeBackedUp = $false

if (-not (Test-Path $releasesDir)) {
    New-Item -ItemType Directory -Force -Path $releasesDir | Out-Null
}

if (Test-Path $localRuntimeDir) {
    if (Test-Path $runtimeBackupDir) {
        Remove-Item -LiteralPath $runtimeBackupDir -Recurse -Force
    }
    $runtimeBackupParent = Split-Path -Parent $runtimeBackupDir
    New-Item -ItemType Directory -Force -Path $runtimeBackupParent | Out-Null
    Copy-Item -LiteralPath $localRuntimeDir -Destination $runtimeBackupDir -Recurse -Force
    $runtimeBackedUp = $true
}

try {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "build_portable.ps1") `
        -PythonExe $PythonExe `
        -ZipPath $releaseZipPath

    if ($LASTEXITCODE -ne 0) {
        throw "Release package build failed."
    }
}
finally {
    # The release zip is created before local data is restored, so it remains clean.
    $rebuiltPackageDir = Join-Path $projectRoot "dist\AttendanceRebuild"
    if ($runtimeBackedUp -and (Test-Path $runtimeBackupDir) -and (Test-Path $rebuiltPackageDir)) {
        $rebuiltRuntimeDir = Join-Path $rebuiltPackageDir ".attendance_auth"
        Copy-Item -LiteralPath $runtimeBackupDir -Destination $rebuiltRuntimeDir -Recurse -Force
        Remove-Item -LiteralPath $runtimeBackupDir -Recurse -Force
    }
}

Write-Host "Release package ready:"
Write-Host $releaseZipPath
Write-Host ("Local runtime data restored=" + $runtimeBackedUp)
