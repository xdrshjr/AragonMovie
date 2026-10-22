<#
    build-python-runtime.ps1

    Builds a PORTABLE CPython runtime + bundled media binaries that the Electron
    desktop installer can ship, so end users do not need Python or ffmpeg.

    Produces:
      build\desktop\python\             embedded CPython 3.12.10 + app runtime deps
      build\desktop\python\python312._pth   fixed up sys.path for the embedded runtime
      build\desktop\app\bin\ffmpeg.exe      real ffmpeg binary (not the WinGet alias)
      build\desktop\app\bin\ffprobe.exe     matching ffprobe

    The script is idempotent: the download is cached, build\desktop\python and
    build\desktop\app\bin are recreated from scratch on every run.

    Usage (from anywhere):
      powershell -NoProfile -ExecutionPolicy Bypass -File build\desktop\build-python-runtime.ps1
#>
[CmdletBinding()]
param(
    [string]$PythonVersion = '3.12.10',
    [switch]$ForceDownload
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
$ScriptDir  = $PSScriptRoot                                   # build\desktop
$PythonDir  = Join-Path $ScriptDir 'python'                   # build\desktop\python
$CacheDir   = Join-Path $ScriptDir 'cache'                    # build\desktop\cache
$BinDir     = Join-Path $ScriptDir 'app\bin'                  # build\desktop\app\bin
$RepoRoot   = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$SiteSrc    = Join-Path $RepoRoot 'venv\Lib\site-packages'
$VenvPython = Join-Path $RepoRoot 'venv\Scripts\python.exe'

$ZipName    = "python-$PythonVersion-embed-amd64.zip"
$ZipPath    = Join-Path $CacheDir $ZipName
$DownloadUrl = "https://www.python.org/ftp/python/$PythonVersion/$ZipName"
$PthPath    = Join-Path $PythonDir 'python312._pth'
$SiteDest   = Join-Path $PythonDir 'Lib\site-packages'

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Format-Size([double]$Bytes) {
    if ($Bytes -ge 1GB) { return ('{0:N2} GB' -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ('{0:N2} MB' -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ('{0:N1} KB' -f ($Bytes / 1KB)) }
    return ('{0:N0} B' -f $Bytes)
}

function Get-DirSize([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { return 0 }
    return [double]$sum
}

# --------------------------------------------------------------------------- #
# Prune list: dev-only / unrelated packages that must NOT ship
# --------------------------------------------------------------------------- #
$ExcludeDirNames = @(
    'black', 'blackd', 'blib2to3',              # formatter
    'flake8', 'pyflakes',                       # linter (pyflakes has no dist-info pattern need: dir)
    'mypy', 'mypyc',                            # type checker
    'pytest', 'pytest_asyncio', 'pytest_playwright', '_pytest',
    'pluggy', 'iniconfig',                      # pytest plugins/deps
    'pathspec', 'platformdirs',                 # black/mypy deps
    'playwright', 'pyee',                       # E2E only (browser drivers)
    'greenlet',                                 # playwright/gevent dep, unused at runtime
    '__pycache__'                               # byte-code caches of the dev venv
)

$ExcludeFiles = @(
    'mypy_extensions.py', 'mypy_extensions-*.dist-info',
    'pycodestyle.py', 'pycodestyle-*.dist-info',
    'mccabe.py', 'mccabe-*.dist-info',
    'py.py',
    'numpy-*-cp312-cp312-win_amd64.whl',        # stray wheel dropped into site-packages
    '*__mypyc*.pyd'                             # stray compiled artifact of mypyc
)

# Packages that MUST be present after the copy (fail loudly otherwise)
$RequiredEntries = @(
    'fastapi', 'starlette', 'uvicorn', 'pydantic', 'pydantic_core', 'pydantic_settings',
    'moviepy', 'imageio', 'imageio_ffmpeg', 'proglog', 'decorator', 'PIL',
    'numpy', 'numpy.libs', 'pandas', 'pandas.libs',
    'aiohttp', 'aiosignal', 'frozenlist', 'multidict', 'yarl', 'propcache',
    'attr', 'attrs', 'requests', 'urllib3', 'certifi', 'charset_normalizer', 'idna',
    'openai', 'httpx', 'httpcore', 'h11', 'anyio', 'sniffio',
    'aiofiles', 'filelock', 'loguru', 'yaml', '_yaml', 'dotenv',
    'typing_extensions.py', 'annotated_types', 'click', 'colorama', 'distro', 'tqdm',
    'dateutil', 'six.py', 'pytz', 'packaging', 'win32_setctime',
    'slugify', 'text_unidecode', 'future', 'past', 'ffmpeg', 'tzdata'
)

# --------------------------------------------------------------------------- #
# 1. Preconditions
# --------------------------------------------------------------------------- #
Write-Step 'Checking prerequisites'
if (-not (Test-Path -LiteralPath $SiteSrc)) {
    throw "Runtime dependency source not found: $SiteSrc (create the venv first: python -m venv venv; pip install -r requirements.txt)"
}
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Warning "venv python not found at $VenvPython - the imageio_ffmpeg fallback will be unavailable."
}
Write-Host "  repo root        : $RepoRoot"
Write-Host "  site-packages    : $SiteSrc"
Write-Host "  output runtime   : $PythonDir"

# --------------------------------------------------------------------------- #
# 2. Download + cache the embedded distribution
# --------------------------------------------------------------------------- #
Write-Step "Preparing embedded CPython $PythonVersion"
if (-not (Test-Path -LiteralPath $CacheDir)) {
    New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
}

$cachedOk = $false
if ((Test-Path -LiteralPath $ZipPath) -and (-not $ForceDownload)) {
    $cachedOk = $true
}

if ($cachedOk) {
    Write-Host "  cached archive   : $ZipPath ($(Format-Size (Get-Item -LiteralPath $ZipPath).Length))"
}
else {
    if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    Write-Host "  downloading      : $DownloadUrl"
    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath -UseBasicParsing -ErrorAction Stop
    }
    catch {
        if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue }
        throw "Failed to download $DownloadUrl : $($_.Exception.Message)"
    }
    Write-Host "  downloaded       : $ZipPath ($(Format-Size (Get-Item -LiteralPath $ZipPath).Length))"
}

# Validate the cached archive (corrupt cache must not silently produce a broken runtime)
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
    $zipCheck = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    $entryCount = $zipCheck.Entries.Count
    $zipCheck.Dispose()
}
catch {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    throw "Cached archive is corrupt and was removed, re-run the script: $ZipPath ($($_.Exception.Message))"
}
if ($entryCount -lt 10) {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    throw "Downloaded archive looks invalid ($entryCount entries) and was removed, re-run: $ZipPath"
}
Write-Host "  archive entries  : $entryCount"

