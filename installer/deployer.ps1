<#
.SYNOPSIS
    Deployer management CLI.

.DESCRIPTION
    deployer status                 Runtime, containers and health
    deployer start                  Start the stack (and the WSL engine if needed)
    deployer stop                   Stop the stack
    deployer restart [service]      Restart everything or one service
    deployer logs [service] [-Follow] [-Tail 200]
    deployer update [-Ref v0.2.0] [-FromSource]
                                    Download new deploy files (keeps .env), pull images, restart
    deployer backup                 MariaDB + MongoDB dumps and .env into backups\<timestamp>
    deployer open                   Open the dashboard in your browser
    deployer config                 Show non-secret settings
    deployer compose -- <args>      Run any docker compose command against the stack
    deployer uninstall [-KeepData] [-Yes]
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = 'help',
    [Parameter(Position = 1)]
    [string]$Service = '',
    [switch]$Follow,
    [int]$Tail = 200,
    [string]$Ref = '',
    [switch]$FromSource,
    [switch]$KeepData,
    [switch]$Yes,
    [switch]$Background,
    [string]$InstallDir = '',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

. (Join-Path $PSScriptRoot 'lib\common.ps1')

if (-not $InstallDir) {
    $parent = Split-Path -Parent $PSScriptRoot
    if (Test-Path -LiteralPath (Join-Path $parent 'docker-compose.yml')) {
        $InstallDir = $parent
    } elseif ($env:DEPLOYER_HOME) {
        $InstallDir = $env:DEPLOYER_HOME
    } else {
        $InstallDir = Join-Path $env:ProgramData 'Deployer'
    }
}
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')

function Show-Help {
    Write-Host ''
    Write-Host 'Deployer management CLI' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '  deployer status                      Runtime, containers and health'
    Write-Host '  deployer start | stop                Start or stop the stack'
    Write-Host '  deployer restart [service]           Restart everything or one service (api, dashboard, caddy, ...)'
    Write-Host '  deployer logs [service] [-Follow]    Show logs (-Tail N lines, default 200)'
    Write-Host '  deployer update [-Ref <tag>]         Update deploy files and images; .env and data are kept'
    Write-Host '  deployer backup                      Dump MariaDB/MongoDB and copy .env to backups\<timestamp>'
    Write-Host '  deployer open                        Open the dashboard'
    Write-Host '  deployer config                      Show non-secret settings'
    Write-Host '  deployer compose -- <args>           Run docker compose (e.g. deployer compose -- ps -a)'
    Write-Host '  deployer uninstall [-KeepData]       Remove Deployer (asks for confirmation)'
    Write-Host ''
    Write-Host "  Install directory: $InstallDir"
    Write-Host ''
}

function Get-Context {
    $state = Read-DeployerState -InstallDir $InstallDir
    if ($null -eq $state) {
        throw "Deployer is not installed in $InstallDir (runtime.json missing). Run the installer first, or pass -InstallDir."
    }
    $envValues = Read-DeployerEnvFile -Path (Join-Path $InstallDir '.env')
    $port = 8080
    if ($envValues['DEPLOYER_HTTP_PORT'] -match '^\d+$') { $port = [int]$envValues['DEPLOYER_HTTP_PORT'] }
    elseif ((Get-DeployerStateValue $state 'port') -as [int]) { $port = [int](Get-DeployerStateValue $state 'port') }
    return [pscustomobject]@{
        State   = $state
        Runtime = [string](Get-DeployerStateValue $state 'runtime' 'existing')
        Port    = $port
        Env     = $envValues
        Lan     = (Get-DeployerStateValue $state 'lan')
    }
}

function Assert-Admin {
    param([string]$Why)
    if (Test-DeployerIsAdmin) { return $true }
    Write-DeployerInfo "Administrator rights are needed to $Why. Asking Windows..."
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, $Command, '-InstallDir', $InstallDir)
    if ($KeepData) { $argList += '-KeepData' }
    if ($Yes) { $argList += '-Yes' }
    if ($Ref) { $argList += @('-Ref', $Ref) }
    if ($FromSource) { $argList += '-FromSource' }
    $quoted = ($argList | ForEach-Object { ConvertTo-DeployerArgument $_ }) -join ' '
    $p = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $quoted -Verb RunAs -PassThru -Wait
    exit $p.ExitCode
}

