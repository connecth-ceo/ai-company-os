param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS scheduled briefing read-only cloud check"
Write-Host "This does not send Telegram messages or start an OpenAI task."
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
    Write-Host "1/3 Checking deployed schema and service readiness..."
    $ready = Invoke-RestMethod -Method Get -Uri "$BaseUrl/ready"
    if ($ready.status -ne "ready" -or $ready.components.schema -ne "e1f3a5c7d9b2") {
        throw "The service is not ready on briefing delivery schema e1f3a5c7d9b2."
    }

    Write-Host "2/3 Checking safe schedule configuration..."
    $schedule = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/briefing-schedule" -Headers $headers
    if (-not $schedule.enabled -or $schedule.daily_time -ne "07:00") {
        throw "Scheduled briefing is not enabled for 07:00."
    }

    Write-Host "3/3 Reading delivery history without sending a message..."
    $deliveries = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/briefing-deliveries?limit=5" -Headers $headers)
    Write-Host "SCHEDULED BRIEFING CHECK PASSED" -ForegroundColor Green
    Write-Host "Daily time: $($schedule.daily_time) $($schedule.timezone)"
    Write-Host "Quiet hours: $($schedule.quiet_hours)"
    Write-Host "Recorded deliveries: $($deliveries.Count)"
}
catch {
    Write-Host "SCHEDULED BRIEFING CHECK FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    $apiKey = $null
    try { Set-Clipboard -Value "" } catch { }
}
