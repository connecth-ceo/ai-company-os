param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS Project hierarchy cloud smoke test"
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
    Write-Host "1/4 Creating a project..."
    $projectBody = @{
        title = "[SMOKE] Project hierarchy $timestamp"
        description = "Cloud verification record. No AI task is executed."
        status = "active"
    } | ConvertTo-Json
    $project = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/projects" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $projectBody

    Write-Host "2/4 Creating a parent task..."
    $parentBody = @{
        title = "[SMOKE] Parent task"
        request = "Verify the project and task relationship only. Do not execute."
        project_id = $project.id
    } | ConvertTo-Json
    $parent = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/tasks" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $parentBody

    Write-Host "3/4 Creating a child task..."
    $childBody = @{
        title = "[SMOKE] Child task"
        request = "Verify the parent and child relationship only. Do not execute."
        project_id = $project.id
        parent_task_id = $parent.id
    } | ConvertTo-Json
    $child = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/tasks" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $childBody

    Write-Host "4/4 Reading the project back..."
    $verified = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/projects/$($project.id)" -Headers $headers

    if ($verified.id -ne $project.id -or $child.project_id -ne $project.id -or $child.parent_task_id -ne $parent.id) {
        throw "The returned hierarchy does not match the created records."
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Project: $($project.id)"
    Write-Host "Parent task: $($parent.id)"
    Write-Host "Child task: $($child.id)"
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
