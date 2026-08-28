param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS monthly AI cost check"
Write-Host "This check is read-only and does not start an OpenAI task."
Write-Host "Copy APP_API_KEY from Render. Do NOT paste it into this window."
Write-Host "Press Enter once; the script will read the clipboard automatically."
[void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
$apiKey = (Get-Clipboard -Raw) -replace '[\x00-\x20\x7F]', ''

if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Length -lt 32) {
    Write-Host "APP_API_KEY was not found in the clipboard." -ForegroundColor Red
    exit 1
}

$headers = @{
    "X-API-Key" = $apiKey
    "X-Tenant-ID" = "owner"
}

try {
    $summary = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/ai-costs/current-month" -Headers $headers
    $ledger = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/ai-costs/ledger?limit=10" -Headers $headers
    Write-Host ""
    Write-Host "COST CONTROL ONLINE" -ForegroundColor Green
    Write-Host "Period: $($summary.period_start)"
    Write-Host "Monthly budget: `$$($summary.budget_usd)"
    Write-Host "Completed estimate: `$$($summary.estimated_spend_usd)"
    Write-Host "Active reservations: `$$($summary.reserved_usd)"
    Write-Host "Uncertain/quarantined: `$$($summary.uncertain_spend_usd)"
    Write-Host "Remaining: `$$($summary.remaining_usd)"
    Write-Host ""
    Write-Host "Recent execution estimates:"
    if ($ledger.Count -eq 0) {
        Write-Host "  No cost ledger entries yet."
    }
    foreach ($entry in $ledger) {
        Write-Host "  $($entry.occurred_at) | $($entry.model) | $($entry.calculation_status) | `$$($entry.estimated_cost_usd)"
    }
    Write-Host ""
    Write-Host "These are token-based estimates, not provider invoice amounts."
}
catch {
    Write-Host ""
    Write-Host "COST CHECK FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    Set-Clipboard -Value " "
    $apiKey = $null
    $headers = $null
}
