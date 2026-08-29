param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS provenance quality queue read-only cloud smoke test"
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

    Write-Host "2/3 Checking the quality API contract..."
    $openApi = Invoke-RestMethod -Method Get -Uri "$BaseUrl/openapi.json"
    $qualityPath = $openApi.paths.'/api/v1/provenance/quality'
    if ($null -eq $qualityPath.get) {
        throw "The provenance quality API contract was not found."
    }

    Write-Host "3/3 Reading the provenance quality queue..."
    $quality = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/provenance/quality?limit=8" -Headers $headers
    if ($quality.rule_version -ne "provenance-quality-v1") {
        throw "Unexpected provenance quality rule version."
    }
    if ($quality.summary.total_records -lt 0 -or $quality.summary.verification_coverage_percent -lt 0 -or $quality.summary.verification_coverage_percent -gt 100) {
        throw "Unexpected provenance quality summary."
    }
    foreach ($item in @($quality.items)) {
        if ($item.quality_level -notin @("watch", "action", "critical")) {
            throw "Unexpected queue quality level."
        }
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Total provenance records: $($quality.summary.total_records)"
    Write-Host "Needs review: $($quality.summary.needs_review_records)"
    Write-Host "Rejected: $($quality.summary.rejected_records)"
    Write-Host "Verification coverage: $($quality.summary.verification_coverage_percent)%"
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
