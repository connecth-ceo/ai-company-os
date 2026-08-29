param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS decision follow-through read-only cloud smoke test"
Write-Host "The API key is read from the clipboard, used only in memory, and not saved."
Write-Host "Copy APP_API_KEY from Render. Do NOT paste it into this window."
Write-Host "Press Enter once; the script will read the clipboard automatically."
[void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
$apiKey = Get-Clipboard -Raw
$apiKey = $apiKey -replace '[\x00-\x20\x7F]', ''

if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Length -lt 32) {
    Write-Host "APP_API_KEY was not found in the clipboard." -ForegroundColor Red
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

    Write-Host "2/3 Checking the follow-through API contract..."
    $openApi = Invoke-RestMethod -Method Get -Uri "$BaseUrl/openapi.json"
    $followThroughPath = $openApi.paths.'/api/v1/decisions/follow-through'
    if ($null -eq $followThroughPath.get) {
        throw "The decision follow-through API contract was not found."
    }

    Write-Host "3/3 Reading the decision follow-through queue..."
    $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/decisions/follow-through?limit=6" -Headers $headers
    if ($result.rule_version -ne "decision-follow-through-v1") {
        throw "Unexpected decision follow-through rule version."
    }
    foreach ($item in @($result.items)) {
        if ($item.follow_through_level -notin @("at_risk", "untracked", "in_progress", "planned")) {
            throw "Unexpected default queue follow-through level."
        }
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Active decisions: $($result.summary.active_decisions)"
    Write-Host "Execution coverage: $($result.summary.execution_coverage_percent)%"
    Write-Host "At risk: $($result.summary.at_risk_decisions)"
    Write-Host "Untracked: $($result.summary.untracked_decisions)"
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
