param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS Delegation Guardrails cloud smoke test"
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
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

try {
    Write-Host "1/4 Creating a parent task..."
    $parentBody = @{
        title = "[SMOKE] Delegation parent $timestamp"
        request = "Verify guarded delegation only. Do not execute OpenAI."
    } | ConvertTo-Json
    $parent = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/tasks" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $parentBody

    Write-Host "2/4 Creating a guarded child delegation..."
    $delegationBody = @{
        title = "[SMOKE] Delegated research child"
        request = "Verify the delegation record only. Do not execute OpenAI."
        delegated_role = "research"
        reason = "Cloud deployment smoke verification"
        priority = 3
        token_budget = 1000
        timeout_seconds = 60
        cost_budget_usd = 0.1
    } | ConvertTo-Json
    $delegation = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/tasks/$($parent.id)/delegations" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $delegationBody

    Write-Host "3/4 Reading the child task..."
    $child = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/tasks/$($delegation.child_task_id)" -Headers $headers

    Write-Host "4/4 Reading the delegation record..."
    $records = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/tasks/$($parent.id)/delegations" -Headers $headers

    if ($delegation.parent_task_id -ne $parent.id -or $child.parent_task_id -ne $parent.id) {
        throw "The returned parent-child relationship does not match."
    }
    if ($child.status -ne "queued" -or $child.source -ne "delegation") {
        throw "The delegated child did not remain safely queued."
    }
    if ($delegation.delegated_role -ne "research" -or $delegation.depth -ne 1) {
        throw "The delegation role or depth is incorrect."
    }
    if (-not ($records.id -contains $delegation.id)) {
        throw "The delegation record was not returned by the list API."
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Parent task: $($parent.id)"
    Write-Host "Delegation: $($delegation.id)"
    Write-Host "Child task: $($child.id)"
    Write-Host "Child status: $($child.status)"
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