# --------------------------------------------------------------------------- #
# 3. Extract into a clean build\desktop\python
# --------------------------------------------------------------------------- #
Write-Step 'Extracting embedded runtime'
if (Test-Path -LiteralPath $PythonDir) {
    Remove-Item -LiteralPath $PythonDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null
Expand-Archive -LiteralPath $ZipPath -DestinationPath $PythonDir -Force
$pythonExe = Join-Path $PythonDir 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Extraction failed: $pythonExe is missing"
}
Write-Host "  extracted        : $pythonExe"

# --------------------------------------------------------------------------- #
# 4. Copy runtime dependencies (everything except the prune list)
# --------------------------------------------------------------------------- #
Write-Step 'Copying runtime dependencies from venv\Lib\site-packages'
New-Item -ItemType Directory -Path $SiteDest -Force | Out-Null

$robocopyArgs = @(
    $SiteSrc,
    $SiteDest,
    '/E',            # include subdirs (empty ones too)
    '/R:1', '/W:1',  # be quick about locked files
    '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS', '/NP',
    '/XD'
) + $ExcludeDirNames + @('/XF') + $ExcludeFiles

& robocopy @robocopyArgs | Out-Null
$rc = $LASTEXITCODE
if ($rc -ge 8) {
    throw "robocopy failed with exit code $rc while copying $SiteSrc -> $SiteDest"
}

