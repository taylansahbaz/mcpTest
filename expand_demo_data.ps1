$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$container = 'mcp-demo-lab-db-1'
if (-not (docker inspect -f '{{.State.Running}}' $container 2>$null) -eq 'true') {
    throw 'mcp-demo-lab-db-1 çalışmıyor.'
}

Get-Content -LiteralPath .\expand_demo_data.sql -Encoding UTF8 |
    docker exec -i $container psql -v ON_ERROR_STOP=1 -U postgres -d mcp_demo

if ($LASTEXITCODE -ne 0) {
    throw 'Demo veri artırma işlemi başarısız oldu.'
}
