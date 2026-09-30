# Regression checks for LAN access on the WSL runtime (audit A-065): always a netsh port forward, never
# WSL mirrored networking. Changes nothing outside a temp folder:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\lan.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$dir = Join-Path $env:TEMP ('deployer-lan-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $dir | Out-Null
$realProfile = $env:USERPROFILE
try {
    $env:USERPROFILE = $dir
    $cfg = Join-Path $dir '.wslconfig'
    Set-Content -LiteralPath $cfg -Value "[wsl2]`r`nnetworkingMode=mirrored"
    $before = Get-Content -LiteralPath $cfg -Raw

    function Add-DeployerFirewallRule { param([int]$Port) }
    function Update-DeployerPortProxy { param([int]$Port) $script:proxied = $Port; $true }
    function Write-DeployerInfo { param($Message) }
    function Write-DeployerWarn { param($Message) $script:warned = $Message }

    # 1. WSL LAN access is a port forward, even with mirrored already on; .wslconfig is never touched.
    Assert-That ((Enable-DeployerLanAccess -Runtime 'wsl-engine' -Port 8080) -eq 'portproxy' -and $script:proxied -eq 8080) 'WSL LAN access uses the port forward'
    Assert-That ((Get-Content -LiteralPath $cfg -Raw) -eq $before -and @(Get-ChildItem -LiteralPath $dir).Count -eq 1) '.wslconfig is left alone'
    Assert-That ((Enable-DeployerLanAccess -Runtime 'docker-desktop' -Port 8080) -eq 'direct') 'Docker Desktop LAN access is direct'
    Assert-That (-not (Get-Command Enable-DeployerLanAccess).Parameters.ContainsKey('UseMirrored')) 'the mirrored option is gone'

    # 2. A mirrored .wslconfig gets a warning; the default one does not.
    Write-DeployerMirroredWarning
    Assert-That ($script:warned -match 'mirrored') 'mirrored networking is warned about'
    Set-Content -LiteralPath $cfg -Value "[wsl2]`r`nmemory=4GB"
    $script:warned = $null
    Write-DeployerMirroredWarning
    Assert-That ($null -eq $script:warned) 'no warning without mirrored'

    # 3. A stale 'mirrored' LAN mode from an older version still gets its port forward refreshed on start.
    $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deployer.ps1'), [ref]$null, [ref]$null)
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Update-LanForwarding' }, $true)
    . ([scriptblock]::Create($fn.Extent.Text))
    function Write-DeployerOk { param($Message) }
    $script:proxied = $null
    Update-LanForwarding -Ctx ([pscustomobject]@{ Runtime = 'wsl-engine'; Port = 9090; Lan = [pscustomobject]@{ enabled = $true; mode = 'mirrored' } })
    Assert-That ($script:proxied -eq 9090) 'a legacy mirrored mode is refreshed as a port forward'

    # 4. The installer no longer asks about mirrored networking.
    $install = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\install.ps1') -Raw
    Assert-That ($install -notmatch 'Use mirrored networking') 'install.ps1 has no mirrored prompt'
} finally {
    $env:USERPROFILE = $realProfile
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'LAN checks passed'
