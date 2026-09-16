<#
.SYNOPSIS
    Installs Deployer - a self-hosted Supabase + Vercel style platform - on this Windows PC.

.DESCRIPTION
    One-line install (PowerShell):
        irm https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.ps1 | iex

    With options:
        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.ps1))) -Runtime docker-desktop -Port 8090

    Every password and key is generated on this computer. Deployer contains no credentials from its
    authors; optional Google/GitHub sign-in uses OAuth apps that you create in the setup wizard.

.PARAMETER Runtime
    auto (default): use a working Docker if there is one, otherwise the free Docker Engine in WSL.
    wsl-engine: open-source Docker Engine (docker-ce) in a dedicated WSL2 distro named "deployer".
    docker-desktop: install/use Docker Desktop (license terms apply, see the notice shown).
    existing: use the Docker engine that `docker info` already reaches.

.PARAMETER InstallDir
    Where configuration, scripts and the WSL disk live. Default: %ProgramData%\Deployer.

.PARAMETER Port
    Local HTTP port for the dashboard and API. Default 8080.

.PARAMETER Repo
    GitHub owner/repo to install from (forks work). Default nyx-ulrix/deployer.

.PARAMETER Ref
    Release tag (e.g. v0.1.0) or branch. Default: the latest release, or main if none exists.

.PARAMETER NonInteractive
    Never prompt; optional features default to off unless -EnableLan / -PreventSleep are given.

.PARAMETER FromSource
    Build the api and dashboard images locally instead of pulling them from GHCR.

.PARAMETER SourceDir
    Use a local checkout of the repository instead of downloading one.

.PARAMETER EnableLan
    Allow other devices on your private network to open Deployer.

.PARAMETER PreventSleep
    Stop this PC from sleeping while plugged in.
