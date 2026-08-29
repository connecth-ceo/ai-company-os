param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS provenance review read-only cloud smoke test"
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

    Write-Host "2/3 Checking the review API contract..."
    $openApi = Invoke-RestMethod -Method Get -Uri "$BaseUrl/openapi.json"
    $reviewPath = $openApi.paths.'/api/v1/provenance/{record_id}/reviews'
    if ($null -eq $reviewPath.get -or $null -eq $reviewPath.post) {
        throw "The provenance review API contract was not found."
    }

    Write-Host "3/3 Reading provenance review history when records exist..."
    $records = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/provenance?limit=1" -Headers $headers)
    $reviews = @()
    if ($records.Count -gt 0) {
        $recordId = $records[0].id
        $reviews = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/provenance/$recordId/reviews" -Headers $headers)
        foreach ($review in $reviews) {
            if ($review.decision -notin @("verified", "rejected")) {
                throw "Unexpected provenance review decision."
            }
            if ($review.reviewed_content_hash -notmatch '^[0-9a-f]{64}$') {
                throw "Unexpected reviewed content hash."
            }
        }
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Records sampled: $($records.Count)"
    Write-Host "Reviews sampled: $($reviews.Count)"
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
