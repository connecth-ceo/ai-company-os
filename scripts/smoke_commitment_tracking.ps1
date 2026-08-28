param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS Commitment Tracking cloud smoke test"
Write-Host "This creates two marked commitments and closes both after verification."
Write-Host "It does not start an OpenAI task."
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
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$first = $null
$second = $null

try {
    Write-Host "1/6 Creating one overdue commitment..."
    $firstBody = @{
        statement = "[SMOKE] Overdue follow-up $timestamp"
        owner_id = "CEO"
        due_at = (Get-Date).AddMinutes(-5).ToUniversalTime().ToString("o")
        provenance = @{ channel = "cloud_smoke" }
    } | ConvertTo-Json
    $first = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/commitments" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $firstBody

    Write-Host "2/6 Verifying overdue detection..."
    $overdue = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/commitments?overdue_only=true" -Headers $headers)
    if ($overdue.id -notcontains $first.id -or -not $first.is_overdue) {
        throw "The overdue commitment was not detected."
    }

    Write-Host "3/6 Creating one future commitment..."
    $secondBody = @{
        statement = "[SMOKE] Future follow-up $timestamp"
        owner_type = "agent"
        owner_id = "Research Agent"
        due_at = (Get-Date).AddDays(1).ToUniversalTime().ToString("o")
        provenance = @{ channel = "cloud_smoke" }
    } | ConvertTo-Json
    $second = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/commitments" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $secondBody

    Write-Host "4/6 Starting and completing the future commitment..."
    $startedBody = @{ status = "in_progress"; note = "Cloud smoke start" } | ConvertTo-Json
    $started = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/commitments/$($second.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $startedBody
    $completedBody = @{ status = "completed"; note = "Cloud smoke complete" } | ConvertTo-Json
    $completed = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/commitments/$($second.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $completedBody

    Write-Host "5/6 Cancelling the overdue test commitment..."
    $cancelBody = @{ status = "cancelled"; note = "Cloud smoke cleanup" } | ConvertTo-Json
    $cancelled = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/commitments/$($first.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $cancelBody

    Write-Host "6/6 Verifying final records and cleanup..."
    $overdueAfter = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/commitments?overdue_only=true" -Headers $headers)
    if (
        $started.status -ne "in_progress" -or
        $completed.status -ne "completed" -or
        [string]::IsNullOrWhiteSpace($completed.completed_at) -or
        $cancelled.status -ne "cancelled" -or
        $overdueAfter.id -contains $first.id
    ) {
        throw "The returned commitment lifecycle does not match the expected state."
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Cancelled test commitment: $($first.id)"
    Write-Host "Completed test commitment: $($second.id)"
    Write-Host "No OpenAI task was executed."
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
