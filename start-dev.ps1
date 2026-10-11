<#
.SYNOPSIS
    AragonMovie 开发环境一键启动 / 停止脚本

.DESCRIPTION
    启动: 后端 FastAPI (默认 :8000) + 前端 Next.js (默认 :3000)，各占一个独立窗口，
          自动完成环境自检（.env / python 依赖 / node_modules），端口就绪后可自动打开浏览器。
    停止: 加 -Stop 参数，按记录的 PID 树终止全部服务窗口（含端口兜底清理）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
    .\start-dev.ps1                 # 启动所有服务并打开浏览器
    .\start-dev.ps1 -NoBrowser      # 启动但不打开浏览器
    .\start-dev.ps1 -Stop           # 停止所有服务
    .\start-dev.ps1 -BackendPort 8001 -FrontendPort 3001   # 自定义端口
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$NoBrowser,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = 'Stop'
$Root    = $PSScriptRoot
$PidFile = Join-Path $Root '.dev-pids.txt'

function Step($msg) { Write-Host "[*] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[+] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[x] $msg" -ForegroundColor Red }

function Get-PortPids([int]$Port) {
    try {
        @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch { @() }
}

function Test-PortOpen([int]$Port) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $ar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($ar.AsyncWaitHandle.WaitOne(1000, $false) -and $c.Connected) { return $true }
        return $false
    } catch { return $false } finally { $c.Close() }
}

function Wait-ForPort([int]$Port, [int]$TimeoutSec) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-PortOpen $Port) { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

# ============================================================
# 停止模式
# ============================================================
function Stop-Services {
    Step 'Stopping AragonMovie dev services...'
    $stopped = $false

    if (Test-Path $PidFile) {
        foreach ($p in (Get-Content $PidFile)) {
            if ($p -notmatch '^\d+$') { continue }
            $proc = Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue
            if ($proc) {
                Step "Killing process tree PID=$p ($($proc.ProcessName))"
                & taskkill /PID $p /T /F 2>$null | Out-Null
                $stopped = $true
            }
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }

    # 兜底：清理仍占用端口的进程（例如手动启动的服务）
    foreach ($port in @($BackendPort, $FrontendPort)) {
        foreach ($p in (Get-PortPids $port)) {
            Warn "Port $port still held by PID=$p, force killing"
            & taskkill /PID $p /T /F 2>$null | Out-Null
            $stopped = $true
        }
    }

    if ($stopped) { Ok 'All services stopped' } else { Warn 'No running services found' }
}

if ($Stop) { Stop-Services; exit 0 }

# ============================================================
# 启动模式：环境自检
# ============================================================
Write-Host ''
Write-Host '============================================================' -ForegroundColor DarkCyan
Write-Host ' AragonMovie Dev Launcher' -ForegroundColor DarkCyan
Write-Host '============================================================' -ForegroundColor DarkCyan

# 端口占用检查
foreach ($port in @($BackendPort, $FrontendPort)) {
    $holders = Get-PortPids $port
    if ($holders.Count -gt 0) {
        Fail "Port $port is already in use (PID: $($holders -join ', '))."
        Fail "Run '.\start-dev.ps1 -Stop' first, or free the port manually."
        exit 1
    }
}

# Python 解释器：优先 venv
$VenvPy = Join-Path $Root 'venv\Scripts\python.exe'
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
    Ok "Using venv python: $PythonExe"
} else {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd) { Fail 'python not found on PATH. Install Python 3.10+ or create .\venv'; exit 1 }
    $PythonExe = $pyCmd.Source
    Ok "Using system python: $PythonExe"
}

# Python 依赖自检（快速失败，避免窗口一闪而过）
Step 'Checking backend dependencies (fastapi/uvicorn)...'
& $PythonExe -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail 'fastapi/uvicorn not installed for this python.'
    Fail "Run: & '$PythonExe' -m pip install -r requirements.txt"
    exit 1
}
Ok 'Backend dependencies OK'

