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

# 2. The loop starts the stack, starts it again when the VM stopped by itself, and stops looping after
#    "deployer stop". No real waiting: Start-Sleep only records the delay the loop asked for.
$dir = Join-Path $env:TEMP ('deployer-keepalive-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $dir | Out-Null
$marker = Join-Path $dir $script:DeployerStopMarker
function Start-Sleep { param([int]$Seconds) $script:sleeps += $Seconds }
function Write-DeployerLog { param($Level, $Message) $script:logs += "$Level $Message" }
function Reset-Loop { $script:sleeps = @(); $script:logs = @(); $script:starts = 0; $script:keepAlives = 0; Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue }
try {
    function Start-DeployerKeepAlive { param([switch]$Wait) $script:keepAlives++ }
    Reset-Loop
    Invoke-DeployerKeepAliveLoop -InstallDir $dir -HeldSeconds 0 -Start {
        $script:starts++
        # The user runs "deployer stop" while the restarted stack is up.
        if ($script:starts -eq 3) { Set-Content -LiteralPath $marker -Value 'test' }
    }
    Assert-That ($script:starts -eq 3 -and $script:keepAlives -eq 2) 'the loop starts the stack, starts it again after the keep-alive ended, and a stop during that start ends it without a new keep-alive'
    Assert-That (($script:sleeps -join ',') -eq '15,15,30') 'a keep-alive that held resets the delay to 15 s'

    Reset-Loop
    Set-Content -LiteralPath $marker -Value 'test'
    Invoke-DeployerKeepAliveLoop -InstallDir $dir -Start { $script:starts++ }
    Assert-That ($script:starts -eq 1 -and $script:keepAlives -eq 0) 'the loop never starts again after an intentional stop'

    # (K) wsl.exe cannot launch while the WSL Store package updates itself (Win32 error 786): the loop
    # logs one line, backs off (15 s doubling) and keeps trying instead of ending the task.
    function Start-DeployerKeepAlive {
        param([switch]$Wait)
        $script:keepAlives++
        if ($script:keepAlives -eq 4) { Set-Content -LiteralPath $marker -Value 'test' }
        throw "Program 'wsl.exe' failed to run: Access to %1 has been restricted by your Administrator by policy rule %2"
    }
    Reset-Loop
    Invoke-DeployerKeepAliveLoop -InstallDir $dir -MaxDelaySeconds 60 -Start { $script:starts++ }
    Assert-That ($script:keepAlives -eq 4 -and $script:starts -eq 4) 'a keep-alive launch failure is retried until the stop marker, never ending the loop'
    Assert-That (($script:sleeps -join ',') -eq '15,30,60,60') 'launch failures back off 15 s doubling up to the maximum'
    Assert-That (@($script:logs | Where-Object { $_ -match 'could not start \(Program' }).Count -eq 4) 'each launch failure is logged in one plain line'

    # A start that fails (compose up cannot run either) is retried with the same backoff, without a keep-alive.
    function Start-DeployerKeepAlive { param([switch]$Wait) $script:keepAlives++ }
    Reset-Loop
    Invoke-DeployerKeepAliveLoop -InstallDir $dir -MaxDelaySeconds 60 -Start {
        $script:starts++
        if ($script:starts -eq 3) { Set-Content -LiteralPath $marker -Value 'test' }
        throw 'docker compose up failed (exit code -1).'
    }
    Assert-That ($script:starts -eq 3 -and $script:keepAlives -eq 0 -and ($script:sleeps -join ',') -eq '15,30,60') 'a failed start is tried again with backoff and no keep-alive'
    Assert-That (@($script:logs | Where-Object { $_ -match 'did not start \(docker compose up failed' }).Count -eq 3) 'each failed start is logged in one plain line'
} finally {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

# 3. (A-063) The start the loop runs refreshes LAN port forwarding: the WSL IP changes after sleep/hibernate.
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deployer.ps1'), [ref]$null, [ref]$null)
$loopCall = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Invoke-DeployerKeepAliveLoop' }, $true) | Select-Object -First 1
$startStack = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Start-Stack' }, $true)
Assert-That ($null -ne $loopCall -and $loopCall.Extent.Text -match 'Start-Stack' -and $startStack.Extent.Text -match 'Update-LanForwarding') 'the keep-alive start refreshes LAN forwarding'
Assert-That ($startStack.Extent.Text -match 'Start-DeployerKeepAlive[\s\S]*Invoke-DeployerCompose') 'the keep-alive is started before compose up, so WSL cannot stop the distro during the health wait'
$update = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-Update' }, $true)
Assert-That ($update.Extent.Text -match "Test-DeployerTaskRegistered[\s\S]*'installer\\deployer\.ps1'\) autostart on[\s\S]*Start-ScheduledTask") 'deployer update registers the sign-in task again with the new files (the watchdog) and restarts its loop'

# 3b. (K) The sign-in task also runs every 5 minutes as a watchdog (IgnoreNew while the loop runs).
#     The module is loaded first: autoloading it later would put its own Register-ScheduledTask over the fake.
Import-Module ScheduledTasks
function Register-ScheduledTask { param($TaskName, $Action, $Trigger, $Principal, $Settings, $Description, [switch]$Force) $script:tasks[$TaskName] = @{ Trigger = @($Trigger)[0]; Settings = $Settings } }
$script:tasks = @{}
Register-DeployerTask -InstallDir (Join-Path $env:TEMP 'deployer-no-such-dir') -Watchdog
$task = $script:tasks[$script:DeployerTaskName]
Assert-That ($task.Trigger.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' -and $task.Trigger.Repetition.Interval -eq 'PT5M' -and -not $task.Trigger.Repetition.Duration) 'the sign-in trigger repeats every 5 minutes for the whole sign-in'
Assert-That ($task.Settings.MultipleInstances -eq 'IgnoreNew') 'a repeat is ignored while the loop still runs'
Register-DeployerTask -InstallDir (Join-Path $env:TEMP 'deployer-no-such-dir')
Assert-That (-not $script:tasks[$script:DeployerTaskName].Trigger.Repetition.Interval) 'without the WSL keep-alive loop (Docker Desktop) the task does not repeat'
$signedIn = Get-DeployerSignInTime
Assert-That ($signedIn -is [datetime] -and $signedIn -le (Get-Date)) "this process's sign-in time is read from its own logon session"

# 3c. (K) A watchdog repeat after "deployer stop" leaves Deployer stopped; a sign-in starts it.
$fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-Start' }, $true)
. ([scriptblock]::Create($fn.Extent.Text))
$InstallDir = Join-Path $env:TEMP ('deployer-k-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $InstallDir | Out-Null
$Background = $true
function Get-Context { [pscustomobject]@{ Runtime = 'wsl-engine'; Port = 8080; State = $null; Env = @{}; Lan = $null } }
function Test-DeployerIsAdmin { $false }
function Write-DeployerStep { param($Message) }
function Invoke-DeployerKeepAliveLoop { param($InstallDir, $Start) $script:loops++ }
function Get-DeployerSignInTime { $script:signIn }
try {
    $marker = Join-Path $InstallDir $script:DeployerStopMarker
    Set-Content -LiteralPath $marker -Value 'test'
    $script:loops = 0; $script:signIn = (Get-Date).AddHours(-1)
    Invoke-Start
    Assert-That ($script:loops -eq 0 -and (Test-Path -LiteralPath $marker)) 'a stop from this sign-in is kept when the watchdog runs the task again'
    $script:signIn = (Get-Date).AddHours(1)
    Invoke-Start
    Assert-That ($script:loops -eq 1 -and -not (Test-Path -LiteralPath $marker)) 'a stop from an earlier sign-in does not stop the sign-in start'
    Set-Content -LiteralPath $marker -Value 'test'
    $script:signIn = $null
    Invoke-Start
    Assert-That ($script:loops -eq 2 -and -not (Test-Path -LiteralPath $marker)) 'without a sign-in time the task starts Deployer as before'
} finally {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
}
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

# 4. (A-063) The WSL IP is eth0's, not whatever `hostname -I` lists first (docker0 can come first).
function Get-DeployerWslExe { 'wsl.exe' }
function Invoke-DeployerNative { param($FilePath, $ArgumentList, $TimeoutSeconds) [pscustomobject]@{ ExitCode = 0; StdOut = $script:fakeOut } }
$script:fakeOut = "2: eth0    inet 172.28.1.5/20 brd 172.28.15.255 scope global eth0`n172.17.0.1 172.28.1.5 `n"
Assert-That ((Get-DeployerWslIp) -eq '172.28.1.5') 'Get-DeployerWslIp prefers the eth0 address'
$script:fakeOut = "10.0.0.7 172.17.0.1 `n"
Assert-That ((Get-DeployerWslIp) -eq '10.0.0.7') 'Get-DeployerWslIp falls back to hostname -I without ip'

# 5. (L-08) A setup-exe update stops the sign-in task's keep-alive loop the way "deployer stop" does,
#    before `wsl --update`, the Docker restart in setup-engine.sh or `wsl --terminate` ends the keep-alive.
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\install.ps1'), [ref]$null, [ref]$null)
$fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Install-WslEngine' }, $true)
. ([scriptblock]::Create($fn.Extent.Text))
function Write-DeployerStep { param($Message) }
function Write-DeployerInfo { param($Message) }
function Write-DeployerOk { param($Message) }
function Write-DeployerWarn { param($Message) }
function Initialize-WslPlatform { param($ResumeScript) $script:calls += 'wsl --update' }
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
    Assert-That (($script:calls -join ',') -eq 'stop-keepalive,wsl --update,engine marker=True,wsl --terminate') 'an update marks the stop and ends the keep-alive before WSL updates or Docker restarts (L-08)'

    Remove-Item -LiteralPath (Join-Path $InstallDir $script:DeployerStopMarker)
    $script:registered = $false; $script:calls = @()
    Install-WslEngine -Facts $null -ResumeScript 'x.ps1'
    Assert-That (($script:calls -join ',') -eq 'wsl --update,import,engine marker=False,wsl --terminate') 'a fresh install leaves no stop marker'

    # 6. (L-08) A distro still registered on a folder deleted after `uninstall -KeepData` is created again.
    $script:registered = $true; $script:diskMissing = $true; $script:calls = @()
    Install-WslEngine -Facts $null -ResumeScript 'x.ps1'
    Assert-That (($script:calls -join ',') -eq 'stop-keepalive,wsl --update,wsl --unregister,import,engine marker=True,wsl --terminate') 'a distro whose disk is gone is unregistered and imported again'
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