#>
[CmdletBinding()]
param(
    [ValidateSet('auto', 'wsl-engine', 'docker-desktop', 'existing')]
    [string]$Runtime = 'auto',
    [string]$InstallDir = (Join-Path $env:ProgramData 'Deployer'),
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,
    [string]$Repo = 'nyx-ulrix/deployer',
    [string]$Ref = '',
    [switch]$NonInteractive,
    [switch]$FromSource,
    [string]$SourceDir = '',
    [switch]$EnableLan,
    [switch]$PreventSleep,
    # Internal: set when relaunched elevated / after a reboot.
    [switch]$Elevated,
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:InstallerExitCode = 0
$script:PortWasGiven = $PSBoundParameters.ContainsKey('Port')
$script:LanWasGiven = $PSBoundParameters.ContainsKey('EnableLan')
$script:SleepWasGiven = $PSBoundParameters.ContainsKey('PreventSleep')
$script:RequiredLibVersion = 1
$script:BootstrapRoot = $null
$script:BootstrapRef = $null

# --------------------------------------------------------------------------------------------------
# Bootstrap helpers (needed before lib\common.ps1 is available)
# --------------------------------------------------------------------------------------------------

function Test-BootstrapAdmin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-InstallerArgumentString {
    param([hashtable]$Overrides = @{})
    $values = [ordered]@{
        Runtime    = $Runtime
        InstallDir = $InstallDir
        Port       = $Port
        Repo       = $Repo
        Ref        = $Ref
        SourceDir  = $SourceDir
    }
    foreach ($k in $Overrides.Keys) { $values[$k] = $Overrides[$k] }
    $parts = @()
    foreach ($k in $values.Keys) {
        $v = [string]$values[$k]
        if ($v -ne '') { $parts += ('-{0} "{1}"' -f $k, $v.TrimEnd('\')) }
    }
    if ($NonInteractive) { $parts += '-NonInteractive' }
    if ($FromSource) { $parts += '-FromSource' }
    if ($EnableLan) { $parts += '-EnableLan' }
    if ($PreventSleep) { $parts += '-PreventSleep' }
    return ($parts -join ' ')
}

function Get-InstallerScriptFile {
    # When run through `irm | iex` there is no file on disk; fetch one so we can relaunch it.
    if ($PSCommandPath) { return $PSCommandPath }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $branch = if ($Ref) { $Ref } else { 'main' }
    $uri = "https://raw.githubusercontent.com/$Repo/$branch/installer/install.ps1"
    $target = Join-Path $env:TEMP ("deployer-install-{0}.ps1" -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
    Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $target
    return $target
}

function Write-Banner {
    Write-Host ''
    Write-Host '  ____             _                        ' -ForegroundColor Magenta
    Write-Host ' |  _ \  ___ _ __ | | ___  _   _  ___ _ __  ' -ForegroundColor Magenta
    Write-Host ' | | | |/ _ \  _ \| |/ _ \| | | |/ _ \  __| ' -ForegroundColor Magenta
    Write-Host ' | |_| |  __/ |_) | | (_) | |_| |  __/ |    ' -ForegroundColor Magenta
    Write-Host ' |____/ \___| .__/|_|\___/ \__, |\___|_|    ' -ForegroundColor Magenta
    Write-Host '            |_|            |___/            ' -ForegroundColor Magenta
    Write-Host '  Self-hosted backend + deployments for your own PC' -ForegroundColor Gray
    Write-Host ''
}

function Wait-ForCloseKey {
    if ($Elevated -and -not $NonInteractive) {
        Write-Host ''
        [void](Read-Host 'Press Enter to close this window')
    }
}

# --------------------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------------------

function Get-SystemFacts {
    $os = Get-CimInstance Win32_OperatingSystem
    $cs = Get-CimInstance Win32_ComputerSystem
    $cpu = @(Get-CimInstance Win32_Processor)
    $drive = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($InstallDir)).TrimEnd('\')
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID = '$drive'" -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        Build              = [int][Environment]::OSVersion.Version.Build
        Caption            = $os.Caption
        Is64Bit            = [Environment]::Is64BitOperatingSystem
        IsArm64            = ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64')
        RamGB              = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
        FreeDiskGB         = $(if ($disk) { [math]::Round($disk.FreeSpace / 1GB, 1) } else { $null })
        Drive              = $drive
        VirtualizationOn   = [bool]($cpu | Where-Object { $_.VirtualizationFirmwareEnabled })
        HypervisorPresent  = [bool]$cs.HypervisorPresent
        Avx                = (Test-DeployerCpuAvx)
        CpuName            = ($cpu | Select-Object -First 1).Name
    }
}

function Invoke-Preflight {
    param($Facts, [bool]$IsUpgrade)
    Write-DeployerStep 'Checking this PC'
    Write-DeployerInfo "$($Facts.Caption) (build $($Facts.Build)), $($Facts.CpuName)"

    if (-not $Facts.Is64Bit) { throw 'Deployer needs 64-bit Windows 10 (version 2004 or newer) or Windows 11.' }
    if ($Facts.Build -lt 19041) {
        throw "Windows build $($Facts.Build) is too old. Update to Windows 10 version 2004 (build 19041) or newer, or Windows 11, via Settings > Windows Update."
    }
    Write-DeployerOk 'Windows version is supported'

    if ($Facts.VirtualizationOn -or $Facts.HypervisorPresent) {
        Write-DeployerOk 'Hardware virtualization is enabled'
    } else {
        Write-DeployerWarn 'Hardware virtualization appears to be DISABLED in the BIOS/UEFI firmware.'
        Write-DeployerInfo 'WSL2 and Docker need it. To enable it: restart the PC, open the firmware setup'
        Write-DeployerInfo '(usually F2, F10, Del or Esc during boot) and turn on "Intel Virtualization Technology"'
        Write-DeployerInfo '(VT-x) or "SVM Mode" (AMD). Save, reboot and run this installer again.'
        $script:VirtualizationMissing = $true
    }

    if ($Facts.RamGB -lt 4) {
        Write-DeployerWarn "Only $($Facts.RamGB) GB RAM. Deployer can run, but 4 GB is the minimum and 8 GB is recommended."
    } elseif ($Facts.RamGB -lt 8) {
        Write-DeployerOk "$($Facts.RamGB) GB RAM (works; 8 GB recommended for several projects)"
    } else {
        Write-DeployerOk "$($Facts.RamGB) GB RAM"
    }

    if ($null -ne $Facts.FreeDiskGB) {
        if ($Facts.FreeDiskGB -lt 10) {
            Write-DeployerWarn "Only $($Facts.FreeDiskGB) GB free on $($Facts.Drive). At least 10 GB is recommended (images + databases)."
        } else {
            Write-DeployerOk "$($Facts.FreeDiskGB) GB free on $($Facts.Drive)"
        }
    }

    if ($Facts.Avx) {
        Write-DeployerOk 'CPU supports AVX: managed MongoDB 5.0 will be enabled'
    } else {
        Write-DeployerWarn 'This CPU has no AVX instructions, which MongoDB 5.0 requires.'
        Write-DeployerInfo 'Managed MongoDB will be turned off. Everything else works, and projects can still'
        Write-DeployerInfo 'attach an external MongoDB such as a free MongoDB Atlas cluster (https://www.mongodb.com/atlas).'
    }

    if ($Facts.IsArm64) {
        Write-DeployerWarn 'ARM64 Windows detected: prebuilt images are amd64 only, so images will be built locally.'
        $script:ForceFromSource = $true
    }

    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        $names = @($listeners | ForEach-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } | Sort-Object -Unique)
        $ours = @($names | Where-Object { $_ -match '^(wslrelay|com\.docker\.backend|docker-proxy|vpnkit|svchost)$' })
        if ($IsUpgrade -and $ours.Count -eq $names.Count) {
            Write-DeployerOk "Port $Port is in use by the existing Deployer install"
        } else {
            throw "Port $Port is already used by: $($names -join ', '). Close that program or choose another port, e.g. -Port 8090."
        }
    } else {
        Write-DeployerOk "Port $Port is free"
    }
}

function Select-Runtime {
    param($State)
    if ($Runtime -ne 'auto') { return $Runtime }
    $previous = Get-DeployerStateValue $State 'runtime'
    if ($previous) {
        Write-DeployerInfo "Keeping the runtime chosen at install time: $previous"
        return $previous
    }

    $dockerWorks = $false
    if (Get-DeployerDockerExe) { $dockerWorks = (Test-DeployerDockerEngine -Runtime 'existing') }
    $default = if ($dockerWorks) { 'existing' } else { 'wsl-engine' }
    if ($NonInteractive) { return $default }

    Write-DeployerStep 'Choose how to run containers'
    $options = @(
        @{ Key = '1'; Value = 'wsl-engine'; Text = 'Free Docker Engine in a dedicated WSL2 distro (open source, recommended)' },
        @{ Key = '2'; Value = 'docker-desktop'; Text = 'Docker Desktop (free for personal use, education and small businesses)' }
    )
    if ($dockerWorks) {
        $options += @{ Key = '3'; Value = 'existing'; Text = 'The Docker that is already running on this PC' }
    }
    foreach ($o in $options) {
        $mark = if ($o.Value -eq $default) { ' (default)' } else { '' }
        Write-Host ("    [{0}] {1}{2}" -f $o.Key, $o.Text, $mark)
    }
    while ($true) {
        $answer = Read-Host '    Your choice (press Enter for the default)'
        if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
        $hit = $options | Where-Object { $_.Key -eq $answer.Trim() }
        if ($hit) { return $hit.Value }
    }
}

function Show-DockerDesktopNotice {
    Write-Host ''
    Write-Host '    Docker Desktop licensing' -ForegroundColor Yellow
    Write-DeployerInfo 'Docker Desktop is free for personal use, education, non-commercial open source projects'
    Write-DeployerInfo 'and small businesses (fewer than 250 employees AND less than USD 10 million annual revenue).'
    Write-DeployerInfo 'Larger organisations need a paid Docker subscription. If yours does, sign in to Docker'
    Write-DeployerInfo 'Desktop yourself after it starts - this installer never asks for Docker credentials.'
    Write-DeployerInfo 'Terms: https://www.docker.com/legal/docker-subscription-service-agreement/'
    Write-DeployerInfo 'Prefer something fully free? Re-run with -Runtime wsl-engine.'
    Write-Host ''
}

function Register-ResumeAfterReboot {
    param([string]$ScriptPath)
    $cmdPath = Join-Path $InstallDir 'installer\resume.cmd'
    New-Item -ItemType Directory -Path (Split-Path -Parent $cmdPath) -Force | Out-Null
    $line = '"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "{0}" -Resume {1}' -f $ScriptPath, (Get-InstallerArgumentString)
    [System.IO.File]::WriteAllText($cmdPath, "@echo off`r`n$line`r`n", (New-Object System.Text.ASCIIEncoding))
    New-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Force | Out-Null
    Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'DeployerInstall' -Value ('"{0}"' -f $cmdPath)
}

function Request-Reboot {
    param([string]$Reason)
    Write-DeployerWarn $Reason
    Write-DeployerInfo 'The installer will continue automatically after you restart and sign in again.'
    if (Read-DeployerYesNo -Question 'Restart the computer now?' -Default $false -NonInteractive:$NonInteractive) {
        Restart-Computer -Force
    } else {
        Write-DeployerInfo 'Restart when you are ready.'
    }
    $script:InstallerExitCode = 3010
    # Unwinds the whole install; caught in the main block without reporting a failure.
    throw (New-Object System.OperationCanceledException('Restart required'))
}

function Initialize-WslPlatform {
    param([string]$ResumeScript)
    $wsl = Get-DeployerWslExe
    $vmp = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
    $wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
    $wslVersion = if (Test-Path -LiteralPath $wsl) { Get-DeployerWslVersion } else { $null }

    $pending = @($vmp, $wslFeature | Where-Object { $_ -and ($_.State -eq 'EnablePending' -or $_.RestartNeeded) })
    if ($pending.Count -gt 0) {
        Register-ResumeAfterReboot -ScriptPath $ResumeScript
        Request-Reboot -Reason 'Windows needs a restart to finish enabling WSL.'
    }

    if ($vmp.State -ne 'Enabled' -or -not $wslVersion) {
        Write-DeployerInfo 'Installing Windows Subsystem for Linux (WSL)...'
        $code = Invoke-DeployerStreaming -FilePath $wsl -ArgumentList @('--install', '--no-distribution')
        $vmp = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
        if ($vmp.State -ne 'Enabled' -or $vmp.RestartNeeded) {
            Register-ResumeAfterReboot -ScriptPath $ResumeScript
            Request-Reboot -Reason 'WSL was installed. Windows needs a restart before it can be used.'
        }
        if ($code -ne 0 -and -not (Get-DeployerWslVersion)) {
            Write-DeployerWarn "wsl --install returned $code; trying wsl --update."
        }
    }

    Write-DeployerInfo 'Updating WSL...'
    $code = Invoke-DeployerStreaming -FilePath $wsl -ArgumentList @('--update')
    if ($code -ne 0) {
        $code = Invoke-DeployerStreaming -FilePath $wsl -ArgumentList @('--update', '--web-download')
    }
    $wslVersion = Get-DeployerWslVersion
    if (-not $wslVersion) {
        throw 'WSL could not be installed or updated. Install it from https://aka.ms/wslinstall (or the Microsoft Store: "Windows Subsystem for Linux"), then run this installer again.'
    }
    Write-DeployerOk "WSL $wslVersion is ready"
}

function Get-UbuntuWslImage {
    param([bool]$Arm64)
    $arch = if ($Arm64) { 'arm64' } else { 'amd64' }
    $cache = Join-Path $InstallDir 'cache'

    $candidates = @()
    try {
        # Point releases of the official Ubuntu 24.04 WSL image (newest first).
        $sums = Get-DeployerWebText -Uri 'https://releases.ubuntu.com/noble/SHA256SUMS'
        $found = foreach ($line in ($sums -split "`r?`n")) {
            if ($line -match "^([0-9a-f]{64})\s+\*?(ubuntu-(24\.04(?:\.\d+)*)-wsl-$arch\.wsl)$") {
                [pscustomobject]@{ Hash = $Matches[1]; Name = $Matches[2]; Version = [version]($Matches[3] + $(if ($Matches[3].Split('.').Count -lt 3) { '.0' } else { '' })) }
            }
        }
        $best = @($found | Sort-Object Version -Descending) | Select-Object -First 1
        if ($best) {
            $candidates += [pscustomobject]@{ Uri = "https://releases.ubuntu.com/noble/$($best.Name)"; Hash = $best.Hash; File = "$($best.Name).tar.gz" }
        }
    } catch {
        Write-DeployerWarn "releases.ubuntu.com unavailable: $_"
    }
    try {
        $base = 'https://cloud-images.ubuntu.com/wsl/releases/24.04/current'
        $name = "ubuntu-noble-wsl-$arch-wsl.rootfs.tar.gz"
        $sums = Get-DeployerWebText -Uri "$base/SHA256SUMS"
        foreach ($line in ($sums -split "`r?`n")) {
            if ($line -match "^([0-9a-f]{64})\s+\*?$([regex]::Escape($name))$") {
                $candidates += [pscustomobject]@{ Uri = "$base/$name"; Hash = $Matches[1]; File = $name }
            }
        }
    } catch {
        Write-DeployerWarn "cloud-images.ubuntu.com unavailable: $_"
    }
    if ($candidates.Count -eq 0) {
        throw 'Could not find the Ubuntu 24.04 WSL image checksums (releases.ubuntu.com / cloud-images.ubuntu.com). Check your internet connection.'
    }

    foreach ($c in $candidates) {
        $target = Join-Path $cache $c.File
        if (Test-Path -LiteralPath $target) {
            if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ieq $c.Hash) {
                Write-DeployerOk "Using cached $($c.File)"
                return $target
            }
            Remove-Item -LiteralPath $target -Force
        }
        try {
            Write-DeployerInfo "Downloading Ubuntu 24.04 for WSL (~380 MB) from $($c.Uri)"
            Invoke-DeployerDownload -Uri $c.Uri -OutFile $target
        } catch {
            Write-DeployerWarn "$_"
            continue
        }
        $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        if ($actual -ieq $c.Hash) {
            Write-DeployerOk 'SHA256 checksum verified'
            return $target
        }
        Remove-Item -LiteralPath $target -Force
        Write-DeployerWarn "Checksum mismatch for $($c.File) (expected $($c.Hash), got $actual). Trying the next source."
    }
    throw 'The Ubuntu image could not be downloaded and verified.'
}

function Install-WslEngine {
    param($Facts, [string]$ResumeScript)
    Write-DeployerStep 'Setting up the free Docker Engine in WSL2'
    Initialize-WslPlatform -ResumeScript $ResumeScript
    $wsl = Get-DeployerWslExe

    if (Test-DeployerWslDistro) {
        Write-DeployerOk "WSL distro '$($script:DeployerDistro)' already exists"
    } else {
        $image = Get-UbuntuWslImage -Arm64 $Facts.IsArm64
        $diskDir = Join-Path $InstallDir 'wsl'
        New-Item -ItemType Directory -Path $diskDir -Force | Out-Null
        Write-DeployerInfo "Creating WSL distro '$($script:DeployerDistro)' in $diskDir"
        $code = Invoke-DeployerStreaming -FilePath $wsl -ArgumentList @('--import', $script:DeployerDistro, $diskDir, $image, '--version', '2')
        if ($code -ne 0) {
            throw "wsl --import failed (exit code $code). If it mentions virtualization, enable it in the BIOS/UEFI firmware."
        }
        Remove-Item -LiteralPath $image -Force -ErrorAction SilentlyContinue
        Write-DeployerOk 'Distro created'
    }

    $setupScript = ConvertTo-DeployerWslPath (Join-Path $InstallDir 'installer\wsl\setup-engine.sh')
    Write-DeployerInfo 'Installing Docker Engine inside the distro (apt, from download.docker.com)...'
    $code = Invoke-DeployerStreaming -FilePath $wsl -ArgumentList @('-d', $script:DeployerDistro, '-u', 'root', '--exec', 'bash', $setupScript)
    if ($code -ne 0) { throw "Docker Engine setup inside WSL failed (exit code $code). See the output above." }

    Write-DeployerInfo 'Restarting the distro with systemd...'
    [void](Invoke-DeployerNative -FilePath $wsl -ArgumentList @('--terminate', $script:DeployerDistro) -TimeoutSeconds 120)
    if (-not (Wait-DeployerDockerEngine -Runtime 'wsl-engine' -TimeoutSeconds 240)) {
        throw 'Docker Engine inside WSL did not start. Try: wsl -d deployer -u root -- systemctl status docker'
    }
    Write-DeployerOk 'Docker Engine is running in WSL'
}

function Install-DockerDesktopRuntime {
    param([string]$ResumeScript)
    Write-DeployerStep 'Setting up Docker Desktop'
    Show-DockerDesktopNotice

    if (-not (Get-DeployerDockerDesktopExe)) {
        if (-not (Read-DeployerYesNo -Question 'Install Docker Desktop now under these terms?' -Default $true -NonInteractive:$NonInteractive)) {
            throw 'Docker Desktop installation cancelled. Re-run with -Runtime wsl-engine for the fully free option.'
        }
        Initialize-WslPlatform -ResumeScript $ResumeScript
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw 'winget (App Installer) was not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and re-run with -Runtime docker-desktop.'
        }
        Write-DeployerInfo 'Installing Docker Desktop with winget (this can take several minutes)...'
        $code = Invoke-DeployerStreaming -FilePath $winget.Source -ArgumentList @(
            'install', '-e', '--id', 'Docker.DockerDesktop', '--source', 'winget',
            '--accept-source-agreements', '--accept-package-agreements')
        if ($code -ne 0 -and -not (Get-DeployerDockerDesktopExe)) {
            throw "winget could not install Docker Desktop (exit code $code). Install it manually from https://www.docker.com/products/docker-desktop/ and re-run with -Runtime docker-desktop."
        }
        Write-DeployerOk 'Docker Desktop installed'
    } else {
        Write-DeployerOk 'Docker Desktop is already installed'
    }

    if (Test-DeployerDockerEngine -Runtime 'docker-desktop') {
        Write-DeployerOk 'Docker Desktop engine is running'
        return
    }
    [void](Start-DeployerDockerDesktop)
    Write-DeployerInfo 'Docker Desktop is starting. If it shows its service agreement, review and accept it in the'
    Write-DeployerInfo 'Docker Desktop window. Signing in is optional unless your organisation needs a subscription.'
    if (-not (Wait-DeployerDockerEngine -Runtime 'docker-desktop' -TimeoutSeconds 900 -WaitingMessage 'Waiting for Docker Desktop')) {
        Register-ResumeAfterReboot -ScriptPath $ResumeScript
        Request-Reboot -Reason 'Docker Desktop did not become ready. A restart (or sign-out) is often needed after installing it.'
    }
    Write-DeployerOk 'Docker Desktop engine is running'
}

