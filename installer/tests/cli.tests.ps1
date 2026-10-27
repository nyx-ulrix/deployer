# Regression checks for the everyday commands deployer.ps1 hands to the Python client (docs/CLI.md), the way
# deployer.sh does: before any administrator re-run, with the arguments exactly as typed and the client's
# exit code. Changes nothing outside %TEMP%:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\cli.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\common.ps1')

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

$cliPath = Join-Path $PSScriptRoot '..\deployer.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($cliPath, [ref]$null, [ref]$null)
$list = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$CliCommands' }, $true)
. ([scriptblock]::Create($list.Extent.Text))
foreach ($name in @('Test-CliSignedIn', 'Test-CliCommand', 'Find-Python')) {
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true)
    . ([scriptblock]::Create($fn.Extent.Text))
}

function Start-Cli {
    # Runs deployer.ps1 the way deployer.cmd does: powershell.exe -File <script> %*
    param([string]$Script, [string[]]$Typed, [string]$PathVar = $env:PATH)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $psi.Arguments = ((@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Script) + $Typed) | ForEach-Object { ConvertTo-DeployerArgument $_ }) -join ' '
    $psi.EnvironmentVariables['PATH'] = $PathVar
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $text = $p.StandardOutput.ReadToEnd()
    [void]$p.WaitForExit(60000)
    return [pscustomobject]@{ ExitCode = $p.ExitCode; Output = $text }
}

# 1. The same commands as deployer.sh; `oauth` only in a normal window, signed in, and not from Deployer Control.
$sh = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\deployer.sh') -Raw
$shList = @(([regex]::Match($sh, '(?m)^\s*(login\|[a-z|-]+)\)').Groups[1].Value -split '\|') | Where-Object { $_ -ne 'oauth-cli' })
Assert-That ((($shList | Sort-Object) -join ' ') -eq ((@($CliCommands) | Sort-Object) -join ' ')) "the commands match deployer.sh ($($CliCommands -join ', '))"

