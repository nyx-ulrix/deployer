# Regression checks for uninstall restoring sleep settings (audit A-069) and the lid action (A-146).
# Records the powercfg calls instead of running them:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\keepawake.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$script:calls = @()
$script:acIndex = @{ STANDBYIDLE = '0x00000708'; HIBERNATEIDLE = '0x00002a30'; LIDACTION = '0x00000001' }
function Invoke-DeployerNative {
    param([string]$FilePath, [string[]]$ArgumentList, [int]$TimeoutSeconds)
    if ($ArgumentList[0] -eq '/query') {
        $v = $script:acIndex[$ArgumentList[3]]
        if (-not $v) { return [pscustomobject]@{ ExitCode = 1; StdOut = '' } }
        return [pscustomobject]@{ ExitCode = 0; StdOut = "    Current AC Power Setting Index: $v`r`n    Current DC Power Setting Index: 0x00000000`r`n" }
    }
    $script:calls += , ($ArgumentList -join ' ')
}

$state = '{"keepAwake":{"enabled":true,"standbyAcMinutes":15,"hibernateAcMinutes":60}}' | ConvertFrom-Json
Restore-DeployerKeepAwake -State $state
Assert-That (($calls -join '|') -eq '/change standby-timeout-ac 15|/change hibernate-timeout-ac 60') "the saved AC timeouts are restored: $($calls -join '|')"

foreach ($json in @('{"keepAwake":{"enabled":false}}', '{}')) {
    $script:calls = @()
    Restore-DeployerKeepAwake -State ($json | ConvertFrom-Json)
    Assert-That ($calls.Count -eq 0) "power settings untouched when keep awake was not on: $json"
}
# A-146: turning it on also stops a closed lid from sleeping the PC on AC, and saves the old action.
$script:calls = @()
$table = Set-DeployerKeepAwake -Enabled $true
Assert-That ($table.standbyAcMinutes -eq 30 -and $table.hibernateAcMinutes -eq 180 -and $table.lidAcAction -eq 1) "the current AC values are saved: $($table | ConvertTo-Json -Compress)"
Assert-That (($calls -join '|') -eq '/change standby-timeout-ac 0|/change hibernate-timeout-ac 0|/setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0|/setactive SCHEME_CURRENT') "sleep, hibernate and lid close are all off: $($calls -join '|')"

$script:calls = @()
Restore-DeployerKeepAwake -State ([pscustomobject]@{ keepAwake = [pscustomobject]$table })
Assert-That (($calls -join '|') -eq '/change standby-timeout-ac 30|/change hibernate-timeout-ac 180|/setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 1|/setactive SCHEME_CURRENT') "the saved lid action is restored: $($calls -join '|')"

# A PC whose scheme has no lid setting: the timeouts still change and nothing lid-related is stored.
$script:acIndex.Remove('LIDACTION')
$script:calls = @()
$table = Set-DeployerKeepAwake -Enabled $true
Assert-That (-not $table.ContainsKey('lidAcAction') -and ($calls -join '|') -eq '/change standby-timeout-ac 0|/change hibernate-timeout-ac 0') "no lid setting leaves the lid alone: $($calls -join '|')"
Write-Host 'keep awake checks passed'

