<#
    install-git-hooks.ps1 — install the credential-gate pre-commit hook.

    The hook blocks a commit whose staged diff contains a credential: a value
    from your own .env / runtime settings, or a credential-shaped string.
    .git/hooks is not versioned, so run this once per clone.

    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -File build\desktop\install-git-hooks.ps1
      ... -Verify        # install, then prove block/allow behaviour end to end
      ... -Uninstall
#>
param(
    [switch]$Uninstall,
    [switch]$Verify
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Template = Join-Path $PSScriptRoot 'git-hooks\pre-commit'
$HooksDir = Join-Path $RepoRoot '.git\hooks'
$Target = Join-Path $HooksDir 'pre-commit'

if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) {
    throw "not a git repository: $RepoRoot"
}

if ($Uninstall) {
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Force
        Write-Host "removed $Target"
    }
    else {
        Write-Host 'no pre-commit hook installed'
    }
    return
}

if (-not (Test-Path -LiteralPath $Template)) {
    throw "hook template not found: $Template"
}

New-Item -ItemType Directory -Path $HooksDir -Force | Out-Null

# Normalise to LF: core.autocrlf=true would otherwise produce a CRLF shebang and
# Git's bundled sh would refuse to run the hook.
$content = [IO.File]::ReadAllText($Template) -replace "`r`n", "`n"
[IO.File]::WriteAllText($Target, $content, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "installed  $Target"
Write-Host ("           {0} chars, LF, shebang: {1}" -f $content.Length, ($content -split "`n")[0])

$hooksPath = & git -C $RepoRoot config --get core.hooksPath
if ($hooksPath) {
    Write-Warning "core.hooksPath='$hooksPath' — Git ignores .git/hooks; unset it or install there instead"
}

if (-not $Verify) { return }

# ---------------------------------------------------------------------------
# self-test
#
# Every native git call below may write to stderr (hook messages, autocrlf
# warnings) and may intentionally fail, so the exit code is the signal.
# Nothing here can commit unrelated staged work: each probe first asserts that
# the probe file is the ONLY staged path, and aborts otherwise.
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '== self-test =='
$ErrorActionPreference = 'Continue'

$probeRel = 'docs/zz-credential-gate-probe.md'
$probe = Join-Path $RepoRoot $probeRel
$headBefore = (& git -C $RepoRoot rev-parse HEAD).Trim()
$failures = 0

function Invoke-ProjectGit {
    param([string[]]$GitArgs)
    $log = Join-Path $env:TEMP ("aragon-hook-" + [guid]::NewGuid().ToString('N') + ".log")
    & git -C $RepoRoot @GitArgs *> $log
    $exit = $LASTEXITCODE
    $text = if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Raw } else { '' }
    if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }
    return [pscustomobject]@{ Exit = $exit; Output = $text }
}

function Test-ProbeOnlyStaged {
    $staged = @(& git -C $RepoRoot diff --cached --name-only)
    return ($staged.Count -eq 1 -and $staged[0] -eq $probeRel)
}

function Clear-Probe {
    & git -C $RepoRoot rm --cached -q --ignore-unmatch $probeRel 2>$null | Out-Null
    if (Test-Path -LiteralPath $probe) { Remove-Item -LiteralPath $probe -Force }
}

# ---- 1. a credential-SHAPED value must be blocked -------------------------
try {
    Set-Content -LiteralPath $probe -Encoding UTF8 -Value '# credential gate probe', 'API_KEY=sk-zzprobe0q7w8e9r0t1y2u3i4o5p6a7s8d9f0g'  # credential-gate: allow (synthetic probe literal)
    & git -C $RepoRoot add -- $probeRel | Out-Null
    if (-not (Test-ProbeOnlyStaged)) {
        Write-Host '  SKIP other files are staged; refusing to run the commit probe' -ForegroundColor Yellow
        $failures++
    }
    else {
        $result = Invoke-ProjectGit @('commit', '-m', 'probe: must be blocked')
        $headAfter = (& git -C $RepoRoot rev-parse HEAD).Trim()
        if ($result.Exit -ne 0 -and $headAfter -eq $headBefore) {
            Write-Host ('  ok   credential-shaped value blocked (exit {0}, HEAD unchanged)' -f $result.Exit) -ForegroundColor Green
        }
        else {
            Write-Host '  FAIL credential-shaped value was NOT blocked' -ForegroundColor Red
            foreach ($line in ($result.Output -split "`n" | Select-Object -First 12)) { if ($line.Trim()) { Write-Host "       $line" } }
            $failures++
        }
        if ($result.Output -match 'COMMIT BLOCKED') {
            Write-Host '  ok   developer sees the "COMMIT BLOCKED" guidance' -ForegroundColor Green
        }
        else {
            Write-Host '  warn "COMMIT BLOCKED" text missing from the hook output' -ForegroundColor Yellow
        }
    }
}
finally { Clear-Probe }