$dir = Join-Path $env:TEMP ('deployer-cli-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $dir | Out-Null
$saved = @{ DEPLOYER_TOKEN = $env:DEPLOYER_TOKEN; DEPLOYER_CONFIG = $env:DEPLOYER_CONFIG; DEPLOYER_TEST_ARGV = $env:DEPLOYER_TEST_ARGV }
try {
    $env:DEPLOYER_TOKEN = $null
    $env:DEPLOYER_CONFIG = Join-Path $dir 'cli.json'
    Assert-That ((Test-CliCommand -Name 'deploy' -IsAdmin $true -InstallDirGiven $false) -and -not (Test-CliCommand -Name 'status' -IsAdmin $false -InstallDirGiven $false)) 'deploy goes to Python, status does not'
    Assert-That (-not (Test-CliCommand -Name 'oauth' -IsAdmin $false -InstallDirGiven $false)) 'oauth stays here when not signed in'
    Set-Content -LiteralPath $env:DEPLOYER_CONFIG -Value '{}' -Encoding ASCII
    Assert-That (Test-CliCommand -Name 'oauth' -IsAdmin $false -InstallDirGiven $false) 'oauth goes to Python once signed in (DEPLOYER_CONFIG)'
    Assert-That (-not (Test-CliCommand -Name 'oauth' -IsAdmin $true -InstallDirGiven $false) -and -not (Test-CliCommand -Name 'oauth' -IsAdmin $false -InstallDirGiven $true)) 'oauth stays here elevated or with -InstallDir'
    Remove-Item -LiteralPath $env:DEPLOYER_CONFIG
    $env:DEPLOYER_TOKEN = 'dpt_test'
    Assert-That (Test-CliCommand -Name 'oauth' -IsAdmin $false -InstallDirGiven $false) 'DEPLOYER_TOKEN counts as signed in'
    $env:DEPLOYER_TOKEN = $null

    # 2. A copy of the launcher next to a stand-in deployer_cli.py that records what it was given.
    $inst = Join-Path $dir 'installer'
    New-Item -ItemType Directory -Path (Join-Path $inst 'lib') | Out-Null
    Copy-Item -LiteralPath $cliPath -Destination $inst
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\lib\common.ps1') -Destination (Join-Path $inst 'lib')
    Set-Content -LiteralPath (Join-Path $inst 'deployer_cli.py') -Encoding ASCII -Value @(
        'import json, os, sys',
        "open(os.environ['DEPLOYER_TEST_ARGV'], 'w').write(json.dumps(sys.argv[1:]))",
        'sys.exit(7)'
    )
    $argvFile = Join-Path $dir 'argv.json'
    $env:DEPLOYER_TEST_ARGV = $argvFile
    $launcher = Join-Path $inst 'deployer.ps1'

    # No Python on PATH (py.exe lives in C:\Windows, the Store stub in WindowsApps): one line naming winget.
    $r = Start-Cli -Script $launcher -Typed @('whoami') -PathVar (Join-Path $env:SystemRoot 'System32')
    Assert-That ($r.ExitCode -eq 1 -and $r.Output -match 'winget install Python\.Python\.3\.12' -and -not (Test-Path -LiteralPath $argvFile)) 'without Python it says how to install it and exits 1'

    if (Find-Python) {
        $typed = @('Env', 'set', 'app', 'KEY', 'say "hi"', '', '--tail', '50', '-Json')
        $r = Start-Cli -Script $launcher -Typed $typed
        $got = (Get-Content -LiteralPath $argvFile -Raw).Trim()
        Assert-That ($r.ExitCode -eq 7) "the client's exit code comes back (got $($r.ExitCode))"
        Assert-That ($got -eq '["env", "set", "app", "KEY", "say \"hi\"", "", "--tail", "50", "-Json"]') "the arguments arrive as typed: $got"

        # Called from PowerShell itself (not deployer.cmd): rebuilt from what was bound.
        Remove-Item -LiteralPath $argvFile
        & $launcher deploy app --wait -Json
        $got = (Get-Content -LiteralPath $argvFile -Raw).Trim()
        Assert-That ($LASTEXITCODE -eq 7 -and $got -eq '["deploy", "app", "--wait", "--json"]') "a call from PowerShell passes them too: $got"
    } else {
        Write-Host 'skip the client runs (no Python 3.9+ on this machine)'
    }

    # 3. py -3 first; the Microsoft Store stub is skipped; nothing usable means $null.
    $script:onPath = @{ py = @('C:\Windows\py.exe'); python = @('C:\Python312\python.exe'); python3 = @() }
    function Get-Command { param([string]$Name, $CommandType, $ErrorAction) foreach ($s in @($script:onPath[$Name])) { [pscustomobject]@{ Source = $s } } }
    function Invoke-DeployerNative {
        param($FilePath, $ArgumentList, $TimeoutSeconds)
        [pscustomobject]@{ ExitCode = $(if ($FilePath -like '*\WindowsApps\*') { 9009 } else { 0 }) }
    }
    $found = Find-Python
    Assert-That ($found.File -eq 'C:\Windows\py.exe' -and ($found.Args -join ' ') -eq '-3') 'py -3 is preferred'
    $script:onPath = @{ py = @(); python = @('C:\Users\me\AppData\Local\Microsoft\WindowsApps\python.exe'); python3 = @('C:\Python312\python3.exe') }
    Assert-That ((Find-Python).File -eq 'C:\Python312\python3.exe') 'the Store stub is skipped'
    $script:onPath = @{ py = @(); python = @('C:\Users\me\AppData\Local\Microsoft\WindowsApps\python.exe'); python3 = @() }
    Assert-That ($null -eq (Find-Python)) 'only the Store stub means no Python'
    Remove-Item -LiteralPath function:\Get-Command, function:\Invoke-DeployerNative
} finally {
    foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'CLI hand-over checks passed'
