<#
===============================================================================
 build.ps1 – CMake configure + build helper (Windows PowerShell 5.1)
-------------------------------------------------------------------------------
    -Config            Debug | Release          (default: Release)
    -BuildDir          Path to build directory  (default: C:/build)
    -InstallDir        Path to install directory (default: C:/install)
    -Vesrsion          Version string           (default: 0.0.0)
    -Generator         CMake generator name     (auto: Ninja if in PATH, else VS 2022)
    -Clean             Remove contents of BuildDir before configuring

    -SkipPythonInterpreter   Do NOT build embedded Python interpreter
    -SkipPythonLauncher      Do NOT build Python module launcher
    -SkipRequirements        Do NOT install requirements.txt
    -SkipModule              Do NOT install main Python module
    -SkipPythonLibs          Do NOT install standard Python libraries
    -SkipTests               Do NOT build unit tests
    -SkipDocs                Do NOT build documentation
    -SkipInstaller           Do NOT build installer package
    -SkipDocs                Do NOT build documentation

    -h / -Help         Display this help
===============================================================================
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet('Debug','Release')]
    [string] $Config = 'Release',

    [string] $BuildDir = "C:/build",
    [string] $InstallDir = "C:/install",

    [string] $Version = '0.0.0',

    [string] $Generator,

    [switch] $Clean,

    [switch] $SkipConfigure,
    [switch] $SkipBuild,
    [switch] $SkipInstall,
    [switch] $SkipPythonInterpreter,
    [switch] $SkipPythonLauncher,
    [switch] $SkipRequirements,
    [switch] $SkipModule,
    [switch] $SkipPythonLibs,
    [switch] $SkipTests,
    [switch] $SkipInstaller,
    [switch] $SkipDocs,

    [Alias('h')]
    [switch] $Help
)


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Info {  param($t) Write-Host '[INFO]'  $t -ForegroundColor Cyan }

function Step {  param($t) Write-Host "`n=== $t ===" -ForegroundColor Yellow }

function Die  {  param($t) Write-Host '[ERROR]' $t -ForegroundColor Red ; exit 1 }

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory)][string[]] $Cmd,
        [Parameter(Mandatory)][string]   $ErrorContext
    )
    Info "Running: $($Cmd -join ' ')"
    & $Cmd[0] @($Cmd[1..($Cmd.Length-1)])
    if ($LASTEXITCODE) { Die "$ErrorContext failed (exit code $LASTEXITCODE)" }
}

function Convert-SkipToCMake {
    param(
        [Parameter(Mandatory)]
        [bool] $Skip
    )
    if ($Skip) { 'OFF' } else { 'ON' }
}


if ($Help) { Get-Help $MyInvocation.MyCommand.Path -Detailed ; exit 0 }


# ───────────────────────────────────────────────────────────
# Setup
# ───────────────────────────────────────────────────────────
Step 'Setup'

$BuildDir = [IO.Path]::GetFullPath($BuildDir)
$BuildDir = $BuildDir -replace '\\', '/'

$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$InstallDir = $InstallDir -replace '\\', '/'

if ($Clean -and (Test-Path $BuildDir)) {
    Step 'Clean'
    Info "Removing contents of $BuildDir"
    Remove-Item "$BuildDir\*" -Recurse -Force
}
if ($Clean -and (Test-Path $InstallDir)) {
    Step 'Clean'
    Info "Removing contents of $InstallDir"
    Remove-Item "$InstallDir\*" -Recurse -Force
}

if (-not (Test-Path $BuildDir)) {
    New-Item -ItemType Directory -Path $BuildDir | Out-Null
}
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}


# choose CMake generator
if (-not $Generator) {
    $Generator = if (Get-Command ninja.exe -ErrorAction SilentlyContinue) {
        'Ninja'
    } else {
        'Visual Studio 17 2022'
    }
}


# covert skip flags to CMake ON/OFF
$CMakeBuildPythonInterpreter = Convert-SkipToCMake $SkipPythonInterpreter
$CMakeBuildPythonLauncher    = Convert-SkipToCMake $SkipPythonLauncher
$CMakeInstallRequirements    = Convert-SkipToCMake $SkipRequirements
$CMakeInstallModule          = Convert-SkipToCMake $SkipModule
$CMakeInstallPythonLibs      = Convert-SkipToCMake $SkipPythonLibs
$CMakeBuildTests             = Convert-SkipToCMake $SkipTests
$CMakeBuildInstaller         = Convert-SkipToCMake $SkipInstaller
$CMakeBuildDocs              = Convert-SkipToCMake $SKipDocs


# summary
Info "Configuration           : $Config"
Info "Build dir               : $BuildDir"
info "Install dir             : $InstallDir"
Info "Generator               : $Generator"
Info "Build Python Interpreter: $CMakeBuildPythonInterpreter"
Info "Build Python Launcher   : $CMakeBuildPythonLauncher"
Info "Install Requirements    : $CMakeInstallRequirements"
Info "Install Module          : $CMakeInstallModule"
Info "Install PythonLibs      : $CMakeInstallPythonLibs"
Info "Build Tests             : $CMakeBuildTests"
Info "Build Installer         : $CMakeBuildInstaller"
info "Build Docs              : $CmakeBuildDocs"
if ($Clean) { Info 'Clean build             : Yes' }

