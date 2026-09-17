<#
.SYNOPSIS
    Builds DeployerSetup.exe (setup wizard + Deployer Control) with the C# compiler that ships with
    Windows (.NET Framework 4.8). No SDK or NuGet packages needed.

.DESCRIPTION
    Outputs (default: <repo>\dist):
      DeployerSetup.exe            requireAdministrator manifest - the file people download
      DeployerSetup.selftest.exe   same code with an asInvoker manifest, used by CI:
                                   DeployerSetup.selftest.exe /selftest <folder>

    Embedded as resources: installer\install.ps1, installer\deployer.ps1, installer\lib\*,
    installer\wsl\*, deploy\docker-compose.yml, deploy\Caddyfile, deploy\.env.example.

.PARAMETER Version
    Version shown in the app and written to the file properties. Default: __version__ from
    api\app\__init__.py.

.PARAMETER Repo
    GitHub owner/repo the exe installs from (forks: pass your own). Default nyx-ulrix/deployer.

.PARAMETER Ref
    Release tag or branch passed to install.ps1 -Ref. Default: main (release.yml passes the tag).

.PARAMETER OutDir
    Output folder. Default: <repo>\dist.
#>
[CmdletBinding()]
param(
    [string]$Version = '',
    [string]$Repo = 'nyx-ulrix/deployer',
    [string]$Ref = '',
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = (Resolve-Path (Join-Path $here '..\..')).Path

if (-not $Version) {
    $init = Get-Content -LiteralPath (Join-Path $root 'api\app\__init__.py') -Raw
    if ($init -notmatch '__version__\s*=\s*["'']([^"'']+)["'']') { throw 'Could not read __version__ from api\app\__init__.py; pass -Version.' }
    $Version = $Matches[1]
}
$Version = $Version.TrimStart('v')
if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.\-]+)?$') { throw "Version '$Version' is not semantic (e.g. 0.1.0 or 0.2.0-rc.1)." }
$numericVersion = '{0}.{1}.{2}.0' -f $Matches[1], $Matches[2], $Matches[3]
# Release builds pass the tag explicitly (release.yml). Anything else is a development build whose
# version tag may not exist on GitHub yet, so it installs from the main branch.
if (-not $Ref) { $Ref = 'main' }
if ($Repo -notmatch '^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$') { throw "Repo '$Repo' must look like owner/name." }
if (-not $OutDir) { $OutDir = Join-Path $root 'dist' }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

$csc = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $csc)) { $csc = Join-Path $env:SystemRoot 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path -LiteralPath $csc)) { throw '.NET Framework 4.x C# compiler (csc.exe) not found.' }

$obj = Join-Path $here 'obj'
if (Test-Path -LiteralPath $obj) { Remove-Item -LiteralPath $obj -Recurse -Force }
New-Item -ItemType Directory -Path $obj -Force | Out-Null

Write-Host "Building Deployer Setup $Version ($Repo @ $Ref)" -ForegroundColor Cyan

# --- Icon (drawn by src\Logo.cs, the same code the app uses) ---------------------------------------
if (-not ('DeployerSetup.Logo' -as [type])) {
    Add-Type -TypeDefinition (Get-Content -LiteralPath (Join-Path $here 'src\Logo.cs') -Raw) -ReferencedAssemblies System.Drawing
}
$icoPath = Join-Path $obj 'Deployer.ico'
[System.IO.File]::WriteAllBytes($icoPath, [DeployerSetup.Logo]::BuildIco([int[]](16, 20, 24, 32, 40, 48, 64, 256)))

# --- Version info -----------------------------------------------------------------------------------
function ConvertTo-CSharpString {
    param([string]$Value)
    return '"' + ($Value -replace '\\', '\\' -replace '"', '\"') + '"'
}
$assemblyInfo = @(
    'using System.Reflection;',
    "[assembly: AssemblyVersion(""$numericVersion"")]",
    "[assembly: AssemblyFileVersion(""$numericVersion"")]",
    "[assembly: AssemblyInformationalVersion($(ConvertTo-CSharpString $Version))]",
    '[assembly: AssemblyDescription("Deployer Setup and Deployer Control")]',
    "[assembly: AssemblyMetadata(""DeployerRepo"", $(ConvertTo-CSharpString $Repo))]",
    "[assembly: AssemblyMetadata(""DeployerRef"", $(ConvertTo-CSharpString $Ref))]"
)
$assemblyInfoPath = Join-Path $obj 'AssemblyInfo.g.cs'
[System.IO.File]::WriteAllLines($assemblyInfoPath, $assemblyInfo, (New-Object System.Text.UTF8Encoding($false)))

