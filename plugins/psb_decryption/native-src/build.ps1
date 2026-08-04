$ErrorActionPreference = "Stop"
$rustRoot = $PSScriptRoot
$packageDir = Split-Path -Parent $rustRoot
$manifest = Join-Path $rustRoot "Cargo.toml"
$env:CARGO_TARGET_DIR = Join-Path $rustRoot "target"
if (-not (Test-Path $packageDir)) { throw "Python package not found: $packageDir" }
cargo build --manifest-path $manifest --workspace --release --locked
$source = Join-Path $env:CARGO_TARGET_DIR "release\_freemote_native.dll"
if (-not (Test-Path $source)) { throw "Native library was not produced: $source" }
$target = Join-Path $packageDir "_freemote_native.pyd"
Copy-Item $source $target -Force
$projectRoot = Split-Path -Parent (Split-Path -Parent $packageDir)
Push-Location $projectRoot
try {
    python -c "from plugins.psb_decryption import _native; assert _native.available('psp_lzss_unpack'), _native.load_error()"
}
finally {
    Pop-Location
}
Write-Output "Built $target"