$ErrorActionPreference = "Stop"

$bytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($bytes)
    $newKey = [Convert]::ToBase64String($bytes)
    Set-Clipboard -Value $newKey
    Write-Host "NEW APP_API_KEY COPIED TO CLIPBOARD" -ForegroundColor Green
    Write-Host "Return to Render and paste it only into the APP_API_KEY value field."
    Write-Host "The key was not displayed or saved to a file."
}
finally {
    $rng.Dispose()
    [Array]::Clear($bytes, 0, $bytes.Length)
    $newKey = $null
}
