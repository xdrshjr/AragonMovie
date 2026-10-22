<#
    verify-python-runtime.ps1

    Verifies the portable runtime produced by build-python-runtime.ps1:
      1. build\desktop\python\python.exe runs and reports its version
      2. the whole backend dependency set imports inside the bundled runtime
      3. backend.main (FastAPI app + settings) imports without raising
      4. ffmpeg / ffprobe resolve through build\desktop\app\bin (bundled, via PATH)
      5. `python -m uvicorn backend.main:app` serves GET /health -> 200 with JSON

    Exit code is 0 only when every check passes.

    NOTE on sys.path: python312._pth makes the embedded interpreter run in
    isolated mode (sys.flags.isolated = 1), which means PYTHONPATH is IGNORED by
    design. PYTHONPATH is still set below (as specified) and every app-import
    check additionally inserts the repo root into sys.path, and uvicorn is
    started with --app-dir <repo root> so the backend package is importable.

    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -File build\desktop\verify-python-runtime.ps1
#>
[CmdletBinding()]
param(
    [int]$Port = 8799,
    [int]$HealthTimeoutSeconds = 40
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
$ScriptDir = $PSScriptRoot
$PythonDir = Join-Path $ScriptDir 'python'
$PythonExe = Join-Path $PythonDir 'python.exe'
$PthPath   = Join-Path $PythonDir 'python312._pth'
$BinDir    = Join-Path $ScriptDir 'app\bin'
$FfmpegExe = Join-Path $BinDir 'ffmpeg.exe'
$FfprobeExe = Join-Path $BinDir 'ffprobe.exe'
$RepoRoot  = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$TmpDir    = Join-Path $ScriptDir '.tmp'
$HealthUrl = "http://127.0.0.1:$Port/health"

$script:Failures = New-Object System.Collections.ArrayList

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host "==> $Text" -ForegroundColor Cyan
}
function Add-Pass([string]$Text) {
    Write-Host "  [ OK ] $Text" -ForegroundColor Green
}
function Add-Fail([string]$Text) {
    Write-Host "  [FAIL] $Text" -ForegroundColor Red
    [void]$script:Failures.Add($Text)
}

# Run a native command, capturing stdout+stderr as plain strings.
# ($ErrorActionPreference = 'Stop' would otherwise turn any stderr output into
#  a terminating NativeCommandError and swallow the real traceback.)
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $FilePath @Arguments 2>&1 | ForEach-Object { [string]$_ })
        return [PSCustomObject]@{
            Output   = $lines
            ExitCode = $LASTEXITCODE
        }
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

# --------------------------------------------------------------------------- #
# 0. Artifacts must exist, and environment setup
# --------------------------------------------------------------------------- #
Write-Step 'Runtime artifacts'
foreach ($required in @($PythonExe, $PthPath, $FfmpegExe, $FfprobeExe)) {
    if (Test-Path -LiteralPath $required) {
        Add-Pass ((Split-Path -Leaf $required) + ' present: ' + $required)
    }
    else {
        Add-Fail "missing artifact: $required (run build-python-runtime.ps1 first)"
    }
}
if ($script:Failures.Count -gt 0) {
    Write-Host ''
    Write-Host 'Verification aborted: runtime artifacts are missing.' -ForegroundColor Red
    exit 1
}

