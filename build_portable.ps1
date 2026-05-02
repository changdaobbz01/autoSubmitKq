param(
    [string]$PythonExe = "E:\anaconda\python.exe",
    [switch]$PreserveRuntimeData,
    [string]$ZipPath = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $projectRoot "dist"
$buildRoot = Join-Path $projectRoot "build"
$appName = "AttendanceRebuild"
$portableAssetsDir = Join-Path $projectRoot "portable_assets"
$backupRoot = Join-Path $projectRoot ".build_state_backup"
$runtimeDataBackupDir = Join-Path $backupRoot ".attendance_auth"

Set-Location $projectRoot

& $PythonExe -m pip install --upgrade pyinstaller

if (Test-Path $buildRoot) {
    Remove-Item -Recurse -Force $buildRoot
}

$packageDir = Join-Path $distRoot $appName
$packageRuntimeDir = Join-Path $packageDir ".attendance_auth"
$runtimeDataBackedUp = $false

if ($PreserveRuntimeData -and (Test-Path $packageRuntimeDir)) {
    if (Test-Path $runtimeDataBackupDir) {
        Remove-Item -Recurse -Force $runtimeDataBackupDir
    }
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    Copy-Item -LiteralPath $packageRuntimeDir -Destination $runtimeDataBackupDir -Recurse -Force
    $runtimeDataBackedUp = $true
}

if (Test-Path $packageDir) {
    Remove-Item -Recurse -Force $packageDir
}

& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name $appName `
    --paths $projectRoot `
    --add-data "rebuild_login\web;rebuild_login\web" `
    rebuild_login\server.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$launcherPath = Join-Path $packageDir "Launch-AttendanceRebuild.bat"
$launcherContent = @'
@echo off
setlocal
cd /d "%~dp0"
start "" "AttendanceRebuild.exe"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8765"
endlocal
'@
Set-Content -LiteralPath $launcherPath -Value $launcherContent -Encoding Ascii

$backgroundLauncherSource = Join-Path $portableAssetsDir "Launch-AttendanceRebuild-Background.vbs"
$backgroundLauncherPath = Join-Path $packageDir "Launch-AttendanceRebuild-Background.vbs"
Copy-Item -LiteralPath $backgroundLauncherSource -Destination $backgroundLauncherPath -Force

$autostartManagerSource = Join-Path $portableAssetsDir "Manage-AttendanceRebuild-Autostart.ps1"
$autostartManagerPath = Join-Path $packageDir "Manage-AttendanceRebuild-Autostart.ps1"
Copy-Item -LiteralPath $autostartManagerSource -Destination $autostartManagerPath -Force

if ($PreserveRuntimeData -and $runtimeDataBackedUp -and (Test-Path $runtimeDataBackupDir)) {
    Copy-Item -LiteralPath $runtimeDataBackupDir -Destination $packageRuntimeDir -Recurse -Force
}

$readmePath = Join-Path $packageDir "README.txt"
$readmeContent = @'
AttendanceRebuild portable package

1. Double-click Launch-AttendanceRebuild.bat
2. Wait 2 seconds and your browser should open http://127.0.0.1:8765
3. Runtime data will be created in .attendance_auth next to the executable
4. Import your own xlsx before running real submit or polling
5. To enable backend autostart without opening the browser, run:
   powershell -ExecutionPolicy Bypass -File .\Manage-AttendanceRebuild-Autostart.ps1 -Mode Install

Notes:
- This package does not ship cached xlsx account data unless build_portable.ps1 is run with -PreserveRuntimeData.
- Copy the whole AttendanceRebuild folder to another device, not only the exe.
- Put it in a writable folder such as Desktop or D:\Work.
- If port 8765 is already occupied, run AttendanceRebuild.exe --port 8876 from a terminal.
'@
Set-Content -LiteralPath $readmePath -Value $readmeContent -Encoding UTF8

if (-not $ZipPath) {
    $zipFileName = if ($PreserveRuntimeData) {
        "AttendanceRebuild-portable-with-runtime.zip"
    } else {
        "AttendanceRebuild-portable.zip"
    }
    $ZipPath = Join-Path $distRoot $zipFileName
}

$zipDir = Split-Path -Parent $ZipPath
if ($zipDir -and -not (Test-Path $zipDir)) {
    New-Item -ItemType Directory -Force -Path $zipDir | Out-Null
}
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}
Compress-Archive -Path $packageDir -DestinationPath $ZipPath

Write-Host "Portable package ready:"
Write-Host $packageDir
Write-Host $ZipPath
Write-Host ("PreserveRuntimeData=" + $PreserveRuntimeData.IsPresent)
