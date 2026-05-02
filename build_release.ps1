param(
    [string]$PythonExe = "E:\anaconda\python.exe"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$releasesDir = Join-Path $projectRoot "releases"
$releaseZipPath = Join-Path $releasesDir "AttendanceRebuild-portable.zip"

if (-not (Test-Path $releasesDir)) {
    New-Item -ItemType Directory -Force -Path $releasesDir | Out-Null
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "build_portable.ps1") `
    -PythonExe $PythonExe `
    -ZipPath $releaseZipPath

if ($LASTEXITCODE -ne 0) {
    throw "Release package build failed."
}

Write-Host "Release package ready:"
Write-Host $releaseZipPath
