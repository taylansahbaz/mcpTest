$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. .\_database_env.ps1

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Python sanal ortami bulunamadi.'
}

Set-McpReaderEnvironment
& $python -m unittest discover -s tests -v
exit $LASTEXITCODE