# Node/npm 自检
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) { Fail 'npm not found. Install Node.js >= 18 first (needed by frontend and aragon CLI)'; exit 1 }
Ok "npm found: $($npmCmd.Source)"

# .env 自检
$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root '.env.example') $envFile
    Warn '.env was missing - created from .env.example (API keys are empty).'
    Warn "Configure keys later in the Settings UI: http://localhost:$FrontendPort/settings"
} else {
    Ok '.env found'
}

# 前端依赖自检
if (-not (Test-Path (Join-Path $Root 'frontend\node_modules'))) {
    Step 'First run: installing frontend dependencies (npm install, may take minutes)...'
    Push-Location (Join-Path $Root 'frontend')
    & npm install --no-audit --no-fund
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { Fail 'npm install failed'; exit 1 }
    Ok 'Frontend dependencies installed'
} else {
    Ok 'frontend/node_modules found'
}

# aragon CLI（Agent 协助配置主模式，可选）
if (Get-Command aragon -ErrorAction SilentlyContinue) {
    Ok 'aragon CLI detected - Agent assist can run in full mode'
} else {
    Warn 'aragon CLI not found. Agent assist will use LLM fallback mode.'
    Warn 'Install with: npm i -g @aragon-agent/cli'
}

# ============================================================
# 启动服务（独立窗口）
# ============================================================
Step "Starting backend  -> http://localhost:$BackendPort"
$backendInner = "`$host.UI.RawUI.WindowTitle = 'AragonMovie | Backend :$BackendPort'; " +
                "Set-Location -LiteralPath '$Root'; " +
                "& '$PythonExe' 'backend\run_dev.py'"
$backendProc = Start-Process powershell -PassThru -WorkingDirectory $Root -ArgumentList @(
    '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $backendInner
)

Step "Starting frontend -> http://localhost:$FrontendPort"
$frontendInner = "`$host.UI.RawUI.WindowTitle = 'AragonMovie | Frontend :$FrontendPort'; " +
                 "Set-Location -LiteralPath '$Root\frontend'; " +
                 "npm run dev"
$frontendProc = Start-Process powershell -PassThru -WorkingDirectory $Root -ArgumentList @(
    '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $frontendInner
)

# 记录 PID 供 -Stop 使用
@($backendProc.Id, $frontendProc.Id) | Set-Content -Path $PidFile -Encoding ascii

# ============================================================
# 等待端口就绪
# ============================================================
Step 'Waiting for backend to come up (max 120s)...'
if ($backendProc.HasExited) {
    Fail "Backend window exited immediately (code $($backendProc.ExitCode)). Check the 'AragonMovie | Backend' window for errors."
    exit 1
}
if (Wait-ForPort $BackendPort 120) {
    Ok "Backend ready  : http://localhost:$BackendPort  (API docs: /docs)"
} else {
    Warn "Backend port $BackendPort not open after 120s - check the backend window logs."
}

Step 'Waiting for frontend to come up (max 120s)...'
if ($frontendProc.HasExited) {
    Fail "Frontend window exited immediately (code $($frontendProc.ExitCode)). Check the 'AragonMovie | Frontend' window for errors."
    exit 1
}
if (Wait-ForPort $FrontendPort 120) {
    Ok "Frontend ready : http://localhost:$FrontendPort"
} else {
    Warn "Frontend port $FrontendPort not open after 120s - check the frontend window logs."
}

# ============================================================
# 完成
# ============================================================
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' All services launched' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host "  Frontend      : http://localhost:$FrontendPort"
Write-Host "  Settings UI   : http://localhost:$FrontendPort/settings"
Write-Host "  Backend API   : http://localhost:$BackendPort"
Write-Host "  API Docs      : http://localhost:$BackendPort/docs"
Write-Host ''
Write-Host '  Logs stream in the two service windows ( titled AragonMovie | ... ).' -ForegroundColor DarkGray
Write-Host "  Stop everything : .\start-dev.ps1 -Stop" -ForegroundColor DarkGray
Write-Host ''

if (-not $NoBrowser) {
    Start-Process "http://localhost:$FrontendPort"
}
