param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS portfolio health read-only cloud smoke test"
Write-Host "The API key is read from the clipboard, used only in memory, and not saved."
Write-Host "Copy APP_API_KEY from Render. Do NOT paste it into this window."
Write-Host "Press Enter once; the script will read the clipboard automatically."
[void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
$apiKey = Get-Clipboard -Raw
$apiKey = $apiKey -replace '[\x00-\x20\x7F]', ''

if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Length -lt 32) {
    Write-Host "APP_API_KEY was not found in the clipboard." -ForegroundColor Red
    Write-Host "Return to Render and click Copy value on the APP_API_KEY row."
    exit 1
}

$headers = @{
    "X-API-Key" = $apiKey
    "X-Tenant-ID" = "owner"
}

try {
    Write-Host "1/2 Checking service readiness..."
    $ready = Invoke-RestMethod -Method Get -Uri "$BaseUrl/ready"
    if ($ready.status -ne "ready") {
        throw "The service readiness response is not ready."
    }

    Write-Host "2/2 Reading portfolio health..."
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/portfolio/health" -Headers $headers
    if ($health.rule_version -ne "portfolio-health-v1" -or $null -eq $health.summary.health_counts) {
        throw "The portfolio health response does not match the expected contract."
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Open goals: $($health.summary.open_goals)"
    Write-Host "Overdue goals: $($health.summary.overdue_goals)"
    Write-Host "Open projects: $($health.summary.open_projects)"
    Write-Host "Task completion: $($health.summary.completion_percent)%"
    Write-Host "No data was changed and no OpenAI task was executed."
}
catch {
    Write-Host ""
    Write-Host "SMOKE TEST FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    Set-Clipboard -Value " "
    $apiKey = $null
    $headers = $null
}

