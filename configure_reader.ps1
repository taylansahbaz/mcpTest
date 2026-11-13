$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. .\_database_env.ps1

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker bulunamadi.'
}

$containerName = 'mcp-demo-lab-db-1'
$runningContainers = docker ps --format '{{.Names}}'
if ($runningContainers -notcontains $containerName) {
    throw "$containerName calismiyor. Once PostgreSQL paketini baslatin."
}

$credentials = Get-McpDatabaseCredentials
$readerPassword = $credentials.ReaderPassword
$roleMarker = 'Managed by device-data-mcp demo setup'

$sql = @"
\set ON_ERROR_STOP on
DO `$setup`$
DECLARE
    existing_comment text;
BEGIN
    SELECT shobj_description(oid, 'pg_authid')
      INTO existing_comment
      FROM pg_roles
     WHERE rolname = 'mcp_demo_mcp_reader';

    IF FOUND AND existing_comment IS DISTINCT FROM '$roleMarker' THEN
        RAISE EXCEPTION 'mcp_demo_mcp_reader exists but is not managed by this project';
    ELSIF FOUND THEN
        ALTER ROLE mcp_demo_mcp_reader WITH LOGIN PASSWORD '$readerPassword';
    ELSE
        CREATE ROLE mcp_demo_mcp_reader LOGIN PASSWORD '$readerPassword';
    END IF;
END
`$setup`$;

ALTER ROLE mcp_demo_mcp_reader
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE mcp_demo_mcp_reader SET default_transaction_read_only = on;
COMMENT ON ROLE mcp_demo_mcp_reader IS '$roleMarker';
GRANT CONNECT ON DATABASE mcp_demo TO mcp_demo_mcp_reader;
GRANT USAGE ON SCHEMA public TO mcp_demo_mcp_reader;
GRANT SELECT ON TABLE public.devices, public.measurements TO mcp_demo_mcp_reader;
DO `$grant_events`$
BEGIN
    IF to_regclass('public.device_events') IS NOT NULL THEN
        GRANT SELECT ON TABLE public.device_events TO mcp_demo_mcp_reader;
    END IF;
END
`$grant_events`$;

SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin
FROM pg_roles
WHERE rolname = 'mcp_demo_mcp_reader';
"@

$sql | docker exec -i $containerName psql -U postgres -d mcp_demo
if ($LASTEXITCODE -ne 0) {
    throw 'Salt okunur PostgreSQL rolu yapilandirilamadi.'
}

Write-Host 'Salt okunur PostgreSQL rolu hazir.'
