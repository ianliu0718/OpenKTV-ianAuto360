$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$ReleaseVersion = "v1.0.0"
$AppName = "ianAutoKTV_Server"
$DistRoot = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $DistRoot "ianAutoKTV_Server"
$TempDistRoot = Join-Path $DistRoot "_update_build"
$TempBuildDir = Join-Path $TempDistRoot "ianAutoKTV_Server"
$UpdateDir = Join-Path $DistRoot "ianAutoKTV_Update_$ReleaseVersion"

if (-not (Test-Path $Python)) {
    throw "Python virtual environment not found: $Python"
}

& $Python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed." }

Remove-Item $TempDistRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $UpdateDir -Recurse -Force -ErrorAction SilentlyContinue
& $Python -m PyInstaller --noconfirm --clean --distpath $TempDistRoot (Join-Path $ProjectDir "ianAutoKTV_Server.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

New-Item $UpdateDir -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $TempBuildDir "ianAutoKTV_Server.exe") $UpdateDir -Force
Copy-Item (Join-Path $TempBuildDir "_internal") $UpdateDir -Recurse -Force
Copy-Item (Join-Path $ProjectDir "templates") $UpdateDir -Recurse -Force
Set-Content (Join-Path $UpdateDir "VERSION.txt") $ReleaseVersion -Encoding ASCII
Remove-Item $TempDistRoot -Recurse -Force

Write-Host "Update package ready: $UpdateDir" -ForegroundColor Green
Write-Host "Copy its files over an existing installation after closing the server." -ForegroundColor Green