function Initialize-Engine {
    param($Ctx, [int]$TimeoutSeconds = 300)
    if (Test-DeployerDockerEngine -Runtime $Ctx.Runtime) { return }
    switch ($Ctx.Runtime) {
        'wsl-engine' { $msg = 'Starting the Docker Engine in WSL' }
        'docker-desktop' { $msg = 'Starting Docker Desktop' }
        default { $msg = 'Waiting for Docker' }
    }
    if (-not (Wait-DeployerDockerEngine -Runtime $Ctx.Runtime -TimeoutSeconds $TimeoutSeconds -WaitingMessage $msg)) {
        throw "The Docker engine ($($Ctx.Runtime)) is not reachable. For Docker Desktop, open it and wait until it says 'Engine running'."
    }
}

function Update-LanForwarding {
    param($Ctx)
    if ($null -eq $Ctx.Lan) { return }
    if (-not (Get-DeployerStateValue $Ctx.Lan 'enabled' $false)) { return }
    if ((Get-DeployerStateValue $Ctx.Lan 'mode' '') -eq 'portproxy') {
        if (Update-DeployerPortProxy -Port $Ctx.Port) { Write-DeployerOk 'LAN port forwarding refreshed' }
    }
}

function Invoke-Start {
    $ctx = Get-Context
    if ($Background) {
        $script:DeployerQuiet = $true
        $script:DeployerLogFile = Join-Path $InstallDir 'logs\deployer.log'
        New-Item -ItemType Directory -Path (Split-Path -Parent $script:DeployerLogFile) -Force | Out-Null
        $log = Get-Item -LiteralPath $script:DeployerLogFile -ErrorAction SilentlyContinue
        if ($log -and $log.Length -gt 1MB) { Move-Item -LiteralPath $log.FullName -Destination "$($log.FullName).1" -Force }
        Write-DeployerLog 'INFO' "Autostart (runtime $($ctx.Runtime))"
    }
    Write-DeployerStep 'Starting Deployer'
    $timeout = if ($Background) { 900 } else { 300 }
    Initialize-Engine -Ctx $ctx -TimeoutSeconds $timeout
    if ($ctx.Runtime -eq 'wsl-engine' -and -not $Background) { Start-DeployerKeepAlive }
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('up', '-d', '--remove-orphans')
    if ($code -ne 0) { throw "docker compose up failed (exit code $code)." }
    Update-LanForwarding -Ctx $ctx
    if ($Background) {
        Write-DeployerLog 'INFO' 'Stack started.'
        if ($ctx.Runtime -eq 'wsl-engine') {
            # Blocks for as long as the user is signed in, keeping the WSL VM (and the site) running.
            Start-DeployerKeepAlive -Wait
        }
        return
    }
    $health = Wait-DeployerHealth -Port $ctx.Port -TimeoutSeconds 240
    if ($health) {
        Write-DeployerOk "Running at http://localhost:$($ctx.Port)"
    } else {
        Write-DeployerWarn "Started, but http://localhost:$($ctx.Port)/v1/health is not answering yet. Check 'deployer logs api'."
    }
}

function Invoke-Stop {
    $ctx = Get-Context
    Write-DeployerStep 'Stopping Deployer'
    if (Test-DeployerDockerEngine -Runtime $ctx.Runtime) {
        $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('stop')
        if ($code -ne 0) { throw "docker compose stop failed (exit code $code)." }
    } else {
        Write-DeployerInfo 'The Docker engine is not running; nothing to stop.'
    }
    if ($ctx.Runtime -eq 'wsl-engine') {
        Stop-DeployerKeepAlive
        Write-DeployerInfo 'The WSL distro will shut down when idle, freeing its memory.'
    }
    Write-DeployerOk 'Stopped. Run "deployer start" to start again (it also starts at your next sign-in).'
}

function Invoke-Restart {
    $ctx = Get-Context
    Initialize-Engine -Ctx $ctx
    if ($Service) {
        $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('restart', $Service)
        if ($code -ne 0) { throw "Restarting $Service failed (exit code $code)." }
        Write-DeployerOk "Restarted $Service"
        return
    }
    [void](Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('stop'))
    Invoke-Start
}