# PYTHONPATH as specified (informational only under the embedded _pth runtime)
$env:PYTHONPATH = $RepoRoot
# Prepend the bundled binaries so plain `ffmpeg` / `ffprobe` resolve to the bundle
$env:PATH = "$BinDir;$env:PATH"
$env:PYTHONUNBUFFERED = '1'
if (-not (Test-Path -LiteralPath $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null }

Write-Host "  repo root : $RepoRoot"
Write-Host "  runtime   : $PythonDir"
Write-Host "  bin       : $BinDir"
Write-Host "  PYTHONPATH: $env:PYTHONPATH (ignored by _pth isolated mode - see NOTE in this script)"

# --------------------------------------------------------------------------- #
# 1. Interpreter runs
# --------------------------------------------------------------------------- #
Write-Step 'Interpreter'
$versionResult = Invoke-Native -FilePath $PythonExe -Arguments @('-c', 'import sys; print(sys.version)')
$versionOut = $versionResult.Output
if ($versionResult.ExitCode -ne 0) {
    Add-Fail "python.exe -c 'import sys; print(sys.version)' failed (exit $($versionResult.ExitCode)): $($versionOut -join ' ')"
}
else {
    $versionText = ($versionOut | Out-String).Trim()
    Write-Host "  version   : $versionText"
    if ($versionText -match '^3\.12\.') { Add-Pass 'CPython 3.12 runtime works' }
    else { Add-Fail "unexpected CPython version string: $versionText" }
}

# _pth must contain exactly the four expected lines
$pthLines = @(Get-Content -LiteralPath $PthPath)
$expectedPth = @('python312.zip', '.', 'Lib\site-packages', 'import site')
if (($pthLines.Count -eq $expectedPth.Count) -and (($pthLines -join '|') -eq ($expectedPth -join '|'))) {
    Add-Pass "python312._pth is correct ($($pthLines -join ' ; '))"
}
else {
    Add-Fail "python312._pth mismatch: $($pthLines -join ' ; ')"
}

# --------------------------------------------------------------------------- #
# 2. Dependency import test (inside the bundled runtime)
# --------------------------------------------------------------------------- #
Write-Step 'Dependency imports'

$sysPathInsert = "import sys; sys.path.insert(0, r'$RepoRoot');"

# 2a. What PYTHONPATH alone can do (documents the isolated-mode behaviour)
$pyPathProbe = @"
import sys
print('isolated=' + str(sys.flags.isolated))
try:
    import backend
    print('backend_via_pythonpath=yes')
except Exception as exc:
    print('backend_via_pythonpath=no (' + type(exc).__name__ + ': ' + str(exc) + ')')
"@
$probeResult = Invoke-Native -FilePath $PythonExe -Arguments @('-c', $pyPathProbe)
$probeOut = $probeResult.Output
Write-Host ("  probe     : " + (($probeOut -join ' | ').Trim()))
if (($probeOut -join "`n") -match 'isolated=1') {
    Write-Host '  note      : _pth forces isolated mode, so PYTHONPATH is ignored; repo root is inserted into sys.path explicitly.' -ForegroundColor Yellow
}

$importCode = @"
$sysPathInsert
import importlib.metadata
import fastapi, uvicorn, starlette, pydantic, pydantic_settings
import moviepy, imageio, imageio_ffmpeg, proglog, decorator, ffmpeg
from moviepy import (VideoFileClip, AudioFileClip, ImageClip, ColorClip,
                     CompositeVideoClip, CompositeAudioClip, concatenate_videoclips,
                     concatenate_audioclips)
import PIL, numpy, pandas
from PIL import Image, ImageDraw, ImageFont
import aiohttp, aiosignal, frozenlist, multidict, yarl
import httpx, httpcore, h11, anyio, sniffio
import openai, aiofiles, filelock, loguru, dotenv, requests, yaml
from dotenv import load_dotenv
import typing_extensions, annotated_types, click, colorama, distro, tqdm
import dateutil, six, pytz, packaging, propcache, win32_setctime, slugify, text_unidecode
try:
    import moviepy.editor  # moviepy 2.x removed this module
    editor_state = 'present'
except ModuleNotFoundError:
    editor_state = 'absent (moviepy ' + moviepy.__version__ + ' - top-level API used instead)'
try:
    ffmpeg_python_version = importlib.metadata.version('ffmpeg-python')
except Exception:
    ffmpeg_python_version = 'unknown'
print('python=' + sys.version.split()[0])
print('moviepy=' + moviepy.__version__)
print('moviepy.editor=' + editor_state)
print('numpy=' + numpy.__version__ + ' pandas=' + pandas.__version__ + ' PIL=' + PIL.__version__)
print('fastapi=' + fastapi.__version__ + ' starlette=' + starlette.__version__ +
      ' uvicorn=' + uvicorn.__version__ + ' pydantic=' + pydantic.VERSION)
print('imageio=' + imageio.__version__ + ' imageio_ffmpeg=' + imageio_ffmpeg.__version__)
print('ffmpeg_python=' + ffmpeg_python_version + ' openai=' + openai.__version__ + ' httpx=' + httpx.__version__)
print('deps_ok=True')
"@

$importResult = Invoke-Native -FilePath $PythonExe -Arguments @('-c', $importCode)
$importOut = $importResult.Output
$importExit = $importResult.ExitCode
if ($importExit -ne 0) {
    Add-Fail "dependency import test failed (exit $importExit):`n$($importOut -join "`n")"
}
else {
    foreach ($line in $importOut) {
        if ($line.Trim()) { Write-Host "  $($line.Trim())" }
    }
    Add-Pass 'entire dependency set imports inside the bundled runtime'
}

# 2b. backend.main (constructs FastAPI app + settings singletons)
Write-Step 'backend.main import'
$backendCode = @"
$sysPathInsert
import backend.main
print('app_title=' + backend.main.app.title)
print('app_routes=' + str(len(backend.main.app.routes)))
print('backend_main_ok=True')
"@
$backendResult = Invoke-Native -FilePath $PythonExe -Arguments @('-c', $backendCode)
$backendOut = $backendResult.Output
$backendExit = $backendResult.ExitCode
if ($backendExit -ne 0) {
    Add-Fail "import backend.main failed (exit $backendExit):`n$($backendOut -join "`n")"
}
else {
    foreach ($line in $backendOut) {
        if ($line.Trim()) { Write-Host "  $($line.Trim())" }
    }
    Add-Pass 'backend.main imports and builds the FastAPI app'
}

# --------------------------------------------------------------------------- #
# 3. ffmpeg / ffprobe resolve through the bundle
# --------------------------------------------------------------------------- #
Write-Step 'Bundled media binaries'
$ffmpegCmd = Get-Command ffmpeg -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $ffmpegCmd) {
    Add-Fail 'ffmpeg does not resolve through PATH (build\desktop\app\bin not usable)'
}
elseif ($ffmpegCmd.Source -ne $FfmpegExe) {
    Add-Fail "ffmpeg resolves to $($ffmpegCmd.Source) instead of the bundle ($FfmpegExe)"
}
else {
    $ffmpegResult = Invoke-Native -FilePath $FfmpegExe -Arguments @('-version')
    $ffmpegLine = if ($ffmpegResult.Output.Count -gt 0) { $ffmpegResult.Output[0] } else { '(no output)' }
    Write-Host "  resolves  : $($ffmpegCmd.Source)"
    Write-Host "  version   : $ffmpegLine"
    if ($ffmpegResult.ExitCode -eq 0 -and $ffmpegLine -match '^ffmpeg version') {
        Add-Pass 'ffmpeg resolves to the bundled binary via PATH'
    }
    else {
        Add-Fail "bundled ffmpeg -version failed (exit $($ffmpegResult.ExitCode)): $ffmpegLine"
    }
}

