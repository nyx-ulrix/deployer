# Deployer - shared helpers for install.ps1 and deployer.ps1.
# Windows PowerShell 5.1 compatible. Keep this file ASCII-only (5.1 reads BOM-less files as ANSI).

# Bumped when install.ps1 / deployer.ps1 need functions that older copies of this file lack.
$script:DeployerLibVersion = 3
$script:DeployerDistro = 'deployer'
$script:DeployerTaskName = 'Deployer'
$script:DeployerTrayTaskName = 'Deployer Tray'
$script:DeployerControlExe = 'DeployerControl.exe'
$script:DeployerFirewallRule = 'Deployer-HTTP'
# Written by `deployer stop` (in the install dir) so the sign-in task's keep-alive loop does not undo it.
$script:DeployerStopMarker = 'stop-requested'
$script:DeployerLogFile = $null
$script:DeployerQuiet = $false

# wsl.exe prints UTF-16 unless told otherwise; docker/compose print UTF-8.
$env:WSL_UTF8 = '1'
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
} catch {
    Write-Verbose 'Console encoding unchanged (no console attached).'
}
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Verbose 'Could not enable TLS 1.2 explicitly.'
}

# ------------------------------------------------------------------------------------------------
# Output
# ------------------------------------------------------------------------------------------------

function Write-DeployerLog {
    param([string]$Level, [string]$Message)
    if ($script:DeployerLogFile) {
        try {
            $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
            Add-Content -LiteralPath $script:DeployerLogFile -Value $line -Encoding UTF8
        } catch {
            Write-Verbose "Log write failed: $_"
        }
    }
}

function Write-DeployerStep {
    param([string]$Message)
    Write-DeployerLog 'STEP' $Message
    Write-Host ''
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-DeployerInfo {
    param([string]$Message)
    Write-DeployerLog 'INFO' $Message
    Write-Host "    $Message"
}

function Write-DeployerOk {
    param([string]$Message)
    Write-DeployerLog 'OK' $Message
    Write-Host "    [ok] $Message" -ForegroundColor Green
}

function Write-DeployerWarn {
    param([string]$Message)
    Write-DeployerLog 'WARN' $Message
    Write-Host "    [!] $Message" -ForegroundColor Yellow
}

function Write-DeployerError {
    param([string]$Message)
    Write-DeployerLog 'ERROR' $Message
    Write-Host "    [x] $Message" -ForegroundColor Red
}

function Write-DeployerMarker {
    # Machine-readable progress line for DeployerSetup.exe, e.g. "##deployer:step 3/10 Installing Docker".
    param([string]$Text)
    Write-Host "##deployer:$Text"
}

function Read-DeployerYesNo {
    param([string]$Question, [bool]$Default = $false, [switch]$NonInteractive)
    if ($NonInteractive) { return $Default }
    $hint = if ($Default) { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        $answer = Read-Host "    $Question $hint"
        if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
        switch -Regex ($answer.Trim()) {
            '^(y|yes)$' { return $true }
            '^(n|no)$' { return $false }
        }
    }
}

# ------------------------------------------------------------------------------------------------
# Processes
# ------------------------------------------------------------------------------------------------

function Test-DeployerIsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function ConvertTo-DeployerArgument {
    # Quotes one argument using the rules of CommandLineToArgvW / the MS C runtime.
    param([AllowEmptyString()][string]$Value)
    if ($Value -eq '') { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('"')
    $slashes = 0
    foreach ($ch in $Value.ToCharArray()) {
        if ($ch -eq [char]'\') {
            $slashes++
            continue
        }
        if ($ch -eq [char]'"') {
            [void]$sb.Append([char]'\', (2 * $slashes) + 1)
        } elseif ($slashes -gt 0) {
            [void]$sb.Append([char]'\', $slashes)
        }
        [void]$sb.Append($ch)
        $slashes = 0
    }
    if ($slashes -gt 0) { [void]$sb.Append([char]'\', 2 * $slashes) }
    [void]$sb.Append('"')
    return $sb.ToString()
}

function Invoke-DeployerNative {
    <#
      Runs a program and captures stdout/stderr without PowerShell 5.1's stderr-to-ErrorRecord
      conversion. Returns an object with ExitCode, StdOut, StdErr and Output (both combined).
      -StdinText is written to the program's stdin as UTF-8 (the way to hand it a secret: never argv).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [int]$TimeoutSeconds = 0,
        [string]$StdinText = ''
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (@($ArgumentList) | ForEach-Object { ConvertTo-DeployerArgument $_ }) -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $psi.RedirectStandardInput = [bool]$StdinText
    try {
        $process = [System.Diagnostics.Process]::Start($psi)
    } catch {
        return [pscustomobject]@{ ExitCode = -1; StdOut = ''; StdErr = "$_"; Output = "$_" }
    }
    if ($StdinText) {
        # Raw UTF-8 bytes: the .NET Framework stdin writer would use the console code page.
        $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($StdinText)
        try {
            $process.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
            $process.StandardInput.Close()
        } catch {
            Write-Verbose "Writing stdin failed: $($_.Exception.Message)"
        }
    }
    $outTask = $process.StandardOutput.ReadToEndAsync()
    $errTask = $process.StandardError.ReadToEndAsync()
    if ($TimeoutSeconds -gt 0) {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { Write-Verbose "Kill failed: $_" }
            return [pscustomobject]@{ ExitCode = -2; StdOut = ''; StdErr = 'timed out'; Output = 'timed out' }
        }
    }
    $process.WaitForExit()
    # Legacy wsl.exe ignores WSL_UTF8 and emits UTF-16; strip the NULs so text still matches.
    $stdout = ($outTask.Result -replace "`0", '')
    $stderr = ($errTask.Result -replace "`0", '')
    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        StdOut   = $stdout
        StdErr   = $stderr
        Output   = ($stdout + $stderr)
    }
}

function Invoke-DeployerStreaming {
    # Runs a program with its output shown live (or captured to the log in quiet/background mode).
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )
    Write-DeployerLog 'EXEC' ("{0} {1}" -f $FilePath, ($ArgumentList -join ' '))
    if ($script:DeployerQuiet) {
        $result = Invoke-DeployerNative -FilePath $FilePath -ArgumentList $ArgumentList
        if ($result.Output) { Write-DeployerLog 'OUT' $result.Output.TrimEnd() }
        return $result.ExitCode
    }
    # Out-Host keeps the program's output off this function's return value while still streaming it.
    & $FilePath @ArgumentList | Out-Host
    return $LASTEXITCODE
}

# ------------------------------------------------------------------------------------------------
# Secrets, .env and ACLs
# ------------------------------------------------------------------------------------------------

function New-DeployerRandomBytes {
    param([int]$Count)
    $bytes = New-Object byte[] $Count
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return , $bytes
}

function New-DeployerSecret {
    # Letters and digits only: safe inside URLs (redis://), shells and connection strings.
    param([int]$Length = 32)
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    $sb = New-Object System.Text.StringBuilder
    while ($sb.Length -lt $Length) {
        foreach ($b in (New-DeployerRandomBytes -Count ($Length * 2))) {
            # Rejection sampling keeps the distribution uniform (62 * 4 = 248).
            if ($b -lt 248 -and $sb.Length -lt $Length) {
                [void]$sb.Append($alphabet[$b % 62])
            }
        }
    }
    return $sb.ToString()
}

function New-DeployerMasterKey {
    return [Convert]::ToBase64String((New-DeployerRandomBytes -Count 32))
}

function Read-DeployerEnvFile {
    param([string]$Path)
    $values = [ordered]@{}
    if (-not (Test-Path -LiteralPath $Path)) { return $values }
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
            $values[$Matches[1]] = $Matches[2].Trim()
        }
    }
    return $values
}

function Write-DeployerTextFile {
    # UTF-8 without BOM, LF line endings.
    param([string]$Path, [string[]]$Lines)
    $text = (($Lines -join "`n").TrimEnd("`n")) + "`n"
    [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Set-DeployerEnvValues {
    <#
      Updates KEY=value pairs in place, appending keys that are missing.
      -OnlyIfMissing never touches keys that already exist (used for secrets on upgrade).
    #>
    param(
        [string]$Path,
        [System.Collections.IDictionary]$Values,
        [switch]$OnlyIfMissing
    )
    $lines = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $Path) {
        foreach ($l in [System.IO.File]::ReadAllLines($Path)) { $lines.Add($l) }
    }
    $seen = @{}
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
            $key = $Matches[1]
            if ($Values.Contains($key)) {
                $seen[$key] = $true
                if (-not $OnlyIfMissing) { $lines[$i] = "$key=$($Values[$key])" }
            }
        }
    }
    $missing = @($Values.Keys | Where-Object { -not $seen.ContainsKey($_) })
    $hadKeys = @($lines | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' }).Count -gt 0
    if ($missing.Count -gt 0) {
        if ($hadKeys) {
            $lines.Add('')
            $lines.Add("# Added by the Deployer installer on $(Get-Date -Format 'yyyy-MM-dd')")
        }
        foreach ($key in $missing) { $lines.Add("$key=$($Values[$key])") }
    }
    Write-DeployerTextFile -Path $Path -Lines $lines.ToArray()
}

function Get-DeployerUserSid {
    return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}

function Set-DeployerPrivateAcl {
    # Administrators + SYSTEM + the installing user only (for .env and backups).
    param([string]$Path, [string]$UserSid = (Get-DeployerUserSid))
    $isDir = (Get-Item -LiteralPath $Path -Force).PSIsContainer
    $inherit = if ($isDir) { '(OI)(CI)' } else { '' }
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    $r = Invoke-DeployerNative -FilePath $icacls -ArgumentList @(
        $Path, '/inheritance:r', '/grant:r',
        "*S-1-5-32-544:$($inherit)(F)", "*S-1-5-18:$($inherit)(F)", "*$($UserSid):$($inherit)(F)"
    )
    if ($r.ExitCode -ne 0) { throw "Could not restrict permissions on ${Path}: $($r.Output)" }
}

function Protect-DeployerDataDirs {
    # backups (dumps + .env copy), logs (install transcripts) and wsl (ext4.vhdx = every database) must not
    # inherit the Users:RX the install dir grants, or any local account could copy them and read them offline.
    param([string]$InstallDir, [string]$UserSid = (Get-DeployerUserSid))
    foreach ($name in @('backups', 'logs', 'wsl')) {
        $path = Join-Path $InstallDir $name
        if (Test-Path -LiteralPath $path) { Set-DeployerPrivateAcl -Path $path -UserSid $UserSid }
    }
}

function Set-DeployerInstallDirAcl {
    # Scripts here run elevated at logon, so ordinary users must not be able to modify them.
    param([string]$Path, [string]$UserSid = (Get-DeployerUserSid))
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    $r = Invoke-DeployerNative -FilePath $icacls -ArgumentList @(
        $Path, '/inheritance:r', '/grant:r',
        '*S-1-5-32-544:(OI)(CI)(F)', '*S-1-5-18:(OI)(CI)(F)',
        "*$($UserSid):(OI)(CI)(M)", '*S-1-5-32-545:(OI)(CI)(RX)'
    )
    if ($r.ExitCode -ne 0) { throw "Could not set permissions on ${Path}: $($r.Output)" }
}

# ------------------------------------------------------------------------------------------------
# State (runtime.json)
# ------------------------------------------------------------------------------------------------

function Read-DeployerState {
    param([string]$InstallDir)
    $path = Join-Path $InstallDir 'runtime.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json)
}

function Save-DeployerState {
    param([string]$InstallDir, [System.Collections.IDictionary]$State)
    $path = Join-Path $InstallDir 'runtime.json'
    Write-DeployerTextFile -Path $path -Lines @(($State | ConvertTo-Json -Depth 5))
}

function ConvertTo-DeployerStateTable {
    param($State)
    $table = [ordered]@{}
    if ($null -ne $State) {
        foreach ($p in $State.PSObject.Properties) { $table[$p.Name] = $p.Value }
    }
    return $table
}

function Get-DeployerStateValue {
    param($State, [string]$Name, $Default = $null)
    if ($null -eq $State) { return $Default }
    $prop = $State.PSObject.Properties[$Name]
    if ($null -eq $prop -or $null -eq $prop.Value) { return $Default }
    return $prop.Value
}

# ------------------------------------------------------------------------------------------------
# Hardware
# ------------------------------------------------------------------------------------------------

function Test-DeployerCpuAvx {
    if (-not ('Deployer.NativeCpu' -as [type])) {
        Add-Type -Namespace Deployer -Name NativeCpu -MemberDefinition @'
[DllImport("kernel32.dll")]
[return: MarshalAs(UnmanagedType.U1)]
public static extern bool IsProcessorFeaturePresent(uint ProcessorFeature);
'@
    }
    # 39 = PF_AVX_INSTRUCTIONS_AVAILABLE
    return [bool][Deployer.NativeCpu]::IsProcessorFeaturePresent(39)
}

# ------------------------------------------------------------------------------------------------
# WSL
# ------------------------------------------------------------------------------------------------

function Get-DeployerWslExe {
    return (Join-Path $env:SystemRoot 'System32\wsl.exe')
}

function ConvertTo-DeployerWslPath {
    # C:\ProgramData\Deployer -> /mnt/c/ProgramData/Deployer
    param([string]$WindowsPath)
    $full = [System.IO.Path]::GetFullPath($WindowsPath)
    if ($full -notmatch '^([A-Za-z]):\\?(.*)$') {
        throw "Deployer must be installed on a local drive letter path (got '$WindowsPath')."
    }
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2].TrimEnd('\') -replace '\\', '/'
    if ($rest) { return "/mnt/$drive/$rest" }
    return "/mnt/$drive"
}

function Test-DeployerWslDistro {
    param([string]$Name = $script:DeployerDistro)
    $r = Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('--list', '--quiet') -TimeoutSeconds 60
    if ($r.ExitCode -ne 0) { return $false }
    foreach ($line in ($r.StdOut -split "`r?`n")) {
        if ($line.Trim() -ieq $Name) { return $true }
    }
    return $false
}

function Get-DeployerWslVersion {
    # Returns [version] of the Store WSL package, or $null for inbox/legacy WSL.
    $r = Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('--version') -TimeoutSeconds 60
    if ($r.ExitCode -ne 0) { return $null }
    if ($r.StdOut -match '(\d+\.\d+\.\d+)') { return [version]$Matches[1] }
    return $null
}

function Get-DeployerKeepAliveProcess {
    Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "-d\s+$($script:DeployerDistro)\b" -and $_.CommandLine -match 'sleep\s+infinity' }
}

