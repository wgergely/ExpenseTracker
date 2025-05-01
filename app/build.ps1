<#
===============================================================================
 build.ps1 – CMake configure + build helper (Windows PowerShell 5.1)
-------------------------------------------------------------------------------
    -Config            Debug | Release          (default: Release)
    -BuildDir          Path to build directory  (default: .\build)
    -Generator         CMake generator name     (auto: Ninja if in PATH, else VS 2022)
    -Clean             Remove contents of BuildDir before configuring

    -SkipPythonInterpreter   Do NOT build embedded Python interpreter
    -SkipPythonLauncher      Do NOT build Python module launcher
    -SkipRequirements        Do NOT install requirements.txt
    -SkipModule              Do NOT install main Python module
    -SkipStdlib              Do NOT install standard Python libraries
    -SkipTests               Do NOT build unit tests

    -h / -Help         Display this help
===============================================================================
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet('Debug','Release')]
    [string] $Config = 'Release',

    [string] $BuildDir = "$PSScriptRoot\build",

    [string] $Generator,

    [switch] $Clean,

    [switch] $SkipPythonInterpreter,
    [switch] $SkipPythonLauncher,
    [switch] $SkipRequirements,
    [switch] $SkipModule,
    [switch] $SkipStdlib,
    [switch] $SkipTests,

    [Alias('h')]
    [switch] $Help
)

# ───────── global settings ────────────────────────────────────────────────
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ───────── helpers ────────────────────────────────────────────────────────
function Info {  param($t) Write-Host '[INFO ]'  $t -ForegroundColor Cyan }
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

# ───────── normalise / create build directory ────────────────────────────
$BuildDir = [IO.Path]::GetFullPath($BuildDir)

if ($Clean -and (Test-Path $BuildDir)) {
    Step 'Clean'
    Info "Removing contents of $BuildDir"
    Remove-Item "$BuildDir\*" -Recurse -Force
}

if (-not (Test-Path $BuildDir)) {
    New-Item -ItemType Directory -Path $BuildDir | Out-Null
}

# ───────── choose generator if none supplied ─────────────────────────────
if (-not $Generator) {
    $Generator = if (Get-Command ninja.exe -ErrorAction SilentlyContinue) {
        'Ninja'
    } else {
        'Visual Studio 17 2022'
    }
}

# ───────── convert switches to ON/OFF for CMake ──────────────────────────
$CMakeBuildPythonInterpreter = Convert-SkipToCMake $SkipPythonInterpreter
$CMakeBuildPythonLauncher    = Convert-SkipToCMake $SkipPythonLauncher
$CMakeInstallRequirements    = Convert-SkipToCMake $SkipRequirements
$CMakeInstallModule          = Convert-SkipToCMake $SkipModule
$CMakeInstallStdlib          = Convert-SkipToCMake $SkipStdlib
$CMakeBuildTests             = Convert-SkipToCMake $SkipTests

# ───────── summary ───────────────────────────────────────────────────────
Info "Configuration           : $Config"
Info "Build dir               : $BuildDir"
Info "Generator               : $Generator"
Info "Build Python Interpreter: $CMakeBuildPythonInterpreter"
Info "Build Python Launcher   : $CMakeBuildPythonLauncher"
Info "Install Requirements    : $CMakeInstallRequirements"
Info "Install Module          : $CMakeInstallModule"
Info "Install Stdlib          : $CMakeInstallStdlib"
Info "Build Tests             : $CMakeBuildTests"
if ($Clean) { Info 'Clean build             : Yes' }

# ───────── decide CMAKE_BUILD_TYPE flag (skip for multi-config gens) ─────
$IsMulti = $Generator -match 'Visual Studio|Xcode'
$CfgFlag = if ($IsMulti) { '' } else { "-DCMAKE_BUILD_TYPE=$Config" }

# ───────── CONFIGURE step ────────────────────────────────────────────────
Step 'Configure'
$ConfigureCmd = @(
    'cmake', '-S', $PSScriptRoot,
    '-B', $BuildDir,
    '-G', $Generator,
    "-DBUILD_PYTHON_INTERPRETER:BOOL=$CMakeBuildPythonInterpreter",
    "-DBUILD_PYTHON_LAUNCHER:BOOL=$CMakeBuildPythonLauncher",
    "-DINSTALL_REQUIREMENTS:BOOL=$CMakeInstallRequirements",
    "-DINSTALL_MODULE:BOOL=$CMakeInstallModule",
    "-DINSTALL_STDLIB:BOOL=$CMakeInstallStdlib",
    "-DBUILD_TESTS:BOOL=$CMakeBuildTests"
)
if ($CfgFlag) { $ConfigureCmd += $CfgFlag }

Info "CMake command line  : $($ConfigureCmd -join ' ')"
Invoke-ExternalCommand $ConfigureCmd 'CMake configuration'

# ───────── BUILD step ────────────────────────────────────────────────────
Step 'Build'
$Cpu = $Env:NUMBER_OF_PROCESSORS
Invoke-ExternalCommand @('cmake', '--build', $BuildDir, '--config', $Config, '--parallel', $Cpu) 'Build'
Write-Host "`nBuild succeeded" -ForegroundColor Green

# ───────── INSTALL step (into $BuildDir\install) ─────────────────────────
Step 'Install'
$InstallDir = Join-Path $BuildDir 'install'
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir | Out-Null }
Invoke-ExternalCommand @('cmake', '--install', $BuildDir, '--config', $Config, '--prefix', $InstallDir) 'Install'
Write-Host "`nInstall succeeded to $InstallDir" -ForegroundColor Green
