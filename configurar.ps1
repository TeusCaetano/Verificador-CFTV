$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Add-CameraKey {
    $content = [IO.File]::ReadAllText((Join-Path $PSScriptRoot '.env'))
    if ($content -notmatch '(?m)^CAMERA_KEY=') {
        $keyBytes = New-Object byte[] 32
        $keyRng = [Security.Cryptography.RandomNumberGenerator]::Create()
        $keyRng.GetBytes($keyBytes); $keyRng.Dispose()
        $keyValue = [Convert]::ToBase64String($keyBytes).Replace('+','-').Replace('/','_')
        [IO.File]::AppendAllText((Join-Path $PSScriptRoot '.env'), "`nCAMERA_KEY=$keyValue`n", (New-Object Text.UTF8Encoding($false)))
    }
}
if (Test-Path '.env') { Add-CameraKey; Write-Host 'Configuracao preservada e chave de cameras pronta.'; exit 0 }
$secret = Read-Host 'Defina a senha do administrador (minimo 12 caracteres)' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try { $adminPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ($adminPassword.Length -lt 12 -or $adminPassword -match "['`r`n]") { throw 'Use 12 ou mais caracteres e nao use aspas simples.' }
$bytes = New-Object byte[] 24
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$dbPassword = -join ($bytes | ForEach-Object { $_.ToString('x2') })
[IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), "DB_PASSWORD=$dbPassword`nADMIN_PASSWORD='$adminPassword'`n", (New-Object Text.UTF8Encoding($false)))
$adminPassword = $null
Write-Host 'Configurado. Execute: docker compose up -d --build'

Add-CameraKey
