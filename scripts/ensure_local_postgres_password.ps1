$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envPath)) {
    throw ".env was not found at $envPath"
}

$content = [IO.File]::ReadAllText($envPath)
if ($content -match '(?m)^POSTGRES_PASSWORD=.+$') {
    Write-Host 'POSTGRES_PASSWORD is already configured; value was not displayed.'
    exit 0
}

$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($bytes)
}
finally {
    $rng.Dispose()
}
$password = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')

$normalized = $content.TrimEnd("`r", "`n")
$updated = "$normalized`r`nPOSTGRES_PASSWORD=$password`r`n"
[IO.File]::WriteAllText($envPath, $updated, [Text.UTF8Encoding]::new($false))
Write-Host 'POSTGRES_PASSWORD was generated and stored in .env; value was not displayed.'
