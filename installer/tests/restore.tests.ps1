# Regression checks for 'deployer restore' (audit A-068): the dump is copied from the path the docker CLI
# of the runtime sees, and the password is read inside the container, not expanded by PowerShell.
# Records the docker compose calls instead of running them; works on a temp folder only:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\restore.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$script:calls = @()
function Invoke-DeployerCompose {
    param([string]$InstallDir, [string]$Runtime, [string[]]$Arguments)
    $script:calls += , @($Arguments)
    return 0
}

$dir = Join-Path $env:TEMP ('deployer-restore-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
try {
    $backup = Join-Path $dir 'backups\20260101-000000'
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $dir '.env') -Value 'MASTER_KEY=abc'
    Set-Content -LiteralPath (Join-Path $backup 'env.backup') -Value 'MASTER_KEY=abc'
    Set-Content -LiteralPath (Join-Path $backup 'mariadb.sql') -Value '-- dump'
    Set-Content -LiteralPath (Join-Path $backup 'mongodb.archive.gz') -Value 'gz'

    Invoke-DeployerRestore -InstallDir $dir -Runtime 'wsl-engine' -Folder $backup -Mongo $true
    $wsl = ConvertTo-DeployerWslPath $backup
    Assert-That ($calls.Count -eq 4) "four compose calls (cp + load for MariaDB and MongoDB): $($calls.Count)"
    Assert-That (($calls[0] -join ' ') -eq "cp $wsl/mariadb.sql mariadb:/tmp/deployer-restore.sql") "WSL copies from /mnt/...: $($calls[0] -join ' ')"
    Assert-That (($calls[2] -join ' ') -eq "cp $wsl/mongodb.archive.gz mongodb:/tmp/deployer-restore.archive.gz") 'the Mongo archive too'
    $scripts = @($calls[1][-1], $calls[3][-1])
    Assert-That ($scripts[0] -like '*MYSQL_PWD=$MARIADB_ROOT_PASSWORD*' -and $scripts[1] -like '*--password=$MONGO_INITDB_ROOT_PASSWORD*') 'passwords are expanded by sh inside the container'
    Assert-That (-not ($scripts -match '"')) 'no double quotes for PowerShell 5.1 to mangle'

    $script:calls = @()
    Invoke-DeployerRestore -InstallDir $dir -Runtime 'docker-desktop' -Folder $backup -Mongo $false
    Assert-That ($calls.Count -eq 2 -and $calls[0][1] -eq "$backup/mariadb.sql") 'Docker Desktop copies from the Windows path; Mongo skipped when disabled'

    Set-Content -LiteralPath (Join-Path $dir '.env') -Value 'MASTER_KEY=other'
    $script:calls = @()
    $refused = $false
    try { Invoke-DeployerRestore -InstallDir $dir -Runtime 'docker-desktop' -Folder $backup -Mongo $false } catch { $refused = $_.Exception.Message -match 'different MASTER_KEY' }
    Assert-That ($refused -and $calls.Count -eq 0) 'a backup with another MASTER_KEY is refused before anything runs'
    Invoke-DeployerRestore -InstallDir $dir -Runtime 'docker-desktop' -Folder $backup -Mongo $false -Force
    Assert-That ($calls.Count -eq 2) '-Force restores it anyway'

    Set-Content -LiteralPath (Join-Path $backup 'env.backup') -Value @('MASTER_KEY=other', 'MARIADB_PASSWORD=old')
    Set-Content -LiteralPath (Join-Path $dir '.env') -Value @('MASTER_KEY=other', 'MARIADB_PASSWORD=new')
    $script:calls = @()
    $refused = $false
    try { Invoke-DeployerRestore -InstallDir $dir -Runtime 'docker-desktop' -Folder $backup -Mongo $false -Force } catch { $refused = $_.Exception.Message -match 'MARIADB_PASSWORD differ' }
    Assert-That ($refused -and $calls.Count -eq 0) 'a backup from another install (other database passwords) is refused, even with -Force'

    $refused = $false
    try { Invoke-DeployerRestore -InstallDir $dir -Runtime 'docker-desktop' -Folder $dir -Mongo $false } catch { $refused = $_.Exception.Message -match 'mariadb.sql is missing' }
    Assert-That $refused 'a folder without mariadb.sql is refused'
} finally {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'restore checks passed'
