# Regression checks for uninstall restoring sleep settings (audit A-069).
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
function Invoke-DeployerNative {
    param([string]$FilePath, [string[]]$ArgumentList)
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
Write-Host 'keep awake checks passed'
