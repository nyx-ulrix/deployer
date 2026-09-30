# Regression check for audit A-152: the WSL platform step decides on a pending restart from the feature
# State alone (RestartNeeded on Get-WindowsOptionalFeature output is not a pending-restart signal).
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\wslplatform.tests.ps1
$ErrorActionPreference = 'Stop'

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\install.ps1'), [ref]$null, [ref]$null)
$fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Initialize-WslPlatform' }, $true)
Assert-That ($null -ne $fn) 'install.ps1 defines Initialize-WslPlatform'
. ([scriptblock]::Create($fn.Extent.Text))

function Write-DeployerInfo { param($Message) }
function Write-DeployerWarn { param($Message) }
function Write-DeployerOk { param($Message) }
function Get-DeployerWslExe { $PSCommandPath }
function Get-DeployerWslVersion { '2.4.0' }
function Invoke-DeployerStreaming { param($FilePath, $ArgumentList) 0 }
function Register-ResumeAfterReboot { param($ScriptPath) }
function Request-Reboot { param($Reason) $script:rebootAsked = $true; throw 'reboot' }
function Get-WindowsOptionalFeature {
    param([switch]$Online, $FeatureName)
    [pscustomobject]@{ FeatureName = $FeatureName; State = $script:state; RestartNeeded = $true }
}

function Test-Reboot {
    param([string]$State)
    $script:state = $State
    $script:rebootAsked = $false
    try { Initialize-WslPlatform -ResumeScript 'x.ps1' } catch { if ("$_" -ne 'reboot') { throw } }
    $script:rebootAsked
}

Assert-That (-not (Test-Reboot 'Enabled')) 'enabled features never ask for a restart, whatever RestartNeeded says'
Assert-That (Test-Reboot 'EnablePending') 'an EnablePending feature asks for a restart'
Assert-That (Test-Reboot 'Disabled') 'a feature still disabled after wsl --install asks for a restart'
Write-Host 'wsl platform checks passed'
