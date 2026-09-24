[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [string] $InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\DeepTutor'),
    [switch] $NoDesktopShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-SupportedPythonVersion {
    param([string] $VersionText)

    if ($VersionText -notmatch '(?<major>\d+)\.(?<minor>\d+)') {
        return $false
    }
    $major = [int] $Matches.major
    $minor = [int] $Matches.minor
    return $major -eq 3 -and $minor -ge 11 -and $minor -le 14
}

function Get-PythonSpec {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($minor in @(14, 13, 12, 11)) {
            $selector = "-3.$minor"
            $version = & $launcher.Source $selector --version 2>&1
            $bits = & $launcher.Source $selector -c 'import struct; print(struct.calcsize("P") * 8)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $bits -match '^64$' -and (Test-SupportedPythonVersion ($version -join ' '))) {
                return [pscustomobject]@{
                    Executable = $launcher.Source
                    PrefixArgs = @($selector)
                    Version = ($version -join ' ').Trim()
                }
            }
        }
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        $version = & $python.Source --version 2>&1
        $bits = & $python.Source -c 'import struct; print(struct.calcsize("P") * 8)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $bits -match '^64$' -and (Test-SupportedPythonVersion ($version -join ' '))) {
            return [pscustomobject]@{
                Executable = $python.Source
                PrefixArgs = @()
                Version = ($version -join ' ').Trim()
            }
        }
    }

    throw 'Python 3.11–3.14 was not found. Install a supported 64-bit Python from python.org, then run this installer again.'
}

function Get-NodeVersion {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) {
        throw 'Node.js 20.9 or newer was not found. Install the current Node.js LTS release, reopen PowerShell, and run this installer again.'
    }
    $versionText = & $node.Source --version 2>&1
    if ($LASTEXITCODE -ne 0 -or $versionText -notmatch '^v(?<major>\d+)\.(?<minor>\d+)') {
        throw 'Could not read the Node.js version. Repair the Node.js installation and try again.'
    }
    $major = [int] $Matches.major
    $minor = [int] $Matches.minor
    if ($major -lt 20 -or ($major -eq 20 -and $minor -lt 9)) {
        throw "Node.js 20.9 or newer is required; found $versionText. Install the current Node.js LTS release and try again."
    }
    return ($versionText -join ' ').Trim()
}

function Invoke-Python {
    param(
        [Parameter(Mandatory)] $Python,
        [Parameter(Mandatory)] [string[]] $Arguments
    )
    $allArguments = @($Python.PrefixArgs) + $Arguments
    & $Python.Executable @allArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

$python = Get-PythonSpec
$nodeVersion = Get-NodeVersion
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$venvPython = Join-Path $InstallDir '.venv\Scripts\python.exe'
$venvPythonw = Join-Path $InstallDir '.venv\Scripts\pythonw.exe'
$scriptsDir = Join-Path $InstallDir 'scripts'
$launcherPath = Join-Path $scriptsDir 'start_deeptutor.vbs'

Write-Host "Python: $($python.Version)"
Write-Host "Node.js: $nodeVersion"
Write-Host "Install directory: $InstallDir"
Write-Host 'The published deeptutor wheel includes the packaged web app; this installer does not build frontend assets.'

if (-not $PSCmdlet.ShouldProcess($InstallDir, 'Install or upgrade DeepTutor and create its launcher')) {
    return
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Invoke-Python -Python $python -Arguments (@('-m', 'venv', (Join-Path $InstallDir '.venv')))
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf) -or -not (Test-Path -LiteralPath $venvPythonw -PathType Leaf)) {
    throw "The virtual environment was not created correctly at $(Join-Path $InstallDir '.venv'). No existing files were removed."
}

& $venvPython -m pip install --disable-pip-version-check --upgrade deeptutor
if ($LASTEXITCODE -ne 0) {
    throw 'DeepTutor installation failed. The virtual environment is preserved so you can inspect or retry it.'
}

New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'start_deeptutor.vbs') -Destination $launcherPath -Force

if (-not $NoDesktopShortcut) {
    $wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
    if (-not (Test-Path -LiteralPath $wscript -PathType Leaf)) {
        throw "Windows Script Host was not found at $wscript. Installation succeeded; create a shortcut to $launcherPath manually."
    }
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    $shortcutPath = Join-Path $desktop 'DeepTutor.lnk'
    $shortcut = $null
    $expectedArguments = '"' + $launcherPath + '"'
    if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
        $existingShortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
        if ($existingShortcut.TargetPath -ne $wscript -or $existingShortcut.Arguments -ne $expectedArguments) {
            Write-Warning "An unrelated Desktop shortcut already uses $shortcutPath; it was preserved. Use -NoDesktopShortcut and launch $launcherPath manually."
        }
        else {
            $shortcut = $existingShortcut
        }
    }
    else {
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    }
    if ($shortcut) {
        $shortcut.TargetPath = $wscript
        $shortcut.Arguments = $expectedArguments
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = 'Start DeepTutor'
        $shortcut.Save()
    }
}

Write-Host ''
Write-Host 'Running offline startup diagnostics (this does not call a model provider)...'
Push-Location $InstallDir
try {
    & $venvPython -m deeptutor_cli.main doctor startup
    $doctorExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($doctorExit -ne 0) {
    Write-Warning 'DeepTutor is installed, but one or more startup checks need attention. Run "deeptutor doctor startup" after setup.'
}

Write-Host "DeepTutor is installed in $InstallDir"
Write-Host "Launcher: $launcherPath"
Write-Host "To start from PowerShell: & `"$venvPython`" -m deeptutor_cli.main start"
Write-Host 'To stop a detached instance: deeptutor stop'
