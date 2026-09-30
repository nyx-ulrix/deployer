# Regression check for the data dirs ACL (audit A-067): the WSL disk (every database), logs and backups
# must not inherit the Users:RX the install dir grants. Works on a temp folder only:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\acl.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

$dir = Join-Path $env:TEMP ('deployer-acl-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
try {
    foreach ($name in @('wsl', 'logs', 'backups')) { New-Item -ItemType Directory -Path (Join-Path $dir $name) -Force | Out-Null }
    $vhdx = Join-Path $dir 'wsl\ext4.vhdx'
    Set-Content -LiteralPath $vhdx -Value 'disk'
    # Same Users grant Set-DeployerInstallDirAcl puts on the install dir (without locking out this non-admin run).
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    & $icacls $dir /grant '*S-1-5-32-545:(OI)(CI)(RX)' | Out-Null
    $usersSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')
    function Test-UsersCanRead([string]$Path) {
        foreach ($rule in (Get-Acl -LiteralPath $Path).Access) {
            if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]) -eq $usersSid) { return $true }
        }
        return $false
    }
    if (-not (Test-UsersCanRead $vhdx)) { throw 'FAIL: test setup did not give Users read on the vhdx' }

    Protect-DeployerDataDirs -InstallDir $dir
    foreach ($path in @($vhdx, (Join-Path $dir 'logs'), (Join-Path $dir 'backups'))) {
        if (Test-UsersCanRead $path) { throw "FAIL: Users can still read $path" }
    }
    Get-Content -LiteralPath $vhdx | Out-Null  # the installing user keeps access
    Write-Host 'ok   the WSL disk, logs and backups are private to Administrators, SYSTEM and the installing user'
} finally {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
