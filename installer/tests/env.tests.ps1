# Regression checks for the .env merge (audit A-072): an upgrade must never rotate a secret the databases
# already use, while installer-managed keys are refreshed; plus ConvertTo-DeployerArgument quoting.
# Works on a temp folder only:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\env.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$secretKeys = @('MARIADB_PASSWORD', 'MARIADB_ROOT_PASSWORD', 'MONGO_ROOT_PASSWORD', 'REDIS_PASSWORD', 'JWT_SECRET', 'MASTER_KEY')
$dir = Join-Path $env:TEMP ('deployer-env-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $dir | Out-Null
$envPath = Join-Path $dir '.env'
$composePath = Join-Path $dir 'docker-compose.yml'
try {
    # V-07: a version from before A-143 hardcodes mongo:5.0, so its new .env must not claim 8.0 data.
    Set-Content -LiteralPath $composePath -Value "services:`n  mongodb:`n    image: mongo:5.0`n"
    [void](Initialize-DeployerEnv -InstallDir $dir -Port 8080 -MongoEnabled $true -ImagePrefix 'ghcr.io/a' -Version 'v1' -Bind '127.0.0.1')
    Assert-That (-not (Read-DeployerEnvFile -Path $envPath)['MONGODB_IMAGE']) 'a new install of a pre-A-143 version does not get MONGODB_IMAGE'
    Remove-Item -LiteralPath $envPath
    Set-Content -LiteralPath $composePath -Value "services:`n  mongodb:`n    image: `${MONGODB_IMAGE:-mongo:5.0}`n"

    # 1. A fresh install writes every secret and managed key once.
    $isNew = Initialize-DeployerEnv -InstallDir $dir -Port 8080 -MongoEnabled $false -ImagePrefix 'ghcr.io/a' -Version 'v1' -Bind '127.0.0.1'
    $first = Read-DeployerEnvFile -Path $envPath
    Assert-That ($isNew -eq $true) 'first run creates .env'
    Assert-That (@($secretKeys | Where-Object { -not $first[$_] }).Count -eq 0) 'every secret is generated'
    Assert-That ($first['DEPLOYER_VERSION'] -eq 'v1' -and $first['DEPLOYER_HTTP_PORT'] -eq '8080') 'managed keys are written'
    Assert-That ($first['MONGODB_IMAGE'] -eq 'mongo:8.0') 'a new install starts on MongoDB 8.0 (A-143)'
    # A pre-A-143 .env has 5.0 data: only Update-DeployerMongo may move it to 8.0.
    Set-Content -LiteralPath $envPath -Value (Get-Content -LiteralPath $envPath | Where-Object { $_ -notmatch '^MONGODB_IMAGE=' })

    # 2. The user's edits survive an upgrade; secrets stay; managed keys follow the new install.
    Set-DeployerEnvValues -Path $envPath -Values ([ordered]@{ GOOGLE_CLIENT_ID = 'mine' })
    Add-Content -LiteralPath $envPath -Value '# my note'
    $isNew = Initialize-DeployerEnv -InstallDir $dir -Port 9090 -MongoEnabled $true -ImagePrefix 'ghcr.io/b' -Version 'v2' -Bind '0.0.0.0'
    $second = Read-DeployerEnvFile -Path $envPath
    $text = Get-Content -LiteralPath $envPath -Raw
    Assert-That ($isNew -eq $false) 'second run is an upgrade'
    Assert-That (@($secretKeys | Where-Object { $second[$_] -ne $first[$_] }).Count -eq 0) 'no secret is rotated on upgrade'
    Assert-That ($second['DEPLOYER_VERSION'] -eq 'v2' -and $second['DEPLOYER_IMAGE_PREFIX'] -eq 'ghcr.io/b' -and $second['DEPLOYER_BIND'] -eq '0.0.0.0') 'managed keys are updated'
    Assert-That ($second['COMPOSE_PROFILES'] -eq 'mongodb' -and $second['MANAGED_MONGODB_ENABLED'] -eq 'true') 'the MongoDB choice is updated'
    Assert-That (-not $second['MONGODB_IMAGE']) 'an upgrade does not switch MongoDB data it has not upgraded'
    Assert-That ($second['DEPLOYER_HTTP_PORT'] -eq '8080' -and $second['PUBLIC_URL'] -eq 'http://localhost:8080') 'the port is kept without -SetPort'
    Assert-That ($second['GOOGLE_CLIENT_ID'] -eq 'mine' -and $text.Contains('# my note')) 'user edits are kept'
    $keys = @(Get-Content -LiteralPath $envPath | Where-Object { $_ -match '^[A-Za-z_]\w*=' } | ForEach-Object { ($_ -split '=', 2)[0] })
    Assert-That ($keys.Count -eq @($keys | Select-Object -Unique).Count) 'no key is written twice'

    # 3. A secret deleted by hand is regenerated alone; the others are untouched.
    Set-Content -LiteralPath $envPath -Value (Get-Content -LiteralPath $envPath | Where-Object { $_ -notmatch '^REDIS_PASSWORD=' })
    Initialize-DeployerEnv -InstallDir $dir -Port 9090 -MongoEnabled $true -ImagePrefix 'ghcr.io/b' -Version 'v2' -Bind '0.0.0.0' | Out-Null
    $third = Read-DeployerEnvFile -Path $envPath
    Assert-That ($third['REDIS_PASSWORD'] -and $third['REDIS_PASSWORD'] -ne $first['REDIS_PASSWORD']) 'a missing secret is added'
    Assert-That (@($secretKeys | Where-Object { $_ -ne 'REDIS_PASSWORD' -and $third[$_] -ne $first[$_] }).Count -eq 0) 'the other secrets are unchanged'

    # 4. -SetPort moves the port and a localhost PUBLIC_URL, but never a custom PUBLIC_URL.
    Initialize-DeployerEnv -InstallDir $dir -Port 9090 -MongoEnabled $true -ImagePrefix 'ghcr.io/b' -Version 'v2' -Bind '0.0.0.0' -SetPort | Out-Null
    $fourth = Read-DeployerEnvFile -Path $envPath
    Assert-That ($fourth['DEPLOYER_HTTP_PORT'] -eq '9090' -and $fourth['PUBLIC_URL'] -eq 'http://localhost:9090') '-SetPort updates the port and a localhost URL'
    Set-DeployerEnvValues -Path $envPath -Values ([ordered]@{ PUBLIC_URL = 'https://apps.example.com' })
    Initialize-DeployerEnv -InstallDir $dir -Port 7070 -MongoEnabled $true -ImagePrefix 'ghcr.io/b' -Version 'v2' -Bind '0.0.0.0' -SetPort | Out-Null
    $fifth = Read-DeployerEnvFile -Path $envPath
    Assert-That ($fifth['DEPLOYER_HTTP_PORT'] -eq '7070' -and $fifth['PUBLIC_URL'] -eq 'https://apps.example.com') 'a custom PUBLIC_URL is kept'
    Assert-That (@($secretKeys | Where-Object { $_ -ne 'REDIS_PASSWORD' -and $fifth[$_] -ne $first[$_] }).Count -eq 0) 'secrets survive -SetPort'
} finally {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}

# 5. Arguments are quoted the way CommandLineToArgvW reads them back.
$cases = [ordered]@{
    ''                   = '""'
    'plain'              = 'plain'
    'C:\no\spaces'       = 'C:\no\spaces'
    'two words'          = '"two words"'
    'say "hi"'           = '"say \"hi\""'
    'C:\Program Files\'  = '"C:\Program Files\\"'
    'a\"b'               = '"a\\\"b"'
    'a\\b c'             = '"a\\b c"'
}
foreach ($in in $cases.Keys) {
    Assert-That ((ConvertTo-DeployerArgument -Value $in) -ceq $cases[$in]) "quotes [$in] as [$($cases[$in])]"
}

Write-Host 'All .env merge checks passed.'
