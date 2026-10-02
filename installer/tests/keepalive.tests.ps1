# Regression checks for the sign-in task's WSL keep-alive loop (audit A-015). Runs without WSL or Docker:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\keepalive.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

# 1. -Wait blocks on a keep-alive someone else started instead of returning at once (the 15 s spin).
$other = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\PING.EXE') -ArgumentList '-n 3 127.0.0.1' -WindowStyle Hidden -PassThru
function Get-DeployerKeepAliveProcess { if (-not $other.HasExited) { [pscustomobject]@{ ProcessId = $other.Id } } }
function Get-DeployerWslExe { throw 'must not start a second keep-alive' }
$watch = [Diagnostics.Stopwatch]::StartNew()
Start-DeployerKeepAlive -Wait
Assert-That ($other.HasExited -and $watch.Elapsed.TotalSeconds -ge 1) 'Start-DeployerKeepAlive -Wait waits for an existing keep-alive'

# 2. The loop restarts the stack when the VM stopped by itself, and stops looping after "deployer stop".
$dir = Join-Path $env:TEMP ('deployer-keepalive-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $dir | Out-Null
try {
    function Start-DeployerKeepAlive { param([switch]$Wait) }
    $script:restarts = 0
    Invoke-DeployerKeepAliveLoop -InstallDir $dir -DelaySeconds 0 -Restart {
        $script:restarts++
        # The user runs "deployer stop" while the restarted stack is up.
        Set-Content -LiteralPath (Join-Path $dir $script:DeployerStopMarker) -Value 'test'
    }
    Assert-That ($script:restarts -eq 1) 'the loop restarts once, then exits on the stop marker'

    $script:restarts = 0
    Invoke-DeployerKeepAliveLoop -InstallDir $dir -DelaySeconds 0 -Restart { $script:restarts++ }
    Assert-That ($script:restarts -eq 0) 'the loop never restarts after an intentional stop'
} finally {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}

# 3. (A-063) The loop's restart refreshes LAN port forwarding: the WSL IP changes after sleep/hibernate.
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deployer.ps1'), [ref]$null, [ref]$null)
$loopCall = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Invoke-DeployerKeepAliveLoop' }, $true) | Select-Object -First 1
Assert-That ($null -ne $loopCall -and $loopCall.Extent.Text -match 'Update-LanForwarding') 'the keep-alive restart refreshes LAN forwarding'

# 4. (A-063) The WSL IP is eth0's, not whatever `hostname -I` lists first (docker0 can come first).
function Get-DeployerWslExe { 'wsl.exe' }
function Invoke-DeployerNative { param($FilePath, $ArgumentList, $TimeoutSeconds) [pscustomobject]@{ ExitCode = 0; StdOut = $script:fakeOut } }
$script:fakeOut = "2: eth0    inet 172.28.1.5/20 brd 172.28.15.255 scope global eth0`n172.17.0.1 172.28.1.5 `n"
Assert-That ((Get-DeployerWslIp) -eq '172.28.1.5') 'Get-DeployerWslIp prefers the eth0 address'
$script:fakeOut = "10.0.0.7 172.17.0.1 `n"
Assert-That ((Get-DeployerWslIp) -eq '10.0.0.7') 'Get-DeployerWslIp falls back to hostname -I without ip'

# 5. (L-08) A setup-exe update stops the sign-in task's keep-alive loop the way "deployer stop" does,
#    before setup-engine.sh restarts Docker and `wsl --terminate` ends the keep-alive.
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\install.ps1'), [ref]$null, [ref]$null)
$fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Install-WslEngine' }, $true)
. ([scriptblock]::Create($fn.Extent.Text))
function Write-DeployerStep { param($Message) }
function Write-DeployerInfo { param($Message) }
function Write-DeployerOk { param($Message) }
function Write-DeployerWarn { param($Message) }
function Initialize-WslPlatform { param($ResumeScript) }
function ConvertTo-DeployerWslPath { param($Path) '/mnt/x' }
function Wait-DeployerDockerEngine { param($Runtime, $TimeoutSeconds) $true }
function Get-UbuntuWslImage { 'none.tar.gz' }
function Set-DeployerPrivateAcl { param($Path) }
function Test-DeployerWslDistro { $script:registered }
function Test-DeployerWslDistroDiskMissing { $script:diskMissing }
function Stop-DeployerKeepAlive { $script:calls += 'stop-keepalive' }
function Invoke-DeployerNative {
    param($FilePath, $ArgumentList, $TimeoutSeconds)
    $script:calls += "wsl $($ArgumentList[0])"
    if ($ArgumentList[0] -eq '--unregister') { $script:registered = $false }
    [pscustomobject]@{ ExitCode = 0; StdOut = '' }
}
function Invoke-DeployerStreaming {
    param($FilePath, $ArgumentList)
    $script:calls += $(if ($ArgumentList[0] -eq '--import') { 'import' } else { "engine marker=$(Test-Path -LiteralPath (Join-Path $InstallDir $script:DeployerStopMarker))" })
    0
}
$InstallDir = Join-Path $env:TEMP ('deployer-l08-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $InstallDir | Out-Null
try {
    $script:registered = $true; $script:diskMissing = $false; $script:calls = @()
    Install-WslEngine -Facts $null -ResumeScript 'x.ps1'
    Assert-That (($script:calls -join ',') -eq 'stop-keepalive,engine marker=True,wsl --terminate') 'an update marks the stop and ends the keep-alive before Docker restarts (L-08)'

    Remove-Item -LiteralPath (Join-Path $InstallDir $script:DeployerStopMarker)
    $script:registered = $false; $script:calls = @()
    Install-WslEngine -Facts $null -ResumeScript 'x.ps1'
    Assert-That (($script:calls -join ',') -eq 'import,engine marker=False,wsl --terminate') 'a fresh install leaves no stop marker'

    # 6. (L-08) A distro still registered on a folder deleted after `uninstall -KeepData` is created again.
    $script:registered = $true; $script:diskMissing = $true; $script:calls = @()
    Install-WslEngine -Facts $null -ResumeScript 'x.ps1'
    Assert-That (($script:calls -join ',') -eq 'wsl --unregister,import,engine marker=False,wsl --terminate') 'a distro whose disk is gone is unregistered and imported again'
} finally {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
}

# 7. (L-08) "Disk gone" is only claimed for a registered folder without a .vhdx, never on a guess.
. (Join-Path $PSScriptRoot '..\lib\common.ps1')
function Get-ItemProperty { [CmdletBinding()] param([string]$LiteralPath) $script:lxss }
function Get-ChildItem { [CmdletBinding()] param([string]$LiteralPath) [pscustomobject]@{ PSPath = 'fake' } }
$disk = Join-Path $env:TEMP ('deployer-l08-disk-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $disk | Out-Null
try {
    $script:lxss = [pscustomobject]@{ DistributionName = 'deployer'; BasePath = "\\?\$disk" }
    Assert-That (Test-DeployerWslDistroDiskMissing) 'a registered folder without a disk counts as missing'
    Set-Content -LiteralPath (Join-Path $disk 'ext4.vhdx') -Value 'x'
    Assert-That (-not (Test-DeployerWslDistroDiskMissing)) 'a registered folder with its disk is kept'
    Remove-Item -LiteralPath $disk -Recurse -Force
    Assert-That (Test-DeployerWslDistroDiskMissing) 'a deleted folder counts as missing'
    $script:lxss = [pscustomobject]@{ DistributionName = 'other'; BasePath = $disk }
    Assert-That (-not (Test-DeployerWslDistroDiskMissing)) 'an unknown location is never treated as missing'
} finally {
    Remove-Item -LiteralPath $disk -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'keep-alive checks passed'
