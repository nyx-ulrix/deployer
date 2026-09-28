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
Write-Host 'keep-alive checks passed'
