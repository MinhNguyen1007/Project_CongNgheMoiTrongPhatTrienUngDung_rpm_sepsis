# scripts/dev-down.ps1
# Dừng backend/frontend/consumer (theo port + tên process) và docker-compose.
# Chạy: powershell -ExecutionPolicy Bypass -File scripts\dev-down.ps1

$ErrorActionPreference = "Continue"
$root = (Resolve-Path "$PSScriptRoot\..").Path

Write-Host "`n== Sepsis RPM dev-down ==" -ForegroundColor Cyan

function Stop-Port($port, $label) {
    $targetPids = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess
    foreach ($targetPid in ($targetPids | Select-Object -Unique)) {
        if ($targetPid) {
            try {
                Stop-Process -Id $targetPid -Force -ErrorAction Stop
                Write-Host ("stopped {0} (pid={1}, port={2})" -f $label, $targetPid, $port) -ForegroundColor Green
            } catch {
                Write-Warning ("could not stop pid={0} on port {1}: {2}" -f $targetPid, $port, $_)
            }
        }
    }
}

Stop-Port 8000 "backend"
Stop-Port 5173 "frontend"

# Consumer không expose port — tìm python process chạy handler.py
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "consumer[\\/]handler\.py" } |
    ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force
            Write-Host ("stopped consumer (pid={0})" -f $_.ProcessId) -ForegroundColor Green
        } catch {
            Write-Warning ("could not stop consumer pid={0}: {1}" -f $_.ProcessId, $_)
        }
    }

# Docker infra + monitoring (grafana, prometheus dùng profile)
Write-Host "`nStopping docker-compose services (including monitoring profile)..." -ForegroundColor Yellow
Push-Location $root
docker compose --profile monitoring down | Out-Host
Pop-Location

Write-Host "`nDone. Dung 'docker compose --profile monitoring down -v' neu muon xoa sach volume." -ForegroundColor Cyan
