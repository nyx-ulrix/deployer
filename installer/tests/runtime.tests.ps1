# Regression check for switching runtime (audit A-095): install.ps1 never swaps the runtime of an existing
# installation in place (its databases would be stranded); it points to export, uninstall, install, restore.
# Changes nothing:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\runtime.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\install.ps1'), [ref]$null, [ref]$null)
$help = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$script:RuntimeSwitchHelp' }, $true)
$fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Select-Runtime' }, $true)
. ([scriptblock]::Create($help.Extent.Text))
. ([scriptblock]::Create($fn.Extent.Text))
function Write-DeployerInfo { param($Message) }

$InstallDir = 'C:\ProgramData\Deployer'
$installed = [pscustomobject]@{ runtime = 'docker-desktop' }

$Runtime = 'wsl-engine'
$err = $null
try { [void](Select-Runtime -State $installed) } catch { $err = $_.Exception.Message }
Assert-That ($err -match 'Export & import' -and $err -match 'Restore from export') "a different -Runtime on an existing install is refused with the export path: $err"

$Runtime = 'docker-desktop'
Assert-That ((Select-Runtime -State $installed) -eq 'docker-desktop') 'the same -Runtime (what the wizard passes on update) is accepted'

$Runtime = 'auto'
Assert-That ((Select-Runtime -State $installed) -eq 'docker-desktop') '-Runtime auto keeps the installed runtime'

$Runtime = 'wsl-engine'
Assert-That ((Select-Runtime -State $null) -eq 'wsl-engine') 'a fresh install takes the -Runtime given'

# A-147: hints shown before the last step put 'deployer' on the PATH use the shim's full path.
$hintFn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-InstallerCliHint' }, $true)
. ([scriptblock]::Create($hintFn.Extent.Text))
Assert-That ((Get-InstallerCliHint 'logs api') -eq 'C:\ProgramData\Deployer\deployer.cmd logs api') 'the hint names the full path of deployer.cmd'
$InstallDir = 'C:\My Apps\Deployer'
Assert-That ((Get-InstallerCliHint 'status') -eq "& 'C:\My Apps\Deployer\deployer.cmd' status") 'a path with spaces is quoted so it runs as typed'
$source = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot '..\install.ps1'))
$beforePath = $source.Substring(0, $source.IndexOf('Add-DeployerUserPath -Directory'))
Assert-That ($beforePath -notmatch '[''"]deployer (logs|status)') 'no message before the PATH step tells the user to run a bare deployer command'