function Invoke-Status {
    $ctx = Get-Context
    Write-DeployerStep 'Deployer status'
    Write-DeployerInfo "Install dir : $InstallDir"
    Write-DeployerInfo "Runtime     : $($ctx.Runtime)"
    Write-DeployerInfo "Version     : $(Get-DeployerStateValue $ctx.State 'ref' 'unknown') (images: $($ctx.Env['DEPLOYER_VERSION']))"
    Write-DeployerInfo "URL         : http://localhost:$($ctx.Port)"
    $task = Get-ScheduledTask -TaskName $script:DeployerTaskName -ErrorAction SilentlyContinue
    Write-DeployerInfo ("Autostart   : {0}" -f $(if ($task) { "scheduled task ($($task.State))" } else { 'not registered' }))
    if ($ctx.Runtime -eq 'wsl-engine') {
        Write-DeployerInfo ("Keep-alive  : {0}" -f $(if (Get-DeployerKeepAliveProcess) { 'running' } else { 'not running' }))
    }
    if (-not (Test-DeployerDockerEngine -Runtime $ctx.Runtime)) {
        Write-DeployerWarn 'Docker engine: not reachable. Run "deployer start".'
        return
    }
    Write-DeployerOk 'Docker engine reachable'
    [void](Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('ps'))
    $health = Get-DeployerHealth -Port $ctx.Port
    if ($health) { Write-DeployerOk "Health: $health" } else { Write-DeployerWarn "Health endpoint http://localhost:$($ctx.Port)/v1/health is not answering." }
}

function Invoke-Logs {
    $ctx = Get-Context
    $composeArgs = @('logs', '--tail', "$Tail")
    if ($Follow) { $composeArgs += '--follow' }
    if ($Service) { $composeArgs += $Service }
    $inv = Get-DeployerComposeInvocation -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments $composeArgs
    & $inv.File @($inv.Args)
}

function Invoke-Compose {
    $ctx = Get-Context
    $composeArgs = @()
    if ($Service) { $composeArgs += $Service }
    $composeArgs += @($Rest | Where-Object { $_ -ne '--' })
    if ($composeArgs.Count -eq 0) { throw 'Usage: deployer compose -- <docker compose arguments>' }
    $inv = Get-DeployerComposeInvocation -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments $composeArgs
    & $inv.File @($inv.Args)
    exit $LASTEXITCODE
}