$ffprobeCmd = Get-Command ffprobe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $ffprobeCmd) {
    Add-Fail 'ffprobe does not resolve through PATH'
}
elseif ($ffprobeCmd.Source -ne $FfprobeExe) {
    Add-Fail "ffprobe resolves to $($ffprobeCmd.Source) instead of the bundle ($FfprobeExe)"
}
else {
    $ffprobeResult = Invoke-Native -FilePath $FfprobeExe -Arguments @('-version')
    $ffprobeLine = if ($ffprobeResult.Output.Count -gt 0) { $ffprobeResult.Output[0] } else { '(no output)' }
    Write-Host "  version   : $ffprobeLine"
    if ($ffprobeResult.ExitCode -eq 0 -and $ffprobeLine -match '^ffprobe version') {
        Add-Pass 'ffprobe resolves to the bundled binary via PATH'
    }
    else {
        Add-Fail "bundled ffprobe -version failed (exit $($ffprobeResult.ExitCode)): $ffprobeLine"
    }
}

# What moviepy/imageio_ffmpeg will actually use inside a packaged build
$iioCode = "import sys; sys.path.insert(0, r'$RepoRoot'); import imageio_ffmpeg, os; p = imageio_ffmpeg.get_ffmpeg_exe(); sys.stdout.write(p + '|' + str(os.path.getsize(p)))"
$iioResult = Invoke-Native -FilePath $PythonExe -Arguments @('-c', $iioCode)
if ($iioResult.ExitCode -eq 0 -and ($iioResult.Output -join '').Trim()) {
    $iioText = ($iioResult.Output -join '').Trim()
    $iioParts = $iioText -split '\|'
    $iioSizeMb = [math]::Round(([double]$iioParts[1]) / 1MB, 2)
    Write-Host "  imageio_ffmpeg ffmpeg: $($iioParts[0]) ($iioSizeMb MB)"
}
else {
    Write-Host "  imageio_ffmpeg ffmpeg: could not resolve ($($iioResult.Output -join ' '))" -ForegroundColor Yellow
}

# --------------------------------------------------------------------------- #
# 4. uvicorn + /health
# --------------------------------------------------------------------------- #
Write-Step "Starting uvicorn on 127.0.0.1:$Port and probing /health"

# Port must be free
$portBusy = $false
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect('127.0.0.1', $Port)
    $portBusy = $client.Connected
    $client.Close()
}
catch { $portBusy = $false }
if ($portBusy) {
    Add-Fail "port $Port is already in use - cannot start uvicorn"
}

