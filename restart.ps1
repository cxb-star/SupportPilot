# ============================================================
# restart.ps1 - one-shot restart for agent_knowledge_self_built
# Usage:  .\restart.ps1             kill port + re-ingest + start
#        .\restart.ps1 -NoIngest   skip ingest, just restart
#        .\restart.ps1 -Port 8001  use a different port
# ============================================================
param(
    [switch]$NoIngest,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $proj

Write-Host ""
Write-Host "==> project dir: $proj" -ForegroundColor Cyan

# 1. free the port
Write-Host "==> clearing port ${Port} ..." -ForegroundColor Cyan
$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        Write-Host "    stopping PID $p ..." -ForegroundColor Yellow
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
} else {
    Write-Host "    port ${Port} free, nothing to clear." -ForegroundColor DarkGray
}

# 2. re-ingest (optional)
if (-not $NoIngest) {
    Write-Host "==> re-ingesting rag.ingest_main ..." -ForegroundColor Cyan
    python -m rag.ingest_main 2>&1 | Out-Host
} else {
    Write-Host "==> skip ingest (-NoIngest)" -ForegroundColor DarkGray
}

# 3. start service in background
Write-Host "==> starting python -m app.main on port ${Port} ..." -ForegroundColor Cyan
$proc = Start-Process -FilePath "python" -ArgumentList "-m","app.main" `
    -WorkingDirectory $proj -PassThru -WindowStyle Hidden
Write-Host "    launched, PID $($proc.Id), waiting for readiness ..." -ForegroundColor Yellow

# 4. poll /health for up to 20s
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:${Port}/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}

Write-Host ""
if ($ready) {
    $body = (Invoke-WebRequest "http://127.0.0.1:${Port}/health" -UseBasicParsing).Content
    $info = $body | ConvertFrom-Json
    Write-Host "==> service ready: http://127.0.0.1:${Port}" -ForegroundColor Green
    Write-Host ("    LLM configured: {0}   Embedding configured: {1}" -f $info.llm_configured, $info.embedding_configured) -ForegroundColor Green
    Write-Host ""
    Write-Host "   open in browser: http://127.0.0.1:${Port}  (if you see the old UI, press Ctrl+Shift+R to hard refresh)" -ForegroundColor Cyan
} else {
    Write-Host "==> startup timed out or failed; check the logs above." -ForegroundColor Red
}
