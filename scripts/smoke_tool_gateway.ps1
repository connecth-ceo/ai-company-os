param(
    [string]$BaseUrl = "https://ai-company-os-uydy.onrender.com"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "AI Company OS Tool Gateway read-only cloud check"
Write-Host "This does not start an OpenAI task, send Telegram, or create test data."
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
    Write-Host "1/2 Checking service readiness..."
    $ready = Invoke-RestMethod -Method Get -Uri "$BaseUrl/ready"
    if ($ready.status -ne "ready") {
        throw "The service is not ready."
    }

    Write-Host "2/2 Verifying the fail-closed public tool catalog..."
    $catalog = @(Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/tool-catalog" -Headers $headers)
    if (
        $catalog.Count -ne 1 -or
        $catalog[0].key -ne "web_search" -or
        $catalog[0].risk -ne "read_only" -or
        $catalog[0].side_effects -ne $false -or
        $catalog[0].required_permissions -notcontains "web.search"
    ) {
        throw "The deployed tool catalog is not the expected read-only allowlist."
    }

    Write-Host "TOOL GATEWAY CHECK PASSED" -ForegroundColor Green
    Write-Host "Registered tool: $($catalog[0].key)"
    Write-Host "Risk: $($catalog[0].risk)"
    Write-Host "No OpenAI task was executed."
}
catch {
    Write-Host "TOOL GATEWAY CHECK FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
finally {
    $apiKey = $null
    $headers = $null
    try { Set-Clipboard -Value "" } catch { }
}
