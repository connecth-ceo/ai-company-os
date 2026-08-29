param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"

Write-Host "AI Company OS portfolio lifecycle cloud smoke test"
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
    Write-Host "1/6 Creating a planned goal..."
    $goalBody = @{
        title = "[SMOKE] Portfolio lifecycle $timestamp"
        description = "Cloud lifecycle verification. No AI task is executed."
        success_metric = "Lifecycle transitions verified"
        status = "planned"
    } | ConvertTo-Json
    $goal = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/goals" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $goalBody

    Write-Host "2/6 Starting the goal..."
    $goalActive = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/goals/$($goal.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body '{"status":"active","note":"Cloud smoke test"}'

    Write-Host "3/6 Creating a linked project..."
    $projectBody = @{
        title = "[SMOKE] Lifecycle project $timestamp"
        description = "Empty project used only for lifecycle verification."
        goal_id = $goal.id
        status = "active"
    } | ConvertTo-Json
    $project = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/projects" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $projectBody

    Write-Host "4/6 Completing the empty project..."
    $projectCompleted = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/projects/$($project.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body '{"status":"completed","note":"Cloud smoke test"}'

    Write-Host "5/6 Marking the goal achieved..."
    $goalAchieved = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/goals/$($goal.id)/transition" -Headers $headers -ContentType "application/json; charset=utf-8" -Body '{"status":"achieved","note":"Cloud smoke test"}'

    Write-Host "6/6 Verifying stored states..."
    $storedGoal = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/goals/$($goal.id)" -Headers $headers
    $storedProject = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/projects/$($project.id)" -Headers $headers
    if ($goalActive.status -ne "active" -or $goalAchieved.status -ne "achieved" -or $storedGoal.status -ne "achieved" -or $projectCompleted.status -ne "completed" -or $storedProject.status -ne "completed") {
        throw "The returned lifecycle states do not match the expected values."
    }

    Write-Host ""
    Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Goal: $($goal.id) (achieved)"
    Write-Host "Project: $($project.id) (completed)"
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
