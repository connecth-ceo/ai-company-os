param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS decision readiness queue read-only cloud smoke test"
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
    Write-Host "1/3 Checking service readiness..."
    $ready = Invoke-RestMethod -Method Get -Uri "$BaseUrl/ready"
    if ($ready.status -ne "ready" -or $ready.components.schema -ne "c5e7f9b1d3a5") {
        throw "The service is not ready on the expected database revision."
    }

    Write-Host "2/3 Checking the readiness API contract..."
    $openApi = Invoke-RestMethod -Method Get -Uri "$BaseUrl/openapi.json"
    $readinessPath = $openApi.paths.'/api/v1/decisions/readiness'
    if ($null -eq $readinessPath.get) {
        throw "The decision readiness API contract was not found."
    }

    Write-Host "3/3 Reading the decision readiness queue..."
    $readiness = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/decisions/readiness?limit=6" -Headers $headers
    if ($readiness.rule_version -ne "decision-readiness-v1") {
        throw "Unexpected decision readiness rule version."
    }
    if ($readiness.summary.total_decisions -lt 0) {
        throw "Unexpected decision readiness summary."
    }
    foreach ($item in @($readiness.items)) {
        if ($item.readiness_level -notin @("watch", "review", "blocked")) {
            throw "Unexpected default queue readiness level."
        }
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Total decisions: $($readiness.summary.total_decisions)"
    Write-Host "Ready: $($readiness.summary.ready_decisions)"
    Write-Host "Review: $($readiness.summary.review_decisions)"
    Write-Host "Blocked: $($readiness.summary.blocked_decisions)"
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