function Stop-PythonTree {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process) { return }
    try {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            $Process.WaitForExit(5000) | Out-Null
        }
    }
    catch { }
}

function Wait-ForHealth {
    param([int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { return $resp }
        }
        catch { }
        Start-Sleep -Milliseconds 700
    }
    return $null
}

$serverProcess = $null
$serverLog = Join-Path $TmpDir 'uvicorn'
$attempts = @(
    [PSCustomObject]@{
        Name   = 'spec: python -m uvicorn backend.main:app (cwd = repo root, PYTHONPATH set)'
        Args   = @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', "$Port")
        Window = 8
    },
    [PSCustomObject]@{
        Name   = 'fallback: python -m uvicorn backend.main:app --app-dir <repo root>'
        Args   = @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', "$Port", '--app-dir', $RepoRoot)
        Window = $HealthTimeoutSeconds
    }
)

$healthResponse = $null
$usedAttempt = $null
foreach ($attempt in $attempts) {
    if ($portBusy) { break }
    Write-Host "  attempt   : $($attempt.Name)"
    $stdoutFile = "$serverLog.out.log"
    $stderrFile = "$serverLog.err.log"
    Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    try {
        $serverProcess = Start-Process -FilePath $PythonExe -ArgumentList $attempt.Args `
            -WorkingDirectory $RepoRoot -PassThru -NoNewWindow `
            -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -ErrorAction Stop
    }
    catch {
        Add-Fail "could not start uvicorn: $($_.Exception.Message)"
        break
    }

    $healthResponse = Wait-ForHealth -TimeoutSeconds $attempt.Window
    if ($healthResponse) {
        $usedAttempt = $attempt.Name
        break
    }

    # Failed: collect the tail of the log, then clean up before the next attempt
    $errTail = @()
    if (Test-Path -LiteralPath $stderrFile) {
        $errTail = @(Get-Content -LiteralPath $stderrFile -ErrorAction SilentlyContinue |
                     Where-Object { $_.Trim() } | Select-Object -Last 6)
    }
    if ($errTail.Count -eq 0 -and (Test-Path -LiteralPath $stdoutFile)) {
        $errTail = @(Get-Content -LiteralPath $stdoutFile -ErrorAction SilentlyContinue |
                     Where-Object { $_.Trim() } | Select-Object -Last 6)
    }
    Write-Host "  attempt failed after $($attempt.Window)s" -ForegroundColor Yellow
    if ($errTail.Count -gt 0) {
        foreach ($line in $errTail) { Write-Host "    $line" -ForegroundColor DarkGray }
    }
    Stop-PythonTree -Process $serverProcess
    $serverProcess = $null
    Start-Sleep -Milliseconds 500
}

try {
    if ($healthResponse) {
        $healthJson = $healthResponse.Content
        Write-Host ''
        Write-Host '  /health -> 200 OK'
        Write-Host "  JSON      : $healthJson"
        $parsed = $healthJson | ConvertFrom-Json
        if ($parsed.status -eq 'healthy') { Add-Pass "GET /health returned 200 {`"status`": `"healthy`"} (via $usedAttempt)" }
        else { Add-Fail "GET /health returned unexpected payload: $healthJson" }
    }
    elseif (-not $portBusy) {
        Add-Fail "GET $HealthUrl never returned 200 within ${HealthTimeoutSeconds}s"
    }
}
finally {
    if ($serverProcess) {
        Stop-PythonTree -Process $serverProcess
        $portAlive = $false
        try {
            $c = New-Object System.Net.Sockets.TcpClient
            $c.Connect('127.0.0.1', $Port)
            $portAlive = $c.Connected
            $c.Close()
        }
        catch { }
        if ($portAlive) { Write-Host "  warning   : 127.0.0.1:$Port still accepts connections" -ForegroundColor Yellow }
        else { Write-Host '  server    : stopped' }
    }
}

# --------------------------------------------------------------------------- #
# 5. Result
# --------------------------------------------------------------------------- #
Write-Step 'Result'
if ($script:Failures.Count -eq 0) {
    Write-Host '  All runtime checks passed.' -ForegroundColor Green
    Remove-Item -LiteralPath $TmpDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 0
}
else {
    Write-Host "  $($script:Failures.Count) check(s) failed:" -ForegroundColor Red
    foreach ($f in $script:Failures) { Write-Host "   - $f" -ForegroundColor Red }
    Write-Host "  logs kept in $TmpDir" -ForegroundColor Yellow
    exit 1
}
