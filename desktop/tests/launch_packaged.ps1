<#
    launch_packaged.ps1 — start the PACKAGED app for verification.

    Uses the installed build when present, otherwise the unpacked build produced
    by `node scripts\dist.js`. Provider credentials that the build machine
    exports globally are removed so the run behaves like a fresh user machine.

    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -File desktop\tests\launch_packaged.ps1 -Clean -Port 9223
      ... -Unpacked        # use desktop\release\win-unpacked instead of the install
#>
param(
    [switch]$Clean,
    [switch]$Unpacked,
    [int]$Port = 9223
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$installedExe = Join-Path $env:LOCALAPPDATA 'Programs\AragonMovie\AragonMovie.exe'
$unpackedExe = Join-Path $RepoRoot 'desktop\release\win-unpacked\AragonMovie.exe'

if ($Unpacked -or -not (Test-Path -LiteralPath $installedExe)) {
    $exe = $unpackedExe
}
else {
    $exe = $installedExe
}
if (-not (Test-Path -LiteralPath $exe)) {
    throw "AragonMovie.exe not found. Build it first: node desktop\scripts\dist.js"
}

if ($Clean) {
    Write-Host '==> Removing %APPDATA%\AragonMovie (factory reset)'
    Remove-Item -LiteralPath (Join-Path $env:APPDATA 'AragonMovie') -Recurse -Force -ErrorAction SilentlyContinue
}

$names = @(
    'FAST_LLM_API_KEY', 'JUDGE_LLM_API_KEY', 'ALI_TOKEN_PLAN_API_KEY',
    'TTS_API_KEY', 'TTS_NATIVE_API_KEY', 'DOUBAO_API_KEY', 'NANO_BANANA_API_KEY',
    'MIDJOURNEY_API_KEY', 'VEO3_API_KEY', 'SORA2_API_KEY', 'AGENT_API_KEY',
    'ARK_API_KEY', 'GEMINI_API_KEY'
)
foreach ($name in $names) { Remove-Item -Path "env:$name" -ErrorAction SilentlyContinue }

Write-Host "==> launching $exe (debug port $Port)"
& $exe "--remote-debugging-port=$Port"
