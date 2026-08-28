param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS Attention Queue cloud smoke test"
Write-Host "This creates one marked overdue commitment and one approval, verifies them, and closes both."
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
$commitment = $null
$approval = $null

try {
    Write-Host "1/5 Creating one critical overdue commitment..."
    $commitmentBody = @{
        statement = "[SMOKE] Attention overdue follow-up $timestamp"
        owner_id = "CEO"
        due_at = (Get-Date).AddHours(-80).ToUniversalTime().ToString("o")
        provenance = @{ channel = "attention_cloud_smoke" }
    } | ConvertTo-Json
    $commitment = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/commitments" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $commitmentBody

    Write-Host "2/5 Creating one pending approval..."
    $approvalBody = @{
        action = "[SMOKE] Attention approval $timestamp"
        reason = "Attention Queue cloud verification"
        risk = "medium"
    } | ConvertTo-Json
    $approval = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/approvals" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $approvalBody

    Write-Host "3/5 Verifying severity, order, and filters..."
    $queue = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/attention" -Headers $headers
    $commitmentItem = @($queue.items | Where-Object { $_.resource_id -eq $commitment.id })[0]
    $approvalItem = @($queue.items | Where-Object { $_.resource_id -eq $approval.id })[0]
    $critical = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/attention?min_level=critical&kind=overdue_commitment" -Headers $headers
    if (
        $null -eq $commitmentItem -or
        $commitmentItem.level -ne "critical" -or
        $null -eq $approvalItem -or
        $approvalItem.level -ne "decision" -or
        $critical.items.resource_id -notcontains $commitment.id
    ) {
        throw "The attention queue did not return the expected deterministic results."
    }

    Write-Host "4/5 Closing both marked test records..."
    $cancelBody = @{ status = "cancelled"; note = "Attention smoke cleanup" } | ConvertTo-Json
    $cancelled = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/commitments/$($commitment.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $cancelBody
    $decisionBody = @{ approved = $false; decided_by = "CEO"; note = "Attention smoke cleanup" } | ConvertTo-Json
    $decided = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/approvals/$($approval.id)/decide" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $decisionBody

    Write-Host "5/5 Verifying resolved items leave the queue..."
    $after = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/attention" -Headers $headers
    if (
        $cancelled.status -ne "cancelled" -or
        $decided.status -ne "rejected" -or
        $after.items.resource_id -contains $commitment.id -or
        $after.items.resource_id -contains $approval.id
    ) {
        throw "Resolved smoke records remained in the attention queue."
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Cancelled test commitment: $($commitment.id)"
    Write-Host "Rejected test approval: $($approval.id)"
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
