$ErrorActionPreference = "Stop"

$Version = $env:STOCKFISH_VERSION
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = "sf_18"
}

$Url = $env:STOCKFISH_URL
if ([string]::IsNullOrWhiteSpace($Url)) {
    $Url = "https://github.com/official-stockfish/Stockfish/releases/download/$Version/stockfish-windows-x86-64-avx2.zip"
}

$RootDir = Split-Path -Parent $PSScriptRoot
$EnginesDir = Join-Path $RootDir "engines"
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("stockfish-" + [System.Guid]::NewGuid().ToString())
$ZipPath = Join-Path $TempDir "stockfish.zip"

New-Item -ItemType Directory -Path $EnginesDir -Force | Out-Null
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

try {
    Write-Host "Downloading Stockfish 18 from $Url"
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $ZipPath
    Expand-Archive -Path $ZipPath -DestinationPath $TempDir -Force

    $StockfishExe = Get-ChildItem -Path $TempDir -Recurse -Filter "*.exe" |
        Where-Object { $_.Name -like "stockfish*" } |
        Select-Object -First 1

    if (-not $StockfishExe) {
        throw "Could not find a Stockfish executable in the downloaded archive."
    }

    $Destination = Join-Path $EnginesDir "stockfish.exe"
    Copy-Item -LiteralPath $StockfishExe.FullName -Destination $Destination -Force
    Write-Host "Installed $Destination"
}
finally {
    if (Test-Path $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force
    }
}