# ---- 2. a developer's OWN configured secret must be blocked too ------------
# AUDIT_EXTRA_SECRETS feeds the checker an extra value without putting it in the
# checker source; a synthetic value is used so nothing real is written to disk.
try {
    $needle = 'probe-needle-0f3a9c2b7d5e8a1f4c6b9d2e5a8f1c4b7d0e'  # credential-gate: allow (synthetic probe literal)
    Set-Content -LiteralPath $probe -Value '# configured-secret probe', "SOME_CONFIG=$needle" -Encoding UTF8
    & git -C $RepoRoot add -- $probeRel | Out-Null
    if (-not (Test-ProbeOnlyStaged)) {
        Write-Host '  SKIP other files are staged; refusing to run the commit probe' -ForegroundColor Yellow
        $failures++
    }
    else {
        $env:AUDIT_EXTRA_SECRETS = $needle
        $result = Invoke-ProjectGit @('commit', '-m', 'probe: configured secret must be blocked')
        Remove-Item Env:\AUDIT_EXTRA_SECRETS -ErrorAction SilentlyContinue
        $headAfter = (& git -C $RepoRoot rev-parse HEAD).Trim()
        if ($result.Exit -ne 0 -and $headAfter -eq $headBefore) {
            Write-Host '  ok   a configured secret value is blocked even though it is not sk-* shaped' -ForegroundColor Green
        }
        else {
            Write-Host '  FAIL the configured-secret path did not block the commit' -ForegroundColor Red
            foreach ($line in ($result.Output -split "`n" | Select-Object -First 12)) { if ($line.Trim()) { Write-Host "       $line" } }
            $failures++
        }
    }
}
finally {
    Remove-Item Env:\AUDIT_EXTRA_SECRETS -ErrorAction SilentlyContinue
    Clear-Probe
}

# ---- 3. a clean staged diff must pass ------------------------------------
try {
    Set-Content -LiteralPath $probe -Value '# harmless probe', 'nothing to see here' -Encoding UTF8
    & git -C $RepoRoot add -- $probeRel | Out-Null
    if (Test-ProbeOnlyStaged) {
        $result = Invoke-ProjectGit @('commit', '--dry-run', '-m', 'probe: must be allowed')
        if ($result.Exit -eq 0) {
            Write-Host '  ok   a clean staged diff passes the gate' -ForegroundColor Green
        }
        else {
            Write-Host ('  FAIL a clean staged diff was rejected (exit {0})' -f $result.Exit) -ForegroundColor Red
            foreach ($line in ($result.Output -split "`n" | Select-Object -First 12)) { if ($line.Trim()) { Write-Host "       $line" } }
            $failures++
        }
    }
    else {
        Write-Host '  SKIP other files are staged; refusing to run the allow probe' -ForegroundColor Yellow
        $failures++
    }
}
finally { Clear-Probe }

# ---- 4. nothing was committed -------------------------------------------
$headNow = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($headNow -eq $headBefore) {
    Write-Host '  ok   no probe commit was created' -ForegroundColor Green
}
else {
    Write-Host "  FAIL a probe commit was created ($headBefore -> $headNow); run 'git log' and undo it" -ForegroundColor Red
    $failures++
}

Write-Host ''
if ($failures -gt 0) {
    Write-Host "SELF-TEST FAILED ($failures issue(s))" -ForegroundColor Red
    exit 1
}
Write-Host 'SELF-TEST PASSED — the credential gate is active' -ForegroundColor Green