function Test-ExistingRuntime {
    Write-DeployerStep 'Checking the existing Docker installation'
    if (-not (Get-DeployerDockerExe)) { throw 'No docker command found. Choose -Runtime wsl-engine or docker-desktop instead.' }
    if (-not (Test-DeployerDockerEngine -Runtime 'existing')) {
        throw '`docker info` fails: the Docker engine is not running. Start it and re-run, or choose -Runtime wsl-engine.'
    }
    Write-DeployerOk 'Docker engine reachable'
}

function Resolve-Source {
    if ($SourceDir) {
        $full = [System.IO.Path]::GetFullPath($SourceDir)
        if (-not (Test-Path -LiteralPath (Join-Path $full 'deploy\docker-compose.yml'))) {
            throw "-SourceDir '$SourceDir' does not contain deploy\docker-compose.yml."
        }
        return @{ Root = $full; Ref = 'local' }
    }
    if ($PSScriptRoot -and -not $Ref) {
        $checkout = Split-Path -Parent $PSScriptRoot
        if ((Test-Path -LiteralPath (Join-Path $checkout 'deploy\docker-compose.yml')) -and (Test-Path -LiteralPath (Join-Path $checkout '.git'))) {
            Write-DeployerInfo "Using the local checkout at $checkout"
            return @{ Root = $checkout; Ref = 'local' }
        }
    }
    if ($script:BootstrapRoot) {
        Write-DeployerInfo "Installing $Repo@$($script:BootstrapRef)"
        return @{ Root = $script:BootstrapRoot; Ref = $script:BootstrapRef }
    }
    $resolved = Resolve-DeployerRef -Repo $Repo -Ref $Ref
    Write-DeployerInfo "Installing $Repo@$resolved"
    $work = Join-Path $env:TEMP 'deployer-source'
    $root = Get-DeployerSource -Repo $Repo -Ref $resolved -WorkDir $work
    return @{ Root = $root; Ref = $resolved }
}

