# Regression check for audit A-151: the installer and `deployer update` leave no source downloads or
# staging copies in %TEMP%. Uses throwaway folders under %TEMP% that it deletes again:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\tempfiles.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

# 1. A failed download removes the half-filled work folder.
function Write-DeployerInfo { param($Message) }
function Write-DeployerWarn { param($Message) }
function Invoke-DeployerDownload { param($Uri, $OutFile) Set-Content -LiteralPath $OutFile -Value 'partial'; throw 'offline' }
$work = Join-Path $env:TEMP ('deployer-tempfiles-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$err = $null
try { [void](Get-DeployerSource -Repo 'example/deployer' -Ref 'v0.0.1' -WorkDir $work) } catch { $err = $_.Exception.Message }
Assert-That ($err -match 'Could not download') "the download failure is still reported: $err"
Assert-That (-not (Test-Path -LiteralPath $work)) 'a failed download leaves no work folder behind'

# 2. install.ps1 removes every temp path it recorded when the run ends.
$installPath = Join-Path $PSScriptRoot '..\install.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($installPath, [ref]$null, [ref]$null)
$fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Remove-InstallerTempFiles' }, $true)
Assert-That ($null -ne $fn) 'install.ps1 defines Remove-InstallerTempFiles'
. ([scriptblock]::Create($fn.Extent.Text))
$dir = Join-Path $env:TEMP ('deployer-tempfiles-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path (Join-Path $dir 'x\deploy') -Force | Out-Null
Set-Content -LiteralPath (Join-Path $dir 'x\deploy\docker-compose.yml') -Value 'services: {}'
$file = "$dir.ps1"
Set-Content -LiteralPath $file -Value '# relaunch copy'
$script:InstallerTempPaths = @($dir, $file, (Join-Path $env:TEMP 'deployer-tempfiles-never-created'))
Remove-InstallerTempFiles
Assert-That (-not (Test-Path -LiteralPath $dir)) 'a recorded download folder is removed'
Assert-That (-not (Test-Path -LiteralPath $file)) 'the recorded relaunch script is removed'
Assert-That ($script:InstallerTempPaths.Count -eq 0) 'the list is emptied'

$source = [System.IO.File]::ReadAllText($installPath)
$tempJoins = [regex]::Matches($source, 'Join-Path \$env:TEMP').Count
$recorded = [regex]::Matches($source, '\$script:InstallerTempPaths \+=').Count
Assert-That ($tempJoins -eq $recorded) "every %TEMP% path install.ps1 makes is recorded ($recorded of $tempJoins)"
$finallyCalls = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.TryStatementAst] -and $n.Finally -and $n.Finally.Extent.Text -match 'Remove-InstallerTempFiles' }, $true)
Assert-That (@($finallyCalls).Count -eq 2) 'both the non-admin launcher and the installer run clean up in finally'

# 3. deployer update removes its download in finally.
$cli = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deployer.ps1'), [ref]$null, [ref]$null)
$update = $cli.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-Update' }, $true)
$try = $update.Find({ param($n) $n -is [System.Management.Automation.Language.TryStatementAst] -and $n.Finally }, $true)
Assert-That ($null -ne $try -and $try.Finally.Extent.Text -match 'Remove-Item -LiteralPath \$work') 'deployer update removes its download folder in finally'
Write-Host 'temp file checks passed'