# Safety net: robocopy /XF wildcard matching is not reliable for every pattern,
# so re-apply the prune list with PowerShell wildcards and drop byte-code caches.
$removedCount = 0
foreach ($pattern in $ExcludeFiles) {
    $hits = @(Get-ChildItem -LiteralPath $SiteDest -Filter $pattern -File -Force -ErrorAction SilentlyContinue)
    foreach ($hit in $hits) {
        Remove-Item -LiteralPath $hit.FullName -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $hit.FullName)) {
            $removedCount++
            Write-Host "  pruned file      : $($hit.Name)"
        }
    }
}
foreach ($dirName in $ExcludeDirNames) {
    $hits = @(Get-ChildItem -LiteralPath $SiteDest -Recurse -Directory -Force -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -eq $dirName })
    foreach ($hit in $hits) {
        Remove-Item -LiteralPath $hit.FullName -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $hit.FullName)) {
            $removedCount++
            Write-Host "  pruned dir       : $($hit.FullName.Substring($SiteDest.Length + 1))"
        }
    }
}
if ($removedCount -gt 0) {
    Write-Host "  safety net       : $removedCount leftover item(s) pruned after robocopy"
}
else {
    Write-Host '  safety net       : robocopy prune list was already complete'
}

# Hard assertion: nothing from the prune list may survive
$leaks = @()
foreach ($pattern in $ExcludeFiles) {
    $leaks += @(Get-ChildItem -LiteralPath $SiteDest -Filter $pattern -File -Force -ErrorAction SilentlyContinue |
                ForEach-Object { $_.Name })
}
foreach ($dirName in $ExcludeDirNames) {
    $leaks += @(Get-ChildItem -LiteralPath $SiteDest -Recurse -Directory -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -eq $dirName } |
                ForEach-Object { $_.FullName })
}
if ($leaks.Count -gt 0) {
    throw "Prune list was not applied, still present in ${SiteDest}: $($leaks -join ', ')"
}

# Sanity check the required packages
$missing = @()
foreach ($entry in $RequiredEntries) {
    $candidate = Join-Path $SiteDest $entry
    if (-not (Test-Path -LiteralPath $candidate)) { $missing += $entry }
}
if ($missing.Count -gt 0) {
    throw "Copy is incomplete, missing from ${SiteDest}: $($missing -join ', ')"
}

$copiedFiles = @(Get-ChildItem -LiteralPath $SiteDest -Recurse -File -Force -ErrorAction SilentlyContinue)
Write-Host "  copied           : $($copiedFiles.Count) files, $(Format-Size (Get-DirSize $SiteDest))"

# --------------------------------------------------------------------------- #
# 4b. Drop imageio-ffmpeg's private ffmpeg build (~84 MB dupe)
#     The desktop shell prepends build\desktop\app\bin to PATH and exports
#     IMAGEIO_FFMPEG_EXE, so moviepy/imageio-ffmpeg resolve the bundled
#     ffmpeg 8.x instead of shipping a second copy.
# --------------------------------------------------------------------------- #
Write-Step 'Pruning duplicate ffmpeg shipped by imageio-ffmpeg'
$imageioBin = Join-Path $SiteDest 'imageio_ffmpeg\binaries'
if (Test-Path -LiteralPath $imageioBin) {
    $dupes = @(Get-ChildItem -LiteralPath $imageioBin -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'ffmpeg*.exe' })
    foreach ($dupe in $dupes) {
        $size = $dupe.Length
        Remove-Item -LiteralPath $dupe.FullName -Force
        Write-Host "  pruned dupe ffmpeg: $($dupe.Name) ($(Format-Size $size)) — using app\bin instead"
    }
}

