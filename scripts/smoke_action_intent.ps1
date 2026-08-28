param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS ActionIntent proposal-only cloud smoke test"
Write-Host "This creates and rejects one test proposal. No OpenAI or Telegram call is made."
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

try {
    Write-Host "1/4 Checking current deployed schema..."
    $ready = Invoke-RestMethod -Method Get -Uri "$BaseUrl/ready"
    if ($ready.status -ne "ready" -or $ready.components.schema -ne "f2a4b6c8d0e2") {
        throw "The service is not ready on ActionIntent schema f2a4b6c8d0e2."
    }

    Write-Host "2/4 Creating one immutable test proposal..."
    $body = @{
        action_type = "external_publish"
        summary = "[SMOKE] ActionIntent proposal $timestamp"
        reason = "Proposal-only cloud verification"
        risk = "high"
        payload = @{
            channel = "smoke_test_only"
            draft_id = "smoke-$timestamp"
        }
        expires_in_minutes = 30
        idempotency_key = "action-intent-smoke-$timestamp"
    } | ConvertTo-Json -Depth 4
    $intent = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/action-intents" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $body
    if ($intent.status -ne "proposed" -or $intent.execution_scope -ne "single_use" -or $intent.payload_hash.Length -ne 64) {
        throw "The created proposal did not contain the expected immutable fields."
    }

    Write-Host "3/4 Rejecting the smoke approval to close it..."
    $decisionBody = @{
        approved = $false
        decided_by = "CEO"
        note = "ActionIntent smoke cleanup"
    } | ConvertTo-Json
    $approval = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/approvals/$($intent.approval_id)/decide" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $decisionBody

    Write-Host "4/4 Verifying linked rejected state..."
    $stored = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/action-intents/$($intent.id)" -Headers $headers
    if ($approval.status -ne "rejected" -or $stored.status -ne "rejected") {
        throw "The linked approval and proposal did not close together."
    }

    Write-Host "ACTION INTENT SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "ActionIntent: $($intent.id)"
    Write-Host "Payload hash: $($intent.payload_hash)"
    Write-Host "No external action was executed."
}
catch {
    Write-Host "ACTION INTENT SMOKE TEST FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    $apiKey = $null
    $headers = $null
    try { Set-Clipboard -Value "" } catch { }
}