function Set-LanAccess {
    param([string]$Rt, [int]$HttpPort, [bool]$UseMirrored)
    Write-DeployerInfo 'Adding a Windows Firewall rule (Private networks only)...'
    Add-DeployerFirewallRule -Port $HttpPort
    if ($Rt -ne 'wsl-engine') { return 'direct' }
    if ($UseMirrored) {
        $cfg = Join-Path $env:USERPROFILE '.wslconfig'
        if ((Test-Path -LiteralPath $cfg) -and ((Get-Content -LiteralPath $cfg -Raw) -match '(?im)^\s*networkingMode\s*=\s*mirrored')) {
            Write-DeployerOk 'WSL mirrored networking is already enabled'
            return 'mirrored'
        }
        $lines = New-Object System.Collections.Generic.List[string]
        if (Test-Path -LiteralPath $cfg) {
            $backup = "$cfg.deployer-backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
            Copy-Item -LiteralPath $cfg -Destination $backup
            Write-DeployerInfo "Backed up $cfg to $backup"
            foreach ($l in [System.IO.File]::ReadAllLines($cfg)) { $lines.Add($l) }
        }
        $section = -1
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match '^\s*\[wsl2\]\s*$') { $section = $i; break }
        }
        if ($section -lt 0) {
            if ($lines.Count -gt 0) { $lines.Add('') }
            $lines.Add('[wsl2]')
            $lines.Add('networkingMode=mirrored')
        } else {
            $replaced = $false
            for ($j = $section + 1; $j -lt $lines.Count -and $lines[$j] -notmatch '^\s*\['; $j++) {
                if ($lines[$j] -match '^\s*networkingMode\s*=') { $lines[$j] = 'networkingMode=mirrored'; $replaced = $true }
            }
            if (-not $replaced) { $lines.Insert($section + 1, 'networkingMode=mirrored') }
        }
        [System.IO.File]::WriteAllText($cfg, (($lines.ToArray() -join "`r`n") + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
        Write-DeployerInfo 'Restarting WSL to switch to mirrored networking...'
        Stop-DeployerKeepAlive
        [void](Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('--shutdown') -TimeoutSeconds 120)
        [void](Wait-DeployerDockerEngine -Runtime 'wsl-engine' -TimeoutSeconds 240)
        return 'mirrored'
    }
    [void](Update-DeployerPortProxy -Port $HttpPort)
    return 'portproxy'
}