function Invoke-Update {
    $ctx = Get-Context
    [void](Assert-Admin -Why 'update program files and keep .env permissions locked down')
    $repo = [string](Get-DeployerStateValue $ctx.State 'repo' 'nyx-ulrix/deployer')
    $currentRef = [string](Get-DeployerStateValue $ctx.State 'ref' '')
    $target = Resolve-DeployerRef -Repo $repo -Ref $Ref
    Write-DeployerStep "Updating Deployer from $repo ($currentRef -> $target)"
    $script:DeployerLogFile = Join-Path $InstallDir 'logs\deployer.log'

    $backupFirst = Read-DeployerYesNo -Question 'Take a backup before updating?' -Default $true -NonInteractive:$Yes
    if ($backupFirst) { Invoke-Backup }

    $work = Join-Path $env:TEMP 'deployer-update'
    $root = Get-DeployerSource -Repo $repo -Ref $target -WorkDir $work
    Copy-DeployerFiles -SourceRoot $root -InstallDir $InstallDir

    $mongo = [bool](Get-DeployerStateValue $ctx.State 'managedMongodb' $true)
    $bind = if ($ctx.Env['DEPLOYER_BIND']) { [string]$ctx.Env['DEPLOYER_BIND'] } else { '127.0.0.1' }
    [void](Initialize-DeployerEnv -InstallDir $InstallDir -Port $ctx.Port -MongoEnabled $mongo `
            -ImagePrefix (Get-DeployerImagePrefix -Repo $repo) -Version (Get-DeployerImageVersion -Ref $target) -Bind $bind)
    Write-DeployerOk 'Deploy files updated; .env kept'

    Initialize-Engine -Ctx $ctx
    $mode = Invoke-DeployerImages -InstallDir $InstallDir -Runtime $ctx.Runtime -FromSource:$FromSource
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('up', '-d', '--remove-orphans')
    if ($code -ne 0) {
        Show-DeployerDiagnostics -InstallDir $InstallDir -Runtime $ctx.Runtime
        throw "docker compose up failed (exit code $code)."
    }
    $timeout = if ($mode -eq 'built') { 600 } else { 420 }
    $health = Wait-DeployerHealth -Port $ctx.Port -TimeoutSeconds $timeout
    if (-not $health) {
        Show-DeployerDiagnostics -InstallDir $InstallDir -Runtime $ctx.Runtime
        throw 'Deployer did not become healthy after the update. Your previous backup is in the backups folder.'
    }

    $table = ConvertTo-DeployerStateTable $ctx.State
    $table['ref'] = $target
    $table['updatedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    Save-DeployerState -InstallDir $InstallDir -State $table
    Write-DeployerOk "Updated to $target"
    [void](Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('image', 'prune', '-f'))
}

function Invoke-Backup {
    $ctx = Get-Context
    Initialize-Engine -Ctx $ctx
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $dir = Join-Path $InstallDir "backups\$stamp"
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    if (Test-DeployerIsAdmin) { Set-DeployerPrivateAcl -Path (Join-Path $InstallDir 'backups') }
    Write-DeployerStep "Backing up to $dir"
    $runtimeDir = ConvertTo-DeployerRuntimePath -Runtime $ctx.Runtime -WindowsPath $dir

    Copy-Item -LiteralPath (Join-Path $InstallDir '.env') -Destination (Join-Path $dir 'env.backup')
    Write-DeployerOk '.env copied (contains MASTER_KEY - keep this folder private)'

    # MariaDB: dump inside the container, then copy the file out (avoids console encoding issues).
    $dump = 'export MYSQL_PWD=$MARIADB_ROOT_PASSWORD; exec mariadb-dump -uroot --all-databases --single-transaction --quick --routines --events --triggers --hex-blob --result-file=/tmp/deployer-mariadb.sql'
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('exec', '-T', 'mariadb', 'sh', '-c', $dump)
    if ($code -ne 0) { throw "mariadb-dump failed (exit code $code). Is the stack running?" }
    $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('cp', 'mariadb:/tmp/deployer-mariadb.sql', "$runtimeDir/mariadb.sql")
    [void](Invoke-DeployerComposeCapture -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('exec', '-T', 'mariadb', 'rm', '-f', '/tmp/deployer-mariadb.sql'))
    if ($code -ne 0) { throw "Copying the MariaDB dump failed (exit code $code)." }
    Write-DeployerOk 'MariaDB dumped to mariadb.sql'

    if ($ctx.Env['COMPOSE_PROFILES'] -match 'mongodb') {
        $mongoDump = 'exec mongodump --quiet --username=$MONGO_INITDB_ROOT_USERNAME --password=$MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase=admin --gzip --archive=/tmp/deployer-mongodb.archive.gz'
        $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('exec', '-T', 'mongodb', 'sh', '-c', $mongoDump)
        if ($code -ne 0) { throw "mongodump failed (exit code $code)." }
        $code = Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('cp', 'mongodb:/tmp/deployer-mongodb.archive.gz', "$runtimeDir/mongodb.archive.gz")
        [void](Invoke-DeployerComposeCapture -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments @('exec', '-T', 'mongodb', 'rm', '-f', '/tmp/deployer-mongodb.archive.gz'))
        if ($code -ne 0) { throw "Copying the MongoDB dump failed (exit code $code)." }
        Write-DeployerOk 'MongoDB dumped to mongodb.archive.gz'
    } else {
        Write-DeployerInfo 'Managed MongoDB is disabled; skipped.'
    }

    $readme = @(
        "Deployer backup $stamp",
        '',
        'env.backup           copy of .env (MASTER_KEY decrypts secrets stored in MariaDB)',
        'mariadb.sql          mariadb-dump --all-databases',
        'mongodb.archive.gz   mongodump --gzip --archive (if managed MongoDB is enabled)',
        '',
        'Restore (stack running, same MASTER_KEY in .env):',
        '  deployer compose -- cp <backup>/mariadb.sql mariadb:/tmp/restore.sql',
        '  deployer compose -- exec -T mariadb sh -c "mariadb -uroot -p$MARIADB_ROOT_PASSWORD < /tmp/restore.sql"',
        '  deployer compose -- cp <backup>/mongodb.archive.gz mongodb:/tmp/restore.gz',
        '  deployer compose -- exec -T mongodb sh -c "mongorestore --drop --gzip --archive=/tmp/restore.gz -u $MONGO_INITDB_ROOT_USERNAME -p $MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase admin"',
        '',
        'For moving to another computer, prefer the encrypted export in the dashboard (Instance settings > Export).'
    )
    Write-DeployerTextFile -Path (Join-Path $dir 'README.txt') -Lines $readme
    Write-DeployerOk "Backup complete: $dir"
}

function Invoke-Open {
    $ctx = Get-Context
    Open-DeployerUrl -Url "http://localhost:$($ctx.Port)/"
}

function Invoke-Config {
    $ctx = Get-Context
    Write-DeployerStep 'Deployer configuration'
    foreach ($p in $ctx.State.PSObject.Properties) {
        $value = if ($p.Value -is [System.Management.Automation.PSCustomObject]) { ($p.Value | ConvertTo-Json -Compress) } else { $p.Value }
        Write-DeployerInfo ('{0,-22} {1}' -f $p.Name, $value)
    }
    Write-Host ''
    Write-DeployerInfo ".env ($InstallDir\.env) - secrets hidden:"
    foreach ($key in $ctx.Env.Keys) {
        $value = [string]$ctx.Env[$key]
        if ($key -match 'PASSWORD|SECRET|MASTER_KEY|TOKEN') {
            $value = if ($value) { '********' } else { '(empty)' }
        }
        Write-DeployerInfo ('{0,-24} {1}' -f $key, $value)
    }
}

function Invoke-Uninstall {
    $ctx = Get-Context
    [void](Assert-Admin -Why 'remove the scheduled task, firewall rules and files')
    Write-DeployerStep 'Uninstall Deployer'
    if ($KeepData) {
        Write-DeployerInfo 'Containers, the scheduled task and program files will be removed.'
        Write-DeployerInfo 'Kept: databases (Docker volumes / WSL distro), .env and backups.'
    } else {
        Write-DeployerWarn 'This PERMANENTLY deletes all Deployer databases and settings on this PC:'
        $extra = if ($ctx.Runtime -eq 'wsl-engine') { ' and the WSL distro "deployer"' } else { '' }
        Write-DeployerWarn ('containers, Docker volumes, .env, backups' + $extra + '.')
        Write-DeployerInfo 'Tip: run "deployer backup" or export from the dashboard first, or use -KeepData.'
    }
    if (-not $Yes) {
        $answer = Read-Host '    Type UNINSTALL to continue'
        if ($answer -cne 'UNINSTALL') { Write-DeployerInfo 'Cancelled.'; return }
    }

    Set-Location -LiteralPath $env:TEMP
    Unregister-DeployerTask
    Write-DeployerOk 'Scheduled task removed'

    if (Test-DeployerDockerEngine -Runtime $ctx.Runtime) {
        $downArgs = @('--profile', 'mongodb', 'down', '--remove-orphans')
        if (-not $KeepData) { $downArgs += '--volumes' }
        [void](Invoke-DeployerCompose -InstallDir $InstallDir -Runtime $ctx.Runtime -Arguments $downArgs)
        Write-DeployerOk 'Containers removed'
    } else {
        Write-DeployerWarn 'Docker engine not reachable; containers were not removed.'
    }

    if ($ctx.Runtime -eq 'wsl-engine') {
        Stop-DeployerKeepAlive
        if (-not $KeepData) {
            [void](Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('--unregister', $script:DeployerDistro) -TimeoutSeconds 300)
            Write-DeployerOk 'WSL distro "deployer" removed'
        } else {
            [void](Invoke-DeployerNative -FilePath (Get-DeployerWslExe) -ArgumentList @('--terminate', $script:DeployerDistro) -TimeoutSeconds 120)
        }
    }

    Remove-DeployerFirewallRule
    Remove-DeployerPortProxy -Port $ctx.Port
    Remove-DeployerUserPath -Directory $InstallDir
    Write-DeployerOk 'Firewall rule, port forwarding and PATH entry removed'
    $lanMode = if ($ctx.Lan) { Get-DeployerStateValue $ctx.Lan 'mode' '' } else { '' }
    if ($lanMode -eq 'mirrored') {
        Write-DeployerInfo 'WSL mirrored networking was left on in %USERPROFILE%\.wslconfig (a .deployer-backup-* copy of your old file is next to it).'
    }

    $keep = if ($KeepData) { @('.env', 'backups', 'wsl') } else { @() }
    Get-ChildItem -LiteralPath $InstallDir -Force | Where-Object { $keep -notcontains $_.Name } | ForEach-Object {
        try {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
        } catch {
            Write-DeployerWarn "Could not remove $($_.FullName): $($_.Exception.Message)"
        }
    }
    if (-not $KeepData) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($ctx.Runtime -eq 'docker-desktop') {
        Write-DeployerInfo 'Docker Desktop itself was not removed; uninstall it from Windows Settings > Apps if you no longer need it.'
    }
    Write-DeployerOk 'Deployer has been uninstalled.'
}

try {
    switch ($Command.ToLowerInvariant()) {
        'status' { Invoke-Status }
        'start' { Invoke-Start }
        'stop' { Invoke-Stop }
        'restart' { Invoke-Restart }
        'logs' { Invoke-Logs }
        'update' { Invoke-Update }
        'backup' { Invoke-Backup }
        'open' { Invoke-Open }
        'config' { Invoke-Config }
        'compose' { Invoke-Compose }
        'uninstall' { Invoke-Uninstall }
        { $_ -in @('help', '-h', '--help', '/?') } { Show-Help }
        default {
            Write-DeployerError "Unknown command '$Command'."
            Show-Help
            exit 2
        }
    }
} catch {
    Write-DeployerError $_.Exception.Message
    Write-DeployerLog 'ERROR' ($_ | Out-String)
    exit 1
}
