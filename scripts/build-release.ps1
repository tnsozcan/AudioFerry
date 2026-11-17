$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $Root 'release'
$BuildDir = Join-Path $Root 'build-release'
$DistDir = Join-Path $Root 'dist-release'
$StageDir = Join-Path $ReleaseDir 'AudioFerry-v1.0.0-beta.1-win-x64'
$ZipPath = Join-Path $ReleaseDir 'AudioFerry-v1.0.0-beta.1-win-x64.zip'
Set-Location $Root

python scripts\generate-third-party-inventory.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'verify.ps1')
if (!(Test-Path -LiteralPath $ReleaseDir)) { New-Item -ItemType Directory -Path $ReleaseDir | Out-Null }
if (Test-Path -LiteralPath $StageDir) { Remove-Item -LiteralPath $StageDir -Recurse -Force }
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
if (Test-Path -LiteralPath (Join-Path $ReleaseDir 'SHA256SUMS.txt')) {
    Remove-Item -LiteralPath (Join-Path $ReleaseDir 'SHA256SUMS.txt') -Force
}
if (Test-Path -LiteralPath $BuildDir) { Remove-Item -LiteralPath $BuildDir -Recurse -Force }
if (Test-Path -LiteralPath $DistDir) { Remove-Item -LiteralPath $DistDir -Recurse -Force }
python -m PyInstaller --clean --noconfirm --workpath $BuildDir --distpath $DistDir AudioFerry.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

New-Item -ItemType Directory -Path $StageDir | Out-Null
Copy-Item -LiteralPath (Join-Path $DistDir 'AudioFerry.exe') -Destination $StageDir
Copy-Item -LiteralPath (Join-Path $Root 'LICENSE') -Destination $StageDir
Copy-Item -LiteralPath (Join-Path $Root 'THIRD_PARTY_NOTICES.md') -Destination $StageDir
Copy-Item -LiteralPath (Join-Path $Root 'THIRD_PARTY_INVENTORY.md') -Destination $StageDir
Copy-Item -LiteralPath (Join-Path $Root 'TRADEMARKS.md') -Destination $StageDir
Copy-Item -LiteralPath (Join-Path $Root 'RELEASE_NOTES_v1.0.0-beta.1.md') -Destination $StageDir
Copy-Item -LiteralPath (Join-Path $Root 'third_party_licenses') -Destination $StageDir -Recurse

if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -LiteralPath $StageDir -DestinationPath $ZipPath -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$Hash  AudioFerry-v1.0.0-beta.1-win-x64.zip" | Set-Content -LiteralPath (Join-Path $ReleaseDir 'SHA256SUMS.txt') -Encoding ascii
Write-Output "Release: $ZipPath"
