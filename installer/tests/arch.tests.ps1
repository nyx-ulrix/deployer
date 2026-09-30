# Regression check for ARM64 PCs (audit A-066): preflight refuses them up front instead of starting a
# local image build that can never succeed. Runs install.ps1 -DryRun, which changes nothing:
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\arch.tests.ps1
$ErrorActionPreference = 'Stop'

$dir = Join-Path $env:TEMP ('deployer-arch-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$env:PROCESSOR_ARCHITEW6432 = 'ARM64'
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot '..\install.ps1') -DryRun -InstallDir $dir *>&1 | Out-String
if ($out -notmatch '##deployer:check arch fail .*Intel/AMD 64-bit PCs only') { throw "FAIL: ARM64 is not refused in preflight:`n$out" }
if ($out -match 'images locally') { throw 'FAIL: ARM64 still plans a local image build' }
Write-Host 'ok   ARM64 fails preflight with a clear message'
