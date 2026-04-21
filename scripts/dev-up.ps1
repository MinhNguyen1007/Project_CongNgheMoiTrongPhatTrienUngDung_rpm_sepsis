# scripts/dev-up.ps1
# Start the full dev stack from project root:
#   powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1
#
# Spawns 3 PowerShell windows: backend, frontend, consumer.
# Infra (docker-compose core services) is started first.

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..").Path

Write-Host "`n== Sepsis RPM dev-up ==" -ForegroundColor Cyan
Write-Host "root: $root"

# 1. Infra
Write-Host "`n[1/4] docker-compose core services..." -ForegroundColor Yellow
Push-Location $root
docker-compose up -d localstack postgres minio minio-init redis mlflow | Out-Host
Pop-Location

# 2. MLflow health
Write-Host "`n[2/4] verify MLflow..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:5000/health" -TimeoutSec 5
    Write-Host "   MLflow OK: $health"
} catch {
    Write-Warning "MLflow not ready on :5000 - backend may fail. Wait 10s and rerun if needed."
}

# 3. Spawn backend (uvicorn, port 8000)
Write-Host "`n[3/4] spawning backend (port 8000)..." -ForegroundColor Yellow
$backendCmd = "Write-Host 'BACKEND' -ForegroundColor Green; python -m uvicorn app.backend.main:app --reload --port 8000"
Start-Process powershell -WorkingDirectory $root `
    -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal

# 4. Spawn frontend (vite, port 5173)
Write-Host "[3/4] spawning frontend (port 5173)..." -ForegroundColor Yellow
$frontendCmd = "Write-Host 'FRONTEND' -ForegroundColor Green; npm run dev"
Start-Process powershell -WorkingDirectory (Join-Path $root "app\frontend") `
    -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal

# 5. Spawn consumer (waits 8s so backend is ready)
Write-Host "[4/4] spawning consumer (waits 8s for backend)..." -ForegroundColor Yellow
$consumerCmd = "Write-Host 'CONSUMER - waiting 8s for backend' -ForegroundColor Green; Start-Sleep -Seconds 8; python data-pipeline\consumer\handler.py"
Start-Process powershell -WorkingDirectory $root `
    -ArgumentList "-NoExit", "-Command", $consumerCmd -WindowStyle Normal

Write-Host "`nAll services spawning. Check:" -ForegroundColor Cyan
Write-Host "   Backend:   http://localhost:8000/health"
Write-Host "   Frontend:  http://localhost:5173"
Write-Host "   MLflow:    http://localhost:5000"
Write-Host "   MinIO:     http://localhost:9001  (minioadmin/minioadmin123)"
Write-Host "`nRun simulator when you want to push data:" -ForegroundColor Yellow
Write-Host "   python data-pipeline\simulator\run.py --patients 10 --speed 0.2s"
Write-Host "`nStop all: scripts\dev-down.ps1" -ForegroundColor Yellow
