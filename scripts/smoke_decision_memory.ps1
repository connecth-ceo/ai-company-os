param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS Decision Memory cloud smoke test"
Write-Host "This creates two marked test decisions. It does not start an OpenAI task."
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
    Write-Host "1/6 Creating a proposed decision..."
    $proposalBody = @{
        subject = "[SMOKE] Decision lifecycle $timestamp"
        choice = "Proposed choice"
        rationale = "Cloud lifecycle verification only."
        status = "proposed"
    } | ConvertTo-Json
    $proposal = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/decisions" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $proposalBody

    Write-Host "2/6 Confirming that the proposal is not effective..."
    $effectiveBefore = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/decisions?effective_only=true" -Headers $headers)
    if ($effectiveBefore.id -contains $proposal.id) {
        throw "A proposed decision appeared in the effective decision list."
    }

    Write-Host "3/6 Activating the proposal..."
    $activationBody = @{ status = "active"; note = "Cloud smoke activation" } | ConvertTo-Json
    $activated = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/decisions/$($proposal.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $activationBody

    Write-Host "4/6 Creating a replacement decision..."
    $replacementBody = @{
        subject = "[SMOKE] Replacement decision $timestamp"
        choice = "Replacement choice"
        rationale = "Cloud supersession verification only."
        supersedes_decision_id = $proposal.id
    } | ConvertTo-Json
    $replacement = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/decisions" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $replacementBody

    Write-Host "5/6 Verifying the old decision history..."
    $oldDecision = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/decisions/$($proposal.id)" -Headers $headers

    Write-Host "6/6 Verifying the effective replacement..."
    $effectiveAfter = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/decisions?effective_only=true" -Headers $headers)
    if (
        $activated.status -ne "active" -or
        $oldDecision.status -ne "superseded" -or
        $effectiveAfter.id -notcontains $replacement.id -or
        $effectiveAfter.id -contains $proposal.id
    ) {
        throw "The returned decision lifecycle does not match the expected state."
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Superseded decision: $($proposal.id)"
    Write-Host "Effective replacement: $($replacement.id)"
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
