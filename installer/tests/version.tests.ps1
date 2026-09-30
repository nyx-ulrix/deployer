# Regression check for audit A-074: 'deployer update' keeps the Apps & Features version in step.
# Uses a throwaway key under HKCU\Software that it deletes again:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\version.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$keyPath = 'Software\DeployerVersionTest-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$hive = [Microsoft.Win32.RegistryHive]::CurrentUser
Assert-That (-not (Set-DeployerDisplayVersion -Ref 'v0.3.0' -Hive $hive -KeyPath $keyPath)) 'no Apps & Features entry: nothing is created'
$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, [Microsoft.Win32.RegistryView]::Registry64)
try {
    $key = $base.CreateSubKey($keyPath)
    $key.SetValue('DisplayVersion', '0.2.0')
    Assert-That (Set-DeployerDisplayVersion -Ref 'v0.3.0' -Hive $hive -KeyPath $keyPath) 'a version tag updates the entry'
    Assert-That ($key.GetValue('DisplayVersion') -eq '0.3.0') 'DisplayVersion follows the update without the v'
    Assert-That (-not (Set-DeployerDisplayVersion -Ref 'main' -Hive $hive -KeyPath $keyPath)) 'a branch ref is not a version'
    Assert-That ($key.GetValue('DisplayVersion') -eq '0.3.0') 'a branch update keeps the last version'
    $key.Dispose()
} finally {
    $base.DeleteSubKeyTree($keyPath, $false)
    $base.Dispose()
}