# decide CMAKE_BUILD_TYPE flag (skip for multi-config gens)
$IsMulti = $Generator -match 'Visual Studio|Xcode'
$CfgFlag = if ($IsMulti) { '' } else { "-DCMAKE_BUILD_TYPE=$Config" }


# ───────────────────────────────────────────────────────────
# CMake configuration step
# ───────────────────────────────────────────────────────────
Step 'Configure'

if ($SkipConfigure) {
    Write-Host "`nSkipping configuration" -ForegroundColor Yellow
} else {
    $ConfigureCmd = @(
        'cmake', '-S', $PSScriptRoot,
        '-B', $BuildDir,
        '-G', $Generator,
        "-DBUILD_PYTHON_INTERPRETER:BOOL=$CMakeBuildPythonInterpreter", # python.exe
        "-DBUILD_PYTHON_LAUNCHER:BOOL=$CMakeBuildPythonLauncher",       # ExpenseTracker.exe
        "-DINSTALL_REQUIREMENTS:BOOL=$CMakeInstallRequirements",        # requirements.txt
        "-DINSTALL_MODULE:BOOL=$CMakeInstallModule",
        "-DINSTALL_PYTHONLIBS:BOOL=$CMakeInstallPythonLibs",
        "-DCMAKE_INSTALL_PREFIX:PATH=$InstallDir",
        "-DCMAKE_PREFIX_PATH:PATH=$InstallDir"
    )
    if ($CfgFlag) { $ConfigureCmd += $CfgFlag }

    Info "CMake command line  : $($ConfigureCmd -join ' ')"
    Invoke-ExternalCommand $ConfigureCmd 'CMake configuration'
}



# ───────────────────────────────────────────────────────────
# Build step
# ───────────────────────────────────────────────────────────
Step 'Build'

if ($SkipBuild) {
    Write-Host "`nSkipping build" -ForegroundColor Yellow
} else {
    $Cpu = $Env:NUMBER_OF_PROCESSORS
    Invoke-ExternalCommand @(
        'cmake', 
        '--build', $BuildDir, 
        '--config', $Config, 
        '--parallel', $Cpu) 'Build'
    Write-Host "`nBuild succeeded" -ForegroundColor Green
}



# ──────────────────────────────────────────────────────────
# Install step
# ──────────────────────────────────────────────────────────
Step 'Install'

if ($SkipInstall) {
    Write-Host "`nSkipping install" -ForegroundColor Yellow
} else {    
    Info "Installing to $InstallDir"
    $InstallCmd = @(
        'cmake',
        '--install', $BuildDir,
        '--config', $Config,
        '--prefix', $InstallDir
    )
    Info "Install command line  : $($InstallCmd -join ' ')"
    Invoke-ExternalCommand $InstallCmd 'CMake install'
    Write-Host "`nInstall succeeded to $InstallDir" -ForegroundColor Green
}


# ───────────────────────────────────────────────────────────
# Run tests step
# ───────────────────────────────────────────────────────────
Step 'Test'

if ($SkipTests) {
    Write-Host "`nSkipping tests" -ForegroundColor Yellow
} else {
    # check if install/python.exe exists
    $PythonExe = "$InstallDir/python.exe"
    if (-not (Test-Path $PythonExe)) {
        Die "$PythonExe not found."
    }
    
    # install/tests
    $TestDir = "$InstallDir/lib/tests"
    if (-not (Test-Path $TestDir)) {
        Die "$TestDir not found."
    }

    Info "Running tests"
    $TestCmd = @(
        $PythonExe,
        '-m', 'unittest',
        'discover',
        '-s', "$TestDir",
        '-p', '*.py'
    )
    Info "Test command line  : $($TestCmd -join ' ')"
    Invoke-ExternalCommand $TestCmd 'Unit tests'

    # Fail if any tests failed
    $TestResult = & $TestCmd
    if ($TestResult -match 'FAILED') {
        Write-Host "`nTests failed" -ForegroundColor Red
        Die "Tests failed."
    } else {
        Write-Host "`nTests passed" -ForegroundColor Green
    }
}


# ─────────────────────────────────────────────────────────
# Installer step
# ─────────────────────────────────────────────────────────
Step 'Installer'

if ($SkipInstaller) {
    Write-Host "`nSkipping installer build" -ForegroundColor Yellow
} else {
    $InstallerDir = Join-Path $BuildDir 'installer'
    if (-not (Test-Path $InstallerDir)) { New-Item -ItemType Directory -Path $InstallerDir | Out-Null }
    Invoke-ExternalCommand @(
        'cmake', 
        '--build', $BuildDir, 
        '--config', $Config,
        '--target', 'package') 'Installer'
    Write-Host "`nInstaller succeeded to $InstallerDir" -ForegroundColor Green
}