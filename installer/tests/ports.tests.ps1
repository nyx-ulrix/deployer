# Regression checks for the dashboard port vs the app port range 8100-8199 (audit A-064). Changes nothing:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\ports.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

Assert-That ((Test-DeployerAppPort 8100) -and (Test-DeployerAppPort 8199) -and -not (Test-DeployerAppPort 8090) -and -not (Test-DeployerAppPort 8200)) 'the app range is 8100-8199'

# Preflight names each program listening inside the range; -SkipOwn (upgrade) ignores Deployer's own.
function Get-NetTCPConnection {
    param($State, $LocalPort, $ErrorAction)
    [pscustomobject]@{ LocalPort = 8080; OwningProcess = 1 }
    [pscustomobject]@{ LocalPort = 8150; OwningProcess = 2 }
    [pscustomobject]@{ LocalPort = 8101; OwningProcess = 3 }
}
function Get-Process {
    param($Id, $ErrorAction)
    [pscustomobject]@{ ProcessName = @{ 1 = 'nginx'; 2 = 'node'; 3 = 'wslrelay' }[[int]$Id] }
}
$users = @(Get-DeployerAppPortUsers)
Assert-That (($users -join ', ') -eq '8101 (wslrelay), 8150 (node)') "listeners in the range are named: $($users -join ', ')"
$users = @(Get-DeployerAppPortUsers -SkipOwn)
Assert-That (($users -join ', ') -eq '8150 (node)') 'Deployer''s own listeners are skipped on upgrade'

# set-port refuses the range before it reads or writes anything.
$dir = Join-Path $env:TEMP ('deployer-ports-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot '..\deployer.ps1') set-port 8150 -InstallDir $dir *>&1 | Out-String
Assert-That ($LASTEXITCODE -eq 1 -and $out -match 'keeps for deployed apps' -and -not (Test-Path -LiteralPath $dir)) 'deployer set-port 8150 is refused'
Write-Host 'port checks passed'
