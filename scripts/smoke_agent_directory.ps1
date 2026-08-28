param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS read-only AI Employee Registry smoke test"
Write-Host "No OpenAI, Telegram, database write, or external action will be started."
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
$expected = @("chief_of_staff", "legal_review", "marketing", "research", "reviewer", "strategy")

try {
    Write-Host "1/3 Checking the current service schema..."
    $ready = Invoke-RestMethod -Method Get -Uri "$BaseUrl/ready"
    if ($ready.status -ne "ready" -or $ready.components.schema -ne "f2a4b6c8d0e2") {
        throw "The service is not ready on schema f2a4b6c8d0e2."
    }

    Write-Host "2/3 Reading the six employee profiles..."
    $agents = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/agents" -Headers $headers)
    $keys = @($agents | ForEach-Object { $_.key } | Sort-Object)
    if ($agents.Count -ne 6 -or (Compare-Object $expected $keys)) {
        throw "The deployed registry does not match the six expected roles."
    }

    Write-Host "3/3 Checking that sensitive definition fields are absent..."
    $json = $agents | ConvertTo-Json -Depth 8
    if ($json -match 'system_prompt|output_schema|OPENAI_API_KEY|APP_API_KEY') {
        throw "A private definition field appeared in the public directory response."
    }

    Write-Host "AI EMPLOYEE REGISTRY SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host "Agents: $($keys -join ', ')"
    Write-Host "No external action was executed."
}
catch {
    Write-Host "AI EMPLOYEE REGISTRY SMOKE TEST FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    $apiKey = $null
    $headers = $null
    try { Set-Clipboard -Value "" } catch { }
}
