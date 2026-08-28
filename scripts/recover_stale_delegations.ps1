param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS stale delegation recovery"
Write-Host "The first scan is read-only. No OpenAI task will be started."
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
    $previewBody = @{ dry_run = $true; limit = 100 } | ConvertTo-Json
    $preview = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/delegations/recover-stale" -Headers $headers -ContentType "application/json" -Body $previewBody
    Write-Host ""
    Write-Host "DRY RUN COMPLETE" -ForegroundColor Green
    Write-Host "Scanned: $($preview.scanned)"
    Write-Host "Stale: $($preview.stale)"
    Write-Host "Safe reset candidates: $($preview.reset_for_retry)"
    Write-Host "Manual-review quarantine candidates: $($preview.quarantined)"
    foreach ($item in $preview.items) {
        Write-Host "  $($item.delegation_id) | $($item.previous_status) | $($item.action)"
    }
    if ($preview.stale -eq 0) {
        Write-Host "No recovery action is needed."
        exit 0
    }

    Write-Host ""
    Write-Host "Running executions will never be retried automatically."
    $confirmation = Read-Host "Type RECOVER to apply exactly the displayed recovery plan"
    if ($confirmation -cne "RECOVER") {
        Write-Host "No state was changed."
        exit 0
    }
    $applyBody = @{ dry_run = $false; limit = 100 } | ConvertTo-Json
    $result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/delegations/recover-stale" -Headers $headers -ContentType "application/json" -Body $applyBody
    Write-Host ""
    Write-Host "RECOVERY COMPLETE" -ForegroundColor Green
    Write-Host "Reset for retry: $($result.reset_for_retry)"
    Write-Host "Quarantined for manual review: $($result.quarantined)"
}
catch {
    Write-Host ""
    Write-Host "RECOVERY FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    Set-Clipboard -Value " "
    $apiKey = $null
    $headers = $null
}
