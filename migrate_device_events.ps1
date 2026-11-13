$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$container = 'mcp-demo-lab-db-1'
if (-not (docker inspect -f '{{.State.Running}}' $container 2>$null) -eq 'true') {
    throw 'mcp-demo-lab-db-1 çalışmıyor.'
}

Get-Content -LiteralPath .\migrate_device_events.sql -Encoding UTF8 |
    docker exec -i $container psql -v ON_ERROR_STOP=1 -U postgres -d mcp_demo

if ($LASTEXITCODE -ne 0) {
    throw 'Cihaz olayları geçişi başarısız oldu.'
}

Write-Host 'Cihaz lokasyonları ve 70 sentetik olay hazır.'
