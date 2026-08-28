param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS delegated role execution - ONE paid OpenAI smoke test"
Write-Host "The API key is read from the clipboard, used only in memory, and not saved."
Write-Host "This creates one parent, one delegation, and one short Legal Review Agent run."
Write-Host "Copy APP_API_KEY from Render. Do NOT paste it into this window."
Write-Host "Press Enter once; the script will read the clipboard automatically."
[void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
$apiKey = Get-Clipboard -Raw
$apiKey = $apiKey -replace '[\x00-\x20\x7F]', ''

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
    Write-Host "1/7 Creating a parent task..."
    $parentBody = @{
        title = "[PAID SMOKE] Delegated execution parent $timestamp"
        request = "Verify one mediated delegated role execution."
    } | ConvertTo-Json
    $parent = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/tasks" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $parentBody

    Write-Host "2/7 Creating a Legal Review delegation..."
    $delegationBody = @{
        title = "[PAID SMOKE] Short legal review"
        request = "다음 문구의 일반적인 법률 위험 두 가지를 200자 이내의 예비 검토 초안으로 작성해줘: '고객 데이터는 서비스 개선에 자유롭게 활용할 수 있습니다.' 외부 행동은 하지 마."
        delegated_role = "legal_review"
        reason = "One approved production role-execution verification"
        priority = 3
        token_budget = 5000
        timeout_seconds = 120
        cost_budget_usd = 0.1
    } | ConvertTo-Json
    $delegation = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/tasks/$($parent.id)/delegations" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $delegationBody

    if (-not $delegation.approval_id) {
        throw "The Legal Review delegation did not create a required CEO approval."
    }
    Write-Host "3/7 Verifying the CEO approval gate..."
    $blocked = $false
    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/delegations/$($delegation.id)/run" -Headers $headers
    }
    catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 409) { $blocked = $true } else { throw }
    }
    if (-not $blocked) { throw "Delegation was not blocked before CEO approval." }

    Write-Host "4/7 CEO approval is required before this paid call."
    $confirmation = Read-Host "Type APPROVE to approve exactly one delegated OpenAI run"
    if ($confirmation -cne "APPROVE") { throw "CEO approval was not entered." }
    $decisionBody = @{
        approved = $true
        decided_by = "CEO"
        note = "One explicitly approved paid smoke test"
    } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/approvals/$($delegation.approval_id)/decide" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $decisionBody | Out-Null

    Write-Host "5/7 Dispatching exactly one delegated role run..."
    $dispatch = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/delegations/$($delegation.id)/run" -Headers $headers

    Write-Host "6/7 Waiting for the worker..."
    $detail = $null
    for ($attempt = 0; $attempt -lt 36; $attempt++) {
        Start-Sleep -Seconds 5
        $detail = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/delegations/$($delegation.id)" -Headers $headers
        Write-Host "  status=$($detail.status)"
        if ($detail.status -in @("completed", "failed")) { break }
    }
    if ($null -eq $detail -or $detail.status -ne "completed") {
        throw "Delegated execution did not complete: status=$($detail.status), error=$($detail.error)"
    }

    Write-Host "7/7 Verifying the TaskRun ledger..."
    $child = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/tasks/$($delegation.child_task_id)" -Headers $headers
    if ($child.status -ne "completed" -or $child.runs.Count -ne 1) {
        throw "The child Task/TaskRun completion record is invalid."
    }
    if ($child.runs[0].agent -ne "Legal Risk Review Agent") {
        throw "The stored TaskRun agent does not match the delegated role."
    }
    if ($null -ne $child.runs[0].workflow_run) {
        throw "A delegated single-role execution unexpectedly created a full WorkflowRun."
    }
    if ($detail.runtime_name -ne "openai_agents" -or $detail.total_tokens -le 0) {
        throw "The OpenAI runtime usage ledger was not recorded."
    }

    Write-Host ""
    Write-Host "PAID SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Parent task: $($parent.id)"
    Write-Host "Delegation: $($delegation.id)"
    Write-Host "Child task: $($child.id)"
    Write-Host "Runtime: $($detail.runtime_name)"
    Write-Host "Model: $($detail.model)"
    Write-Host "Tokens: input=$($detail.input_tokens), output=$($detail.output_tokens), total=$($detail.total_tokens)"
    Write-Host "Duration ms: $($detail.duration_ms)"
    Write-Host "Result: stored in the child Task record (content is not printed)."
}
catch {
    Write-Host ""
    Write-Host "PAID SMOKE TEST FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    Set-Clipboard -Value " "
    $apiKey = $null
    $headers = $null
}
