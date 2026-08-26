param(
    [int]$ReadyTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$outputDir = Join-Path $projectRoot 'outputs'
$statusPath = Join-Path $outputDir 'docker-integration.status'
$logPath = Join-Path $outputDir 'docker-integration.log'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
Set-Location $projectRoot

$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($dockerCommand) {
    $docker = $dockerCommand.Source
}
else {
    $docker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
}
if (-not (Test-Path -LiteralPath $docker)) {
    throw 'Docker CLI was not found.'
}

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code ${LASTEXITCODE}: docker $($Arguments -join ' ')"
    }
}

Start-Transcript -Path $logPath -Force
try {
    'RUNNING' | Set-Content -LiteralPath $statusPath
    Write-Host '1/6 Validating Docker Engine and Compose configuration...'
    Invoke-Docker info '--format' 'Docker Engine {{.ServerVersion}} on {{.OperatingSystem}}'
    Invoke-Docker compose config '--quiet'

    Write-Host '2/6 Building and starting PostgreSQL, Redis, migrations, API, and Celery...'
    Invoke-Docker compose up '-d' '--build'

    Write-Host '3/6 Waiting for API readiness...'
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/ready' -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 5
        }
    }
    if (-not $ready) {
        throw "API did not become ready within $ReadyTimeoutSeconds seconds."
    }

    Write-Host '4/6 Verifying database schema and Redis connectivity from the API container...'
    Invoke-Docker compose exec '-T' api python scripts/verify_runtime.py

    Write-Host '5/6 Verifying Celery worker responsiveness...'
    Invoke-Docker compose exec '-T' worker celery '-A' app.worker.celery_app inspect ping '--timeout=10'

    Write-Host '6/6 Capturing final service state...'
    Invoke-Docker compose ps
    'SUCCESS' | Set-Content -LiteralPath $statusPath
    Write-Host 'Docker integration verified successfully.' -ForegroundColor Green
    Write-Host 'CEO Desk: http://127.0.0.1:8000'
}
catch {
    'FAILED' | Set-Content -LiteralPath $statusPath
    Write-Error $_
    Write-Host 'Recent container logs:' -ForegroundColor Yellow
    & $docker compose logs '--tail=100' api worker migrate db redis
    exit 1
}
finally {
    Stop-Transcript
}