function Start-DeployerKeepAlive {
    # WSL stops idle distros; a long-running process keeps the Docker engine (and the site) up.
    param([switch]$Wait)
    $existing = @(Get-DeployerKeepAliveProcess)
    if ($existing.Count -gt 0) {
        # -Wait must block while the VM is kept alive, even by someone else's keep-alive; returning at
        # once made the sign-in task's loop run `compose up` every 15 s.
        if ($Wait) { Wait-Process -Id @($existing | ForEach-Object { $_.ProcessId }) -ErrorAction SilentlyContinue }
        return
    }
    $wslArgs = @('-d', $script:DeployerDistro, '-u', 'root', '--exec', 'sleep', 'infinity')
    if ($Wait) {
        Write-DeployerLog 'INFO' 'Keep-alive running in the foreground (scheduled task).'
        & (Get-DeployerWslExe) @wslArgs
        return
    }
    # Same reason as Register-DeployerTask: with Windows Terminal as the default terminal a hidden
    # console app can still get a visible window, so use a headless console host when available.
    $conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
    if ([Environment]::OSVersion.Version.Build -ge 18362 -and (Test-Path -LiteralPath $conhost)) {
        Start-Process -FilePath $conhost -ArgumentList (@('--headless', "`"$(Get-DeployerWslExe)`"") + $wslArgs -join ' ') -WindowStyle Hidden | Out-Null
    } else {
        Start-Process -FilePath (Get-DeployerWslExe) -ArgumentList ($wslArgs -join ' ') -WindowStyle Hidden | Out-Null
    }
}

function Invoke-DeployerKeepAliveLoop {
    # The sign-in task: keep the WSL VM (and the site) up for as long as the user is signed in. The
    # keep-alive ends whenever the VM stops (sleep/hibernate, `wsl --shutdown`, a WSL update), so bring
    # the stack back with $Restart - unless `deployer stop` ended it on purpose (the stop marker).
    param([string]$InstallDir, [scriptblock]$Restart, [int]$DelaySeconds = 15)
    $marker = Join-Path $InstallDir $script:DeployerStopMarker
    while ($true) {
        Start-DeployerKeepAlive -Wait
        Start-Sleep -Seconds $DelaySeconds
        if (Test-Path -LiteralPath $marker) {
            Write-DeployerLog 'INFO' 'The WSL keep-alive ended after "deployer stop"; not starting again until the next start or sign-in.'
            return
        }
        Write-DeployerLog 'WARN' 'The WSL keep-alive ended; starting Deployer again.'
        & $Restart
    }
}

function Stop-DeployerKeepAlive {
    foreach ($p in @(Get-DeployerKeepAliveProcess)) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { Write-Verbose "Stop keep-alive: $_" }
    }
}

function Test-DeployerWslDistroRunning {
    # Read-only: unlike `wsl -d deployer ...` this never boots the distro.
    param([string]$Name = $script:DeployerDistro)
    $r = Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('--list', '--running', '--quiet') -TimeoutSeconds 60
    if ($r.ExitCode -ne 0) { return $false }
    foreach ($line in ($r.StdOut -split "`r?`n")) {
        if ($line.Trim() -ieq $Name) { return $true }
    }
    return $false
}

function Test-DeployerMirroredEnabled {
    $cfg = Join-Path $env:USERPROFILE '.wslconfig'
    if (-not (Test-Path -LiteralPath $cfg)) { return $false }
    return ((Get-Content -LiteralPath $cfg -Raw) -match '(?im)^\s*networkingMode\s*=\s*mirrored')
}

function Write-DeployerMirroredWarning {
    # Deployer always uses WSL's default NAT networking. Mirrored networking (set by the user or
    # another tool) stops Docker Engine in WSL from publishing ports, so the site is unreachable.
    if (Test-DeployerMirroredEnabled) {
        Write-DeployerWarn 'WSL mirrored networking is on (networkingMode=mirrored in %USERPROFILE%\.wslconfig). Docker Engine in WSL cannot publish ports with it, so Deployer may be unreachable. Remove that line and run "wsl --shutdown" to go back to the default networking.'
    }
}

function Get-DeployerWslIp {
    # Prefer eth0 (the NAT address Windows can reach): `hostname -I` also lists docker0 / bridge
    # addresses and does not promise eth0 comes first. Falls back to it when `ip` is missing.
    $r = Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('-d', $script:DeployerDistro, '-u', 'root', '--exec', 'sh', '-c',
        'ip -4 -o addr show dev eth0 2>/dev/null; hostname -I') -TimeoutSeconds 60
    if ($r.ExitCode -ne 0) { return $null }
    if ($r.StdOut -match '\binet (\d+\.\d+\.\d+\.\d+)/') { return $Matches[1] }
    $first = ($r.StdOut.Trim() -split '\s+') | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1
    return $first
}

# ------------------------------------------------------------------------------------------------
# Docker / compose
# ------------------------------------------------------------------------------------------------

function Get-DeployerDockerExe {
    $cmd = Get-Command docker.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @(
            (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'))) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Get-DeployerDockerDesktopExe {
    foreach ($candidate in @(
            (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'))) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Get-DeployerDockerCommand {
    # Returns @{ File; Prefix } used to run `docker ...` for the given runtime.
    param([string]$Runtime)
    if ($Runtime -eq 'wsl-engine') {
        return @{ File = (Get-DeployerWslExe); Prefix = @('-d', $script:DeployerDistro, '-u', 'root', '--exec', 'docker') }
    }
    $docker = Get-DeployerDockerExe
    if (-not $docker) { throw 'The docker command was not found. Is Docker installed and on PATH?' }
    return @{ File = $docker; Prefix = @() }
}

function Test-DeployerDockerEngine {
    param([string]$Runtime)
    try { $cmd = Get-DeployerDockerCommand -Runtime $Runtime } catch { return $false }
    $r = Invoke-DeployerNative -FilePath $cmd.File -ArgumentList ($cmd.Prefix + @('info', '--format', '{{.ServerVersion}}')) -TimeoutSeconds 90
    return ($r.ExitCode -eq 0 -and $r.StdOut.Trim() -match '^\d')
}

function Test-DeployerComposePlugin {
    param([string]$Runtime)
    try { $cmd = Get-DeployerDockerCommand -Runtime $Runtime } catch { return $false }
    $r = Invoke-DeployerNative -FilePath $cmd.File -ArgumentList ($cmd.Prefix + @('compose', 'version')) -TimeoutSeconds 60
    return ($r.ExitCode -eq 0)
}

function Start-DeployerDockerDesktop {
    $exe = Get-DeployerDockerDesktopExe
    if (-not $exe) { return $false }
    if (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue) { return $true }
    # Launch through explorer.exe so Docker Desktop runs un-elevated even if we are elevated.
    Start-Process -FilePath (Join-Path $env:SystemRoot 'explorer.exe') -ArgumentList ('"{0}"' -f $exe) | Out-Null
    return $true
}

function Test-DeployerDockerDesktopCrashedSince {
    # True when Docker Desktop's backend reported a crash after $Since: it writes backend.error.json
    # and a "backend crashed" line (prefixed with an ISO-8601 UTC timestamp) to its host log.
    param([datetime]$Since)
    $sinceUtc = $Since.ToUniversalTime()
    $errFile = Join-Path $env:LOCALAPPDATA 'Docker\backend.error.json'
    if ((Test-Path -LiteralPath $errFile) -and ((Get-Item -LiteralPath $errFile).LastWriteTimeUtc -gt $sinceUtc)) { return $true }
    # Docker rotates this log at 1 MB, so the newest rotated file is checked too: a crash can be the
    # last thing written before a rotation.
    $logDir = Join-Path $env:LOCALAPPDATA 'Docker\log\host'
    $log = Join-Path $logDir 'com.docker.backend.exe.log'
    if (-not (Test-Path -LiteralPath $log)) { return $false }
    $rotated = Get-ChildItem -LiteralPath $logDir -Filter 'com.docker.backend.exe.log.*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    # The error dialog logs a poll line every few seconds after a crash, so look a few thousand lines back.
    $tails = @(Get-Content -LiteralPath $log -Tail 3000 -ErrorAction SilentlyContinue)
    if ($rotated) { $tails = @(Get-Content -LiteralPath $rotated.FullName -Tail 3000 -ErrorAction SilentlyContinue) + $tails }
    foreach ($line in $tails) {
        if ($line -notmatch 'backend crashed') { continue }
        if ($line -match '^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})') {
            try {
                $at = [datetime]::ParseExact($Matches[1], 'yyyy-MM-ddTHH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture,
                    ([System.Globalization.DateTimeStyles]::AssumeUniversal -bor [System.Globalization.DateTimeStyles]::AdjustToUniversal))
                if ($at -gt $sinceUtc) { return $true }
            } catch {
                Write-Verbose "Unparseable Docker log timestamp: $line"
            }
        }
    }
    return $false
}

function Repair-DeployerDockerDesktop {
    <#
      Recovers Docker Desktop from the crash it hits after an unclean stop (PC restart, standby, a
      killed process): "initializing Secrets Engine / Inference manager: listening on unix://...:
      remove ...: The file cannot be accessed by the system". Docker cannot delete those leftover
      socket files itself, so they are moved aside (never deleted) and Docker Desktop is started
      again. Returns $true when a restart was attempted.
    #>
    if (-not (Get-DeployerDockerDesktopExe)) { return $false }
    Write-DeployerWarn 'Docker Desktop crashed while starting (leftover socket files from an unclean stop). Repairing and starting it again...'
    Get-Process | Where-Object { $_.ProcessName -in @('Docker Desktop', 'com.docker.backend', 'com.docker.build', 'com.docker.dev-envs') } |
        Stop-Process -Force -Confirm:$false -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline -and (Get-Process -Name 'Docker Desktop', 'com.docker.backend' -ErrorAction SilentlyContinue)) { Start-Sleep -Seconds 2 }
    $stamp = Get-Date -Format 'yyyyMMddHHmmss'
    foreach ($dir in @((Join-Path $env:LOCALAPPDATA 'Docker\run'), (Join-Path $env:LOCALAPPDATA 'docker-secrets-engine'))) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        try {
            Rename-Item -LiteralPath $dir -NewName ((Split-Path -Leaf $dir) + ".stale-$stamp") -ErrorAction Stop
            Write-DeployerLog 'DOCKER' "moved $dir aside as .stale-$stamp"
        } catch {
            Write-DeployerWarn "Could not move $dir aside: $($_.Exception.Message)"
        }
    }
    # Only Docker's own distributions are restarted; the user's other WSL distributions are untouched.
    foreach ($distro in @('docker-desktop', 'docker-desktop-data')) {
        [void](Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('--terminate', $distro) -TimeoutSeconds 60)
    }
    Start-Sleep -Seconds 3
    [void](Start-DeployerDockerDesktop)
    return $true
}

function Wait-DeployerDockerEngine {
    # Waits for `docker info` to work. For Docker Desktop (runtimes docker-desktop and existing) it
    # starts the app when needed, repairs it once if it crashes on start, and, for an already
    # installed Docker that stays unresponsive, restarts it once.
    param([string]$Runtime, [int]$TimeoutSeconds = 180, [string]$WaitingMessage = 'Waiting for the Docker engine')
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $nudged = $false
    $nudgedAt = $null
    $repaired = $false
    $announced = $false
    $started = Get-Date
    $desktop = ($Runtime -eq 'docker-desktop' -or $Runtime -eq 'existing')
    while ((Get-Date) -lt $deadline) {
        if (Test-DeployerDockerEngine -Runtime $Runtime) { return $true }
        if (-not $announced) {
            Write-DeployerInfo "$WaitingMessage (up to $([int]($TimeoutSeconds / 60)) min)..."
            $announced = $true
        }
        if ($desktop -and -not $nudged) {
            [void](Start-DeployerDockerDesktop)
            $nudged = $true
            $nudgedAt = Get-Date
        } elseif ($desktop -and $nudged -and -not $repaired) {
            $crashed = Test-DeployerDockerDesktopCrashedSince -Since $nudgedAt
            $stuck = ($Runtime -eq 'existing' -and ((Get-Date) - $nudgedAt).TotalSeconds -gt 240)
            if ($crashed -or $stuck) {
                if ($stuck -and -not $crashed) { Write-DeployerWarn 'Docker Desktop is not responding; restarting it...' }
                $repaired = $true
                [void](Repair-DeployerDockerDesktop)
                $nudgedAt = Get-Date
            }
        } elseif ($desktop -and $repaired -and (Test-DeployerDockerDesktopCrashedSince -Since $nudgedAt)) {
            # Crashed again right after the repair: Windows itself can no longer create Docker's socket
            # files ("The file cannot be accessed by the system"), which happens after sleep/wake. Only a
            # Windows restart clears it, so stop waiting and say so.
            $script:DeployerDockerNeedsWindowsRestart = $true
            Write-DeployerMarker 'docker-needs-windows-restart'
            Write-DeployerWarn 'Docker Desktop crashed again after the repair. Windows must be restarted before Docker Desktop can start'
            Write-DeployerWarn '(a Windows issue with Docker''s socket files after sleep). The free Docker Engine runtime (setup: "Free Docker Engine") does not have this problem.'
            return $false
        }
        if ($Runtime -eq 'wsl-engine' -and -not $nudged -and ((Get-Date) - $started).TotalSeconds -gt 30) {
            # Older WSL without systemd support: start the service by hand.
            [void](Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @(
                    '-d', $script:DeployerDistro, '-u', 'root', '--exec', 'sh', '-c',
                    'systemctl start docker 2>/dev/null || service docker start') -TimeoutSeconds 120)
            $nudged = $true
        }
        Start-Sleep -Seconds 5
    }
    return $false
}

function Get-DeployerComposeInvocation {
    param([string]$InstallDir, [string]$Runtime, [string[]]$Arguments = @())
    if ($Runtime -eq 'wsl-engine') {
        $dir = ConvertTo-DeployerWslPath $InstallDir
        return @{
            File = (Get-DeployerWslExe)
            Args = @('-d', $script:DeployerDistro, '-u', 'root', '--cd', $dir, '--exec', 'docker', 'compose',
                '--project-directory', $dir, '-f', "$dir/docker-compose.yml") + $Arguments
        }
    }
    $docker = Get-DeployerDockerExe
    if (-not $docker) { throw 'The docker command was not found. Is Docker installed and on PATH?' }
    return @{
        File = $docker
        Args = @('compose', '--project-directory', $InstallDir, '-f', (Join-Path $InstallDir 'docker-compose.yml')) + $Arguments
    }
}

function Invoke-DeployerCompose {
    # Streams output; returns the exit code.
    param([string]$InstallDir, [string]$Runtime, [string[]]$Arguments = @())
    $inv = Get-DeployerComposeInvocation -InstallDir $InstallDir -Runtime $Runtime -Arguments $Arguments
    return (Invoke-DeployerStreaming -FilePath $inv.File -ArgumentList $inv.Args)
}

function Invoke-DeployerComposeCapture {
    param([string]$InstallDir, [string]$Runtime, [string[]]$Arguments = @(), [int]$TimeoutSeconds = 0, [string]$StdinText = '')
    $inv = Get-DeployerComposeInvocation -InstallDir $InstallDir -Runtime $Runtime -Arguments $Arguments
    return (Invoke-DeployerNative -FilePath $inv.File -ArgumentList $inv.Args -TimeoutSeconds $TimeoutSeconds -StdinText $StdinText)
}

function ConvertTo-DeployerRuntimePath {
    # Path as seen by the docker CLI for this runtime.
    param([string]$Runtime, [string]$WindowsPath)
    if ($Runtime -eq 'wsl-engine') { return (ConvertTo-DeployerWslPath $WindowsPath) }
    return $WindowsPath
}

function Assert-DeployerRestoreFolder {
    # Refuses a folder that is not a backup, or one whose secrets this install's MASTER_KEY cannot read.
    param([string]$InstallDir, [string]$Folder, [switch]$Force)
    if (-not (Test-Path -LiteralPath (Join-Path $Folder 'mariadb.sql') -PathType Leaf)) {
        throw "$Folder is not a Deployer backup folder (mariadb.sql is missing)."
    }
    $backupEnv = Join-Path $Folder 'env.backup'
    if (Test-Path -LiteralPath $backupEnv) {
        $oldEnv = Read-DeployerEnvFile -Path $backupEnv
        $nowEnv = Read-DeployerEnvFile -Path (Join-Path $InstallDir '.env')
        # The dumps carry the database accounts (mysql.global_priv, admin.system.users), so a backup from
        # another install would replace the passwords Deployer signs in with. -Force does not skip this.
        $accounts = @('MARIADB_USER', 'MARIADB_PASSWORD', 'MARIADB_ROOT_PASSWORD', 'MONGO_ROOT_USERNAME', 'MONGO_ROOT_PASSWORD') |
            Where-Object { $oldEnv[$_] -and [string]$oldEnv[$_] -cne [string]$nowEnv[$_] }
        if ($accounts) {
            throw "This backup comes from another install: its $($accounts -join ', ') differ from $InstallDir\.env. Loading it would replace the database accounts Deployer signs in with and lock it out of its own databases, so a backup only goes back onto the install that made it. To move to another PC, use the encrypted export in the dashboard (Instance settings > Export)."
        }
        $old = [string]$oldEnv['MASTER_KEY']
        $now = [string]$nowEnv['MASTER_KEY']
        if ($old -and $old -cne $now -and -not $Force) {
            throw "This backup was taken with a different MASTER_KEY, so the secrets in it could not be decrypted. Copy the MASTER_KEY line from $backupEnv into $InstallDir\.env and run 'deployer restart' first, or add -Force to restore anyway."
        }
    }
}

function Invoke-DeployerRestore {
    # Loads a 'deployer backup' folder into the running stack (audit A-068). The sh -c scripts hold no
    # double quotes (Windows PowerShell 5.1 does not escape them for native programs) and read the
    # passwords inside the container; they are letters and digits (New-DeployerSecret), so unquoted is safe.
    param([string]$InstallDir, [string]$Runtime, [string]$Folder, [bool]$Mongo, [switch]$Force)
    Assert-DeployerRestoreFolder -InstallDir $InstallDir -Folder $Folder -Force:$Force
    $runtimeDir = ConvertTo-DeployerRuntimePath -Runtime $Runtime -WindowsPath $Folder

    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('cp', "$runtimeDir/mariadb.sql", 'mariadb:/tmp/deployer-restore.sql')
    if ($code -ne 0) { throw "Copying mariadb.sql into the container failed (exit code $code). Is the stack running?" }
    $load = 'export MYSQL_PWD=$MARIADB_ROOT_PASSWORD; mariadb -uroot < /tmp/deployer-restore.sql && mariadb-admin -uroot flush-privileges; rc=$?; rm -f /tmp/deployer-restore.sql; exit $rc'
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('exec', '-T', 'mariadb', 'sh', '-c', $load)
    if ($code -ne 0) { throw "Loading mariadb.sql failed (exit code $code)." }
    Write-DeployerOk 'MariaDB restored from mariadb.sql'

    $archive = Join-Path $Folder 'mongodb.archive.gz'
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { return }
    if (-not $Mongo) {
        Write-DeployerWarn 'The backup has mongodb.archive.gz but managed MongoDB is disabled here; skipped.'
        return
    }
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('cp', "$runtimeDir/mongodb.archive.gz", 'mongodb:/tmp/deployer-restore.archive.gz')
    if ($code -ne 0) { throw "Copying mongodb.archive.gz into the container failed (exit code $code)." }
    $load = 'mongorestore --quiet --drop --gzip --archive=/tmp/deployer-restore.archive.gz --username=$MONGO_INITDB_ROOT_USERNAME --password=$MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase=admin; rc=$?; rm -f /tmp/deployer-restore.archive.gz; exit $rc'
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('exec', '-T', 'mongodb', 'sh', '-c', $load)
    if ($code -ne 0) { throw "mongorestore failed (exit code $code)." }
    Write-DeployerOk 'MongoDB restored from mongodb.archive.gz'
}

function Get-DeployerHealth {
    # The /v1/health body when the API answers 200. -AnyStatus also returns the 503 "degraded" body
    # (the API is up but MariaDB or Redis is not), so "deployer status" can say which one.
    param([int]$Port, [switch]$AnyStatus)
    foreach ($hostName in @('127.0.0.1', 'localhost')) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://${hostName}:$Port/v1/health" -TimeoutSec 5
            if ($resp.StatusCode -eq 200) { return $resp.Content }
        } catch {
            if ($AnyStatus -and $_.ErrorDetails -and $_.ErrorDetails.Message -match '"services"') { return $_.ErrorDetails.Message }
            Write-Verbose "Health check via ${hostName}: $_"
        }
    }
    return $null
}

function Write-DeployerHealth {
    # One line per service instead of the raw /v1/health JSON.
    param([string]$Body)
    $h = $null
    try { $h = $Body | ConvertFrom-Json } catch { Write-Verbose "Health body is not JSON: $_" }
    if (-not $h -or -not $h.services) { Write-DeployerInfo "Health: $Body"; return }
    $line = "Health: $($h.status) (version $($h.version))"
    if ($h.status -eq 'ok') { Write-DeployerOk $line } else { Write-DeployerWarn $line }
    foreach ($svc in $h.services.PSObject.Properties) {
        $state = if ($null -eq $svc.Value) { 'switched off (this CPU has no AVX)' } elseif ($svc.Value) { 'up' } else { 'DOWN' }
        Write-DeployerInfo ('  {0,-8}: {1}' -f $svc.Name, $state)
    }
}

function Wait-DeployerHealth {
    param([int]$Port, [int]$TimeoutSeconds = 300)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $body = Get-DeployerHealth -Port $Port
        if ($body) { return $body }
        Start-Sleep -Seconds 5
    }
    return $null
}

function Get-DeployerComposeServices {
    <#
      Returns one object per container of the stack: Service, State (running/exited/...), Health
      (healthy/unhealthy/starting or empty) and Status text. Handles both the JSON array printed by
      older Compose v2 releases and the one-object-per-line output of newer ones.
    #>
    param([string]$InstallDir, [string]$Runtime)
    $r = Invoke-DeployerComposeCapture -InstallDir $InstallDir -Runtime $Runtime -Arguments @('ps', '--all', '--format', 'json') -TimeoutSeconds 90
    if ($r.ExitCode -ne 0) { return @() }
    $text = $r.StdOut.Trim()
    if (-not $text) { return @() }
    $items = @()
    if ($text.StartsWith('[')) {
        $items = @($text | ConvertFrom-Json)
    } else {
        foreach ($line in ($text -split "`r?`n")) {
            if ($line.Trim().StartsWith('{')) { $items += ($line | ConvertFrom-Json) }
        }
    }
    foreach ($i in $items) {
        [pscustomobject]@{
            Service = [string]$i.Service
            State   = [string]$i.State
            Health  = [string]$i.Health
            Status  = [string]$i.Status
        }
    }
}

function Show-DeployerDiagnostics {
    param([string]$InstallDir, [string]$Runtime)
    Write-DeployerWarn 'Container status:'
    $ps = Invoke-DeployerComposeCapture -InstallDir $InstallDir -Runtime $Runtime -Arguments @('ps', '--all') -TimeoutSeconds 120
    Write-Host $ps.Output
    # mongodb is behind a compose profile: naming it here fails on installs without AVX.
    Write-DeployerWarn 'Last log lines (api, worker, caddy, mariadb, redis):'
    $logs = Invoke-DeployerComposeCapture -InstallDir $InstallDir -Runtime $Runtime -Arguments @('logs', '--no-color', '--tail', '40', 'api', 'worker', 'caddy', 'mariadb', 'redis') -TimeoutSeconds 120
    Write-Host $logs.Output
    Write-DeployerLog 'DIAG' ($ps.Output + "`n" + $logs.Output)
}

function Invoke-DeployerImages {
    # Pulls published images; falls back to building from ./src when they are unavailable.
    param([string]$InstallDir, [string]$Runtime, [switch]$FromSource)
    if (-not $FromSource) {
        Write-DeployerInfo 'Downloading container images...'
        $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('pull')
        if ($code -eq 0) { return 'pulled' }
        Write-DeployerWarn 'Prebuilt Deployer images could not be pulled (not published for this version yet, private, or offline).'
        Write-DeployerWarn 'Building them locally instead. This can take 10-30 minutes on an older PC.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir 'src\api'))) {
        throw 'Source code for building the images is missing (src\api). Re-run the installer or update with network access.'
    }
    [void](Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('pull', '--ignore-buildable'))
    # --progress=plain: BuildKit's interactive (TTY) progress exits 1 at once when stderr is a Windows
    # console relayed by wsl.exe (seen with `deployer update` in an elevated window); plain output also
    # reads better in the log file.
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('build', '--progress=plain')
    if ($code -ne 0) { throw "Building the Deployer images failed (exit code $code)." }
    return 'built'
}

function Update-DeployerMongo {
    # A-143: MongoDB only opens data from its own major or the one before, and installs made before
    # 8.0 have 5.0 data. Before `up`, with the managed MongoDB stopped, deploy/mongodb/upgrade.sh runs
    # in one-off containers: first with the compose image (nothing to do for new or current data,
    # 8.0 is one step away from 7.0), else 6.0 -> 7.0 -> 8.0. Each step is a no-op once done, so an
    # interrupted upgrade resumes where it stopped. docs/BACKUPS.md "MongoDB versions".
    param([string]$InstallDir, [string]$Runtime)
    # V-07: a version from before A-143 runs mongo:5.0 and has no upgrade steps; nothing to do.
    if (-not (Test-DeployerComposeMongoImage -Path (Join-Path $InstallDir 'docker-compose.yml'))) { return }
    [void](Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('stop', '-t', '60', 'mongodb'))
    $steps = @('8')
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('--profile', 'mongodb-upgrade', 'run', '--rm', '-T', 'mongodb-upgrade-8')
    if ($code -eq 3) {
        Write-DeployerInfo 'Upgrading the managed MongoDB data from 5.0 to 8.0, one version at a time (downloads MongoDB 6.0 and 7.0 once)...'
        foreach ($major in '6', '7', '8') {
            $steps += $major
            $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $Runtime -Arguments @('--profile', 'mongodb-upgrade', 'run', '--rm', '-T', "mongodb-upgrade-$major")
            if ($code -ne 0) { break }
        }
    }
    if ($code -ne 0) {
        throw "Upgrading the managed MongoDB data failed at step mongodb-upgrade-$($steps[-1]) (exit code $code). Its data is unchanged since the last finished step; run the update again, or see docs/BACKUPS.md `"MongoDB versions`"."
    }
    # Only now may compose start 8.0 on this data (its fallback without the key is 5.0, which is what
    # the previous `deployer` script, running the first update to this version, leaves in place).
    Set-DeployerEnvValues -Path (Join-Path $InstallDir '.env') -Values ([ordered]@{ MONGODB_IMAGE = 'mongo:8.0' })
    Write-DeployerOk 'Managed MongoDB data is ready for MongoDB 8.0'
}

function Test-DeployerComposeMongoImage {
    # Whether a compose file starts MongoDB from ${MONGODB_IMAGE} (A-143 and later). Older versions
    # hardcode mongo:5.0, which cannot open data that is on 8.0.
    param([string]$Path)
    return ((Test-Path -LiteralPath $Path) -and ([System.IO.File]::ReadAllText($Path) -match '\$\{MONGODB_IMAGE'))
}

function Assert-DeployerMongoRef {
    # V-07: once .env runs MONGODB_IMAGE (new installs, or Update-DeployerMongo after the upgrade) the
    # managed MongoDB data is on 8.0, so refuse a version from before A-143 before any file is replaced.
    param([string]$InstallDir, [string]$SourceRoot, [string]$Ref)
    if (-not (Read-DeployerEnvFile -Path (Join-Path $InstallDir '.env'))['MONGODB_IMAGE']) { return }
    if (Test-DeployerComposeMongoImage -Path (Join-Path $SourceRoot 'deploy\docker-compose.yml')) { return }
    throw "Deployer '$Ref' runs MongoDB 5.0, but the managed MongoDB data on this PC is already on MongoDB 8.0, which 5.0 cannot open. Nothing was changed. To stay on a current version run 'deployer update' without -Ref; going back to '$Ref' means starting its MongoDB on empty data and restoring a backup, see docs/BACKUPS.md `"MongoDB versions`"."
}

# ------------------------------------------------------------------------------------------------
# Downloads and files
# ------------------------------------------------------------------------------------------------

function Invoke-DeployerDownload {
    param([string]$Uri, [string]$OutFile)
    $dir = Split-Path -Parent $OutFile
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $partial = "$OutFile.partial"
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    if (Test-Path -LiteralPath $curl) {
        $curlArgs = @('-fL', '--retry', '3', '--retry-delay', '3', '--connect-timeout', '30', '-o', $partial, $Uri)
        if ($script:DeployerQuiet) { $curlArgs = @('-sS') + $curlArgs } else { $curlArgs = @('-#') + $curlArgs }
        $code = Invoke-DeployerStreaming -FilePath $curl -ArgumentList $curlArgs
        if ($code -ne 0) {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            throw "Download failed ($Uri), curl exit code $code."
        }
    } else {
        $old = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $partial
        } finally {
            $ProgressPreference = $old
        }
    }
    Move-Item -LiteralPath $partial -Destination $OutFile -Force
}

function Get-DeployerWebText {
    param([string]$Uri)
    $resp = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 60 -Headers @{ 'User-Agent' = 'deployer-installer' }
    if ($resp.Content -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($resp.Content) }
    return [string]$resp.Content
}

function Resolve-DeployerRef {
    # An explicit ref wins; otherwise the latest GitHub release; otherwise main.
    param([string]$Repo, [string]$Ref)
    if ($Ref) { return $Ref }
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -TimeoutSec 30 -Headers @{ 'User-Agent' = 'deployer-installer' }
        if ($release.tag_name) { return [string]$release.tag_name }
    } catch {
        Write-Verbose "No published release: $_"
    }
    return 'main'
}

function Get-DeployerImageVersion {
    param([string]$Ref)
    if ($Ref -match '^v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)$') { return $Matches[1] }
    return 'latest'
}

function Set-DeployerDisplayVersion {
    <#
      Sets the version Apps & Features shows for Deployer, so it follows 'deployer update' (A-074).
      Returns $false when there is no entry (installed with install.ps1 alone) or the ref is not a version.
    #>
    param([string]$Ref, [Microsoft.Win32.RegistryHive]$Hive = 'LocalMachine',
        [string]$KeyPath = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Deployer')
    $version = Get-DeployerImageVersion -Ref $Ref
    if ($version -eq 'latest') { return $false }
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($Hive, [Microsoft.Win32.RegistryView]::Registry64)
    try {
        $key = $base.OpenSubKey($KeyPath, $true)
        if ($null -eq $key) { return $false }
        try { $key.SetValue('DisplayVersion', $version) } finally { $key.Dispose() }
        return $true
    } finally {
        $base.Dispose()
    }
}

function Get-DeployerUpdateRecoveryHint {
    <#
      Next steps after 'deployer update' fails once the new files are in place (A-150): how to see why,
      how to go back to the version that was running, and the backup to restore if the new version
      already migrated the database. -MongoNewer: the update moved the managed MongoDB data to 8.0
      and the previous version still runs 5.0, so going back is not one command (V-07).
    #>
    param([string]$PreviousRef, [string]$BackupName, [switch]$MongoNewer)
    $back = if ($PreviousRef) { $PreviousRef } else { '<the version you had>' }
    $lines = @('To see why: deployer logs api')
    $lines += if ($MongoNewer) {
        "To retry: deployer update. The managed MongoDB data is now on MongoDB 8.0, which $back (MongoDB 5.0) cannot open; going back to it takes the steps in docs/BACKUPS.md `"MongoDB versions`"."
    } else {
        "To go back to the previous version: deployer update -Ref $back"
    }
    $lines += if ($BackupName) {
        "If it still fails, the new version may have migrated the database: after going back, run deployer restore $BackupName"
    } else {
        'No backup was taken before this update, so a database the new version already migrated cannot be put back.'
    }
    return ($lines -join "`n")
}

function Get-DeployerSource {
    <#
      Downloads https://github.com/<Repo>/archive/<Ref>.zip (falls back to the release asset
      deployer-deploy.zip) and returns the extracted root that contains deploy\ and installer\.
    #>
    param([string]$Repo, [string]$Ref, [string]$WorkDir)
    if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
    New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
    # A-151: a failed download or extract leaves no half-filled folder in %TEMP%; on success the
    # caller removes WorkDir once the files are copied.
    try {
        $zip = Join-Path $WorkDir 'source.zip'
        $sources = @(
            "https://github.com/$Repo/archive/$Ref.zip",
            "https://github.com/$Repo/releases/download/$Ref/deployer-deploy.zip"
        )
        # A version tag that was never published (e.g. a locally built setup exe before the first release)
        # falls back to the main branch instead of failing the whole install.
        if ($Ref -ne 'main') { $sources += "https://github.com/$Repo/archive/main.zip" }
        $downloaded = $false
        foreach ($uri in $sources) {
            try {
                if ($uri -like '*/archive/main.zip' -and $Ref -ne 'main') {
                    Write-DeployerWarn "'$Ref' is not published on github.com/$Repo; using the main branch instead."
                }
                Write-DeployerInfo "Downloading $uri"
                Invoke-DeployerDownload -Uri $uri -OutFile $zip
                $downloaded = $true
                break
            } catch {
                Write-DeployerWarn "$_"
            }
        }
        if (-not $downloaded) {
            throw "Could not download Deployer '$Ref' from github.com/$Repo. Check the -Repo/-Ref values and your internet connection."
        }
        $extract = Join-Path $WorkDir 'x'
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $candidates = @($extract) + @(Get-ChildItem -LiteralPath $extract -Directory | ForEach-Object { $_.FullName })
        foreach ($c in $candidates) {
            if (Test-Path -LiteralPath (Join-Path $c 'deploy\docker-compose.yml')) { return $c }
        }
        throw "The downloaded archive does not contain deploy\docker-compose.yml."
    } catch {
        Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

function Invoke-DeployerRobocopy {
    param([string]$Source, [string]$Destination, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @(), [switch]$Mirror)
    $robocopy = Join-Path $env:SystemRoot 'System32\robocopy.exe'
    $rcArgs = @($Source, $Destination)
    if ($Mirror) { $rcArgs += '/MIR' } else { $rcArgs += '/E' }
    $rcArgs += @('/R:2', '/W:2', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    if ($ExcludeDirs.Count -gt 0) { $rcArgs += @('/XD') + $ExcludeDirs }
    if ($ExcludeFiles.Count -gt 0) { $rcArgs += @('/XF') + $ExcludeFiles }
    $r = Invoke-DeployerNative -FilePath $robocopy -ArgumentList $rcArgs
    # Robocopy: 0-7 = success variants, 8+ = failure.
    if ($r.ExitCode -ge 8) { throw "Copying $Source to $Destination failed: $($r.Output)" }
}

function Copy-DeployerFiles {
    <#
      Installs deploy files, management scripts and buildable source into InstallDir.
      Never touches .env, runtime.json, backups, logs or the WSL disk.
    #>
    param([string]$SourceRoot, [string]$InstallDir)
    $deploy = Join-Path $SourceRoot 'deploy'
    Get-ChildItem -LiteralPath $deploy -Force | Where-Object { $_.Name -ne '.env' } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $InstallDir -Recurse -Force
    }
    $installerSrc = Join-Path $SourceRoot 'installer'
    if (Test-Path -LiteralPath $installerSrc) {
        Invoke-DeployerRobocopy -Source $installerSrc -Destination (Join-Path $InstallDir 'installer') -Mirror
        # bash refuses CRLF scripts; normalise in case a checkout converted line endings.
        Get-ChildItem -LiteralPath (Join-Path $InstallDir 'installer') -Recurse -Filter '*.sh' | ForEach-Object {
            $text = [System.IO.File]::ReadAllText($_.FullName) -replace "`r`n", "`n"
            [System.IO.File]::WriteAllText($_.FullName, $text, (New-Object System.Text.UTF8Encoding($false)))
        }
    }
    $caddy = Join-Path $InstallDir 'Caddyfile'
    if (Test-Path -LiteralPath $caddy) {
        $text = [System.IO.File]::ReadAllText($caddy) -replace "`r`n", "`n"
        [System.IO.File]::WriteAllText($caddy, $text, (New-Object System.Text.UTF8Encoding($false)))
    }
    $excludeDirs = @('node_modules', '.venv', 'venv', 'dist', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache')
    # deploy\ is a build context too (e.g. deploy\tunnel for the tunnel sidecar).
    foreach ($component in @('api', 'dashboard', 'deploy')) {
        $from = Join-Path $SourceRoot $component
        $to = Join-Path $InstallDir "src\$component"
        if (Test-Path -LiteralPath $from) {
            Invoke-DeployerRobocopy -Source $from -Destination $to -ExcludeDirs $excludeDirs -ExcludeFiles @('.env') -Mirror
        }
    }
    $cmdShim = @(
        '@echo off',
        'rem Deployer management CLI - see "deployer help"',
        '"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\deployer.ps1" %*'
    )
    [System.IO.File]::WriteAllText((Join-Path $InstallDir 'deployer.cmd'), (($cmdShim -join "`r`n") + "`r`n"), (New-Object System.Text.ASCIIEncoding))
}

function Initialize-DeployerEnv {
    <#
      Creates or upgrades .env. Secrets are generated only for keys that do not exist yet, so an
      upgrade never rotates passwords that the databases already use.
    #>
    param(
        [string]$InstallDir,
        [int]$Port,
        [bool]$MongoEnabled,
        [string]$ImagePrefix,
        [string]$Version,
        [string]$Bind,
        [switch]$SetPort
    )
    $path = Join-Path $InstallDir '.env'
    $isNew = -not (Test-Path -LiteralPath $path)
    $existing = Read-DeployerEnvFile -Path $path

    if ($isNew) {
        $header = @(
            '# Deployer configuration - generated on this computer by the installer.',
            "# Created $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'). Every secret below is random and local to this install.",
            '# Keep a copy of this file (especially MASTER_KEY) with your backups. See .env.example for documentation.',
            ''
        )
        Write-DeployerTextFile -Path $path -Lines $header
    }

    $secrets = [ordered]@{
        PUBLIC_URL            = "http://localhost:$Port"
        DEPLOYER_HTTP_PORT    = "$Port"
        MARIADB_DATABASE      = 'deployer'
        MARIADB_USER          = 'deployer'
        MARIADB_PASSWORD      = (New-DeployerSecret -Length 32)
        MARIADB_ROOT_PASSWORD = (New-DeployerSecret -Length 32)
        MONGO_ROOT_USERNAME   = 'admin'
        MONGO_ROOT_PASSWORD   = (New-DeployerSecret -Length 32)
        REDIS_PASSWORD        = (New-DeployerSecret -Length 32)
        JWT_SECRET            = (New-DeployerSecret -Length 64)
        MASTER_KEY            = (New-DeployerMasterKey)
        GOOGLE_CLIENT_ID      = ''
        GOOGLE_CLIENT_SECRET  = ''
        GITHUB_CLIENT_ID      = ''
        GITHUB_CLIENT_SECRET  = ''
        ALLOW_SIGNUP          = 'false'
    }
    $managed = [ordered]@{
        DEPLOYER_BIND           = $Bind
        # Named in the disk-low alert: the drive the WSL disk grows on (docs/MONITORING.md).
        DEPLOYER_HOST_DRIVE     = ([System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($InstallDir))).TrimEnd('\')
        DEPLOYER_IMAGE_PREFIX   = $ImagePrefix
        DEPLOYER_VERSION        = $Version
        DEPLOYER_SOURCE_DIR     = './src'
        COMPOSE_PROFILES        = $(if ($MongoEnabled) { 'mongodb' } else { '' })
        MANAGED_MONGODB_ENABLED = $(if ($MongoEnabled) { 'true' } else { 'false' })
    }
    if ($SetPort -and -not $isNew) {
        $managed['DEPLOYER_HTTP_PORT'] = "$Port"
        $oldUrl = [string]$existing['PUBLIC_URL']
        if (-not $oldUrl -or $oldUrl -match '^http://(localhost|127\.0\.0\.1)(:\d+)?/?$') {
            $managed['PUBLIC_URL'] = "http://localhost:$Port"
        }
    }
    if ($isNew) {
        foreach ($key in $managed.Keys) { $secrets[$key] = $managed[$key] }
        # A new install has no MongoDB 5.0 data. An existing .env gets this key from Update-DeployerMongo
        # only once its data is upgraded; until then compose keeps mongo:5.0 (A-143). A version from
        # before A-143 (install.ps1 -Ref) hardcodes mongo:5.0 and creates 5.0 data, so the key would
        # wrongly say the data is on 8.0 (V-07).
        if (Test-DeployerComposeMongoImage -Path (Join-Path $InstallDir 'docker-compose.yml')) { $secrets['MONGODB_IMAGE'] = 'mongo:8.0' }
        Set-DeployerEnvValues -Path $path -Values $secrets
    } else {
        Set-DeployerEnvValues -Path $path -Values $secrets -OnlyIfMissing
        Set-DeployerEnvValues -Path $path -Values $managed
    }
    Set-DeployerPrivateAcl -Path $path
    return $isNew
}

function Get-DeployerImagePrefix {
    param([string]$Repo)
    $owner = ($Repo -split '/')[0].ToLowerInvariant()
    return "ghcr.io/$owner/deployer"
}

# ------------------------------------------------------------------------------------------------
# Networking (LAN access)
# ------------------------------------------------------------------------------------------------

function Get-DeployerLanAddresses {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and
            $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback|docker' -and
            $_.AddressState -eq 'Preferred'
        } |
        Select-Object -ExpandProperty IPAddress
}

function Get-DeployerLanUrls {
    # The addresses other devices type to open Deployer (A-075).
    param([int]$Port)
    @(Get-DeployerLanAddresses | ForEach-Object { "http://${_}:$Port" })
}

# Deployed apps are served by Caddy on one port each from this range (docs/DEPLOYMENTS.md); LAN
# access forwards and opens it together with the dashboard port.
$script:DeployerAppPortFirst = 8100
$script:DeployerAppPortLast = 8199

# Processes that hold Deployer's own published ports (WSL relay, Docker, netsh portproxy).
$script:DeployerOwnPortProcesses = '^(wslrelay|com\.docker\.backend|docker-proxy|vpnkit|svchost)$'

function Test-DeployerAppPort {
    # Caddy publishes the whole app range, so the dashboard port must stay outside it (A-064).
    param([int]$Port)
    return $Port -ge $script:DeployerAppPortFirst -and $Port -le $script:DeployerAppPortLast
}

function Get-DeployerAppPortUsers {
    # "port (program)" for every listener in the app range; -SkipOwn leaves out Deployer's own.
    param([switch]$SkipOwn)
    @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { Test-DeployerAppPort $_.LocalPort } |
            ForEach-Object { [pscustomobject]@{ Port = [int]$_.LocalPort; Name = [string](Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } } |
            Where-Object { -not ($SkipOwn -and $_.Name -match $script:DeployerOwnPortProcesses) } |
            ForEach-Object { "$($_.Port) ($($_.Name))" } | Sort-Object -Unique)
}

function Get-DeployerLanPorts {
    # The dashboard port plus the app port range.
    param([int]$Port)
    return @($Port) + @($script:DeployerAppPortFirst..$script:DeployerAppPortLast)
}

function Remove-DeployerPortProxy {
    param([int]$Port)
    $ports = @{}
    foreach ($p in (Get-DeployerLanPorts -Port $Port)) { $ports[[int]$p] = $true }
    $netsh = Join-Path $env:SystemRoot 'System32\netsh.exe'
    $show = Invoke-DeployerNative -FilePath $netsh -ArgumentList @('interface', 'portproxy', 'show', 'v4tov4')
    foreach ($line in ($show.StdOut -split "`r?`n")) {
        if ($line -match '^\s*(\d+\.\d+\.\d+\.\d+|\*)\s+(\d+)\s+\S+\s+\d+') {
            if ($ports.ContainsKey([int]$Matches[2])) {
                [void](Invoke-DeployerNative -FilePath $netsh -ArgumentList @('interface', 'portproxy', 'delete', 'v4tov4', "listenport=$($Matches[2])", "listenaddress=$($Matches[1])"))
            }
        }
    }
}

function Update-DeployerPortProxy {
    # WSL NAT mode: forward <LAN IP>:<port> to the distro's current IP (it changes on every boot)
    # for the dashboard port and the app port range. netsh has no range syntax, so one rule each.
    param([int]$Port)
    if (-not (Test-DeployerIsAdmin)) {
        Write-DeployerWarn 'Skipping LAN port forwarding refresh (needs administrator rights).'
        return $false
    }
    $wslIp = Get-DeployerWslIp
    if (-not $wslIp) {
        Write-DeployerWarn 'Could not determine the WSL IP address; LAN forwarding not refreshed.'
        return $false
    }
    Remove-DeployerPortProxy -Port $Port
    $netsh = Join-Path $env:SystemRoot 'System32\netsh.exe'
    $ok = $true
    foreach ($ip in @(Get-DeployerLanAddresses)) {
        foreach ($p in (Get-DeployerLanPorts -Port $Port)) {
            $r = Invoke-DeployerNative -FilePath $netsh -ArgumentList @('interface', 'portproxy', 'add', 'v4tov4',
                "listenport=$p", "listenaddress=$ip", "connectport=$p", "connectaddress=$wslIp")
            if ($r.ExitCode -ne 0) {
                Write-DeployerWarn "portproxy for ${ip}:$p failed: $($r.Output.Trim())"
                $ok = $false
            }
        }
    }
    try { Start-Service -Name iphlpsvc -ErrorAction Stop } catch { Write-Verbose "iphlpsvc: $_" }
    return $ok
}

function Add-DeployerFirewallRule {
    param([int]$Port)
    $range = "$($script:DeployerAppPortFirst)-$($script:DeployerAppPortLast)"
    Remove-NetFirewallRule -Name $script:DeployerFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule -Name $script:DeployerFirewallRule -DisplayName "Deployer (TCP $Port, $range)" `
        -Description 'Allows devices on private networks to reach Deployer and the apps it deploys.' `
        -Direction Inbound -Protocol TCP -LocalPort @("$Port", $range) -Action Allow -Profile Private | Out-Null
    # Earlier versions also added a Hyper-V firewall rule for mirrored networking; drop it.
    if (Get-Command Remove-NetFirewallHyperVRule -ErrorAction SilentlyContinue) {
        Remove-NetFirewallHyperVRule -Name $script:DeployerFirewallRule -ErrorAction SilentlyContinue
    }
}

function Remove-DeployerFirewallRule {
    Remove-NetFirewallRule -Name $script:DeployerFirewallRule -ErrorAction SilentlyContinue
    if (Get-Command Remove-NetFirewallHyperVRule -ErrorAction SilentlyContinue) {
        Remove-NetFirewallHyperVRule -Name $script:DeployerFirewallRule -ErrorAction SilentlyContinue
    }
}

function Get-DeployerBindAddress {
    # Host address the caddy port is published on (DEPLOYER_BIND in .env).
    param([bool]$Lan, [string]$Runtime)
    if ($Lan) { return '0.0.0.0' }
    if ($Runtime -eq 'wsl-engine') {
        # WSL NAT: the distro's own IP is only reachable from this PC; 0.0.0.0 keeps localhost forwarding reliable.
        # Under mirrored networking 0.0.0.0 would be every host interface, so stay on loopback.
        if (Test-DeployerMirroredEnabled) { return '127.0.0.1' }
        return '0.0.0.0'
    }
    return '127.0.0.1'
}

function Enable-DeployerLanAccess {
    <#
      Firewall rule (Private profile) plus, for the WSL runtime, a netsh port forward to the distro
      (refreshed on every start). Returns the mode: direct or portproxy.
    #>
    param([string]$Runtime, [int]$Port)
    Write-DeployerInfo 'Adding a Windows Firewall rule (Private networks only)...'
    Add-DeployerFirewallRule -Port $Port
    if ($Runtime -ne 'wsl-engine') { return 'direct' }
    [void](Update-DeployerPortProxy -Port $Port)
    return 'portproxy'
}

function Get-DeployerNonPrivateNetworks {
    # LAN networks Windows marks Public (or Domain): the Private-only firewall rule blocks other devices there.
    @(Get-NetConnectionProfile -ErrorAction SilentlyContinue |
            Where-Object { $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback|docker' -and "$($_.NetworkCategory)" -ne 'Private' })
}

function Write-DeployerNetworkProfileWarning {
    <#
      The firewall rule is Private-only, so on a network Windows marks Public (or Domain) other devices
      just time out (A-071). Names each such LAN network and says how to switch it; returns their count.
    #>
    $bad = @(Get-DeployerNonPrivateNetworks)
    foreach ($p in $bad) {
        Write-DeployerWarn ("Windows treats the network '$($p.Name)' ($($p.InterfaceAlias)) as $($p.NetworkCategory), so other devices cannot reach Deployer on it. " +
            "If it is your home/office network, set it to Private: Settings > Network & internet > $($p.InterfaceAlias) > $($p.Name) (Properties) > Network profile type > Private network. " +
            "Or, in an administrator PowerShell: Set-NetConnectionProfile -InterfaceAlias '$($p.InterfaceAlias)' -NetworkCategory Private")
    }
    return $bad.Count
}

function Disable-DeployerLanAccess {
    param([int]$Port)
    Remove-DeployerFirewallRule
    Remove-DeployerPortProxy -Port $Port
}

# ------------------------------------------------------------------------------------------------
# Power (keep awake)
# ------------------------------------------------------------------------------------------------

function Get-DeployerAcPowerIndex {
    # Reads the current AC value of a power setting (e.g. SUB_SLEEP STANDBYIDLE, in seconds). The
    # labels are localized, so rely on the fact that the last two hex values printed are AC and DC.
    # /query omits hidden settings (LIDACTION is hidden on many laptops) and still exits 0, so fall
    # back to /qh, which includes them.
    param([string]$SubGroup, [string]$Setting)
    $powercfg = Join-Path $env:SystemRoot 'System32\powercfg.exe'
    foreach ($verb in '/query', '/qh') {
        $r = Invoke-DeployerNative -FilePath $powercfg -ArgumentList @($verb, 'SCHEME_CURRENT', $SubGroup, $Setting) -TimeoutSeconds 30
        if ($null -eq $r -or $r.ExitCode -ne 0) { continue }
        $hex = @([regex]::Matches($r.StdOut, ':\s*0x([0-9a-fA-F]{8})\s*$', 'Multiline') | ForEach-Object { $_.Groups[1].Value })
        if ($hex.Count -ge 2) { return [int][Convert]::ToUInt32($hex[$hex.Count - 2], 16) }
    }
    return $null
}

function Get-DeployerAcPowerTimeoutMinutes {
    param([ValidateSet('STANDBYIDLE', 'HIBERNATEIDLE')][string]$Setting)
    $seconds = Get-DeployerAcPowerIndex -SubGroup SUB_SLEEP -Setting $Setting
    if ($null -eq $seconds) { return $null }
    return [int]($seconds / 60)
}

function Set-DeployerAcLidAction {
    # 0 = do nothing, 1 = sleep, 2 = hibernate, 3 = shut down. Unlike /change, a value index only
    # takes effect once the scheme is re-applied.
    param([int]$Action)
    $powercfg = Join-Path $env:SystemRoot 'System32\powercfg.exe'
    [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/setacvalueindex', 'SCHEME_CURRENT', 'SUB_BUTTONS', 'LIDACTION', "$Action"))
    [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/setactive', 'SCHEME_CURRENT'))
}

function Set-DeployerKeepAwake {
    <#
      Enabled: remembers the current AC sleep/hibernate timeouts and lid action, then sets the
      timeouts to "never" and closing the lid to "do nothing" (A-146: a closed laptop lid otherwise
      still sleeps the PC and takes every site down).
      Disabled: restores the remembered values (Windows defaults for the timeouts if none were saved;
      the lid action only when one was saved, as older versions never changed it).
      Returns the table to store as runtime.json "keepAwake".
    #>
    param([bool]$Enabled, $Previous = $null)
    $powercfg = Join-Path $env:SystemRoot 'System32\powercfg.exe'
    if ($Enabled) {
        $wasEnabled = [bool](Get-DeployerStateValue $Previous 'enabled' $false)
        $standby = if ($wasEnabled) { Get-DeployerStateValue $Previous 'standbyAcMinutes' 30 } else { Get-DeployerAcPowerTimeoutMinutes -Setting STANDBYIDLE }
        $hibernate = if ($wasEnabled) { Get-DeployerStateValue $Previous 'hibernateAcMinutes' 180 } else { Get-DeployerAcPowerTimeoutMinutes -Setting HIBERNATEIDLE }
        # An install from before A-146 was enabled without touching the lid, so its current value is the user's own.
        $lid = if ($wasEnabled) { Get-DeployerStateValue $Previous 'lidAcAction' } else { $null }
        if ($null -eq $lid) { $lid = Get-DeployerAcPowerIndex -SubGroup SUB_BUTTONS -Setting LIDACTION }
        [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/change', 'standby-timeout-ac', '0'))
        [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/change', 'hibernate-timeout-ac', '0'))
        $table = @{ enabled = $true; standbyAcMinutes = $standby; hibernateAcMinutes = $hibernate }
        if ($null -ne $lid) {
            Set-DeployerAcLidAction -Action 0
            $table['lidAcAction'] = $lid
            Write-DeployerOk 'Sleep and hibernate disabled while on AC power; closing the lid no longer sleeps the PC while plugged in'
        } else {
            Write-DeployerOk 'Sleep and hibernate disabled while on AC power'
        }
        return $table
    }
    $standby = Get-DeployerStateValue $Previous 'standbyAcMinutes' 30
    $hibernate = Get-DeployerStateValue $Previous 'hibernateAcMinutes' 180
    [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/change', 'standby-timeout-ac', "$standby"))
    [void](Invoke-DeployerNative -FilePath $powercfg -ArgumentList @('/change', 'hibernate-timeout-ac', "$hibernate"))
    $lid = Get-DeployerStateValue $Previous 'lidAcAction'
    if ($null -ne $lid) { Set-DeployerAcLidAction -Action ([int]$lid) }
    Write-DeployerOk "Sleep restored on AC power (sleep after $standby min, hibernate after $hibernate min; 0 = never)"
    return @{ enabled = $false }
}

function Restore-DeployerKeepAwake {
    # Uninstall (A-069): undo "keep awake" if Deployer turned it on, so the PC can sleep again.
    param($State)
    $previous = Get-DeployerStateValue $State 'keepAwake'
    if (-not [bool](Get-DeployerStateValue $previous 'enabled' $false)) { return }
    [void](Set-DeployerKeepAwake -Enabled $false -Previous $previous)
}

# ------------------------------------------------------------------------------------------------
# Autostart + PATH
# ------------------------------------------------------------------------------------------------

function Register-DeployerTask {
    param([string]$InstallDir)
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $script = Join-Path $InstallDir 'installer\deployer.ps1'
    $psArgs = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" start -Background' -f $script
    # `-WindowStyle Hidden` alone still flashes a console at sign-in, and when Windows Terminal is the
    # default terminal (Windows 11) it opens a terminal window it cannot hide at all. A headless
    # console host (Windows 10 1903+) runs the script with no window of any kind.
    $conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
    if ([Environment]::OSVersion.Version.Build -ge 18362 -and (Test-Path -LiteralPath $conhost)) {
        $action = New-ScheduledTaskAction -Execute $conhost -Argument ('--headless "{0}" {1}' -f $ps, $psArgs)
    } else {
        $action = New-ScheduledTaskAction -Execute $ps -Argument $psArgs
    }
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $trigger.Delay = 'PT20S'
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
    Register-ScheduledTask -TaskName $script:DeployerTaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force `
        -Description 'Starts Deployer (docker compose stack) when you sign in.' | Out-Null

    # Deployer Control (DeployerSetup.exe copied into the install dir) shows a tray icon at sign-in.
    # A task with the highest run level avoids a UAC prompt at every sign-in.
    $exe = Join-Path $InstallDir $script:DeployerControlExe
    if (Test-Path -LiteralPath $exe) {
        $trayAction = New-ScheduledTaskAction -Execute $exe -Argument '/tray'
        $trayTrigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $trayTrigger.Delay = 'PT30S'
        $traySettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $script:DeployerTrayTaskName -Action $trayAction -Trigger $trayTrigger `
            -Principal $principal -Settings $traySettings -Force `
            -Description 'Shows the Deployer Control tray icon when you sign in.' | Out-Null
    }
}

function Test-DeployerTaskRegistered {
    return ($null -ne (Get-ScheduledTask -TaskName $script:DeployerTaskName -ErrorAction SilentlyContinue))
}

function Unregister-DeployerTask {
    foreach ($name in @($script:DeployerTaskName, $script:DeployerTrayTaskName)) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            if ($name -eq $script:DeployerTaskName) { Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue }
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
        }
    }
}

function Get-DeployerUserPath {
    $key = Get-Item -LiteralPath 'HKCU:\Environment'
    return [string]$key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
}

function Send-DeployerEnvironmentChange {
    # Setting a user variable through .NET broadcasts WM_SETTINGCHANGE so new terminals see PATH.
    [Environment]::SetEnvironmentVariable('DEPLOYER_PATH_REFRESH', '1', 'User')
    [Environment]::SetEnvironmentVariable('DEPLOYER_PATH_REFRESH', $null, 'User')
}

function Add-DeployerUserPath {
    param([string]$Directory)
    $current = Get-DeployerUserPath
    $parts = @($current -split ';' | Where-Object { $_ })
    if ($parts | Where-Object { $_.TrimEnd('\') -ieq $Directory.TrimEnd('\') }) { return }
    $new = (@($parts) + $Directory) -join ';'
    Set-ItemProperty -LiteralPath 'HKCU:\Environment' -Name 'Path' -Value $new -Type ExpandString
    Send-DeployerEnvironmentChange
}

function Remove-DeployerUserPath {
    param([string]$Directory)
    $current = Get-DeployerUserPath
    $parts = @($current -split ';' | Where-Object { $_ -and ($_.TrimEnd('\') -ine $Directory.TrimEnd('\')) })
    Set-ItemProperty -LiteralPath 'HKCU:\Environment' -Name 'Path' -Value ($parts -join ';') -Type ExpandString
    Send-DeployerEnvironmentChange
}

function Open-DeployerUrl {
    # explorer.exe hands the URL to the already-running, non-elevated shell.
    param([string]$Url)
    Start-Process -FilePath (Join-Path $env:SystemRoot 'explorer.exe') -ArgumentList $Url | Out-Null
}