# --- Payload (normalised line endings: bash and Caddy need LF, PowerShell 5.1 prefers CRLF) ----------
$payloadFiles = New-Object System.Collections.Generic.List[string]
foreach ($rel in @('installer\install.ps1', 'installer\deployer.ps1', 'deploy\docker-compose.yml', 'deploy\Caddyfile', 'deploy\.env.example')) {
    $payloadFiles.Add($rel)
}
foreach ($dir in @('installer\lib', 'installer\wsl')) {
    Get-ChildItem -LiteralPath (Join-Path $root $dir) -File | Sort-Object Name | ForEach-Object { $payloadFiles.Add("$dir\$($_.Name)") }
}
# Everything else under deploy\ (e.g. sidecar build contexts, entrypoint scripts), never secrets.
$deployRoot = Join-Path $root 'deploy'
Get-ChildItem -LiteralPath $deployRoot -Recurse -File -Force | Sort-Object FullName | ForEach-Object {
    $rel = 'deploy\' + $_.FullName.Substring($deployRoot.Length + 1)
    $isSecret = ($_.Name -eq '.env') -or ($_.Name -like '.env.*' -and $_.Name -ne '.env.example')
    if (-not $isSecret -and -not $payloadFiles.Contains($rel)) { $payloadFiles.Add($rel) }
}
$resourceArgs = @()
foreach ($rel in $payloadFiles) {
    $source = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $source)) { throw "Payload file missing: $rel" }
    $staged = Join-Path $obj ("payload\" + $rel)
    New-Item -ItemType Directory -Path (Split-Path -Parent $staged) -Force | Out-Null
    $leaf = Split-Path -Leaf $rel
    if ($rel -match '\.(ps1|cmd)$') {
        $text = [System.IO.File]::ReadAllText($source)
        $text = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
        [System.IO.File]::WriteAllText($staged, $text, (New-Object System.Text.UTF8Encoding($false)))
    } elseif ($rel -match '\.(sh|ya?ml|conf|json|example|txt|md|py|js|toml|ini)$' -or $leaf -in @('Caddyfile', 'Dockerfile')) {
        # Used inside Linux containers / WSL: LF line endings.
        $text = [System.IO.File]::ReadAllText($source) -replace "`r`n", "`n"
        [System.IO.File]::WriteAllText($staged, $text, (New-Object System.Text.UTF8Encoding($false)))
    } else {
        Copy-Item -LiteralPath $source -Destination $staged -Force
    }
    $name = 'payload/' + ($rel -replace '\\', '/')
    $resourceArgs += "/resource:$staged,$name"
}
$resourceArgs += "/resource:$icoPath,Deployer.ico"

$sources = @(Get-ChildItem -LiteralPath (Join-Path $here 'src') -Filter '*.cs' -File | Sort-Object Name | ForEach-Object { $_.FullName }) + $assemblyInfoPath
$references = @('System.dll', 'System.Core.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll', 'System.Management.dll', 'System.Web.Extensions.dll')

function Invoke-Csc {
    param([string]$Manifest, [string]$Output)
    $cscArgs = @(
        '/nologo', '/target:winexe', '/platform:anycpu', '/optimize+', '/debug-', '/codepage:65001',
        '/warn:4', '/warnaserror+', '/highentropyva+', '/utf8output',
        "/win32icon:$icoPath", "/win32manifest:$Manifest", "/out:$Output"
    )
    $cscArgs += ($references | ForEach-Object { "/reference:$_" })
    $cscArgs += $resourceArgs
    $cscArgs += $sources
    $rsp = Join-Path $obj ([System.IO.Path]::GetFileNameWithoutExtension($Output) + '.rsp')
    $quoted = $cscArgs | ForEach-Object { if ($_ -match '\s') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }
    [System.IO.File]::WriteAllLines($rsp, [string[]]$quoted, (New-Object System.Text.UTF8Encoding($false)))
    # No 2>&1 here: with $ErrorActionPreference = 'Stop', Windows PowerShell 5.1 turns redirected native
    # stderr into a terminating NativeCommandError. csc prints its diagnostics on stdout anyway.
    & $csc "@$rsp" | ForEach-Object { Write-Host "    $_" }
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "csc.exe failed with exit code $code while building $([System.IO.Path]::GetFileName($Output))." }
    Write-Host "    [ok] $Output" -ForegroundColor Green
}

$manifest = Join-Path $here 'app.manifest'
$selftestManifest = Join-Path $obj 'app.selftest.manifest'
$manifestText = [System.IO.File]::ReadAllText($manifest)
if ($manifestText -notmatch 'level="requireAdministrator"') { throw 'app.manifest must request requireAdministrator.' }
[System.IO.File]::WriteAllText($selftestManifest, ($manifestText -replace 'level="requireAdministrator"', 'level="asInvoker"'), (New-Object System.Text.UTF8Encoding($false)))

$exe = Join-Path $OutDir 'DeployerSetup.exe'
$selftestExe = Join-Path $OutDir 'DeployerSetup.selftest.exe'
Invoke-Csc -Manifest $manifest -Output $exe
Invoke-Csc -Manifest $selftestManifest -Output $selftestExe

foreach ($file in @($exe, $selftestExe)) {
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host ('    {0,-28} {1,8:N0} KB  sha256 {2}' -f ([System.IO.Path]::GetFileName($file)), ((Get-Item -LiteralPath $file).Length / 1KB), $hash)
}