# --------------------------------------------------------------------------- #
# 5. python312._pth
# --------------------------------------------------------------------------- #
Write-Step 'Writing python312._pth'
$pthLines = @('python312.zip', '.', 'Lib\site-packages', 'import site')
$pthContent = ($pthLines -join "`r`n") + "`r`n"
[System.IO.File]::WriteAllText($PthPath, $pthContent, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "  wrote            : $PthPath"
Get-Content -LiteralPath $PthPath | ForEach-Object { Write-Host "    | $_" }

# --------------------------------------------------------------------------- #
# 6. Bundle ffmpeg.exe + ffprobe.exe
# --------------------------------------------------------------------------- #
Write-Step 'Resolving real ffmpeg / ffprobe binaries'

$ffmpegPath  = $null
$ffprobePath = $null
$ffmpegSource = $null
$MinBinarySize = 5MB   # anything smaller is a WinGet App Execution Alias, not a real binary

# 6a. WinGet package payload. Get-Command ffmpeg only finds a 0-byte alias in
#     %LOCALAPPDATA%\Microsoft\WinGet\Links, so look inside the package folders.
$wingetPackages = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
if (Test-Path -LiteralPath $wingetPackages) {
    $candidates = @(Get-ChildItem -LiteralPath $wingetPackages -Filter 'ffmpeg.exe' -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -gt $MinBinarySize } |
        Sort-Object -Property @{ Expression = { if ($_.FullName -match '\\ffmpeg-[^\\]*\\bin\\ffmpeg\.exe$') { 0 } else { 1 } } },
                              @{ Expression = { -($_.Length) } })
    Write-Host "  winget candidates: $($candidates.Count)"
    foreach ($candidate in $candidates) {
        $probe = Join-Path $candidate.DirectoryName 'ffprobe.exe'
        if (Test-Path -LiteralPath $probe) {
            if ((Get-Item -LiteralPath $probe).Length -gt $MinBinarySize) {
                $ffmpegPath  = $candidate.FullName
                $ffprobePath = $probe
                $ffmpegSource = 'WinGet package payload'
                break
            }
        }
        if (-not $ffmpegPath) { $ffmpegPath = $candidate.FullName }
    }
}

# 6b. Fallback: the ffmpeg that ships inside imageio_ffmpeg (no ffprobe there).
if (-not $ffmpegPath -and (Test-Path -LiteralPath $VenvPython)) {
    Write-Host '  trying imageio_ffmpeg.get_ffmpeg_exe() fallback'
    $fallback = & $VenvPython -c "import imageio_ffmpeg,sys; sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())" 2>$null
    if ($LASTEXITCODE -eq 0 -and $fallback) {
        $fallback = ([string]$fallback).Trim()
        if (Test-Path -LiteralPath $fallback) {
            $ffmpegPath = $fallback
            $ffmpegSource = 'imageio_ffmpeg bundled binary'
        }
    }
}

# 6c. ffprobe still missing -> look for any real ffprobe on PATH.
if ($ffmpegPath -and -not $ffprobePath) {
    $probeCmd = Get-Command ffprobe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($probeCmd -and (Test-Path -LiteralPath $probeCmd.Source) -and
        (Get-Item -LiteralPath $probeCmd.Source).Length -gt $MinBinarySize) {
        $ffprobePath = $probeCmd.Source
    }
    # sibling of the chosen ffmpeg
    if (-not $ffprobePath) {
        $sibling = Join-Path (Split-Path -Parent $ffmpegPath) 'ffprobe.exe'
        if (Test-Path -LiteralPath $sibling) { $ffprobePath = $sibling }
    }
}

