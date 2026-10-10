# setup.ps1 - Windows one-shot setup for agent_knowledge_self_built
# Usage:
#   .\setup.ps1
#   .\setup.ps1 -Port 8001

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $proj

Write-Host ""
Write-Host "==> project dir: $proj" -ForegroundColor Cyan

# 1. check python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "python not found. Install Python 3.10+ and re-run." -ForegroundColor Red
    exit 1
}
$ver = (python --version)
Write-Host "==> python: $ver" -ForegroundColor Cyan

# 2. venv
$venv = ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "==> creating venv..." -ForegroundColor Cyan
    python -m venv $venv
} else {
    Write-Host "==> venv exists, reuse." -ForegroundColor Cyan
}

$activate = Join-Path $venv "Scripts\Activate.ps1"
. $activate

# 3. install deps
Write-Host "==> installing dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> .env created from .env.example, edit it with your keys." -ForegroundColor Yellow
} else {
    Write-Host "==> .env exists, keep current." -ForegroundColor Cyan
}

# 5. init db + seed docs
Write-Host "==> initializing db and docs..." -ForegroundColor Cyan
python scripts\seed_documents.py
python -c "from store.session import init_db; from config import settings; init_db(settings.SQLITE_PATH); print('db ready')"

# 6. ingest
Write-Host "==> ingesting RAG..." -ForegroundColor Cyan
python -m rag.ingest_main

# 7. start service
$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        Write-Host "==> stopping PID $p on port $Port ..." -ForegroundColor Yellow
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

Write-Host "==> starting service on port $Port ..." -ForegroundColor Cyan
$proc = Start-Process -FilePath "python" -ArgumentList "-m","app.main" `
    -WorkingDirectory $proj -PassThru -WindowStyle Hidden

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}

Write-Host ""
if ($ready) {
    Write-Host "==> setup complete: http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "    next steps:" -ForegroundColor Green
    Write-Host "      1) edit .env with your OPENAI_API_KEY / LLM_MODEL" -ForegroundColor Green
    Write-Host "      2) run .\restart.ps1 -NoIngest after changing .env" -ForegroundColor Green
} else {
    Write-Host "==> startup timed out; check the service log and retry." -ForegroundColor Red
}
