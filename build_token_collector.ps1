param(
    [string]$PythonExe = "E:\anaconda\python.exe",
    [string]$ZipPath = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$appName = "AttendanceTokenCollector"
$distRoot = Join-Path $projectRoot "dist"
$buildRoot = Join-Path $projectRoot "build\$appName"
$packageDir = Join-Path $distRoot $appName
$releasesDir = Join-Path $projectRoot "releases"
$webAssets = Join-Path $projectRoot "token_uploader\web"
$portableReadme = Join-Path $projectRoot "token_uploader\portable_README.txt"
$ffiDll = Join-Path (Split-Path -Parent $PythonExe) "Library\bin\ffi.dll"

function Assert-WorkspaceChild([string]$Path) {
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $rootWithSeparator = $projectRoot.TrimEnd('\') + '\'
    if (-not $fullPath.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the workspace: $fullPath"
    }
}

Assert-WorkspaceChild $buildRoot
Assert-WorkspaceChild $packageDir

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path -LiteralPath $ffiDll)) {
    throw "Conda libffi runtime not found: $ffiDll"
}

if (Test-Path -LiteralPath $buildRoot) {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}
if (Test-Path -LiteralPath $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $distRoot, $buildRoot, $releasesDir | Out-Null
Set-Location $projectRoot

& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name $appName `
    --paths $projectRoot `
    --distpath $distRoot `
    --workpath $buildRoot `
    --specpath $buildRoot `
    --add-data "$webAssets;token_uploader\web" `
    --add-binary "$ffiDll;." `
    --collect-data webview `
    --copy-metadata pywebview `
    --collect-all clr_loader `
    --collect-submodules pkg_resources._vendor `
    --hidden-import clr `
    --hidden-import webview.platforms.winforms `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import webview.platforms.mshtml `
    --exclude-module webview.platforms.qt `
    --exclude-module webview.platforms.gtk `
    --exclude-module webview.platforms.cocoa `
    --exclude-module webview.platforms.android `
    --exclude-module webview.platforms.cef `
    --exclude-module PyQt5 `
    --exclude-module PyQt6 `
    --exclude-module PySide6 `
    --exclude-module qtpy `
    --exclude-module numpy `
    --exclude-module PIL `
    (Join-Path $projectRoot "token_uploader\app.py")

if ($LASTEXITCODE -ne 0) {
    throw "AttendanceTokenCollector build failed."
}

Copy-Item -LiteralPath $portableReadme -Destination (Join-Path $packageDir "README.txt") -Force

if (-not $ZipPath) {
    $ZipPath = Join-Path $releasesDir "$appName-portable.zip"
}
$zipFullPath = [System.IO.Path]::GetFullPath($ZipPath)
Assert-WorkspaceChild $zipFullPath
$zipDirectory = Split-Path -Parent $zipFullPath
New-Item -ItemType Directory -Force -Path $zipDirectory | Out-Null
if (Test-Path -LiteralPath $zipFullPath) {
    Remove-Item -LiteralPath $zipFullPath -Force
}
Compress-Archive -LiteralPath $packageDir -DestinationPath $zipFullPath -CompressionLevel Optimal

$hash = (Get-FileHash -LiteralPath $zipFullPath -Algorithm SHA256).Hash
Write-Host "Portable package ready:"
Write-Host $packageDir
Write-Host $zipFullPath
Write-Host "SHA256=$hash"
