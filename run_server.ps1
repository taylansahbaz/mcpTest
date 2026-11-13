$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. .\_database_env.ps1

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Python sanal ortami bulunamadi. requirements.txt bagimliliklarini kurun.'
}

Set-McpReaderEnvironment
& $python (Join-Path $PSScriptRoot 'server.py')
exit $LASTEXITCODE
