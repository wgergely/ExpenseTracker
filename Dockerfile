# escape=`

FROM mcr.microsoft.com/windows/servercore:ltsc2022 AS builder

# Use PowerShell as the default shell
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';"]



# ————————————————————————————————————————————————————————————
# Install Visual Studio Build Tools
# ————————————————————————————————————————————————————————————
RUN Invoke-WebRequest -Uri https://aka.ms/vs/17/release/vs_buildtools.exe -OutFile vs_buildtools.exe; `
    Start-Process -FilePath vs_buildtools.exe -ArgumentList '--quiet', '--wait', '--norestart', '--nocache', `
    '--installPath', '"%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools"', `
    '--add', 'Microsoft.Net.Component.4.7.TargetingPack', `
    '--add', 'Microsoft.Net.Component.4.7.2.SDK', `
    '--add', 'Microsoft.Net.Component.4.7.2.TargetingPack', `
    '--remove', 'Microsoft.VisualStudio.Component.Windows10SDK.10240', `
    '--remove', 'Microsoft.VisualStudio.Component.Windows10SDK.10586', `
    '--remove', 'Microsoft.VisualStudio.Component.Windows10SDK.14393', `
    '--remove', 'Microsoft.VisualStudio.Component.Windows81SDK' -Wait -PassThru | Out-Null; `
    if ($LASTEXITCODE -eq 3010) { Write-Host "Restart required, but continuing anyway..."; $LASTEXITCODE = 0; }; `
    Remove-Item -Force vs_buildtools.exe

    
# ————————————————————————————————————————————————————————————    
# Download and install CMake
# ————————————————————————————————————————————————————————————
RUN Invoke-WebRequest -Uri https://github.com/Kitware/CMake/releases/download/v3.31.6/cmake-3.31.6-windows-x86_64.msi -OutFile cmake-installer.msi; `
    Start-Process -FilePath "msiexec.exe" -ArgumentList '/i', 'cmake-installer.msi', '/quiet', '/norestart' -Wait -PassThru | Out-Null; `
    if ($LASTEXITCODE -eq 3010) { Write-Host "Restart required, but continuing anyway..."; $LASTEXITCODE = 0; }; `
    Remove-Item -Force cmake-installer.msi

# Verify CMake installation
RUN cmake --version



# ————————————————————————————————————————————————————————————
# Download and install Python 3
# ————————————————————————————————————————————————————————————
RUN Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.11.6/python-3.11.6-amd64.exe -OutFile python-installer.exe; `
    Start-Process -FilePath python-installer.exe -ArgumentList '/quiet', 'InstallAllUsers=1', 'PrependPath=1', 'Include_test=0' -Wait -PassThru | Out-Null; `
    if ($LASTEXITCODE -eq 3010) { Write-Host "Restart required, but continuing anyway..."; $LASTEXITCODE = 0; }; `
    Remove-Item -Force python-installer.exe

# Verify Python installation
RUN python --version



# ————————————————————————————————————————————————————————————
# Install .NET 7.0 SDK
# ————————————————————————————————————————————————————————————
RUN powershell -NoProfile -ExecutionPolicy Bypass -Command `
    Invoke-WebRequest -Uri https://dot.net/v1/dotnet-install.ps1 -OutFile dotnet-install.ps1; `
    .\dotnet-install.ps1 `
      -Channel 7.0 `
      -InstallDir 'C:/dotnet' `
      -NoPath; `
    Remove-Item -Force dotnet-install.ps1

# Add .NET to PATH (using PowerShell)
RUN [Environment]::SetEnvironmentVariable('PATH', $Env:PATH + ';C:/dotnet', [EnvironmentVariableTarget]::Machine);
RUN [Environment]::SetEnvironmentVariable('DOTNET_ROOT', 'C:/dotnet', [EnvironmentVariableTarget]::Machine);

# Verify .NET installation
RUN dotnet --version



# ————————————————————————————————————————————————————————————
# Install WIX for package management
# ————————————————————————————————————————————————————————————
RUN dotnet tool install --global wix

# Verify WIX installation
RUN wix --version



# ————————————————————————————————————————————————————————————
# Download and install git
# ————————————————————————————————————————————————————————————
RUN Invoke-WebRequest -Uri https://github.com/git-for-windows/git/releases/download/v2.49.0.windows.1/Git-2.49.0-64-bit.exe -OutFile git-installer.exe; `
    Start-Process -FilePath git-installer.exe -ArgumentList '/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS', '/COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"' -Wait -PassThru | Out-Null; `
    if ($LASTEXITCODE -eq 3010) { Write-Host "Restart required, but continuing anyway..."; $LASTEXITCODE = 0; }; `
    Remove-Item -Force git-installer.exe

# Verify git installation
RUN git --version



# ————————————————————————————————————————————————————————————
# Install python requirements
# ————————————————————————————————————————————————————————————
COPY requirements.txt .
RUN python -m pip install --upgrade pip; `
    python -m pip install -r requirements.txt; `
    Remove-Item -Force requirements.txt

COPY docs/requirements.txt .
RUN python -m pip install --upgrade pip; `
    python -m pip install -r requirements.txt; `
    Remove-Item -Force requirements.txt
    

WORKDIR C:/workspace