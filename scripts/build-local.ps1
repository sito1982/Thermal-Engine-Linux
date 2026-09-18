# Local Build Script for ThermalEngine
# Usage: .\scripts\build-local.ps1 (from project root)
#    or: .\build-local.ps1 (from scripts folder)

param(
    [string]$Version = "local-dev",
    [switch]$SkipInstaller,
    [switch]$Clean,
    # Firma Authenticode opcional: ruta al .pfx y su contraseña.
    [string]$CertPfx = "",
    [string]$CertPassword = ""
)

$ErrorActionPreference = "Stop"

# Change to project root (script can be run from scripts/ or project root)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
if (Test-Path "$ProjectRoot\main.py") {
    Set-Location $ProjectRoot
} elseif (-not (Test-Path "main.py")) {
    Write-Host "ERROR: Run this script from the project root or scripts folder" -ForegroundColor Red
    exit 1
}

$BuildDir = "dist"

# Firma Authenticode opcional (solo si se pasa -CertPfx).
function Invoke-Sign([string]$File) {
    if (-not $CertPfx) { return }
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" `
        -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -Last 1
    if (-not $signtool) {
        Write-Host "  signtool no encontrado; se omite la firma de $File" -ForegroundColor Yellow
        return
    }
    & $signtool.FullName sign /f $CertPfx /p $CertPassword /fd SHA256 `
        /tr "http://timestamp.digicert.com" /td SHA256 $File
    if ($LASTEXITCODE -ne 0) { throw "Firma fallida: $File" }
    Write-Host "  Firmado: $File" -ForegroundColor Green
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ThermalEngine Local Build" -ForegroundColor Cyan
Write-Host "  Version: $Version" -ForegroundColor Cyan
Write-Host "  Branch: $(git branch --show-current)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Clean previous build if requested
if ($Clean) {
    Write-Host "`n[1/5] Cleaning previous build..." -ForegroundColor Yellow
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
} else {
    Write-Host "`n[1/5] Skipping clean (use -Clean to remove previous build)" -ForegroundColor Gray
}

# Install Python dependencies
Write-Host "`n[2/5] Installing Python dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install nuitka ordered-set zstandard --quiet

# Build with Nuitka
Write-Host "`n[3/5] Building with Nuitka (this may take several minutes)..." -ForegroundColor Yellow
$versionNum = $Version.TrimStart('v').Split('-')[0]
if ($versionNum -notmatch '^\d+\.\d+\.\d+') { $versionNum = "1.0.0" }
python -m nuitka `
    --standalone `
    --windows-console-mode=disable `
    --windows-icon-from-ico=assets/icon.ico `
    --windows-company-name="Thermal Engine" `
    --windows-product-name="ThermalEngine" `
    --windows-product-version="$versionNum" `
    --windows-file-version="$versionNum" `
    --enable-plugin=pyside6 `
    --include-package=cv2 `
    --include-package=numpy `
    --include-package=PIL `
    --include-package=psutil `
    --include-package=hid `
    --include-package=usb `
    --include-package=pynvml `
    --include-package=wmi `
    --include-package=win32com `
    --include-package=pythoncom `
    --include-package=elements `
    --include-data-dir=presets=presets `
    --include-data-dir=assets=assets `
    --include-data-dir=icons=icons `
    --include-data-dir=templates=templates `
    --include-data-dir=plugins=plugins `
    --include-data-files=elements/*.py=elements/ `
    --include-data-files=assets/icon.ico=icon.ico `
    --include-data-files=assets/icon.png=icon.png `
    --assume-yes-for-downloads `
    --output-dir=dist `
    --output-filename=ThermalEngine.exe `
    main.py

# Verify build output
if (-not (Test-Path "dist\main.dist\elements")) {
    Write-Host "ERROR: elements folder missing!" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "dist\main.dist\presets")) {
    Write-Host "ERROR: presets folder missing!" -ForegroundColor Red
    exit 1
}

# Rename output folder
if (Test-Path "dist\main.dist") {
    if (Test-Path "dist\ThermalEngine") {
        Remove-Item -Recurse -Force "dist\ThermalEngine"
    }
    Move-Item -Path "dist\main.dist" -Destination "dist\ThermalEngine" -Force
}
Write-Host "  Nuitka build complete"

# Optional Authenticode signing of the main executable.
Invoke-Sign "dist\ThermalEngine\ThermalEngine.exe"

# Create ZIP archive
Write-Host "`n[4/5] Creating ZIP archive..." -ForegroundColor Yellow
$zipName = "ThermalEngine-$Version.zip"
if (Test-Path $zipName) { Remove-Item $zipName }
Compress-Archive -Path "dist/ThermalEngine/*" -DestinationPath $zipName
Write-Host "  Created $zipName"

# Build installer (optional)
if (-not $SkipInstaller) {
    Write-Host "`n[5/5] Building installer with Inno Setup..." -ForegroundColor Yellow
    $innoPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $innoPath) {
        $versionNum = $Version.TrimStart('v').Split('-')[0]
        if ($versionNum -notmatch '^\d+\.\d+\.\d+') { $versionNum = "1.0.0" }
        & $innoPath "/DMyAppVersion=$Version" "/DMyAppVersionNum=$versionNum" "installer.iss"
        Write-Host "  Installer built successfully"
        $setupExe = Get-ChildItem -Filter "ThermalEngine-*-Setup.exe" |
            Sort-Object LastWriteTime | Select-Object -Last 1
        if ($setupExe) { Invoke-Sign $setupExe.FullName }
    } else {
        Write-Host "  Inno Setup not found, skipping installer (install with: choco install innosetup)" -ForegroundColor Gray
    }
} else {
    Write-Host "`n[5/5] Skipping installer (use without -SkipInstaller to build)" -ForegroundColor Gray
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Output: dist\ThermalEngine\" -ForegroundColor White
Write-Host "ZIP:    $zipName" -ForegroundColor White
Write-Host "Run:    dist\ThermalEngine\ThermalEngine.exe" -ForegroundColor White
Write-Host ""
Write-Host "NOTE: Sensors work natively on Windows (NVML + psutil/WMI), no admin needed." -ForegroundColor Yellow
Write-Host "      HWiNFO is OPTIONAL (Preferences > Sensors) for extra metrics." -ForegroundColor Yellow
Write-Host ""