# --------------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------------

Write-Banner

# 1. Administrator rights ---------------------------------------------------------------------------
if (-not (Test-BootstrapAdmin)) {
    Write-Host '==> Administrator rights are needed (WSL, firewall and scheduled task). Asking Windows...' -ForegroundColor Cyan
    try {
        $scriptFile = Get-InstallerScriptFile
        $argString = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Elevated {1}' -f $scriptFile, (Get-InstallerArgumentString)
        if ($Resume) { $argString += ' -Resume' }
        $child = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $argString -Verb RunAs -PassThru -Wait
        $script:InstallerExitCode = $child.ExitCode
        if ($child.ExitCode -eq 0) {
            Write-Host '    Deployer installation finished in the administrator window.' -ForegroundColor Green
        } elseif ($child.ExitCode -eq 3010) {
            Write-Host '    A restart is needed; installation continues after you sign in again.' -ForegroundColor Yellow
        } else {
            Write-Host "    The installer exited with code $($child.ExitCode). See the log in $InstallDir\logs." -ForegroundColor Red
        }
    } catch {
        Write-Host "    Could not start the installer as administrator: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host '    Right-click PowerShell, choose "Run as administrator", and run the install command again.' -ForegroundColor Red
        $script:InstallerExitCode = 1
    }
} else {
    $transcriptStarted = $false
    try {
        $InstallDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
        New-Item -ItemType Directory -Path (Join-Path $InstallDir 'logs') -Force | Out-Null
        try {
            Start-Transcript -Path (Join-Path $InstallDir ("logs\install-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))) | Out-Null
            $transcriptStarted = $true
        } catch {
            Write-Verbose "Transcript unavailable: $_"
        }
        if ($Resume) {
            Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'DeployerInstall' -ErrorAction SilentlyContinue
            Write-Host '==> Resuming the Deployer installation' -ForegroundColor Cyan
        }

        # 5 (early). Source: provides lib\common.ps1 and the deploy files --------------------------
        Write-Host ''
        Write-Host '==> Fetching Deployer' -ForegroundColor Cyan
        $libLocal = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'lib\common.ps1' } else { '' }
        if ($libLocal -and (Test-Path -LiteralPath $libLocal)) { . $libLocal }
        if (-not (Get-Command Resolve-DeployerRef -ErrorAction SilentlyContinue)) {
            # Minimal bootstrap: download the source first, then load its helpers.
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            $bootRef = $Ref
            if (-not $bootRef) {
                try {
                    $bootRef = [string](Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -TimeoutSec 30 -Headers @{ 'User-Agent' = 'deployer-installer' }).tag_name
                } catch {
                    $bootRef = ''
                }
                if (-not $bootRef) { $bootRef = 'main' }
            }
            if ($SourceDir) {
                $bootRoot = [System.IO.Path]::GetFullPath($SourceDir)
            } else {
                $bootWork = Join-Path $env:TEMP 'deployer-bootstrap'
                if (Test-Path -LiteralPath $bootWork) { Remove-Item -LiteralPath $bootWork -Recurse -Force }
                New-Item -ItemType Directory -Path $bootWork -Force | Out-Null
                $bootZip = Join-Path $bootWork 'source.zip'
                Write-Host "    Downloading https://github.com/$Repo/archive/$bootRef.zip"
                Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/$bootRef.zip" -OutFile $bootZip
                Expand-Archive -LiteralPath $bootZip -DestinationPath (Join-Path $bootWork 'x') -Force
                $bootRoot = (Get-ChildItem -LiteralPath (Join-Path $bootWork 'x') -Directory | Select-Object -First 1).FullName
            }
            $bootLib = Join-Path $bootRoot 'installer\lib\common.ps1'
            if (-not (Test-Path -LiteralPath $bootLib)) { throw "installer\lib\common.ps1 not found in $Repo@$bootRef." }
            . $bootLib
            if (-not $SourceDir) {
                $script:BootstrapRoot = $bootRoot
                $script:BootstrapRef = $bootRef
            }
        }
        if (-not (Get-Variable -Name DeployerLibVersion -Scope Script -ErrorAction SilentlyContinue) -or $script:DeployerLibVersion -lt $script:RequiredLibVersion) {
            throw "This install.ps1 needs a newer installer\lib\common.ps1. Run the install.ps1 from the same release: https://raw.githubusercontent.com/$Repo/<tag>/installer/install.ps1"
        }
        $script:DeployerLogFile = Join-Path $InstallDir 'logs\deployer.log'

        $state = Read-DeployerState -InstallDir $InstallDir
        $isUpgrade = ($null -ne $state) -or (Test-Path -LiteralPath (Join-Path $InstallDir '.env'))
        if ($isUpgrade) { Write-DeployerInfo "Existing installation found in $InstallDir - upgrading it (your .env and data are kept)." }
        if ($isUpgrade -and -not $script:PortWasGiven) {
            $existingEnv = Read-DeployerEnvFile -Path (Join-Path $InstallDir '.env')
            if ($existingEnv['DEPLOYER_HTTP_PORT'] -match '^\d+$') { $Port = [int]$existingEnv['DEPLOYER_HTTP_PORT'] }
        }

        # 2. Preflight ----------------------------------------------------------------------------
        $script:VirtualizationMissing = $false
        $script:ForceFromSource = $false
        $facts = Get-SystemFacts
        Invoke-Preflight -Facts $facts -IsUpgrade $isUpgrade

        # 3. Runtime + questions up front, so the long steps run unattended --------------------------
        $chosen = Select-Runtime -State $state
        Write-DeployerOk "Runtime: $chosen"
        if ($chosen -ne 'existing' -and $script:VirtualizationMissing) {
            throw 'Virtualization must be enabled in the firmware for WSL2/Docker Desktop (see above).'
        }
        $identityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        if ($Elevated -and $chosen -ne 'existing') {
            Write-DeployerInfo "Installing for Windows account $identityName (WSL distros and Docker Desktop are per-user)."
        }

        $lanDefault = [bool](Get-DeployerStateValue (Get-DeployerStateValue $state 'lan') 'enabled' $false)
        $wantLan = if ($script:LanWasGiven) { [bool]$EnableLan } elseif ($NonInteractive) { $lanDefault } else {
            Write-DeployerStep 'Optional settings'
            Write-DeployerInfo 'Deployer is reachable from this PC only unless you allow other devices on your home/office network.'
            Read-DeployerYesNo -Question 'Allow access from other devices on your private network (LAN)?' -Default $lanDefault
        }
        $useMirrored = $false
        if ($wantLan -and $chosen -eq 'wsl-engine') {
            $wslVer = Get-DeployerWslVersion
            if ($facts.Build -ge 22621 -and $wslVer -and $wslVer -ge [version]'2.0.0') {
                if ($NonInteractive) {
                    $useMirrored = $true
                } else {
                    Write-DeployerInfo 'Windows 11 22H2+ supports WSL "mirrored" networking. Enabling it edits %USERPROFILE%\.wslconfig'
                    Write-DeployerInfo '(a backup is kept) and restarts WSL once, which also restarts other WSL distros / Docker Desktop.'
                    $useMirrored = Read-DeployerYesNo -Question 'Use mirrored networking? (No = Windows port forwarding instead)' -Default $true
                }
            }
        }
        $wantSleepOff = if ($script:SleepWasGiven -or $NonInteractive) { [bool]$PreventSleep } else {
            Read-DeployerYesNo -Question 'Prevent this PC from sleeping while plugged in (keeps your sites online)?' -Default $false
        }

        # 5 (files first: the WSL setup script and the resume-after-reboot script live there) ------
        $source = Resolve-Source
        New-Item -ItemType Directory -Path (Join-Path $InstallDir 'installer') -Force | Out-Null
        Copy-DeployerFiles -SourceRoot $source.Root -InstallDir $InstallDir
        Set-DeployerInstallDirAcl -Path $InstallDir

        # 4. Runtime setup ---------------------------------------------------------------------------
        $resumeScript = Join-Path $InstallDir 'installer\install.ps1'
        switch ($chosen) {
            'wsl-engine' { Install-WslEngine -Facts $facts -ResumeScript $resumeScript }
            'docker-desktop' { Install-DockerDesktopRuntime -ResumeScript $resumeScript }
            'existing' { Test-ExistingRuntime }
        }
        if (-not (Test-DeployerComposePlugin -Runtime $chosen)) {
            throw 'The Docker Compose v2 plugin (`docker compose`) is not available for this Docker installation.'
        }

        # 5/6. Files, .env, permissions ---------------------------------------------------------------
        Write-DeployerStep 'Writing configuration'
        $bind = if ($wantLan) { '0.0.0.0' } elseif ($chosen -eq 'wsl-engine' -and -not $useMirrored) {
            # WSL NAT: the distro's own IP is only reachable from this PC; 0.0.0.0 keeps localhost forwarding reliable.
            $cfgPath = Join-Path $env:USERPROFILE '.wslconfig'
            if ((Test-Path -LiteralPath $cfgPath) -and ((Get-Content -LiteralPath $cfgPath -Raw) -match '(?im)^\s*networkingMode\s*=\s*mirrored')) { '127.0.0.1' } else { '0.0.0.0' }
        } else { '127.0.0.1' }
        $created = Initialize-DeployerEnv -InstallDir $InstallDir -Port $Port -MongoEnabled $facts.Avx `
            -ImagePrefix (Get-DeployerImagePrefix -Repo $Repo) -Version (Get-DeployerImageVersion -Ref $source.Ref) `
            -Bind $bind -SetPort:$script:PortWasGiven
        if ($created) { Write-DeployerOk '.env created with freshly generated secrets (readable by Administrators, SYSTEM and you only)' }
        else { Write-DeployerOk '.env kept; new settings merged in' }
        foreach ($dir in @('backups', 'logs')) { New-Item -ItemType Directory -Path (Join-Path $InstallDir $dir) -Force | Out-Null }
        Set-DeployerPrivateAcl -Path (Join-Path $InstallDir 'backups')

        $stateTable = ConvertTo-DeployerStateTable $state
        $stateTable['runtime'] = $chosen
        $stateTable['distro'] = $(if ($chosen -eq 'wsl-engine') { $script:DeployerDistro } else { $null })
        $stateTable['port'] = $Port
        $stateTable['repo'] = $Repo
        $stateTable['ref'] = $source.Ref
        $stateTable['managedMongodb'] = [bool]$facts.Avx
        $stateTable['installUser'] = $identityName
        $stateTable['installUserSid'] = (Get-DeployerUserSid)
        if (-not $stateTable.Contains('installedAt')) { $stateTable['installedAt'] = (Get-Date).ToUniversalTime().ToString('o') }
        $stateTable['updatedAt'] = (Get-Date).ToUniversalTime().ToString('o')
        $stateTable['lan'] = @{ enabled = $false; mode = 'none' }
        Save-DeployerState -InstallDir $InstallDir -State $stateTable

        # 7. Images + start ----------------------------------------------------------------------------
        Write-DeployerStep 'Starting Deployer'
        $imageMode = Invoke-DeployerImages -InstallDir $InstallDir -Runtime $chosen -FromSource:($FromSource -or $script:ForceFromSource)
        $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $chosen -Arguments @('up', '-d', '--remove-orphans')
        if ($code -ne 0) {
            Show-DeployerDiagnostics -InstallDir $InstallDir -Runtime $chosen
            throw "docker compose up failed (exit code $code)."
        }
        $timeout = if ($imageMode -eq 'built') { 600 } else { 420 }
        Write-DeployerInfo "Waiting for http://localhost:$Port/v1/health (first start runs database migrations)..."
        $health = Wait-DeployerHealth -Port $Port -TimeoutSeconds $timeout
        if (-not $health) {
            Show-DeployerDiagnostics -InstallDir $InstallDir -Runtime $chosen
            throw "Deployer did not become healthy within $([int]($timeout / 60)) minutes. The logs above usually explain why; run 'deployer logs api' for more."
        }
        Write-DeployerOk "Deployer is up: $health"

        # 8. Autostart ---------------------------------------------------------------------------------
        Write-DeployerStep 'Starting Deployer automatically when you sign in'
        Register-DeployerTask -InstallDir $InstallDir
        Write-DeployerOk "Scheduled task '$($script:DeployerTaskName)' runs at logon of $identityName"
        if ($chosen -eq 'wsl-engine') {
            Write-DeployerInfo 'Note: WSL distros belong to one Windows account, so Deployer runs while this account is signed in.'
        }

        # 9. Optional: LAN + sleep ---------------------------------------------------------------------
        $lanMode = 'none'
        if ($wantLan) {
            Write-DeployerStep 'Allowing access from your private network'
            $lanMode = Set-LanAccess -Rt $chosen -HttpPort $Port -UseMirrored $useMirrored
            [void](Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $chosen -Arguments @('up', '-d'))
            if (-not (Wait-DeployerHealth -Port $Port -TimeoutSeconds 240)) {
                Write-DeployerWarn 'Deployer is not answering after the network change yet; check with "deployer status".'
            }
            Write-DeployerOk "LAN access enabled ($lanMode). Make sure your network is set to Private in Windows settings."
        } else {
            Remove-DeployerFirewallRule
            Remove-DeployerPortProxy -Port $Port
        }
        $stateTable['lan'] = @{ enabled = [bool]$wantLan; mode = $lanMode }
        Save-DeployerState -InstallDir $InstallDir -State $stateTable

        if ($wantSleepOff) {
            $powercfg = Join-Path $env:SystemRoot 'System32\powercfg.exe'
            [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/change', 'standby-timeout-ac', '0'))
            [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/change', 'hibernate-timeout-ac', '0'))
            Write-DeployerOk 'Sleep and hibernate disabled while on AC power'
        }

        # 10. CLI, browser, summary ----------------------------------------------------------------------
        Write-DeployerStep 'Finishing up'
        Add-DeployerUserPath -Directory $InstallDir
        Write-DeployerOk "The 'deployer' command is on your PATH (open a new terminal)"
        try {
            Start-ScheduledTask -TaskName $script:DeployerTaskName
        } catch {
            Write-DeployerWarn "Could not start the scheduled task now: $_"
        }
        $setupUrl = "http://localhost:$Port/setup"
        if (-not $NonInteractive) { Open-DeployerUrl -Url $setupUrl }

        Write-Host ''
        Write-Host '  Deployer is installed and running.' -ForegroundColor Green
        Write-Host ''
        Write-Host "    Setup wizard   $setupUrl"
        Write-Host "    Runtime        $chosen"
        Write-Host "    Install dir    $InstallDir"
        Write-Host "    Version        $($source.Ref)"
        $mongoText = if ($facts.Avx) { 'managed MongoDB 5.0 enabled' } else { 'managed MongoDB disabled (no AVX) - use an external MongoDB such as Atlas' }
        Write-Host "    NoSQL          $mongoText"
        if ($wantLan) {
            foreach ($ip in @(Get-DeployerLanAddresses)) { Write-Host "    On your LAN    http://${ip}:$Port" }
        }
        Write-Host ''
        Write-Host '    Manage it with: deployer status | logs | stop | start | update | backup | uninstall'
        Write-Host '    Back up .env (it holds MASTER_KEY) together with your backups.' -ForegroundColor Yellow
        Write-Host ''
    } catch [System.OperationCanceledException] {
        Write-Host ''
        Write-Host '  Installation paused until the restart described above.' -ForegroundColor Yellow
    } catch {
        $script:InstallerExitCode = 1
        Write-Host ''
        Write-Host "  Installation failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Verbose ($_.ScriptStackTrace)
        Write-Host "  Details are in $InstallDir\logs. Fix the problem above and run the installer again;" -ForegroundColor Red
        Write-Host '  it picks up where it left off and never overwrites your existing .env.' -ForegroundColor Red
    } finally {
        if ($transcriptStarted) {
            try { Stop-Transcript | Out-Null } catch { Write-Verbose 'Transcript already stopped.' }
        }
    }
    Wait-ForCloseKey
}

if ($PSCommandPath) { exit $script:InstallerExitCode }
