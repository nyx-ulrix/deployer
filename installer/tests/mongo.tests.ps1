# Regression checks for the managed MongoDB upgrade path (audit A-143): 5.0 data is lifted
# 6.0 -> 7.0 -> 8.0 by the mongodb-upgrade-* compose services before `up`; new or current data only
# runs the 8.0 step. Records the docker compose calls instead of running them:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\mongo.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

# Exit codes per service, used up in order (then 0): what upgrade.sh would return for that data.
$script:codes = @{}
$script:calls = @()
function Invoke-DeployerCompose {
    param([string]$InstallDir, [string]$Runtime, [string[]]$Arguments)
    $script:calls += , ($Arguments -join ' ')
    $queue = $script:codes[$Arguments[-1]]
    if (-not $queue) { return 0 }
    $script:codes[$Arguments[-1]] = @($queue | Select-Object -Skip 1)
    return $queue[0]
}
function Write-DeployerInfo { param([string]$Message) }
function Write-DeployerOk { param([string]$Message) }

# A pre-A-143 .env: no MONGODB_IMAGE, so compose keeps mongo:5.0 until the data is upgraded.
$dir = Join-Path $env:TEMP ('deployer-mongo-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $dir | Out-Null
function Invoke-Case {
    param([hashtable]$Codes)
    $script:codes = $Codes
    $script:calls = @()
    Set-Content -LiteralPath (Join-Path $dir '.env') -Value 'COMPOSE_PROFILES=mongodb'
    try { Update-DeployerMongo -InstallDir $dir -Runtime 'wsl-engine'; return '' } catch { return $_.Exception.Message }
}
function Get-Image { (Read-DeployerEnvFile -Path (Join-Path $dir '.env'))['MONGODB_IMAGE'] }
function Get-Steps { ($script:calls | Select-Object -Skip 1 | ForEach-Object { ($_ -split ' ')[-1] -replace 'mongodb-upgrade-', '' }) -join ',' }

$err = Invoke-Case @{}
Assert-That ($calls[0] -eq 'stop -t 60 mongodb') 'the managed MongoDB is stopped cleanly first'
Assert-That ($calls[1] -eq '--profile mongodb-upgrade run --rm -T mongodb-upgrade-8') 'steps run as one-off containers of the upgrade profile'
Assert-That ($err -eq '' -and (Get-Steps) -eq '8') 'new or current data: only the 8.0 step (no 6.0/7.0 download)'

$err = Invoke-Case @{ 'mongodb-upgrade-8' = @(3) }
Assert-That ($err -eq '' -and (Get-Steps) -eq '8,6,7,8') "5.0 data: 6.0, 7.0 then 8.0 after the 8.0 step says it is too old ($(Get-Steps))"
Assert-That ((Get-Image) -eq 'mongo:8.0') 'only upgraded data switches compose to mongo:8.0'

$err = Invoke-Case @{ 'mongodb-upgrade-8' = @(3); 'mongodb-upgrade-7' = @(1) }
Assert-That ($err -like '*mongodb-upgrade-7*exit code 1*') "a failed step stops the update before 'up' and names it: $err"
Assert-That ((Get-Steps) -eq '8,6,7') 'no later step runs after a failure'
Assert-That (-not (Get-Image)) 'a failed upgrade leaves compose on mongo:5.0'

$err = Invoke-Case @{ 'mongodb-upgrade-8' = @(1) }
Assert-That ($err -like '*mongodb-upgrade-8*exit code 1*' -and (Get-Steps) -eq '8') 'any other failure of the 8.0 step is not mistaken for old data'
Remove-Item -LiteralPath $dir -Recurse -Force
