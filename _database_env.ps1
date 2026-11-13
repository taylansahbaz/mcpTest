function Get-McpDatabaseCredentials {
    param(
        [string]$EnvFile = $(if ($env:MCP_DB_ENV_FILE) {
            $env:MCP_DB_ENV_FILE
        } else {
            Join-Path $env:USERPROFILE 'Downloads\mcp_docker\.env'
        })
    )

    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        throw "Docker ortam dosyasi bulunamadi: $EnvFile"
    }

    $passwordLine = Get-Content -LiteralPath $EnvFile |
        Where-Object { $_ -match '^POSTGRES_PASSWORD=' } |
        Select-Object -First 1

    if (-not $passwordLine) {
        throw 'POSTGRES_PASSWORD Docker ortam dosyasinda bulunamadi.'
    }

    $adminPassword = $passwordLine.Substring($passwordLine.IndexOf('=') + 1).Trim().Trim('"').Trim("'")
    if (-not $adminPassword) {
        throw 'POSTGRES_PASSWORD bos olamaz.'
    }

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $sourceBytes = [System.Text.Encoding]::UTF8.GetBytes("device-data-mcp:v1:$adminPassword")
        $hashBytes = $sha256.ComputeHash($sourceBytes)
        $readerPassword = ([BitConverter]::ToString($hashBytes)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }

    [pscustomobject]@{
        AdminPassword  = $adminPassword
        ReaderPassword = $readerPassword
    }
}

function Set-McpReaderEnvironment {
    $credentials = Get-McpDatabaseCredentials
    $env:PGHOST = '127.0.0.1'
    $env:PGPORT = '55432'
    $env:PGDATABASE = 'mcp_demo'
    $env:PGUSER = 'mcp_demo_mcp_reader'
    $env:PGPASSWORD = $credentials.ReaderPassword
}
