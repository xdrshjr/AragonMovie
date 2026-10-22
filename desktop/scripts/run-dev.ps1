<#
    run-dev.ps1 — launch the Electron shell against the freshly built bundles
    without packaging anything.

    - ARAGON_APP_SOURCE points the backend at build\desktop\app (a clean copy of
      the Python pipeline, no .env, no user data) so first-run onboarding can be
      exercised exactly like on a user machine.
    - ARAGON_WEB_SOURCE is picked up automatically from build\desktop\web.

    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -File desktop\scripts\run-dev.ps1
      ... -Clean        # wipe workspace + settings first (forces first-run wizard)
      ... -DebugPort 9222
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$ScrubCredentials,
    [int]$DebugPort = 9222
)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
$DesktopDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $DesktopDir
$AppDir = Join-Path $RepoRoot 'build\desktop\app'

if (-not (Test-Path -LiteralPath (Join-Path $AppDir 'backend\main.py'))) {
    throw "Python pipeline copy not found at $AppDir — run: node desktop\scripts\build-app-code.js"
}
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'build\desktop\web\server.js'))) {
    throw "Web bundle not found — run: node desktop\scripts\build-web.js"
}

if ($Clean) {
    Write-Host '==> Cleaning workspace + desktop state (first-run simulation)'
    Remove-Item -LiteralPath (Join-Path $AppDir 'backend\data') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $env:APPDATA 'AragonMovie') -Recurse -Force -ErrorAction SilentlyContinue
}

# The build machine exports real provider keys globally. A user machine does
# not, so a first-run test has to hide them to reproduce onboarding.
if ($ScrubCredentials) {
    Write-Host '==> Scrubbing provider credentials from the child environment'
    $names = @(
        'FAST_LLM_API_KEY', 'JUDGE_LLM_API_KEY', 'ALI_TOKEN_PLAN_API_KEY',
        'TTS_API_KEY', 'TTS_NATIVE_API_KEY', 'DOUBAO_API_KEY', 'NANO_BANANA_API_KEY',
        'MIDJOURNEY_API_KEY', 'VEO3_API_KEY', 'SORA2_API_KEY', 'AGENT_API_KEY',
        'ARK_API_KEY', 'GEMINI_API_KEY'
    )
    foreach ($name in $names) {
        Remove-Item -Path "env:$name" -ErrorAction SilentlyContinue
    }
}

$env:ARAGON_APP_SOURCE = $AppDir
if (-not $env:ARAGON_FFMPEG_DIR) {
    $env:ARAGON_FFMPEG_DIR = Join-Path $AppDir 'bin'
}

Set-Location $DesktopDir
Write-Host "==> electron . --dev --remote-debugging-port=$DebugPort"
& npx.cmd electron . --dev "--remote-debugging-port=$DebugPort"
