# Regression checks for the administrator window a command re-launches itself in (audit A-142): on an
# error it waits for Enter instead of closing, and it logs to logs\deployer.log. Changes nothing outside %TEMP%:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\elevated.tests.ps1
$ErrorActionPreference = 'Stop'

function Assert-That {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "FAIL: $Message" }
    Write-Host "ok   $Message"
}

function Start-Cli {
    # set-port 8150 fails before it needs administrator rights (the app port range).
    param([string]$Dir, [switch]$Elevated)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot '..\deployer.ps1')`" set-port 8150 -InstallDir `"$Dir`""
    if ($Elevated) { $psi.Arguments += ' -Elevated' }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.CreateNoWindow = $true
    return [System.Diagnostics.Process]::Start($psi)
}

$dir = Join-Path $env:TEMP ('deployer-elevated-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $dir | Out-Null
try {
    Set-Content -LiteralPath (Join-Path $dir 'runtime.json') -Value '{"runtime":"existing"}' -Encoding ASCII
    $log = Join-Path $dir 'logs\deployer.log'

    $p = Start-Cli -Dir $dir
    Assert-That ($p.WaitForExit(30000) -and $p.ExitCode -eq 1) 'a normal window exits on an error without waiting'
    Assert-That (-not (Test-Path -LiteralPath $log)) 'a normal window does not start a log'

    $p = Start-Cli -Dir $dir -Elevated
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline -and -not ((Test-Path -LiteralPath $log) -and (Get-Content -LiteralPath $log -Raw) -match '\[ERROR\] Port 8150')) {
        Start-Sleep -Milliseconds 200
    }
    Assert-That ((Get-Content -LiteralPath $log -Raw) -match '\[ERROR\] Port 8150') 'the administrator window logs the error to logs\deployer.log'
    Assert-That (-not $p.WaitForExit(1500)) 'the administrator window stays open after the error'
    $p.StandardInput.WriteLine()
    Assert-That ($p.WaitForExit(30000) -and $p.ExitCode -eq 1) 'Enter closes it with exit code 1'
} finally {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'elevated window checks passed'