if (-not $ffmpegPath -or -not (Test-Path -LiteralPath $ffmpegPath)) {
    throw @'
Could not locate a real ffmpeg.exe.
Checked:
  - %LOCALAPPDATA%\Microsoft\WinGet\Packages\**\ffmpeg.exe  (Get-Command ffmpeg only resolves the 0-byte WinGet alias)
  - imageio_ffmpeg.get_ffmpeg_exe() inside the venv
Install it with:  winget install --id Gyan.FFmpeg -e
'@
}
if (-not $ffprobePath -or -not (Test-Path -LiteralPath $ffprobePath)) {
    throw @"
Could not locate a real ffprobe.exe (ffmpeg.exe was found at $ffmpegPath).
ffprobe is required by the desktop bundle (media probing).
Install the full FFmpeg package with ffprobe:  winget install --id Gyan.FFmpeg -e
"@
}

Write-Host "  ffmpeg           : $ffmpegPath ($(Format-Size (Get-Item -LiteralPath $ffmpegPath).Length))"
Write-Host "  ffprobe          : $ffprobePath ($(Format-Size (Get-Item -LiteralPath $ffprobePath).Length))"
Write-Host "  source           : $ffmpegSource"

if (Test-Path -LiteralPath $BinDir) {
    Remove-Item -LiteralPath $BinDir -Recurse -Force
}
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null

$ffmpegDest  = Join-Path $BinDir 'ffmpeg.exe'
$ffprobeDest = Join-Path $BinDir 'ffprobe.exe'
Copy-Item -LiteralPath $ffmpegPath  -Destination $ffmpegDest  -Force
Copy-Item -LiteralPath $ffprobePath -Destination $ffprobeDest -Force

foreach ($dest in @($ffmpegDest, $ffprobeDest)) {
    if (-not (Test-Path -LiteralPath $dest)) { throw "Copy failed, missing: $dest" }
    if ((Get-Item -LiteralPath $dest).Length -lt $MinBinarySize) {
        throw "Copied binary looks like a stub/alias (too small): $dest"
    }
}

$versionLine = $null
try { $versionLine = (& $ffmpegDest -version 2>&1 | Select-Object -First 1) } catch { }
if ($versionLine) { Write-Host "  bundled ffmpeg   : $versionLine" }
else { throw "Bundled ffmpeg does not run: $ffmpegDest" }

# --------------------------------------------------------------------------- #
# 7. Summary
# --------------------------------------------------------------------------- #
$pythonSize = Get-DirSize $PythonDir
$binSize    = Get-DirSize $BinDir

$packageSizes = @(Get-ChildItem -LiteralPath $SiteDest -Directory -Force -ErrorAction SilentlyContinue |
    ForEach-Object {
        [PSCustomObject]@{
            Name = $_.Name
            Bytes = Get-DirSize $_.FullName
        }
    } | Sort-Object -Property Bytes -Descending)

Write-Step 'Summary'
Write-Host ("  {0,-22} {1}" -f 'build\desktop\python', (Format-Size $pythonSize))
Write-Host ("  {0,-22} {1}" -f 'build\desktop\app\bin', (Format-Size $binSize))
Write-Host ("  {0,-22} {1}" -f 'bundled total', (Format-Size ($pythonSize + $binSize)))
Write-Host ''
Write-Host '  Top 5 largest copied packages:'
$packageSizes | Select-Object -First 5 | ForEach-Object {
    Write-Host ("    {0,-28} {1}" -f $_.Name, (Format-Size $_.Bytes))
}
Write-Host ''
Write-Host ("  Excluded dev-only dirs  : {0}" -f ($ExcludeDirNames -join ', '))
Write-Host ("  Excluded dev-only files : {0}" -f ($ExcludeFiles -join ', '))
Write-Host ("  Bundled media binaries  : ffmpeg.exe ({0}), ffprobe.exe ({1}) from {2}" -f `
    (Format-Size (Get-Item -LiteralPath $ffmpegDest).Length), `
    (Format-Size (Get-Item -LiteralPath $ffprobeDest).Length), $ffmpegSource)
Write-Host ''
Write-Host 'Python runtime build completed successfully.' -ForegroundColor Green
